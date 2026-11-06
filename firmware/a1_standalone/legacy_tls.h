// SPDX-License-Identifier: GPL-3.0-only
#pragma once

#include <ESP_SSLClient.h>
#include <WiFi.h>
#include <bssl/bearssl.h>
#include <esp_random.h>
#include <lwip/sockets.h>

class A1Handshake {
 public:
  bool begin(IPAddress device, const char *mac, const uint8_t *certificate, size_t certificateSize,
             const uint8_t *key, size_t keySize) {
    device_ = device;
    mac_ = mac;
    certificate_ = {const_cast<uint8_t *>(certificate), certificateSize};
    br_skey_decoder_init(&key_);
    br_skey_decoder_push(&key_, key, keySize);
    if (!br_skey_decoder_get_rsa(&key_)) {
      return false;
    }
    listener_.begin();
    return listener_ && xTaskCreate(run, "a1-tls", 12288, this, 1, nullptr) == pdPASS;
  }

 private:
  struct Socket {
    int fd;
    uint32_t expires;
  };
  WiFiServer listener_{443, 1};
  IPAddress device_;
  const char *mac_ = nullptr;
  br_x509_certificate certificate_{};
  br_skey_decoder_context key_{};
  br_ssl_server_context tls_{};
  uint8_t buffer_[BR_SSL_BUFSIZE_MONO]{};

  static int transfer(void *context, unsigned char *readBuffer, const unsigned char *writeBuffer,
                      size_t length) {
    const auto &socket = *static_cast<Socket *>(context);
    while (static_cast<int32_t>(socket.expires - millis()) > 0) {
      const int count = readBuffer ? recv(socket.fd, readBuffer, length, MSG_DONTWAIT)
                                   : send(socket.fd, writeBuffer, length, MSG_DONTWAIT);
      if (count > 0) {
        return count;
      }
      if (count == 0 || (errno != EWOULDBLOCK && errno != EAGAIN && errno != EINTR)) {
        break;
      }
      delay(1);
    }
    return -1;
  }

  static void run(void *context) {
    auto &server = *static_cast<A1Handshake *>(context);
    for (;;) {
      WiFiClient client = server.listener_.accept();
      if (client) {
        if (client.remoteIP() == server.device_) {
          server.serve(client);
        }
        client.stop();
      }
      delay(10);
    }
  }

  void serve(WiFiClient &client) {
    br_ssl_server_init_full_rsa(&tls_, &certificate_, 1, br_skey_decoder_get_rsa(&key_));
    br_ssl_engine_set_buffer(&tls_.eng, buffer_, sizeof(buffer_), 0);
    uint8_t entropy[32];
    esp_fill_random(entropy, sizeof(entropy));
    br_ssl_engine_inject_entropy(&tls_.eng, entropy, sizeof(entropy));
    br_ssl_server_reset(&tls_);
    Socket socket{client.fd(), millis() + 6500};
    br_sslio_context io;
    br_sslio_init(&io, &tls_.eng,
                  [](void *ctx, unsigned char *buf, size_t len) { return transfer(ctx, buf, nullptr, len); },
                  &socket,
                  [](void *ctx, const unsigned char *buf, size_t len) { return transfer(ctx, nullptr, buf, len); },
                  &socket);
    char request[512];
    size_t length = 0;
    while (length + 1 < sizeof(request)) {
      if (br_sslio_read(&io, request + length, 1) != 1) {
        Serial.printf("A1 TLS read error: %d\n", br_ssl_engine_last_error(&tls_.eng));
        return;
      }
      if (request[length++] == '\n') {
        break;
      }
    }
    if (!length || request[length - 1] != '\n') {
      return;
    }
    request[length] = '\0';
    unsigned lineLength = 0;
    bool headerComplete = false;
    for (size_t i = 0; i < 4096; ++i) {
      char byte;
      if (br_sslio_read(&io, &byte, 1) != 1) {
        return;
      }
      if (byte == '\n') {
        if (!lineLength) {
          headerComplete = true;
          break;
        }
        lineLength = 0;
      } else if (byte != '\r') {
        ++lineLength;
      }
    }
    if (!headerComplete) {
      return;
    }
    const char *path = strchr(request, ' ');
    char body[64] = "{}";
    if (path && strncmp(path + 1, "/device/active?", sizeof("/device/active?") - 1) == 0) {
      snprintf(body, sizeof(body), "{\"device_id\":\"%s\"}", mac_);
    } else if (path && strncmp(path + 1, "/aircleanerfirmware/checkUpdate",
                               sizeof("/aircleanerfirmware/checkUpdate") - 1) == 0) {
      snprintf(body, sizeof(body), "{\"ver\":\"v1.47\",\"enforce\":false}");
    }
    char reply[192];
    const int size = snprintf(reply, sizeof(reply),
                              "HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n"
                              "Content-Length: %u\r\nConnection: close\r\n\r\n%s",
                              static_cast<unsigned>(strlen(body)), body);
    if (br_sslio_write_all(&io, reply, size) == 0 && br_sslio_flush(&io) == 0) {
      Serial.println("A1 TLS handshake completed");
      br_sslio_close(&io);
    }
  }
};
