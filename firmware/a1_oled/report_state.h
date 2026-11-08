// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include "protocol.h"

namespace a1 {
struct ReportSnapshot {
  uint32_t marker = 0x41315331;
  uint8_t mac[6] = {};
  int8_t mode = -1;
  int8_t speed = -1;
};
static_assert(sizeof(ReportSnapshot) == 12, "Unexpected stored report layout");

class ReportedState {
 public:
  int mode() const { return mode_; }
  int speed() const { return speed_; }
  bool known() const { return validMode(mode_); }
  bool cached() const {
    return known() && (!freshMode_ || (validSpeed(speed_) && !freshSpeed_));
  }
  // A quiet A1 is normal. Connection changes invalidate freshness, not values.
  void connectionLost() { freshMode_ = freshSpeed_ = false; }
  bool receive(int mode, int speed) {
    const bool haveMode = validMode(mode), haveSpeed = validSpeed(speed);
    if (!haveMode && !haveSpeed) return false;
    if (haveMode) { mode_ = mode; freshMode_ = true; }
    if (haveSpeed) { speed_ = speed; freshSpeed_ = true; }
    return true;
  }
  bool confirms(int mode, int speed) const {
    return freshMode_ && mode_ == mode &&
           (speed < 0 || (freshSpeed_ && speed_ == speed));
  }
  ReportSnapshot snapshot(const uint8_t *mac) const {
    ReportSnapshot result;
    memcpy(result.mac, mac, sizeof(result.mac));
    result.mode = static_cast<int8_t>(mode_);
    result.speed = static_cast<int8_t>(speed_);
    return result;
  }
  bool restore(const ReportSnapshot &saved, const uint8_t *mac) {
    mode_ = speed_ = -1;
    connectionLost();
    if (saved.marker != 0x41315331 || memcmp(saved.mac, mac, sizeof(saved.mac)) ||
        !validMode(saved.mode) || (saved.speed != -1 && !validSpeed(saved.speed))) return false;
    mode_ = saved.mode;
    speed_ = saved.speed;
    return true;
  }
 private:
  int mode_ = -1, speed_ = -1;
  bool freshMode_ = false, freshSpeed_ = false;
  static bool validSpeed(int value) { return value >= 30 && value <= 85; }
};
}  // namespace a1
