// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <U8g2lib.h>
#include <Wire.h>
#include "display_model.h"
#include "oled_settings.h"

#if OLED_ROTATE_180
#define A1_OLED_ROTATION U8G2_R2
#else
#define A1_OLED_ROTATION U8G2_R0
#endif

namespace a1oled {
#if OLED_USE_SH1106
using DisplayDriver = U8G2_SH1106_128X64_NONAME_F_HW_I2C;
#else
using DisplayDriver = U8G2_SSD1306_128X64_NONAME_F_HW_I2C;
#endif

static_assert(OLED_FORCE_ADDRESS == 0 || OLED_FORCE_ADDRESS == 0x3c ||
              OLED_FORCE_ADDRESS == 0x3d, "OLED address must be 0, 0x3C or 0x3D");
static_assert(OLED_SDA_PIN != OLED_SCL_PIN && OLED_SDA_PIN != 27 && OLED_SCL_PIN != 27,
              "OLED needs separate I2C pins; GPIO27 is used by the IR receiver");

class Display {
 public:
  void begin() {
    if (!OLED_ENABLED) return;
    Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN, OLED_I2C_CLOCK);
    Wire.setTimeOut(12);
    connect();
    probeAt_ = millis();
  }

  void update(const State &state, uint32_t now) {
    if (!OLED_ENABLED) return;
    if (!address_) {
      if (now - probeAt_ < 10000) return;
      probeAt_ = now;
      connect();
      if (!address_) return;
    }
    if (!responds(address_)) {
      address_ = 0;
      probeAt_ = now;
      Serial.println("OLED disconnected; network and IR control continue");
      return;
    }
    const Lines lines = screenLines(state);
    driver_.clearBuffer();
    driver_.setFont(u8g2_font_wqy12_t_gb2312a);
    drawCentered(12, lines.connection);
    driver_.drawHLine(0, 15, 128);
    drawCentered(42, lines.power, true);
    drawCentered(61, lines.speed);
    driver_.sendBuffer();
  }

  bool ready() const { return address_ != 0; }
  uint8_t address() const { return address_; }

 private:
  DisplayDriver driver_{A1_OLED_ROTATION, U8X8_PIN_NONE, OLED_SCL_PIN, OLED_SDA_PIN};
  uint8_t address_ = 0;
  uint32_t probeAt_ = 0;

  void drawCentered(uint8_t baseline, const char *text, bool large = false) {
    const uint16_t width = driver_.getUTF8Width(text) * (large ? 2 : 1);
    const uint8_t x = width < 128 ? (128 - width) / 2 : 0;
    if (large) driver_.drawUTF8X2(x, baseline, text);
    else driver_.drawUTF8(x, baseline, text);
  }

  bool responds(uint8_t address) {
    Wire.beginTransmission(address);
    return Wire.endTransmission() == 0;
  }

  void connect() {
    const uint8_t addresses[] = {0x3c, 0x3d};
    for (const uint8_t address : addresses) {
      if (OLED_FORCE_ADDRESS && address != OLED_FORCE_ADDRESS) continue;
      if (!responds(address)) continue;
      driver_.setI2CAddress(address << 1);
      driver_.setBusClock(OLED_I2C_CLOCK);
      driver_.begin();
      Wire.setTimeOut(12);
      driver_.setContrast(110);
      address_ = address;
      Serial.printf("OLED online: I2C 0x%02X, SDA=%u SCL=%u\n", address_, OLED_SDA_PIN, OLED_SCL_PIN);
      return;
    }
    Serial.println("OLED not found at 0x3C/0x3D; network and IR control continue");
  }
};
}  // namespace a1oled
