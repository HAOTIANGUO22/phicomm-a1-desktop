// SPDX-License-Identifier: GPL-3.0-only
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <IRremote.hpp>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <lwip/sockets.h>

#include "config.h"
#include "legacy_tls.h"
#include "protocol.h"
#include "report_state.h"
#include "web_page.h"
#include "oled_display.h"

constexpr int irPin = 27;
constexpr uint16_t webPort = 8080;
constexpr uint32_t wifiConnectTimeout = 25000;
const char *webHeaders[] = {"X-A1-Control"};
const char *keys[] = {"1", "0", "2", "3", "4", "up", "down"};
const int modes[] = {1, 0, 2, 4, 5};

IPAddress deviceIp, espIp, gateway, mask, upstream;
uint8_t deviceMac[6];
Preferences saved;
WebServer web(webPort);
WiFiServer listener(9000, 2);
WiFiClient device;
WiFiUDP dns, relay;
A1Handshake tls;
bool started = false, relayEnabled = false, headerReady = false;
bool pending = false, deviceWasConnected = false;
a1::ReportedState reported;
bool setupMode = false;
uint8_t header[a1::headerSize];
uint8_t receiveBuffer[1536];
size_t received = 0;
int manualSpeed = 56;
int expectedMode = -1, expectedSpeed = -1;
uint32_t pendingAt = 0, lastIrAt = 0;
uint32_t wifiStartedAt = 0, restartAt = 0;
String message, irMessage, irCodes[7], lastIr;
String wifiName, wifiKey, a1Mac;
int learnKey = -1;
a1oled::Display oled;
uint32_t screenUpdatedAt = 0;
uint32_t connectionCount = 0, reportCount = 0, lastReportAt = 0;

struct DnsRelay {
  IPAddress peer;
  uint16_t port;
  uint16_t id;
  uint32_t expires;
  bool active = false;
} forwarded;

bool validNetwork(const JsonDocument &config) {
  IPAddress esp, a1, router, subnet, dnsIp;
  const String ssid = config["ssid"] | "";
  const String mac = config["mac"] | "";
  if (ssid.isEmpty() || ssid.length() > 32 || mac.length() != 12 ||
      !esp.fromString(config["esp"] | "") || !a1.fromString(config["a1"] | "") ||
      !router.fromString(config["router"] | "") || !subnet.fromString(config["mask"] | "") ||
      !dnsIp.fromString(config["dns"] | "") || esp == a1 || esp == router || a1 == router ||
      dnsIp == esp || dnsIp == a1 || dnsIp == IPAddress(0, 0, 0, 0)) {
    return false;
  }
  uint32_t netmask = 0;
  uint32_t network = 0;
  for (int i = 0; i < 4; ++i) {
    netmask = (netmask << 8) | subnet[i];
    network = (network << 8) | router[i];
  }
  const uint32_t hostMask = ~netmask;
  if (!netmask || hostMask < 7 || (hostMask & (hostMask + 1))) {
    return false;
  }
  for (const auto &ip : {esp, a1, router}) {
    const uint32_t value = (uint32_t(ip[0]) << 24) | (uint32_t(ip[1]) << 16) |
                           (uint32_t(ip[2]) << 8) | ip[3];
    if (ip[0] == 0 || ip[0] == 127 || ip[0] >= 224 ||
        (value & netmask) != (network & netmask) ||
        (value & hostMask) == 0 || (value & hostMask) == hostMask) {
      return false;
    }
  }
  for (size_t i = 0; i < mac.length(); ++i) {
    if (!isxdigit(mac[i])) {
      return false;
    }
  }
  return mac != "000000000000" && !(strtoul(mac.substring(0, 2).c_str(), nullptr, 16) & 1);
}

bool readConfig() {
  JsonDocument config;
  const String localConfig = saved.getString("network", "");
  if (localConfig.isEmpty()) {
    config["ssid"] = WIFI_SSID;
    config["key"] = WIFI_PASSWORD;
    config["esp"] = ESP_IP;
    config["a1"] = A1_IP;
    config["mac"] = A1_MAC;
    config["router"] = GATEWAY;
    config["mask"] = NETMASK;
    config["dns"] = UPSTREAM_DNS;
  } else if (deserializeJson(config, localConfig)) {
    return false;
  }
  if (!validNetwork(config)) {
    return false;
  }
  wifiName = config["ssid"].as<String>();
  wifiKey = config["key"].as<String>();
  a1Mac = config["mac"].as<String>();
  a1Mac.toLowerCase();
  espIp.fromString(config["esp"].as<const char *>());
  deviceIp.fromString(config["a1"].as<const char *>());
  gateway.fromString(config["router"].as<const char *>());
  mask.fromString(config["mask"].as<const char *>());
  upstream.fromString(config["dns"].as<const char *>());
  for (size_t i = 0; i < 6; ++i) {
    const char pair[] = {a1Mac[i * 2], a1Mac[i * 2 + 1], 0};
    deviceMac[i] = strtoul(pair, nullptr, 16);
  }
  return true;
}

void pollDns() {
  uint8_t packet[512];
  const int response = relayEnabled ? relay.parsePacket() : 0;
  if (response) {
    const int count = relay.read(packet, sizeof(packet));
    if (forwarded.active && relay.remoteIP() == upstream && relay.remotePort() == 53 &&
        count >= 12 && response == count && word(packet[0], packet[1]) == forwarded.id) {
      dns.beginPacket(forwarded.peer, forwarded.port);
      dns.write(packet, count);
      dns.endPacket();
      forwarded.active = false;
    }
    relay.clear();
  }
  if (forwarded.active && static_cast<int32_t>(millis() - forwarded.expires) >= 0) {
    forwarded.active = false;
  }
  const int size = dns.parsePacket();
  if (size <= 0) {
    return;
  }
  const auto peer = dns.remoteIP();
  const auto port = dns.remotePort();
  const int count = dns.read(packet, sizeof(packet));
  dns.clear();
  if (peer != deviceIp || count != size) {
    return;
  }
  const uint8_t ip[] = {espIp[0], espIp[1], espIp[2], espIp[3]};
  const int answer = a1::answerDns(packet, size, sizeof(packet), ip);
  if (answer > 0) {
    dns.beginPacket(peer, port);
    dns.write(packet, answer);
    dns.endPacket();
  } else if (answer == 0 && relayEnabled && !forwarded.active && upstream != espIp) {
    relay.beginPacket(upstream, 53);
    relay.write(packet, size);
    if (relay.endPacket()) {
      forwarded = {peer, port, word(packet[0], packet[1]), millis() + 1800, true};
    }
  }
}

int reportValue(JsonVariantConst field) {
  if (field.is<int>()) {
    return field.as<int>();
  }
  const char *text = field.as<const char *>();
  if (!text || !isDigit(text[0]) || strlen(text) > 2) {
    return -1;
  }
  char *end;
  const long value = strtol(text, &end, 10);
  return *end ? -1 : static_cast<int>(value);
}

void onFrame() {
  const size_t bodySize = received - sizeof(a1::footer);
  if (bodySize <= a1::headerSize || receiveBuffer[a1::headerSize] != '{' ||
      memcmp(receiveBuffer + 17, deviceMac, sizeof(deviceMac)) != 0) {
    return;
  }
  JsonDocument doc;
  if (deserializeJson(doc, receiveBuffer + a1::headerSize, bodySize - a1::headerSize)) {
    return;
  }
  if (!headerReady || memcmp(header, receiveBuffer, sizeof(header)) != 0) {
    memcpy(header, receiveBuffer, sizeof(header));
    saved.putBytes("header", header, sizeof(header));
    headerReady = true;
  }
  if (strcmp(doc["datatype"] | "", "mode") != 0) {
    return;
  }
  const int reportMode = reportValue(doc["data"]["mode"]);
  const int reportSpeed = reportValue(doc["data"]["speed"]);
  const int previousMode = reported.mode(), previousSpeed = reported.speed();
  if (!reported.receive(reportMode, reportSpeed)) return;
  lastReportAt = millis();
  ++reportCount;
  if (reported.known() &&
      (previousMode != reported.mode() || previousSpeed != reported.speed())) {
    const auto snapshot = reported.snapshot(deviceMac);
    if (saved.putBytes("last-report", &snapshot, sizeof(snapshot)) != sizeof(snapshot)) {
      Serial.println("Last report could not be saved; keeping the in-memory state");
    }
  }
  if (reportMode == 2 && reportSpeed >= 30 && reportSpeed <= 85 && manualSpeed != reportSpeed) {
    manualSpeed = reportSpeed;
    saved.putInt("manual", manualSpeed);
  }
  if (reported.known() && (!pending || reported.confirms(expectedMode, expectedSpeed))) {
    pending = false;
    message = reported.cached() ? "已收到部分上报，保留上次状态" : "运行状态已同步";
  }
}

void pollDevice() {
  WiFiClient incoming = listener.accept();
  if (incoming) {
    if (incoming.remoteIP() == deviceIp) {
      device.stop();
      device = incoming;
      device.setNoDelay(true);
      device.setConnectionTimeout(500);
      // A1 can stay silent between state changes. TCP probes detect a powered-off
      // peer without sending unsupported commands or expiring a valid idle state.
      const int keepalive = 1, idleSeconds = 20, intervalSeconds = 5, probeCount = 3;
      const int keepEnabled = device.setSocketOption(SOL_SOCKET, SO_KEEPALIVE, &keepalive, sizeof(keepalive));
      const int keepIdle = device.setSocketOption(IPPROTO_TCP, TCP_KEEPIDLE, &idleSeconds, sizeof(idleSeconds));
      const int keepInterval = device.setSocketOption(IPPROTO_TCP, TCP_KEEPINTVL, &intervalSeconds, sizeof(intervalSeconds));
      const int keepCount = device.setSocketOption(IPPROTO_TCP, TCP_KEEPCNT, &probeCount, sizeof(probeCount));
      if (keepEnabled || keepIdle || keepInterval || keepCount) {
        Serial.println("A1 TCP keepalive setup failed; inspect connection detection during testing");
      }
      received = 0;
      reported.connectionLost();
      pending = false;
      ++connectionCount;
      message = reported.known() ? "A1 已重连，保留上次上报状态" : "A1 已连接，等待设备状态";
    } else {
      incoming.stop();
    }
  }
  for (int i = 0; i < 512 && device.available(); ++i) {
    const int next = device.read();
    if (next < 0) {
      break;
    }
    receiveBuffer[received++] = next;
    if (received >= sizeof(a1::footer) &&
        memcmp(receiveBuffer + received - sizeof(a1::footer), a1::footer, sizeof(a1::footer)) == 0) {
      onFrame();
      received = 0;
    } else if (received == sizeof(receiveBuffer)) {
      device.stop();
      received = 0;
      break;
    }
  }
  const bool connected = device.connected();
  if (!connected) {
    if (deviceWasConnected) {
      reported.connectionLost();
      pending = false;
      message = reported.known() ? "A1 已断开，上次状态已保留" : "A1 已断开，等待重连";
    }
  } else if (pending && millis() - pendingAt >= 10000) {
    pending = false;
    message = "指令已发送，尚未收到 A1 确认";
  }
  deviceWasConnected = connected;
}

bool control(int target, int requested = -1) {
  if (!device.connected() || !headerReady) {
    message = "请先连接 A1 并等待设备上报";
    return false;
  }
  if (pending) {
    message = "上一条指令正在等待 A1 确认";
    return false;
  }
  const int value = target == 4 ? 30 : target == 5 ? 85
      : (target == 1 || target == 2) && requested < 0 ? manualSpeed : requested;
  uint8_t wire[160];
  const size_t length = a1::controlFrame(wire, sizeof(wire), header, deviceMac, target, value);
  if (!length || device.write(wire, length) != length) {
    message = "发送失败，请等待 A1 重新连接";
    device.stop();
    return false;
  }
  expectedMode = target == 1 ? 2 : target;
  expectedSpeed = value;
  pending = !reported.known() || reported.cached() || reported.mode() != expectedMode ||
            (value >= 0 && reported.speed() != value);
  pendingAt = millis();
  message = pending ? "指令已发送，等待 A1 确认" : "设定与最近一次设备回报一致";
  return true;
}

bool deviceRequest(const JsonDocument *configuration, JsonDocument &response) {
  WiFiClient client;
  HTTPClient http;
  http.setConnectTimeout(2000);
  http.setTimeout(2200);
  http.useHTTP10(true);
  const String url = "http://" + deviceIp.toString() + ":8000/" +
                     (configuration ? "config-write" : "config-read");
  if (!http.begin(client, url)) {
    return false;
  }
  int status;
  if (configuration) {
    String payload;
    serializeJson(*configuration, payload);
    http.addHeader("Content-Type", "application/json");
    status = http.POST(payload);
  } else {
    status = http.GET();
  }
  const bool ok = status == 200 && (configuration || !deserializeJson(response, http.getStream()));
  http.end();
  return ok;
}

bool configureDevice(bool restore) {
  JsonDocument identity;
  if (!deviceRequest(nullptr, identity)) {
    message = "无法读取 A1。请核对 IP，确认它已连上 Wi-Fi";
    return false;
  }
  String name = identity["N"] | "";
  name.toUpperCase();
  String suffix(a1Mac.substring(6));
  suffix.toUpperCase();
  if (strcmp(identity["PO"] | "", "com.phicomm.basic") != 0 ||
      strcmp(identity["FW"] | "", "v1.47") != 0 || name.indexOf(suffix) < 0) {
    message = "设备型号、固件或 MAC 与配置不符";
    return false;
  }
  JsonDocument configuration, unused;
  configuration["DHCP"] = restore;
  configuration["DNS Server"] = (restore ? upstream : espIp).toString();
  if (!restore) {
    configuration["IP address"] = deviceIp.toString();
    configuration["Net Mask"] = mask.toString();
    configuration["Gateway"] = gateway.toString();
  }
  if (!deviceRequest(&configuration, unused)) {
    message = "A1 未确认接收网络设置，请核对后重试";
    return false;
  }
  device.stop();
  deviceWasConnected = false;
  pending = false;
  reported.connectionLost();
  message = restore ? "已提交恢复自动联网" : "已提交连接设置，等待 A1 重新联网";
  return true;
}

void pollIr() {
  if (!IrReceiver.decode()) {
    return;
  }
  const IRData data = IrReceiver.decodedIRData;
  IrReceiver.resume();
  constexpr uint8_t ignored = IRDATA_FLAGS_IS_REPEAT | IRDATA_FLAGS_IS_AUTO_REPEAT |
                              IRDATA_FLAGS_PARITY_FAILED | IRDATA_FLAGS_WAS_OVERFLOW;
  if (data.protocol == UNKNOWN || data.flags & ignored) {
    return;
  }
  char code[64];
  snprintf(code, sizeof(code), "%s:%04X:%04X", getProtocolString(data.protocol),
           static_cast<unsigned>(data.address), static_cast<unsigned>(data.command));
  const uint32_t now = millis();
  if (lastIr == code && now - lastIrAt < 250) {
    lastIrAt = now;
    return;
  }
  lastIr = code;
  lastIrAt = now;
  int matched = -1;
  for (int i = 0; i < 7; ++i) {
    if (irCodes[i] == code) {
      matched = i;
      break;
    }
  }
  if (learnKey >= 0) {
    if (matched >= 0 && matched != learnKey) {
      irMessage = "这枚按键已绑定，请短按当前要学习的键";
    } else if (saved.putString(keys[learnKey], code)) {
      irCodes[learnKey] = code;
      irMessage = "按键已保存";
      learnKey = -1;
    } else {
      irMessage = "无法保存按键";
    }
  } else if (matched >= 0 && matched < 5) {
    control(modes[matched]);
  } else if (matched >= 5 && reported.known() && reported.mode() > 0 && reported.speed() >= 30) {
    control(2, constrain(reported.speed() + (matched == 5 ? 5 : -5), 30, 85));
  }
}

bool authorize(bool write = false) {
  if (!web.authenticate("a1", WEB_PASSWORD)) {
    web.requestAuthentication();
    return false;
  }
  if (write && web.header("X-A1-Control") != "1") {
    web.send(403);
    return false;
  }
  return true;
}

void sendStatus(int status) {
  JsonDocument doc;
  doc["connected"] = device.connected();
  doc["ready"] = device.connected() && headerReady;
  doc["pending"] = pending;
  doc["mode"] = reported.known() ? reported.mode() : -1;
  doc["speed"] = reported.known() ? reported.speed() : -1;
  doc["hasReport"] = reported.known();
  doc["stateCached"] = reported.cached() || (reported.known() && !device.connected());
  doc["connectionCount"] = connectionCount;
  doc["reportCount"] = reportCount;
  doc["reportAgeSeconds"] = reportCount ? static_cast<int>((millis() - lastReportAt) / 1000) : -1;
  doc["uptimeMs"] = millis();
  doc["manualSpeed"] = manualSpeed;
  doc["message"] = message;
  doc["irMessage"] = irMessage;
  doc["learning"] = learnKey < 0 ? "" : keys[learnKey];
  doc["firmware"] = "3.1.1-dev";
  auto display = doc["oled"].to<JsonObject>();
  display["enabled"] = bool(OLED_ENABLED);
  display["detected"] = oled.ready();
  display["address"] = oled.address();
  auto bindings = doc["keys"].to<JsonObject>();
  for (int i = 0; i < 7; ++i) {
    bindings[keys[i]] = irCodes[i];
  }
  String response;
  serializeJson(doc, response);
  web.sendHeader("Cache-Control", "no-store");
  web.send(status, "application/json", response);
}

const char setupPage[] PROGMEM = R"A1SETUP(<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>A1 网页遥控 · 首次配置</title>
<style>
body{max-width:32rem;margin:2rem auto;padding:0 1rem;background:#eff5f1;color:#19382f;font:16px system-ui}
label{display:block;margin:1rem 0}input{display:block;box-sizing:border-box;width:100%;padding:.6rem;font:inherit}
button{background:#176345;color:white;border:0;padding:.7rem 1rem;font:inherit}p{line-height:1.5}
</style>
<h1>A1 网页遥控 · 首次配置</h1>
<p>固件已运行。等 A1 接入同一个路由器后，在这里填写网络参数。ESP32 使用 2.4 GHz Wi-Fi。</p>
<form id="form">
<label>Wi-Fi 名称<input name="ssid" required maxlength="32"></label>
<label>Wi-Fi 密码<input name="key" type="password" maxlength="64"></label>
<label>ESP32 的固定 IPv4<input name="esp" required placeholder="在路由器预留地址" inputmode="decimal"></label>
<label>A1 当前 IPv4<input name="a1" required inputmode="decimal"></label>
<label>A1 完整 MAC<input name="mac" required maxlength="17"></label>
<label>路由器 IPv4<input name="router" required inputmode="decimal"></label>
<label>子网掩码<input name="mask" required value="255.255.255.0" inputmode="decimal"></label>
<label>上游 DNS（可留空）<input name="dns" inputmode="decimal"></label>
<button>保存并重启</button>
</form>
<p id="result" role="status"></p>
<script>
document.querySelector('form').addEventListener('submit',async event=>{
  event.preventDefault();
  const button=event.target.querySelector('button'), result=document.querySelector('#result');
  button.disabled=true;
  try {
    const response=await fetch('/api/setup',{method:'POST',headers:{'X-A1-Control':'1'},
      body:new URLSearchParams(new FormData(event.target))});
    result.textContent=await response.text();
    if(!response.ok)button.disabled=false;
  }catch{result.textContent='连接中断，请重新打开网页检查。';button.disabled=false;}
});
</script></html>)A1SETUP";

void startWeb() {
  web.collectHeaders(webHeaders, 1);
  web.on("/", HTTP_GET, [] {
    if (authorize()) {
      web.sendHeader("Cache-Control", "no-store");
      web.send_P(200, "text/html; charset=utf-8", setupMode ? setupPage : CONTROL_PAGE);
    }
  });
  web.on("/setup", HTTP_GET, [] {
    if (authorize()) {
      web.sendHeader("Cache-Control", "no-store");
      web.send_P(200, "text/html; charset=utf-8", setupPage);
    }
  });
  web.on("/api/setup", HTTP_POST, [] {
    if (!authorize(true)) return;
    JsonDocument config;
    const char *fields[] = {"ssid", "key", "esp", "a1", "mac", "router", "mask", "dns"};
    for (const char *field : fields) {
      String value = web.arg(field);
      if (strcmp(field, "key") != 0 && strcmp(field, "ssid") != 0) value.trim();
      if (strcmp(field, "mac") == 0) {
        value.replace(":", "");
        value.replace("-", "");
      }
      config[field] = value;
    }
    if ((config["dns"] | "")[0] == '\0') config["dns"] = config["router"].as<String>();
    const size_t keyLength = config["key"].as<String>().length();
    if (!validNetwork(config) || (keyLength != 0 && (keyLength < 8 || keyLength > 64))) {
      web.send(400, "text/plain; charset=utf-8", "请检查 IP、子网掩码、MAC 和 Wi-Fi 信息。");
      return;
    }
    String settings;
    serializeJson(config, settings);
    if (!saved.putString("network", settings)) {
      web.send(500, "text/plain; charset=utf-8", "保存失败，请重试。");
      return;
    }
    String nextUrl = "已保存。请让手机连回家庭 Wi-Fi，再打开 http://";
    nextUrl += config["esp"].as<String>();
    nextUrl += ":8080/";
    web.send(200, "text/plain; charset=utf-8", nextUrl);
    restartAt = millis() + 1200;
  });
  web.on("/api/state", HTTP_GET, [] { if (authorize()) sendStatus(200); });
  web.on("/api/control", HTTP_POST, [] {
    if (!authorize(true)) return;
    const String action = web.arg("action");
    int target = action == "on" ? 1 : action == "off" ? 0 : action == "daily" ? 2
        : action == "sleep" ? 4 : action == "strong" ? 5 : -1;
    int value = -1;
    if (action == "speed") {
      const String raw = web.arg("speed");
      if (raw.length() == 2 && isDigit(raw[0]) && isDigit(raw[1])) {
        value = raw.toInt();
        if (value >= 30 && value <= 85) target = 2;
      }
    }
    if (target < 0) {
      web.send(400);
      return;
    }
    sendStatus(control(target, value) ? 202 : 409);
  });
  web.on("/api/device", HTTP_POST, [] {
    if (!authorize(true)) return;
    if (setupMode) {
      web.send(409, "text/plain; charset=utf-8", "请先完成网络配置。");
      return;
    }
    const String action = web.arg("action");
    if (action != "connect" && action != "restore") {
      web.send(400);
      return;
    }
    sendStatus(configureDevice(action == "restore") ? 202 : 409);
  });
  web.on("/api/learn", HTTP_POST, [] {
    if (!authorize(true)) return;
    const String button = web.arg("key");
    learnKey = -1;
    for (int i = 0; i < 7; ++i) {
      if (button == keys[i]) learnKey = i;
    }
    irMessage = learnKey < 0 ? "已退出学习" : "请对准红外接收头短按对应键";
    sendStatus(200);
  });
  web.begin();
}

void startSetup() {
  setupMode = true;
  char name[16];
  snprintf(name, sizeof(name), "A1-Setup-%04X", static_cast<unsigned>(ESP.getEfuseMac() & 0xffff));
  WiFi.mode(WIFI_AP);
  if (!WiFi.softAP(name, WEB_PASSWORD)) {
    Serial.println("Setup Wi-Fi could not start");
    return;
  }
  startWeb();
  Serial.printf("Setup Wi-Fi: %s. Open http://%s:%u/\n", name,
                WiFi.softAPIP().toString().c_str(), webPort);
}

void setup() {
  Serial.begin(115200);
  oled.begin();
  IrReceiver.begin(irPin, DISABLE_LED_FEEDBACK);
  if (strlen(WEB_PASSWORD) < 10 || !saved.begin("a1-local")) {
    Serial.println("Invalid setup password or NVS unavailable");
    return;
  }
  WiFi.persistent(false);
  if (!readConfig()) {
    startSetup();
    return;
  }
  manualSpeed = constrain(saved.getInt("manual", 56), 30, 85);
  for (int i = 0; i < 7; ++i) {
    irCodes[i] = saved.getString(keys[i]);
  }
  headerReady = saved.getBytesLength("header") == sizeof(header) &&
                saved.getBytes("header", header, sizeof(header)) == sizeof(header) &&
                memcmp(header + 17, deviceMac, sizeof(deviceMac)) == 0;
  a1::ReportSnapshot snapshot;
  if (saved.getBytesLength("last-report") == sizeof(snapshot) &&
      saved.getBytes("last-report", &snapshot, sizeof(snapshot)) == sizeof(snapshot)) {
    reported.restore(snapshot, deviceMac);
  }
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  if (!WiFi.config(espIp, gateway, mask, upstream)) {
    startSetup();
    return;
  }
  WiFi.begin(wifiName.c_str(), wifiKey.c_str());
  wifiStartedAt = millis();
  Serial.println("Connecting to configured Wi-Fi");
}

void loop() {
  if (restartAt && static_cast<int32_t>(millis() - restartAt) >= 0) {
    ESP.restart();
  }
  if (setupMode) {
    web.handleClient();
  } else if (WiFi.status() == WL_CONNECTED) {
    if (!started) {
      started = true;
      startWeb();
      listener.begin();
      const bool tcpReady = listener;
      const bool dnsReady = dns.begin(53);
      relayEnabled = relay.begin(53053);
      const bool tlsReady = tls.begin(deviceIp, a1Mac.c_str(), TLS_CERT, sizeof(TLS_CERT), TLS_KEY, sizeof(TLS_KEY));
      message = dnsReady && tcpReady && tlsReady
          ? (reported.known() ? "等待 A1 连接，上次状态已保留" : "等待 A1 连接")
          : "A1 网络服务启动失败，请检查串口";
      Serial.printf("Open http://%s:%u/ (DNS=%d TCP=%d TLS=%d)\n", WiFi.localIP().toString().c_str(),
                    webPort, dnsReady, tcpReady, tlsReady);
    }
    pollDns();
    pollDevice();
    web.handleClient();
  } else if (started) {
    device.stop();
    deviceWasConnected = pending = false;
    reported.connectionLost();
    message = reported.known() ? "Wi-Fi 已断开，上次状态已保留" : "Wi-Fi 已断开，等待重新连接";
  } else if (wifiStartedAt && millis() - wifiStartedAt >= wifiConnectTimeout) {
    startSetup();
  }
  if (started) {
    pollIr();
  }
  const uint32_t now = millis();
  if (now - screenUpdatedAt >= 1000) {
    screenUpdatedAt = now;
    const bool wifiConnected = WiFi.status() == WL_CONNECTED;
    a1oled::State screen;
    screen.setupMode = setupMode;
    screen.wifiConnected = wifiConnected;
    screen.deviceConnected = wifiConnected && device.connected();
    screen.hasReport = reported.known();
    screen.cached = reported.cached();
    screen.pending = pending;
    screen.mode = reported.mode();
    screen.speed = reported.speed();
    oled.update(screen, now);
  }
  delay(1);
}
