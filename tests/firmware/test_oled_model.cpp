// SPDX-License-Identifier: GPL-3.0-only
#include <assert.h>
#include <string.h>
#include "../../firmware/a1_oled/display_model.h"

int main() {
  a1oled::State state;
  auto lines = a1oled::screenLines(state);
  assert(strcmp(lines.power, "等待联网") == 0);
  state.setupMode = true;
  lines = a1oled::screenLines(state);
  assert(strcmp(lines.power, "待配网") == 0);
  state.setupMode = false;
  state.wifiConnected = true;
  state.hasReport = true;
  state.mode = 2;
  state.speed = 56;
  lines = a1oled::screenLines(state);
  assert(strcmp(lines.power, "等待连接") == 0);
  assert(strcmp(lines.speed, "--") == 0);
  state.deviceConnected = true;
  state.hasReport = false;
  lines = a1oled::screenLines(state);
  assert(strcmp(lines.power, "等待回报") == 0);
  assert(strcmp(lines.speed, "--") == 0);
  state.hasReport = true;
  lines = a1oled::screenLines(state);
  assert(strcmp(lines.power, "已开机") == 0);
  assert(strcmp(lines.speed, "56") == 0);
  state.pending = true;
  state.mode = 0;
  lines = a1oled::screenLines(state);
  assert(strcmp(lines.power, "已关机") == 0);
  assert(strcmp(lines.connection, "A1 等待确认") == 0);
  state.speed = -1;
  lines = a1oled::screenLines(state);
  assert(strcmp(lines.speed, "--") == 0);
  state.wifiConnected = false;
  lines = a1oled::screenLines(state);
  assert(strcmp(lines.power, "等待联网") == 0);
  assert(strcmp(lines.speed, "--") == 0);
}
