# SPDX-License-Identifier: GPL-3.0-only
"""Send a saved Windows Wi-Fi profile without printing or saving its password."""
import argparse
import ctypes
from ctypes import wintypes
import json
import subprocess
import sys
import xml.etree.ElementTree as ET

from a1_easylink import data_packets, encode, send


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


def saved_password(profile):
    # Windows Native Wi-Fi returns the profile in memory; no export file is used.
    api = ctypes.WinDLL("wlanapi")
    api.WlanOpenHandle.argtypes = [wintypes.DWORD, ctypes.c_void_p,
                                  ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.HANDLE)]
    api.WlanGetProfile.argtypes = [wintypes.HANDLE, ctypes.POINTER(GUID), wintypes.LPCWSTR,
                                  ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
                                  ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
    api.WlanFreeMemory.argtypes = [ctypes.c_void_p]
    api.WlanCloseHandle.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    handle, version = wintypes.HANDLE(), wintypes.DWORD()
    if api.WlanOpenHandle(2, None, ctypes.byref(version), ctypes.byref(handle)):
        raise RuntimeError("Cannot open Windows Wi-Fi service")
    # The interface GUID is read from Windows, never inferred from a virtual adapter.
    query = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "(Get-NetAdapter -Name WLAN).InterfaceGuid.ToString()"],
                           capture_output=True, text=True, check=True)
    import uuid
    guid = GUID.from_buffer_copy(uuid.UUID(query.stdout.strip()).bytes_le)
    xml_pointer = ctypes.c_void_p()
    flags, access = wintypes.DWORD(4), wintypes.DWORD()
    try:
        result = api.WlanGetProfile(handle, ctypes.byref(guid), profile, None,
                                    ctypes.byref(xml_pointer), ctypes.byref(flags), ctypes.byref(access))
        if result:
            raise RuntimeError(f"Cannot read saved Wi-Fi profile (Windows error {result})")
        root = ET.fromstring(ctypes.wstring_at(xml_pointer))
        ns = {"w": "http://www.microsoft.com/networking/WLAN/profile/v1"}
        name = root.findtext("w:SSIDConfig/w:SSID/w:name", namespaces=ns)
        protected = root.findtext("w:MSM/w:security/w:sharedKey/w:protected", namespaces=ns)
        key = root.findtext("w:MSM/w:security/w:sharedKey/w:keyMaterial", namespaces=ns)
        if protected != "false" or not name or not key:
            raise RuntimeError("Windows did not return a usable saved password")
        return name, key
    finally:
        if xml_pointer:
            api.WlanFreeMemory(xml_pointer)
        api.WlanCloseHandle(handle, None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--interface-ip", required=True)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--duration", type=float, default=55)
    args = parser.parse_args()
    try:
        ssid, password = saved_password(args.profile)
        packets = data_packets(encode(ssid, password, args.interface_ip))
        password = None
        print(json.dumps({"status": "ready", "ssid": ssid,
                          "interface_ip": args.interface_ip, "packet_pairs": len(packets)}), flush=True)
        if args.check_only:
            return 0
        count, cycles = send(packets, args.interface_ip, duration=args.duration,
                             progress=lambda n, c, t: print(json.dumps(
                                 {"sent": n, "cycles": c, "elapsed": round(t)}), flush=True))
        print(json.dumps({"status": "sent_only", "packets": count, "cycles": cycles}), flush=True)
        return 0
    except Exception as exc:
        # No exception text: socket errors can include credential-bearing destinations.
        print(json.dumps({"status": "error", "type": type(exc).__name__}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
