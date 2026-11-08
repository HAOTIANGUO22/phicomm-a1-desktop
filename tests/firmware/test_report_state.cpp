// SPDX-License-Identifier: GPL-3.0-only
#include <assert.h>
#include <string.h>
#include "../../firmware/a1_oled/report_state.h"
#include "../../firmware/a1_oled/display_model.h"

int main() {
  const uint8_t mac[] = {2, 0, 0, 0, 0, 1};
  const uint8_t other[] = {2, 0, 0, 0, 0, 2};
  a1::ReportedState report;
  assert(!report.known());
  assert(!report.receive(3, 100));
  assert(report.mode() == -1 && report.speed() == -1);
  assert(report.receive(2, 44));
  assert(report.known() && !report.cached());
  assert(report.confirms(2, 44));

  // A1 can reconnect without another mode report; values must survive.
  for (int i = 0; i < 1000; ++i) {
    report.connectionLost();
    assert(report.known() && report.cached());
    assert(report.mode() == 2 && report.speed() == 44);
    assert(!report.confirms(2, 44));
    assert(!report.receive(-1, 0));
  }
  a1oled::State screen;
  screen.wifiConnected = screen.deviceConnected = true;
  screen.hasReport = report.known();
  screen.cached = report.cached();
  screen.mode = report.mode();
  screen.speed = report.speed();
  auto lines = a1oled::screenLines(screen);
  assert(strcmp(lines.power, "上次开机") == 0);
  assert(strcmp(lines.speed, "44") == 0);

  // Partial reports cannot claim that both cached fields are fresh.
  assert(report.receive(-1, 55));
  assert(report.cached() && !report.confirms(2, 55));
  assert(report.receive(2, -1));
  assert(!report.cached() && report.confirms(2, 55));
  auto stored = report.snapshot(mac);
  a1::ReportedState afterReset;
  assert(afterReset.restore(stored, mac));
  assert(afterReset.known() && afterReset.cached());
  assert(afterReset.mode() == 2 && afterReset.speed() == 55);
  assert(!afterReset.confirms(2, 55));
  assert(afterReset.receive(0, -1));
  assert(afterReset.cached());
  assert(afterReset.confirms(0, -1));
  assert(!afterReset.confirms(0, 55));
  assert(afterReset.receive(-1, 55));
  assert(!afterReset.cached());

  // A saved report is bound to exactly one device and validated on load.
  assert(!afterReset.restore(stored, other));
  assert(!afterReset.known() && afterReset.speed() == -1);
  auto invalid = stored;
  invalid.marker = 0;
  assert(!afterReset.restore(invalid, mac));
  invalid = stored; invalid.mode = 3;
  assert(!afterReset.restore(invalid, mac));
  invalid = stored; invalid.speed = 86;
  assert(!afterReset.restore(invalid, mac));

  // Losing Wi-Fi preserves the last report but never presents it as live.
  screen.wifiConnected = screen.deviceConnected = false;
  lines = a1oled::screenLines(screen);
  assert(strcmp(lines.connection, "Wi-Fi 连接中") == 0);
  assert(strcmp(lines.power, "上次开机") == 0);
  assert(strcmp(lines.speed, "44") == 0);
  screen.wifiConnected = screen.deviceConnected = true;
  screen.cached = false;
  screen.pending = true;
  screen.mode = 0;
  lines = a1oled::screenLines(screen);
  assert(strcmp(lines.connection, "A1 等待确认") == 0);
  assert(strcmp(lines.power, "已关机") == 0);
  assert(strcmp(lines.speed, "44") == 0);
  screen.setupMode = true;
  lines = a1oled::screenLines(screen);
  assert(strcmp(lines.speed, "--") == 0);
  assert(strcmp(lines.power, "待配网") == 0);
  return 0;
}
