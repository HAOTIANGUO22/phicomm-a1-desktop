# SPDX-License-Identifier: GPL-3.0-only
"""Bounded provisioning workflow with device-side verification."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import ipaddress
import threading
import time
from tools.a1_easylink import data_packets, encode, send
from tools.find_a1 import check
from windows_wifi import WindowsWifi, WifiError, mac_for_ip, subnet_for


def is_stock_a1(result):
    return (isinstance(result, dict) and result.get('config_read') is True
            and result.get('PO') == 'com.phicomm.basic' and result.get('FW') == 'v1.47'
            and result.get('HD') == '3080B'
            and str(result.get('N', '')).startswith(('EMW3080B(', 'MK3080B(')))


def discover(network, cancel=None, checker=check, mac_reader=mac_for_ip):
    subnet = ipaddress.IPv4Network(network, strict=False)
    if subnet.num_addresses > 256:
        raise WifiError('自动查找范围不能超过 256 个地址')
    cancel = cancel or threading.Event()
    results = []
    with ThreadPoolExecutor(max_workers=48) as executor:
        futures = [executor.submit(checker, str(ip)) for ip in subnet.hosts()]
        for future in as_completed(futures):
            if cancel.is_set():
                for pending in futures: pending.cancel()
                break
            try:
                result = future.result()
            except Exception:
                continue
            if not is_stock_a1(result):
                continue
            mac = mac_reader(result['ip'])
            if mac and mac[-6:].upper() not in result['N'].upper():
                continue
            results.append({'ip': result['ip'], 'mac': mac, 'name': result['N'],
                            'firmware': result['FW'], 'verified': True})
    return sorted(results, key=lambda d: int(ipaddress.IPv4Address(d['ip'])))


def require_network(adapter, profile, allow_unknown_band=False):
    if not adapter.connected or adapter.profile != profile:
        raise WifiError('电脑尚未连接选中的家庭 Wi-Fi')
    if not adapter.ip or not adapter.ssid:
        raise WifiError('尚未取得无线网卡 IP 或 Wi-Fi 名称，请稍后刷新')
    subnet_for(adapter.ip, adapter.prefix)
    if adapter.frequency is None:
        if not allow_unknown_band:
            raise WifiError('未能读取频段；请先确认是 2.4 GHz，再勾选下方的频段确认选项')
    elif not 2400 <= adapter.frequency < 2500:
        raise WifiError('当前不是 2.4 GHz。请使用独立的 2.4 GHz Wi-Fi 后重试')


class Provisioner:
    def __init__(self, wifi_factory=WindowsWifi, scanner=discover, sender=send, duration=55,
                 verification_seconds=35):
        self.wifi_factory, self.scanner, self.sender = wifi_factory, scanner, sender
        self.duration, self.verification_seconds = duration, verification_seconds

    def run(self, guid, profile, cancel, notify, password=None, use_saved=True,
            allow_unknown_band=False):
        def phase(title, detail=''):
            notify('phase', {'title': title, 'detail': detail})
        def cancelled():
            return {'status': 'cancelled', 'devices': []}
        with self.wifi_factory() as wifi:
            phase('正在检查无线网络', '确认网卡、Wi-Fi 和 2.4 GHz 连接')
            adapters = wifi.adapters()
            adapter = next((a for a in adapters if a.guid == guid), None)
            if adapter is None:
                raise WifiError('找不到选中的无线网卡，请刷新后重试')
            if profile not in adapter.profiles:
                raise WifiError('请先通过 Windows 连接目标 Wi-Fi 一次，再刷新本窗口')
            if (not adapter.connected or adapter.profile != profile
                    or (adapter.frequency is not None and not 2400 <= adapter.frequency < 2500)):
                phase('正在连接家庭 Wi-Fi', '优先选择同名网络中的 2.4 GHz 接入点')
                wifi.connect(guid, profile)
                deadline = time.monotonic() + 25
                while time.monotonic() < deadline:
                    if cancel.wait(1): return cancelled()
                    adapter = next((a for a in wifi.adapters() if a.guid == guid), None)
                    # WlanConnect is asynchronous: the previous 5 GHz association
                    # may remain visible briefly while Windows switches BSSID.
                    if (adapter and adapter.connected and adapter.profile == profile and adapter.ip
                            and (adapter.frequency is None or 2400 <= adapter.frequency < 2500)):
                        break
                else:
                    raise WifiError('电脑未能连接此 Wi-Fi 的 2.4 GHz 接入点，请检查 Windows 连接或拆分双频名称')
            if cancel.is_set(): return cancelled()
            require_network(adapter, profile, allow_unknown_band)
            notify('network', adapter)
            network = subnet_for(adapter.ip, adapter.prefix)
            phase('检查 A1 是否已经联网', '先查找设备，避免重复发送配网信息')
            existing = self.scanner(network, cancel)
            if cancel.is_set(): return cancelled()
            if existing:
                return {'status': 'already_online', 'devices': existing, 'network': network}
            if use_saved:
                ssid, key = wifi.credentials(adapter)
                if ssid != adapter.ssid:
                    raise WifiError('已保存配置与当前 Wi-Fi 不一致，请刷新网络后重试')
            else:
                ssid, key = adapter.ssid, password
                if not key:
                    raise WifiError('请在本机输入当前 Wi-Fi 密码')
            packets = data_packets(encode(ssid, key, adapter.ip))
            key = password = None
            if cancel.is_set(): return cancelled()
            phase('现在按住 A1 的 Wi-Fi 键 1–2 秒', '松开后保持通电，软件正在发送配网数据')
            sender_errors = []
            def transmit():
                try:
                    self.sender(packets, adapter.ip, duration=self.duration, cancel=cancel,
                                progress=lambda count, cycles, elapsed: notify('progress', {
                                    'percent': min(70, elapsed / self.duration * 70),
                                    'detail': f'已发送 {int(elapsed)} 秒，正在等待设备联网'}))
                except Exception:
                    # A socket exception can contain a credential-bearing multicast IP.
                    sender_errors.append(True)
            sender = threading.Thread(target=transmit, daemon=True)
            sender.start()
            start = time.monotonic()
            next_scan = start + min(8, self.duration)
            deadline = start + self.duration + self.verification_seconds
            try:
                while time.monotonic() < deadline:
                    if cancel.wait(.25): return cancelled()
                    if sender_errors:
                        raise WifiError('配网数据发送失败，请检查无线连接或改用另一张网卡')
                    now = time.monotonic()
                    if now >= next_scan:
                        devices = self.scanner(network, cancel)
                        if cancel.is_set(): return cancelled()
                        if devices:
                            return {'status': 'verified', 'devices': devices, 'network': network}
                        next_scan = time.monotonic() + 4
                    if not sender.is_alive():
                        elapsed = now - start - self.duration
                        notify('progress', {'percent': min(98, 70 + max(0, elapsed) / max(1, self.verification_seconds) * 28),
                                            'detail': '发送已结束，正在核对设备身份；尚未确认联网成功'})
                return {'status': 'unconfirmed', 'devices': [], 'network': network}
            finally:
                cancel.set()
                sender.join(timeout=2)
