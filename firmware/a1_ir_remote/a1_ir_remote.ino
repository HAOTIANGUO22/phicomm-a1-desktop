#include <Arduino.h>
#include <HTTPClient.h>
#include <IRremote.hpp>
#include <WiFi.h>

#if __has_include("config.h")
#include "config.h"
#else
constexpr char WIFI_SSID[] = "";
constexpr char WIFI_PASSWORD[] = "";
constexpr char BRIDGE_URL[] = "";
constexpr char BRIDGE_TOKEN[] = "";
#endif

constexpr uint8_t IR_PIN = 27;
bool wifiWasConnected = false;

void sendButton(const char *code) {
  if (!BRIDGE_URL[0] || WiFi.status() != WL_CONNECTED) {
    return;
  }

  WiFiClient client;
  HTTPClient http;
  http.setConnectTimeout(600);
  http.setTimeout(2500);
  if (!http.begin(client, BRIDGE_URL)) {
    Serial.println("Invalid bridge URL");
    return;
  }

  http.addHeader("Content-Type", "text/plain");
  http.addHeader("Authorization", String("Bearer ") + BRIDGE_TOKEN);
  const int status = http.POST(String(code));
  Serial.printf("Bridge HTTP %d\n", status);
  http.end();
}

void setup() {
  Serial.begin(115200);
  IrReceiver.begin(IR_PIN, DISABLE_LED_FEEDBACK);
  Serial.printf("IR receiver ready: GPIO %u\n", IR_PIN);

  if (WIFI_SSID[0] && BRIDGE_URL[0] && BRIDGE_TOKEN[0]) {
    WiFi.persistent(false);
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.println("Connecting to Wi-Fi");
  } else {
    Serial.println("Serial learning mode. Add config.h to enable Wi-Fi.");
  }
}

void loop() {
  const bool connected = WiFi.status() == WL_CONNECTED;
  if (connected != wifiWasConnected) {
    wifiWasConnected = connected;
    Serial.println(connected ? "Wi-Fi connected" : "Wi-Fi disconnected");
    if (connected) {
      Serial.println(WiFi.localIP());
    }
  }

  if (IrReceiver.decode()) {
    const IRData data = IrReceiver.decodedIRData;
    IrReceiver.resume();

    constexpr uint8_t ignoredFlags = IRDATA_FLAGS_IS_REPEAT | IRDATA_FLAGS_IS_AUTO_REPEAT |
                                     IRDATA_FLAGS_PARITY_FAILED | IRDATA_FLAGS_WAS_OVERFLOW;
    if (data.protocol != UNKNOWN && !(data.flags & ignoredFlags)) {
      char code[64];
      snprintf(code, sizeof(code), "%s:%04X:%04X", getProtocolString(data.protocol),
               static_cast<unsigned>(data.address), static_cast<unsigned>(data.command));
      Serial.printf("IR %s\n", code);
      sendButton(code);
    } else if (data.protocol == UNKNOWN) {
      Serial.println("IR signal received, protocol unknown");
    }
  }

  delay(1);
}
