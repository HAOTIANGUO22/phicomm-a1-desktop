# Third-party sources

## EasyLink V2 sender

- File: `tools/a1_easylink.py`.
- Upstream: [phicomm-io/iotcloud-community-firmware](https://github.com/phicomm-io/iotcloud-community-firmware).
- Source: [tools/a1_easylink.py](https://github.com/phicomm-io/iotcloud-community-firmware/blob/main/tools/a1_easylink.py).
- License: GNU General Public License version 3. The full license is included in `LICENSE`.
- The upstream sender is retained with its implementation comments. Its help text and documentation references were updated to describe this project's Windows verification scope. The Windows saved-profile wrapper and subnet discovery utility are separate project code.

Copyright and other upstream notices remain applicable. This repository uses GPL-3.0 for the combined source distribution.

## Protocol references

- [BFG7274/phicomm-a1-local-purifier](https://github.com/BFG7274/phicomm-a1-local-purifier) documents the stock A1 control messages and modes. Its project is MIT licensed. The desktop interface, transport implementation and tests here were written separately; original device-specific envelope values are not distributed.
- [MXCHIP/mico-os](https://github.com/MXCHIP/mico-os), especially its configuration-server implementation, was consulted for the original device's HTTP network-configuration field names. The SDK and firmware are not included.

The references explain interoperability with stock firmware; no vendor firmware binaries are distributed.

## ESP32 build dependencies

The ESP32 sketches use the [Espressif Arduino core](https://github.com/espressif/arduino-esp32), [Arduino-IRremote](https://github.com/Arduino-IRremote/Arduino-IRremote), [ArduinoJson](https://github.com/bblanchon/ArduinoJson), and [ESP_SSLClient](https://github.com/mobizt/ESP_SSLClient). The standalone sketch uses ESP_SSLClient's BearSSL for the A1's legacy local handshake. Arduino CLI installs these dependencies separately. Their source and license notices remain with their respective projects.

The 3.0 OLED sketch additionally uses [U8g2](https://github.com/olikraus/u8g2) and its WenQuanYi Chinese font. Arduino CLI installs the library and its accompanying font notices separately. The display preview is generated offline with the same font and layout using simulated states.
