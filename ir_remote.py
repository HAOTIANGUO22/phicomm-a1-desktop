# SPDX-License-Identifier: GPL-3.0-only
"""Receive learned infrared keys from an ESP32 and drive the local A1 controller."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import re
import secrets
import threading
import time
from tkinter import filedialog, messagebox, simpledialog, ttk
import tkinter as tk


PORT = 8765
IR_CODE = re.compile(r'[A-Za-z0-9_+./ -]{1,40}:[0-9A-F]{4}:[0-9A-F]{4}')
ACTIONS = {
    '1': ('开启净化', 1),
    '0': ('关闭净化', 0),
    '2': ('日常模式', 2),
    '3': ('睡眠模式', 4),
    '4': ('强劲模式', 5),
    '↑': ('风速 +5', None),
    '↓': ('风速 −5', None),
}


class IRRequest(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(2)
        super().setup()

    def log_message(self, *_):
        pass

    def do_POST(self):
        remote = self.server.remote
        if self.path != '/ir':
            self.send_error(404)
            return
        auth = self.headers.get('Authorization', '').encode('latin-1')
        if not hmac.compare_digest(auth, f'Bearer {remote.token}'.encode('ascii')):
            self.send_error(401)
            return
        length = self.headers.get('Content-Length', '')
        if not re.fullmatch(r'[1-9][0-9]?', length) or int(length) > 63:
            self.send_error(400)
            return
        body = self.rfile.read(int(length))
        code = body.decode('ascii', 'replace')
        if len(body) != int(length) or not IR_CODE.fullmatch(code):
            self.send_error(400)
            return
        self.send_response(remote.receive(code))
        self.end_headers()


class IRRemote:
    def __init__(self, controller):
        self.controller = controller
        self.path = controller.root / 'ir-remote.json'
        self.lock = threading.Lock()
        self.server = None
        self.token = ''
        self.keys = {}
        self.learning = None
        self.last_code = ''
        self.last_time = 0
        self.message = '等待遥控器按键'

    @property
    def url(self):
        return f"http://{self.controller.settings['server_ip']}:{PORT}/ir"

    def save(self, keys):
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'token': self.token, 'keys': keys}, ensure_ascii=False, indent=2),
                             encoding='utf-8')
        temporary.replace(self.path)

    def start(self, port=PORT):
        if self.server:
            return
        if self.path.exists():
            config = json.loads(self.path.read_text(encoding='utf-8'))
            self.token = config['token']
            self.keys = config['keys']
            if (not isinstance(self.token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,}', self.token)
                    or not isinstance(self.keys, dict)
                    or any(key not in ACTIONS or not isinstance(code, str) or not IR_CODE.fullmatch(code)
                           for key, code in self.keys.items())
                    or len(set(self.keys.values())) != len(self.keys)):
                raise ValueError('红外遥控配置格式有误')
        else:
            self.token = secrets.token_urlsafe(32)

        server = ThreadingHTTPServer((self.controller.settings['server_ip'], port), IRRequest)
        server.remote = self
        try:
            if not self.path.exists():
                self.save(self.keys)
        except OSError:
            server.server_close()
            raise
        self.server = server
        threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True).start()

    def close(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

    def learn(self, button):
        with self.lock:
            self.learning = button
            self.message = f'请对准接收头短按遥控器上的 {button}' if button else '已退出按键学习'

    def receive(self, code):
        now = time.monotonic()
        with self.lock:
            if self.last_code == code and now - self.last_time < 0.25:
                self.last_time = now
                return 204
            self.last_code, self.last_time = code, now
            button = next((key for key, value in self.keys.items() if value == code), None)
            if self.learning:
                if button is not None and button != self.learning:
                    self.message = f'这枚按键已绑定到 {button}，请按 {self.learning}'
                    return 409
                keys = {**self.keys, self.learning: code}
                try:
                    self.save(keys)
                except OSError as exc:
                    self.message = f'无法保存按键配置：{exc}'
                    return 500
                self.keys = keys
                self.message = f'已学习 {self.learning} · {code}'
                self.learning = None
                return 204
            if button is None:
                self.message = f'收到未绑定按键 · {code}'
                return 204

        name, mode = ACTIONS[button]
        try:
            with self.controller.lock:
                state = self.controller.snapshot()
                if state['command_pending']:
                    raise RuntimeError('上一条指令正在等待净化器确认')
                if mode is None:
                    if not state['connected'] or state['state_cached'] or state['mode'] in (None, 0) or state['speed'] is None:
                        raise RuntimeError('请先开机并等待风速同步')
                    delta = 5 if button == '↑' else -5
                    speed = max(30, min(85, state['speed'] + delta))
                    self.controller.send(speed=speed, mode=2)
                else:
                    self.controller.send(mode=mode)
        except RuntimeError as exc:
            status, detail = 409, str(exc)
        else:
            status, detail = 202, '已发往净化器，结果见主界面'
        message = f'{button} · {name} · {detail}'
        with self.lock:
            self.message = message
        self.controller.event('红外遥控：' + message)
        return status


def export_firmware_config(parent, remote, sketch):
    ssid = simpledialog.askstring('ESP32 配网', '输入 2.4 GHz Wi-Fi 名称', parent=parent)
    if ssid is None:
        return
    if not 1 <= len(ssid.encode('utf-8')) <= 32 or '\0' in ssid:
        messagebox.showerror('Wi-Fi 名称无效', '名称长度应为 1–32 字节。', parent=parent)
        return
    password = simpledialog.askstring('ESP32 配网', '输入 Wi-Fi 密码', show='*', parent=parent)
    if password is None:
        return
    path = filedialog.asksaveasfilename(parent=parent, title='保存到 a1_ir_remote.ino 同一目录',
                                        initialdir=sketch if sketch.is_dir() else None,
                                        initialfile='config.h', defaultextension='.h')
    if not path:
        return
    settings = {'WIFI_SSID': ssid, 'WIFI_PASSWORD': password, 'BRIDGE_URL': remote.url, 'BRIDGE_TOKEN': remote.token}
    # Encode the input as UTF-8 bytes without requiring C++ string escaping by the user.
    lines = ['#pragma once', '']
    for key, value in settings.items():
        literal = ''.join(f'\\{byte:03o}' for byte in value.encode('utf-8'))
        lines.append(f'constexpr char {key}[] = "{literal}";')
    try:
        with open(path, 'w', encoding='ascii') as handle:
            handle.write('\n'.join(lines) + '\n')
    except OSError as exc:
        messagebox.showerror('无法保存配网文件', str(exc), parent=parent)
        return
    messagebox.showinfo('配网文件已生成', '请重新编译并烧录 ESP32。', parent=parent)


def show_remote_window(parent, remote, sketch):
    window = tk.Toplevel(parent)
    window.title('A1 红外遥控')
    window.resizable(False, False)
    body = ttk.Frame(window, padding=18)
    body.pack(fill='both', expand=True)
    ttk.Label(body, text=f'ESP32 接收端  {remote.url}').grid(row=0, columnspan=3, sticky='w')
    ttk.Button(body, text='生成 ESP32 配网文件', command=lambda: export_firmware_config(window, remote, sketch)).grid(
        row=1, columnspan=3, sticky='w', pady=8)
    labels = {}
    for row, (button, (name, _)) in enumerate(ACTIONS.items(), start=2):
        ttk.Label(body, text=f'{button}  {name}', width=16).grid(row=row, column=0, sticky='w', pady=3)
        label = labels[button] = ttk.Label(body, width=28)
        label.grid(row=row, column=1, sticky='w')
        ttk.Button(body, text='学习', command=lambda key=button: remote.learn(key)).grid(row=row, column=2, padx=(8, 0))
    ttk.Button(body, text='取消学习', command=lambda: remote.learn(None)).grid(row=9, column=2, pady=(10, 0))
    status = ttk.Label(body, wraplength=390)
    status.grid(row=10, columnspan=3, sticky='w', pady=(10, 0))

    def refresh():
        with remote.lock:
            for key, label in labels.items():
                label.config(text=remote.keys.get(key, '未学习'))
            status.config(text=remote.message)
        window.after(250, refresh)

    def close():
        remote.learn(None)
        window.destroy()

    window.protocol('WM_DELETE_WINDOW', close)
    refresh()
    return window
