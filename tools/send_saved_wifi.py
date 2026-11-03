# SPDX-License-Identifier: GPL-3.0-only
"""Send a saved Windows Wi-Fi profile without printing or saving its password."""
import argparse
import ctypes
from ctypes import wintypes
import ipaddress
import json
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

from a1_easylink import data_packets, encode, send


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


def adapter_guid(interface_ip, adapter=None):
    """Resolve the actual selected adapter, independent of Windows display language."""
    address = str(ipaddress.IPv4Address(interface_ip))
    selection = (f"Get-NetIPAddress -IPAddress '{address}' -AddressFamily IPv4 -ErrorAction Stop | "
                 "Select-Object -ExpandProperty InterfaceIndex -Unique | "
                 "ForEach-Object { Get-NetAdapter -InterfaceIndex $_ -ErrorAction Stop }")
    if adapter:
        literal = adapter.replace("'", "''")
        selection += f" | Where-Object {{ $_.Name -eq '{literal}' }}"
    query = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command',
                            "$ErrorActionPreference='Stop'; " + selection +
                            ' | Select-Object -ExpandProperty InterfaceGuid'],
                           capture_output=True, text=True, check=True)
    identifiers = [line.strip() for line in query.stdout.splitlines() if line.strip()]
    if len(identifiers) != 1:
        raise RuntimeError('未找到唯一网卡；请检查无线 IPv4，或使用 --adapter 指定无线网卡名称')
    return uuid.UUID(identifiers[0])


def profile_credentials(profile_xml):
    root = ET.fromstring(profile_xml)
    ns = {'w': 'http://www.microsoft.com/networking/WLAN/profile/v1'}
    name = root.findtext('w:SSIDConfig/w:SSID/w:name', namespaces=ns)
    protected = root.findtext('w:MSM/w:security/w:sharedKey/w:protected', namespaces=ns)
    key = root.findtext('w:MSM/w:security/w:sharedKey/w:keyMaterial', namespaces=ns)
    if protected != 'false' or not name or not key:
        raise RuntimeError('Windows 未返回可用密码；可以改用 a1_easylink.py 手动输入')
    return name, key


def saved_password(profile, interface_ip, adapter=None):
    if sys.platform != 'win32':
        raise RuntimeError('读取已保存 Wi-Fi 配置的工具仅支持 Windows')
    identifier = adapter_guid(interface_ip, adapter)
    # Windows Native Wi-Fi returns the profile in memory; no export file is used.
    api = ctypes.WinDLL("wlanapi")
    api.WlanOpenHandle.argtypes = [wintypes.DWORD, ctypes.c_void_p,
                                  ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.HANDLE)]
    api.WlanGetProfile.argtypes = [wintypes.HANDLE, ctypes.POINTER(GUID), wintypes.LPCWSTR,
                                  ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
                                  ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
    api.WlanFreeMemory.argtypes = [ctypes.c_void_p]
    api.WlanCloseHandle.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    api.WlanQueryInterface.argtypes = [wintypes.HANDLE, ctypes.POINTER(GUID), wintypes.DWORD,
                                      ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD),
                                      ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
    handle, version = wintypes.HANDLE(), wintypes.DWORD()
    if api.WlanOpenHandle(2, None, ctypes.byref(version), ctypes.byref(handle)):
        raise RuntimeError("Cannot open Windows Wi-Fi service")
    guid = GUID.from_buffer_copy(identifier.bytes_le)
    xml_pointer = ctypes.c_void_p()
    flags, access = wintypes.DWORD(4), wintypes.DWORD()
    try:
        # The first fields of WLAN_CONNECTION_ATTRIBUTES; no BSSID is logged.
        class ConnectionHeader(ctypes.Structure):
            _fields_ = [('state', wintypes.DWORD), ('mode', wintypes.DWORD),
                        ('profile', wintypes.WCHAR * 256)]
        connection, size, kind = ctypes.c_void_p(), wintypes.DWORD(), wintypes.DWORD()
        try:
            result = api.WlanQueryInterface(handle, ctypes.byref(guid), 7, None,
                         ctypes.byref(size), ctypes.byref(connection), ctypes.byref(kind))
            if result:
                if result == 5023:
                    raise RuntimeError('无线网卡当前未连接 Wi-Fi；请先连接目标 2.4 GHz 网络')
                raise RuntimeError(f'无法检查当前无线连接（Windows 错误 {result}），请确认 Wi-Fi 已连接及系统权限')
            if size.value < ctypes.sizeof(ConnectionHeader):
                raise RuntimeError('Windows 返回的无线连接信息不完整')
            current = ctypes.cast(connection, ctypes.POINTER(ConnectionHeader)).contents
            if current.state != 1 or current.profile != profile:
                raise RuntimeError('无线网卡尚未连接指定配置；请先连接 --profile 指定的 Wi-Fi')
        finally:
            if connection:
                api.WlanFreeMemory(connection)
        result = api.WlanGetProfile(handle, ctypes.byref(guid), profile, None,
                                    ctypes.byref(xml_pointer), ctypes.byref(flags), ctypes.byref(access))
        if result:
            raise RuntimeError(f"Cannot read saved Wi-Fi profile (Windows error {result})")
        return profile_credentials(ctypes.wstring_at(xml_pointer))
    finally:
        if xml_pointer:
            api.WlanFreeMemory(xml_pointer)
        api.WlanCloseHandle(handle, None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--interface-ip", required=True)
    parser.add_argument('--adapter', help='可选：无线网卡名称，例如 WLAN 或 Wi-Fi；默认按 --interface-ip 查找')
    parser.add_argument("--check-only", action="store_true", help='只检查网卡、连接与配网编码，不发送配网数据')
    parser.add_argument("--duration", type=float, default=55)
    args = parser.parse_args()
    try:
        ssid, password = saved_password(args.profile, args.interface_ip, args.adapter)
        packets = data_packets(encode(ssid, password, args.interface_ip))
        password = None
        print(json.dumps({"status": "ready", "ssid": ssid,
                          "interface_ip": args.interface_ip, "packet_pairs": len(packets)}), flush=True)
        if args.check_only:
            return 0
        print('请现在单独按住 A1 的 Wi-Fi 图标键约 1–2 秒后松开；开始发送配网数据。', flush=True)
        count, cycles = send(packets, args.interface_ip, duration=args.duration,
                             progress=lambda n, c, t: print(json.dumps(
                                 {"sent": n, "cycles": c, "elapsed": round(t)}), flush=True))
        print(json.dumps({"status": "sent_only", "packets": count, "cycles": cycles}), flush=True)
        return 0
    except RuntimeError as exc:
        print(json.dumps({'status': 'error', 'message': str(exc)}, ensure_ascii=True), flush=True)
        return 1
    except Exception as exc:
        # No exception text: socket errors can include credential-bearing destinations.
        print(json.dumps({"status": "error", "type": type(exc).__name__}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
