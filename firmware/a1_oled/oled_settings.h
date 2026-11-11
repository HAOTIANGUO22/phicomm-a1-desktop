// SPDX-License-Identifier: GPL-3.0-only
#pragma once

// Four-pin 0.96-inch 128x64 I2C module. Follow the labels on the actual PCB.
#define OLED_ENABLED 1
#define OLED_SDA_PIN 21
#define OLED_SCL_PIN 22
#define OLED_I2C_CLOCK 400000
#define OLED_FORCE_ADDRESS 0  // 0 scans 0x3C and 0x3D. Use a 7-bit address here.
#define OLED_ROTATE_180 0
#define OLED_USE_SH1106 0      // Default is SSD1306, inferred from the photos.
#define OLED_IDLE_TIMEOUT_MS 30000UL
