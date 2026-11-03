# SPDX-License-Identifier: GPL-3.0-only
"""Windows Native Wi-Fi access. Connection secrets remain in process memory."""
from __future__ import annotations
import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass, field
import ipaddress
import json
import socket
import struct
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from tools.send_saved_wifi import GUID, profile_credentials


class WifiError(RuntimeError):
    pass


class Ssid(C.Structure):
    _fields_ = [('length', W.DWORD), ('data', C.c_ubyte * 32)]


class Association(C.Structure):
    _fields_ = [('ssid', Ssid), ('bss_type', W.DWORD), ('bssid', C.c_ubyte * 6),
                ('phy_type', W.DWORD), ('phy_index', W.DWORD), ('quality', W.DWORD),
                ('rx_rate', W.DWORD), ('tx_rate', W.DWORD)]


class Connection(C.Structure):
    _fields_ = [('state', W.DWORD), ('mode', W.DWORD), ('profile', W.WCHAR * 256),
                ('association', Association), ('security', W.BOOL), ('one_x', W.BOOL),
                ('authentication', W.DWORD), ('cipher', W.DWORD)]


class Interface(C.Structure):
    _fields_ = [('guid', GUID), ('description', W.WCHAR * 256), ('state', W.DWORD)]


class Profile(C.Structure):
    _fields_ = [('name', W.WCHAR * 256), ('flags', W.DWORD)]


class RateSet(C.Structure):
    _fields_ = [('length', W.DWORD), ('rates', W.USHORT * 126)]


class Bss(C.Structure):
    _fields_ = [('ssid', Ssid), ('phy_id', W.DWORD), ('bssid', C.c_ubyte * 6),
                ('bss_type', W.DWORD), ('phy_type', W.DWORD), ('rssi', W.LONG),
                ('quality', W.DWORD), ('in_reg_domain', C.c_ubyte), ('beacon', W.USHORT),
                ('timestamp', C.c_ulonglong), ('host_timestamp', C.c_ulonglong),
                ('capabilities', W.USHORT), ('frequency_khz', W.DWORD), ('rates', RateSet),
                ('ie_offset', W.DWORD), ('ie_size', W.DWORD)]


class ObjectHeader(C.Structure):
    _fields_ = [('type', C.c_ubyte), ('revision', C.c_ubyte), ('size', W.USHORT)]


class BssidList(C.Structure):
    _fields_ = [('header', ObjectHeader), ('count', W.DWORD), ('total', W.DWORD),
                ('bssids', (C.c_ubyte * 6) * 1)]


class ConnectParameters(C.Structure):
    _fields_ = [('mode', W.DWORD), ('profile', W.LPCWSTR), ('ssid', C.c_void_p),
                ('bssids', C.POINTER(BssidList)), ('bss_type', W.DWORD), ('flags', W.DWORD)]


@dataclass
class WifiAdapter:
    guid: str = field(repr=False)
    name: str
    description: str
    connected: bool = False
    profile: str = ''
    ssid: str = ''
    ip: str = ''
    prefix: int = 24
    gateway: str = ''
    frequency: int | None = None
    profiles: list[str] = field(default_factory=list)
    issue: str = ''

    @property
    def band(self):
        if self.frequency is None:
            return '未能读取频段'
        if 2400 <= self.frequency < 2500:
            return '2.4 GHz'
        if 4900 <= self.frequency < 5925:
            return '5 GHz'
        if 5925 <= self.frequency < 7200:
            return '6 GHz'
        return '未知频段'


def subnet_for(ip, prefix):
    address = ipaddress.IPv4Address(ip)
    if address.is_loopback or address.is_unspecified or address.is_multicast or address.is_link_local:
        raise WifiError('这张网卡还没有取得可用的局域网地址')
    # Keep automatic discovery bounded to at most one /24.
    return str(ipaddress.IPv4Network(f'{address}/{max(24, int(prefix))}', strict=False))


def adapter_networks():
    script = r"""[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $ErrorActionPreference='Stop'
    $items=@(Get-NetAdapter | ForEach-Object {
      $adapter=$_
      $addresses=@(Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1' } |
        Select-Object IPAddress,PrefixLength)
      $gateway=(Get-NetRoute -InterfaceIndex $adapter.ifIndex -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
        Sort-Object RouteMetric | Select-Object -First 1 -ExpandProperty NextHop)
      [pscustomobject]@{guid=([guid]$adapter.InterfaceGuid).ToString('D');name=$adapter.Name;
        description=$adapter.InterfaceDescription;status=[string]$adapter.Status;addresses=$addresses;gateway=$gateway}
    })
    ConvertTo-Json -InputObject $items -Depth 4 -Compress"""
    try:
        result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script],
                     capture_output=True, timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise WifiError('无法读取网卡地址，请检查 Windows 网络服务')
        return json.loads(result.stdout.decode('utf-8-sig'))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise WifiError('读取网络信息失败，请稍后重试') from None


class WindowsWifi:
    def __init__(self):
        if sys.platform != 'win32':
            raise WifiError('自动配网工具仅支持 Windows')
        self.api = C.WinDLL('wlanapi')
        signatures = {
            'WlanOpenHandle': [W.DWORD, C.c_void_p, C.POINTER(W.DWORD), C.POINTER(W.HANDLE)],
            'WlanCloseHandle': [W.HANDLE, C.c_void_p],
            'WlanFreeMemory': [C.c_void_p],
            'WlanEnumInterfaces': [W.HANDLE, C.c_void_p, C.POINTER(C.c_void_p)],
            'WlanGetProfileList': [W.HANDLE, C.POINTER(GUID), C.c_void_p, C.POINTER(C.c_void_p)],
            'WlanQueryInterface': [W.HANDLE, C.POINTER(GUID), W.DWORD, C.c_void_p,
                 C.POINTER(W.DWORD), C.POINTER(C.c_void_p), C.POINTER(W.DWORD)],
            'WlanGetNetworkBssList': [W.HANDLE, C.POINTER(GUID), C.c_void_p, W.DWORD,
                 W.BOOL, C.c_void_p, C.POINTER(C.c_void_p)],
            'WlanGetProfile': [W.HANDLE, C.POINTER(GUID), W.LPCWSTR, C.c_void_p,
                 C.POINTER(C.c_void_p), C.POINTER(W.DWORD), C.POINTER(W.DWORD)],
            'WlanConnect': [W.HANDLE, C.POINTER(GUID), C.POINTER(ConnectParameters), C.c_void_p],
            'WlanScan': [W.HANDLE, C.POINTER(GUID), C.c_void_p, C.c_void_p, C.c_void_p],
        }
        for name, arguments in signatures.items():
            function = getattr(self.api, name)
            function.argtypes = arguments
            function.restype = W.DWORD
        self.handle, version = W.HANDLE(), W.DWORD()
        result = self.api.WlanOpenHandle(2, None, C.byref(version), C.byref(self.handle))
        if result:
            raise WifiError(f'无法打开 Windows 无线服务（错误 {result}）')

    def __enter__(self): return self
    def __exit__(self, *args): self.api.WlanCloseHandle(self.handle, None)

    @staticmethod
    def guid(value): return GUID.from_buffer_copy(uuid.UUID(value).bytes_le)

    def profile_names(self, guid):
        pointer = C.c_void_p()
        result = self.api.WlanGetProfileList(self.handle, C.byref(guid), None, C.byref(pointer))
        if result:
            return []
        try:
            count = C.cast(pointer, C.POINTER(W.DWORD))[0]
            if count > 1024:
                return []
            entries = C.cast(pointer.value + 8, C.POINTER(Profile))
            return [entries[i].name for i in range(count)]
        finally:
            self.api.WlanFreeMemory(pointer)

    def bss_entries(self, guid):
        pointer = C.c_void_p()
        result = self.api.WlanGetNetworkBssList(self.handle, C.byref(guid), None, 3, False, None, C.byref(pointer))
        if result:
            return []
        try:
            total, count = C.cast(pointer, C.POINTER(W.DWORD))[:2]
            if count > 4096 or 8 + count * C.sizeof(Bss) > total:
                return []
            entries = C.cast(pointer.value + 8, C.POINTER(Bss))
            return [{'ssid': bytes(entries[i].ssid.data[:min(entries[i].ssid.length, 32)]),
                     'bssid': bytes(entries[i].bssid), 'frequency': entries[i].frequency_khz // 1000,
                     'quality': int(entries[i].quality)} for i in range(count)]
        finally:
            self.api.WlanFreeMemory(pointer)

    def connection(self, guid):
        pointer, size, kind = C.c_void_p(), W.DWORD(), W.DWORD()
        result = self.api.WlanQueryInterface(self.handle, C.byref(guid), 7, None,
                                           C.byref(size), C.byref(pointer), C.byref(kind))
        if result:
            return None, result
        try:
            if size.value < C.sizeof(Connection):
                return None, -1
            value = C.cast(pointer, C.POINTER(Connection)).contents
            return {'connected': value.state == 1, 'profile': value.profile,
                    'ssid': bytes(value.association.ssid.data[:min(value.association.ssid.length, 32)]).decode('utf-8', 'replace'),
                    'bssid': bytes(value.association.bssid)}, 0
        finally:
            self.api.WlanFreeMemory(pointer)

    def adapters(self):
        networks = {str(uuid.UUID(item['guid'])): item for item in adapter_networks()}
        pointer = C.c_void_p()
        result = self.api.WlanEnumInterfaces(self.handle, None, C.byref(pointer))
        if result:
            raise WifiError(f'无法枚举无线网卡（错误 {result}）')
        try:
            count = C.cast(pointer, C.POINTER(W.DWORD))[0]
            if count > 128:
                raise WifiError('无线网卡列表异常')
            entries = C.cast(pointer.value + 8, C.POINTER(Interface))
            output = []
            for i in range(count):
                entry = entries[i]
                identifier = str(uuid.UUID(bytes_le=bytes(entry.guid)))
                item = networks.get(identifier, {})
                adapter = WifiAdapter(identifier, item.get('name', entry.description), entry.description)
                addresses = item.get('addresses') or []
                if isinstance(addresses, dict): addresses = [addresses]
                if addresses:
                    adapter.ip = addresses[0]['IPAddress']
                    adapter.prefix = int(addresses[0]['PrefixLength'])
                adapter.gateway = item.get('gateway') or ''
                adapter.profiles = self.profile_names(entry.guid)
                current, error = self.connection(entry.guid)
                if current:
                    adapter.connected = current['connected']
                    adapter.profile, adapter.ssid = current['profile'], current['ssid']
                    matching = [b for b in self.bss_entries(entry.guid) if b['bssid'] == current['bssid']]
                    if matching: adapter.frequency = matching[0]['frequency']
                elif error == 5:
                    adapter.issue = 'Windows 未允许读取当前 Wi-Fi 信息；请检查本机 Wi-Fi／位置权限'
                output.append(adapter)
            return output
        finally:
            self.api.WlanFreeMemory(pointer)

    def profile_xml(self, identifier, profile, plaintext=False):
        guid = self.guid(identifier)
        pointer, flags, access = C.c_void_p(), W.DWORD(4 if plaintext else 0), W.DWORD()
        result = self.api.WlanGetProfile(self.handle, C.byref(guid), profile, None,
                                        C.byref(pointer), C.byref(flags), C.byref(access))
        if result:
            raise WifiError(f'无法读取选中的 Wi-Fi 配置（错误 {result}）')
        try:
            return C.wstring_at(pointer)
        finally:
            self.api.WlanFreeMemory(pointer)

    def credentials(self, adapter):
        try:
            return profile_credentials(self.profile_xml(adapter.guid, adapter.profile, True))
        except RuntimeError:
            raise WifiError('Windows 没有返回可用密码，请取消“使用已保存密码”并在本窗口输入密码') from None

    def connect(self, identifier, profile):
        guid = self.guid(identifier)
        xml = self.profile_xml(identifier, profile)
        root = ET.fromstring(xml)
        ssid = root.findtext('{*}SSIDConfig/{*}SSID/{*}name')
        target = ssid.encode('utf-8') if ssid else None
        candidates = [b for b in self.bss_entries(guid)
                      if b['ssid'] == target and 2400 <= b['frequency'] < 2500]
        desired = None
        if candidates:
            best = max(candidates, key=lambda b: b['quality'])
            desired = BssidList()
            desired.header = ObjectHeader(0x80, 1, C.sizeof(BssidList))
            desired.count = desired.total = 1
            desired.bssids[0][:] = best['bssid']
        params = ConnectParameters(0, profile, None, C.pointer(desired) if desired is not None else None, 1, 0)
        result = self.api.WlanConnect(self.handle, C.byref(guid), C.byref(params), None)
        if result:
            raise WifiError(f'Windows 未能开始连接此 Wi-Fi（错误 {result}）')
        return desired is not None


def mac_for_ip(ip):
    if sys.platform != 'win32':
        return ''
    api = C.WinDLL('iphlpapi').SendARP
    api.argtypes = [W.DWORD, W.DWORD, C.c_void_p, C.POINTER(W.ULONG)]
    api.restype = W.DWORD
    buffer, length = (W.ULONG * 2)(), W.ULONG(8)
    address = struct.unpack('=I', socket.inet_aton(str(ipaddress.IPv4Address(ip))))[0]
    if api(address, 0, C.byref(buffer), C.byref(length)) == 0 and length.value == 6:
        return C.string_at(C.byref(buffer), 6).hex()
    return ''
