// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <stdio.h>

namespace a1oled {
struct State {
  bool setupMode = false;
  bool wifiConnected = false;
  bool deviceConnected = false;
  bool hasReport = false;
  bool pending = false;
  int mode = -1;
  int speed = -1;
};

struct Lines {
  char connection[48] = {};
  char power[48] = {};
  char speed[48] = {};
};

inline Lines screenLines(const State &state) {
  Lines lines;
  snprintf(lines.speed, sizeof(lines.speed), "--");
  if (state.setupMode) {
    snprintf(lines.connection, sizeof(lines.connection), "配置网络");
    snprintf(lines.power, sizeof(lines.power), "待配网");
    return lines;
  }
  if (!state.wifiConnected) {
    snprintf(lines.connection, sizeof(lines.connection), "Wi-Fi 连接中");
    snprintf(lines.power, sizeof(lines.power), "等待联网");
    return lines;
  }
  if (!state.deviceConnected) {
    snprintf(lines.connection, sizeof(lines.connection), "A1 未连接");
    snprintf(lines.power, sizeof(lines.power), "等待连接");
    return lines;
  }
  snprintf(lines.connection, sizeof(lines.connection), "%s",
           state.pending ? "A1 等待确认" : "A1 已连接");
  if (!state.hasReport) {
    snprintf(lines.power, sizeof(lines.power), "等待回报");
    return lines;
  }
  snprintf(lines.power, sizeof(lines.power), "%s", state.mode == 0 ? "已关机" : "已开机");
  if (state.speed >= 30 && state.speed <= 85) {
    snprintf(lines.speed, sizeof(lines.speed), "%d", state.speed);
  }
  return lines;
}
}  // namespace a1oled
