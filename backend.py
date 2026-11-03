# SPDX-License-Identifier: GPL-3.0-only
"""Local controller for a stock Phicomm A1. No firmware images or OTA writes."""
from __future__ import annotations

import datetime
import http.client
import ipaddress
import json
import logging
from pathlib import Path
import socket
import ssl
import struct
import threading
import time
import warnings

FOOTER = b'\xff#END#'
DEFAULT_HEADER = (bytes.fromhex('aa0000000000000000') + bytes(8)
                  + bytes.fromhex('000000000000003d413104'))
DOMAINS = {'aircleanerconnecter.phicomm.com', 'aircleaner.phicomm.com',
           'phicloudsym.phicomm.com'}
DEFAULTS = {'device_ip': '', 'device_mac': '',
            'server_ip': '', 'gateway': '',
            'netmask': '255.255.255.0', 'dns_upstream': '',
            'manual_speed': 56}


def validate_settings(settings):
    values = dict(settings)
    for key, title in [('device_ip', '净化器 IP'), ('server_ip', '电脑 IP'),
                       ('gateway', '路由器 IP')]:
        try:
            address = ipaddress.IPv4Address(values.get(key, '').strip())
            if address.is_unspecified or address.is_multicast or address.is_loopback:
                raise ValueError()
            values[key] = str(address)
        except (ValueError, AttributeError):
            raise ValueError(f'请填写有效的{title}') from None
    values['dns_upstream'] = values.get('dns_upstream', '').strip() or values['gateway']
    try:
        dns = ipaddress.IPv4Address(values['dns_upstream'])
        if dns.is_unspecified or dns.is_multicast or dns.is_loopback:
            raise ValueError()
    except ValueError:
        raise ValueError('请填写有效的上游 DNS') from None
    try:
        network = ipaddress.IPv4Network(f"{values['device_ip']}/{values['netmask']}", strict=False)
    except (KeyError, ValueError):
        raise ValueError('请填写有效的子网掩码') from None
    if any(ipaddress.IPv4Address(values[k]) not in network for k in ('server_ip', 'gateway')):
        raise ValueError('净化器、电脑和路由器需要在同一子网')
    if len({values[k] for k in ('device_ip', 'server_ip', 'gateway')}) != 3:
        raise ValueError('净化器、电脑和路由器不能使用相同地址')
    mac = values.get('device_mac', '').strip().lower().replace(':', '').replace('-', '')
    if len(mac) != 12 or any(c not in '0123456789abcdef' for c in mac) or mac == '0' * 12:
        raise ValueError('请填写净化器完整的 12 位 MAC 地址')
    if int(mac[:2], 16) & 1:
        raise ValueError('请填写设备的单播 MAC 地址')
    values['device_mac'] = mac
    values['netmask'] = str(network.netmask)
    return values


def preset_speed(mode, speed, remembered):
    """Stock preset reports are not a substitute for explicitly setting speed."""
    if mode == 4:
        return 30
    if mode == 5:
        return 85
    if mode == 2 and speed is None:
        return remembered
    return speed


class Frames:
    """Buffer complete frames across arbitrary TCP reads."""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        if len(self.buffer) > 65536:
            self.buffer.clear()
            raise ValueError('Frame buffer exceeded limit')
        frames = []
        while True:
            end = self.buffer.find(FOOTER)
            if end < 0:
                break
            raw = bytes(self.buffer[:end + len(FOOTER)])
            del self.buffer[:end + len(FOOTER)]
            start = raw.find(b'{')
            if start < 0:
                continue
            try:
                message = json.loads(raw[start:end].decode('utf-8'))
            except (ValueError, UnicodeError):
                continue
            if isinstance(message, dict):
                frames.append((raw[:start], message))
        return frames


def control_frame(speed=None, mode=None, header=DEFAULT_HEADER, mac=None):
    data = {}
    if speed is not None:
        if not isinstance(speed, int) or not 30 <= speed <= 85:
            raise ValueError('风量范围为 30–85')
        data['speed'] = speed
    if mode is not None:
        if mode not in (0, 1, 2, 4, 5):
            raise ValueError('不支持的运行模式')
        data['mode'] = mode
    if not data:
        raise ValueError('未指定控制动作')
    body = json.dumps({'datatype': 'control', 'data': data}, separators=(',', ':')).encode()
    # The upstream A1 implementation uses a fixed 28-byte envelope, even when
    # the JSON size changes. Keep its length field until real-device evidence
    # establishes otherwise; replace only the device-specific MAC.
    wire = bytearray(header if len(header) == 28 else DEFAULT_HEADER)
    wire[23:25] = b'\x00\x3d'
    if mac:
        wire[17:23] = bytes.fromhex(mac)
    return bytes(wire) + body + FOOTER


def device_config(ip, settings=None):
    ipaddress.IPv4Address(ip)
    conn = http.client.HTTPConnection(ip, 8000, timeout=6)
    conn._http_vsn = 10
    conn._http_vsn_str = 'HTTP/1.0'
    try:
        if settings is None:
            conn.request('GET', '/config-read', headers={'Connection': 'close'})
        else:
            body = json.dumps(settings, separators=(',', ':')).encode()
            conn.request('POST', '/config-write', body,
                         {'Content-Type': 'application/json', 'Connection': 'close'})
        response = conn.getresponse()
        data = response.read(65536)
        if response.status != 200:
            raise RuntimeError(f'设备接口返回 {response.status}')
        return json.loads(data) if settings is None else {'accepted': True}
    finally:
        conn.close()


def dns_question(packet):
    if len(packet) < 12 or struct.unpack_from('!H', packet, 4)[0] != 1:
        raise ValueError('Invalid DNS question')
    offset, labels = 12, []
    while True:
        if offset >= len(packet):
            raise ValueError('Truncated DNS name')
        length = packet[offset]
        offset += 1
        if not length:
            break
        if length > 63 or offset + length > len(packet):
            raise ValueError('Invalid DNS label')
        labels.append(packet[offset:offset + length].decode('ascii').lower())
        offset += length
    if offset + 4 > len(packet):
        raise ValueError('Missing DNS type')
    qtype, qclass = struct.unpack_from('!HH', packet, offset)
    return '.'.join(labels), qtype, qclass, offset + 4


def dns_answer(packet, server_ip):
    name, qtype, qclass, end = dns_question(packet)
    if name not in DOMAINS:
        return None
    question = packet[12:end]
    if qtype == 1 and qclass == 1:
        answer = b'\xc0\x0c' + struct.pack('!HHIH', 1, 1, 30, 4) + socket.inet_aton(server_ip)
        return packet[:2] + struct.pack('!HHHHH', 0x8180, 1, 1, 0, 0) + question + answer
    return packet[:2] + struct.pack('!HHHHH', 0x8180, 1, 0, 0, 0) + question


def certificate(root):
    cert, key = root / 'local.crt', root / 'local.key'
    if cert.exists() and key.exists():
        return cert, key
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'phicloudsym.phicomm.com')])
    now = datetime.datetime.now(datetime.timezone.utc)
    public = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
              .public_key(private.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(now - datetime.timedelta(days=1))
              .not_valid_after(now + datetime.timedelta(days=3650))
              .add_extension(x509.SubjectAlternativeName([x509.DNSName(d) for d in sorted(DOMAINS)]), False)
              .sign(private, hashes.SHA256()))
    key.write_bytes(private.private_bytes(serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    cert.write_bytes(public.public_bytes(serialization.Encoding.PEM))
    return cert, key


class Controller:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.config_path = self.root / 'settings.json'
        self.settings = dict(DEFAULTS)
        if self.config_path.exists():
            self.settings.update(json.loads(self.config_path.read_text('utf-8')))
        self.stop_event = threading.Event()
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.client = None
        self.listeners = []
        self.header = None
        saved_header = self.settings.get('control_header', '')
        try:
            candidate = bytes.fromhex(saved_header)
            if len(candidate) == 28 and candidate[17:23].hex() == self.settings['device_mac']:
                self.header = candidate
        except ValueError:
            pass
        self.pending_target = None
        self.pending_since = None
        self.state = {'connected': False, 'mode': None, 'speed': None, 'last_seen': None,
                      'dns_queries': 0, 'activation': False, 'message': '等待净化器连接',
                      'command_pending': False, 'identity': None, 'state_cached': False}
        cache_path = self.root / 'last-state.json'
        try:
            cache = json.loads(cache_path.read_text('utf-8'))
            if (cache.get('device_mac') == self.settings['device_mac']
                    and cache.get('mode') in (0, 1, 2, 4, 5)
                    and isinstance(cache.get('speed'), int) and 30 <= cache['speed'] <= 85
                    and isinstance(cache.get('last_seen'), (int, float))):
                self.state.update({k: cache[k] for k in ('mode', 'speed', 'last_seen')})
                self.state['state_cached'] = True
        except (OSError, ValueError, TypeError):
            pass
        self.events = []
        try:
            self.settings['manual_speed'] = min(85, max(30, int(self.settings['manual_speed'])))
        except (TypeError, ValueError):
            self.settings['manual_speed'] = 56

    def event(self, message):
        with self.lock:
            self.events.append({'time': time.strftime('%H:%M:%S'), 'text': message})
            self.events[:] = self.events[-80:]
        logging.info(message)

    def snapshot(self):
        with self.lock:
            if self.state['command_pending'] and self.pending_since and time.monotonic() - self.pending_since > 10:
                self.state.update(command_pending=False, message='指令已发送，但设备未返回新状态；可重新操作')
                self.pending_target = None
            return {**self.state, 'settings': dict(self.settings), 'events': list(self.events)}

    def save(self):
        self.config_path.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), 'utf-8')

    def start(self):
        self.settings = validate_settings(self.settings)
        cert, key = certificate(self.root)
        self.tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)
            self.tls_context.minimum_version = ssl.TLSVersion.TLSv1
        self.tls_context.set_ciphers('ALL:@SECLEVEL=0')
        self.tls_context.load_cert_chain(cert, key)
        ip = self.settings['server_ip']
        try:
            for kind, port, handler in [(socket.SOCK_DGRAM, 53, self.dns_loop),
                                        (socket.SOCK_STREAM, 9000, self.accept_control),
                                        (socket.SOCK_STREAM, 443, self.accept_tls)]:
                listener = socket.socket(socket.AF_INET, kind)
                self.listeners.append(listener)
                listener.settimeout(1)
                listener.bind((ip, port))
                if kind == socket.SOCK_STREAM:
                    listener.listen(8)
                threading.Thread(target=handler, args=(listener,), daemon=True).start()
        except Exception:
            self.close()
            raise
        self.event('本机控制服务已启动')

    def allowed(self, ip):
        return ip == self.settings['device_ip'] or ip == '127.0.0.1' or ip == self.settings['server_ip']

    def dns_loop(self, listener):
        while not self.stop_event.is_set():
            try:
                packet, peer = listener.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not self.allowed(peer[0]):
                continue
            try:
                name, *_ = dns_question(packet)
                answer = dns_answer(packet, self.settings['server_ip'])
                with self.lock:
                    self.state['dns_queries'] += 1
                if answer is None:
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as upstream:
                        upstream.settimeout(2)
                        upstream.sendto(packet, (self.settings['dns_upstream'], 53))
                        answer, _ = upstream.recvfrom(4096)
                else:
                    self.event('已接收净化器的联网请求：' + name)
                listener.sendto(answer, peer)
            except (ValueError, OSError, UnicodeError):
                continue

    def accept_control(self, listener):
        while not self.stop_event.is_set():
            try:
                conn, peer = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            if not self.allowed(peer[0]):
                conn.close()
                continue
            threading.Thread(target=self.read_control, args=(conn, peer), daemon=True).start()

    def read_control(self, conn, peer):
        decoder = Frames()
        conn.settimeout(2)
        with self.lock:
            old = self.client
            self.client = conn
            self.state.update(connected=True, message='设备已连接，等待状态')
        if old and old is not conn:
            old.close()
        self.event('净化器已连接')
        try:
            with conn:
                while not self.stop_event.is_set():
                    try:
                        data = conn.recv(4096)
                    except socket.timeout:
                        continue
                    if not data:
                        break
                    for header, message in decoder.feed(data):
                        datatype = message.get('datatype')
                        payload = message.get('data')
                        with self.condition:
                            if len(header) == 28:
                                self.header = header
                                if self.settings.get('control_header') != header.hex():
                                    self.settings['control_header'] = header.hex()
                                    self.save()
                            if datatype == 'mode' and isinstance(payload, dict):
                                values = {}
                                for key in ('speed', 'mode'):
                                    try:
                                        values[key] = int(payload[key])
                                    except (KeyError, TypeError, ValueError):
                                        pass
                                self.state.update(values)
                                self.state['last_seen'] = time.time()
                                self.state['state_cached'] = False
                                if self.state['mode'] is not None and self.state['speed'] is not None:
                                    cache = {k: self.state[k] for k in ('mode', 'speed', 'last_seen')}
                                    cache['device_mac'] = self.settings['device_mac']
                                    temporary = self.root / 'last-state.tmp'
                                    temporary.write_text(json.dumps(cache), 'utf-8')
                                    temporary.replace(self.root / 'last-state.json')
                                if values.get('mode') == 2 and 30 <= values.get('speed', -1) <= 85:
                                    if self.settings['manual_speed'] != values['speed']:
                                        self.settings['manual_speed'] = values['speed']
                                        self.save()
                                target = self.pending_target
                                if not target or all(self.state.get(k) == v for k, v in target.items()):
                                    self.state['message'] = '运行状态已同步'
                                    self.state['command_pending'] = False
                                    self.pending_target = None
                                self.condition.notify_all()
                        # Record only business state, never Wi-Fi credentials.
                        self.event('设备上报：' + json.dumps({'datatype': datatype,
                                   'data': payload if datatype == 'mode' else None}, ensure_ascii=False))
                        logging.debug('RX envelope %s', header.hex())
        except (OSError, ValueError):
            pass
        finally:
            with self.lock:
                if self.client is conn:
                    self.client = None
                    self.state.update(connected=False, message='设备已断开，等待重新连接')
            self.event('净化器连接结束')

    def send(self, speed=None, mode=None):
        with self.lock:
            if not self.client:
                raise RuntimeError('净化器尚未连接，请先完成本机连接设置')
            if self.header is None:
                raise RuntimeError('首次使用需要设备主动上报：请给净化器断电再通电，等待状态同步')
            # Validate the caller's input before resolving a preset.
            control_frame(speed, mode)
            power_on = mode == 1
            if power_on and speed is None:
                speed = self.settings['manual_speed']
            speed = preset_speed(mode, speed, self.settings['manual_speed'])
            frame = control_frame(speed, mode, self.header, self.settings['device_mac'])
            try:
                self.client.sendall(frame)
            except OSError:
                self.state.update(connected=False, command_pending=False, message='连接已断开，等待重新连接')
                raise RuntimeError('设备连接已断开，请等待重新连接后再试') from None
            self.pending_target = {}
            if speed is not None:
                self.pending_target['speed'] = speed
            if mode is not None:
                self.pending_target['mode'] = 2 if power_on else mode
            self.pending_since = time.monotonic()
            unchanged = (not self.state['state_cached'] and self.pending_target
                         and all(self.state.get(k) == v for k, v in self.pending_target.items()))
            self.state.update(command_pending=not bool(unchanged), message=(
                '指令已发送，设定值与最近回报一致' if unchanged else '指令已发送，等待设备确认'))
        self.event(f'发送控制：风量={speed}，模式={mode}')

    def accept_tls(self, listener):
        while not self.stop_event.is_set():
            try:
                conn, peer = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            if not self.allowed(peer[0]):
                conn.close()
                continue
            threading.Thread(target=self.serve_tls, args=(conn,), daemon=True).start()

    def serve_tls(self, raw):
        try:
            raw.settimeout(5)
            with self.tls_context.wrap_socket(raw, server_side=True) as conn:
                request = bytearray()
                while b'\r\n\r\n' not in request and len(request) < 8192:
                    chunk = conn.recv(2048)
                    if not chunk:
                        break
                    request.extend(chunk)
                first = bytes(request).split(b'\r\n', 1)[0].decode('ascii', 'replace')
                path = first.split(' ')[1] if ' ' in first else ''
                if path.startswith('/device/active?'):
                    body = {'device_id': self.settings['device_mac']}
                    with self.lock:
                        self.state['activation'] = True
                    self.event('已完成本地联网握手')
                elif path.startswith('/aircleanerfirmware/checkUpdate'):
                    body = {'ver': 'v1.47', 'enforce': False}
                else:
                    body = {}
                data = json.dumps(body, separators=(',', ':')).encode()
                conn.sendall(b'HTTP/1.0 200 OK\r\nContent-Type: application/json\r\nContent-Length: '
                             + str(len(data)).encode() + b'\r\nConnection: close\r\n\r\n' + data)
        except (OSError, ssl.SSLError):
            raw.close()
            self.event('收到联网握手请求，等待设备重试')

    def inspect(self):
        identity = device_config(self.settings['device_ip'])
        if identity.get('PO') != 'com.phicomm.basic' or identity.get('FW') != 'v1.47':
            raise RuntimeError('当前仅支持已核对的原厂 A1 v1.47')
        if self.settings['device_mac'][-6:].upper() not in identity.get('N', '').upper():
            raise RuntimeError('设备 MAC 后缀不匹配，停止修改联网设置')
        with self.lock:
            self.state['identity'] = {k: identity.get(k) for k in ('N', 'HD', 'FW', 'RF')}
        return self.state['identity']

    def configure_device(self):
        self.inspect()
        s = self.settings
        backup = {'device_ip': s['device_ip'], 'device_mac': s['device_mac'],
                  'restore': {'DHCP': True, 'DNS Server': s['dns_upstream']},
                  'note': 'Wi-Fi was provisioned with DHCP; credentials are untouched.'}
        (self.root / 'network-restore.json').write_text(json.dumps(backup, indent=2), 'utf-8')
        result = device_config(s['device_ip'], {'DHCP': False, 'IP address': s['device_ip'],
                               'Net Mask': s['netmask'], 'Gateway': s['gateway'],
                               'DNS Server': s['server_ip']})
        self.settings['network_configured'] = True
        self.save()
        self.event('已设置本机连接，等待净化器重新联网')
        return result

    def restore_device(self):
        self.inspect()
        result = device_config(self.settings['device_ip'], {'DHCP': True,
                               'DNS Server': self.settings['dns_upstream']})
        self.settings['network_configured'] = False
        self.save()
        self.event('已恢复自动获取网络地址')
        return result

    def close(self):
        self.stop_event.set()
        for listener in self.listeners:
            listener.close()
        if self.client:
            self.client.close()
