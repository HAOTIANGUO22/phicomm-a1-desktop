// SPDX-License-Identifier: GPL-3.0-only
#pragma once

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

namespace a1 {
constexpr const char *domains[] = {"aircleanerconnecter.phicomm.com",
                                   "aircleaner.phicomm.com", "phicloudsym.phicomm.com"};
constexpr uint8_t footer[] = {0xff, '#', 'E', 'N', 'D', '#'};
constexpr size_t headerSize = 28;

inline bool validMode(int mode) {
  return mode == 0 || mode == 1 || mode == 2 || mode == 4 || mode == 5;
}

inline size_t controlFrame(uint8_t *output, size_t capacity, const uint8_t *header,
                           const uint8_t *mac, int mode, int speed) {
  if (!validMode(mode) || speed > 85 || (speed != -1 && speed < 30) ||
      capacity <= headerSize + sizeof(footer)) {
    return 0;
  }
  const size_t room = capacity - headerSize - sizeof(footer);
  char *body = reinterpret_cast<char *>(output + headerSize);
  const int length = speed == -1
      ? snprintf(body, room, "{\"datatype\":\"control\",\"data\":{\"mode\":%d}}", mode)
      : snprintf(body, room, "{\"datatype\":\"control\",\"data\":{\"speed\":%d,\"mode\":%d}}", speed, mode);
  if (length < 0 || static_cast<size_t>(length) >= room) {
    return 0;
  }
  memcpy(output, header, headerSize);
  memcpy(output + 17, mac, 6);
  output[23] = 0;
  output[24] = 0x3d;
  memcpy(body + length, footer, sizeof(footer));
  return headerSize + length + sizeof(footer);
}

// Return -1 for malformed requests and 0 for a valid question to forward.
inline int answerDns(uint8_t *packet, size_t size, size_t capacity, const uint8_t *ip) {
  if (size < 17 || size > capacity || (packet[2] & 0xf8) || packet[4] != 0 || packet[5] != 1) {
    return -1;
  }
  char name[254];
  size_t offset = 12;
  size_t length = 0;
  while (offset < size && packet[offset]) {
    const uint8_t label = packet[offset++];
    if (label > 63 || offset + label > size || length + label + 1 >= sizeof(name)) {
      return -1;
    }
    if (length) {
      name[length++] = '.';
    }
    for (int i = 0; i < label; ++i) {
      const uint8_t c = packet[offset++];
      if (c < 33 || c > 126) {
        return -1;
      }
      name[length++] = c >= 'A' && c <= 'Z' ? c + ('a' - 'A') : c;
    }
  }
  if (offset + 5 > size) {
    return -1;
  }
  name[length] = '\0';
  bool vendor = false;
  for (const char *domain : domains) {
    vendor |= strcmp(name, domain) == 0;
  }
  if (!vendor) {
    return 0;
  }
  ++offset;
  const bool ipv4 = packet[offset] == 0 && packet[offset + 1] == 1 &&
                    packet[offset + 2] == 0 && packet[offset + 3] == 1;
  const size_t end = offset + 4;
  if (ipv4 && capacity - end < 16) {
    return -1;
  }
  packet[2] = 0x81;
  packet[3] = 0x80;
  memset(packet + 6, 0, 6);
  if (!ipv4) {
    return end;
  }
  packet[7] = 1;
  const uint8_t answer[] = {0xc0, 0x0c, 0, 1, 0, 1, 0, 0, 0, 30, 0, 4};
  memcpy(packet + end, answer, sizeof(answer));
  memcpy(packet + end + sizeof(answer), ip, 4);
  return end + 16;
}
}  // namespace a1
