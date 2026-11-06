# SPDX-License-Identifier: GPL-3.0-only
"""Windows desktop control panel for a stock Phicomm A1."""
from __future__ import annotations
import ctypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

from backend import Controller, validate_settings
from ir_remote import IRRemote, show_remote_window
from setup_dialog import ask_settings

BG = '#F3F6F3'
CARD = '#FFFFFF'
INK = '#173B30'
MUTED = '#74847B'
GREEN = '#176A4B'
PALE = '#E7F3EC'
LINE = '#DCE5DF'
FONT = 'Microsoft YaHei UI'


class App:
    def __init__(self, root, controller):
        self.root, self.controller = root, controller
        self.editing = False
        self.busy = False
        self.log_window = None
        self.remote_window = None
        self.remote = IRRemote(controller)
        self.last_state = None
        root.title('A1 净化器控制台')
        root.geometry('1060x940')
        root.minsize(1000, 880)
        root.configure(bg=BG)
        root.option_add('*Font', (FONT, 10))
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TScale', background=CARD, troughcolor=PALE)
        style.configure('TEntry', padding=8, fieldbackground=CARD)
        container = tk.Frame(root, bg=BG)
        container.pack(fill='both', expand=True, padx=34, pady=26)
        top = tk.Frame(container, bg=BG)
        top.pack(fill='x')
        tk.Label(top, text='A1', font=(FONT, 28, 'bold'), fg=INK, bg=BG).pack(side='left')
        titles = tk.Frame(top, bg=BG)
        titles.pack(side='left', padx=16)
        tk.Label(titles, text='净化器控制台', font=(FONT, 17, 'bold'), fg=INK, bg=BG).pack(anchor='w')
        tk.Label(titles, text='斐讯悟净 A1 · 本机控制', fg=MUTED, bg=BG).pack(anchor='w', pady=(4, 0))
        self.badge = tk.Label(top, text='● 等待连接', fg=MUTED, bg=PALE, padx=14, pady=9)
        self.badge.pack(side='right')

        main = tk.Frame(container, bg=BG)
        main.pack(fill='both', expand=True, pady=(26, 18))
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)
        left = self.card(main)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 10))
        right = self.card(main)
        right.grid(row=0, column=1, sticky='nsew', padx=(10, 0))
        tk.Label(left, text='当前运行状态', font=(FONT, 12, 'bold'), fg=INK, bg=CARD).pack(anchor='w', padx=24, pady=(22, 0))
        self.gauge = tk.Canvas(left, width=315, height=270, bg=CARD, highlightthickness=0)
        self.gauge.pack(pady=(5, 0))
        self.mode_text = tk.Label(left, text='尚未连接', font=(FONT, 15, 'bold'), fg=INK, bg=CARD)
        self.mode_text.pack(pady=(0, 8))
        self.updated = tk.Label(left, text='连接后显示设备实际状态', fg=MUTED, bg=CARD)
        self.updated.pack()
        self.message = tk.Label(left, text='等待净化器连接', fg=MUTED, bg=CARD,
                                wraplength=310, justify='center')
        self.message.pack(padx=20, pady=18)

        tk.Label(right, text='设备控制', font=(FONT, 12, 'bold'), fg=INK, bg=CARD).pack(anchor='w', padx=24, pady=(22, 15))
        power = tk.Frame(right, bg=CARD)
        power.pack(fill='x', padx=24)
        self.on_button = self.button(power, '开启净化', lambda: self.control(mode=1), primary=True)
        self.on_button.pack(side='left', fill='x', expand=True, padx=(0, 6))
        self.off_button = self.button(power, '关闭', lambda: self.control(mode=0))
        self.off_button.pack(side='left', fill='x', expand=True, padx=(6, 0))
        tk.Frame(right, bg=LINE, height=1).pack(fill='x', padx=24, pady=24)
        tk.Label(right, text='运行模式', fg=MUTED, bg=CARD).pack(anchor='w', padx=24)
        modes = tk.Frame(right, bg=CARD)
        modes.pack(fill='x', padx=24, pady=(10, 20))
        self.mode_buttons = {}
        for mode, label in [(2, '日常'), (4, '睡眠'), (5, '强劲')]:
            button = self.button(modes, label, lambda m=mode: self.control(mode=m))
            button.pack(side='left', fill='x', expand=True, padx=(0, 6))
            self.mode_buttons[mode] = button
        wind = tk.Frame(right, bg=CARD)
        wind.pack(fill='x', padx=24)
        tk.Label(wind, text='手动风速设定', fg=MUTED, bg=CARD).pack(side='left')
        self.wind_value = tk.Label(wind, text='—', fg=GREEN, bg=CARD, font=(FONT, 12, 'bold'))
        self.wind_value.pack(side='right')
        self.speed = tk.DoubleVar(value=self.controller.settings['manual_speed'])
        self.scale = ttk.Scale(right, from_=30, to=85, orient='horizontal', variable=self.speed,
                               command=lambda value: self.wind_value.config(text=f'{float(value):.0f}'))
        self.scale.pack(fill='x', padx=24, pady=14)
        self.scale.bind('<ButtonPress-1>', lambda e: setattr(self, 'editing', True))
        self.scale.bind('<ButtonRelease-1>', self.speed_released)
        self.scale.bind('<KeyPress>', lambda e: setattr(self, 'editing', True))
        self.scale.bind('<KeyRelease>', self.speed_released)
        labels = tk.Frame(right, bg=CARD)
        labels.pack(fill='x', padx=24)
        tk.Label(labels, text='30 · 最低档', fg=MUTED, bg=CARD, font=(FONT, 9)).pack(side='left')
        tk.Label(labels, text='85 · 最高档', fg=MUTED, bg=CARD, font=(FONT, 9)).pack(side='right')
        self.apply_button = self.button(right, '应用风速', self.apply_speed)
        self.apply_button.pack(fill='x', padx=24, pady=(20, 10))
        tk.Label(right, text='日常记忆手动风速 · 睡眠 30 · 强劲 85', fg=MUTED, bg=CARD, font=(FONT, 9)).pack(pady=(0, 20))

        bottom = self.card(container)
        bottom.pack(fill='x')
        row = tk.Frame(bottom, bg=CARD)
        row.pack(fill='x', padx=22, pady=18)
        info = tk.Frame(row, bg=CARD)
        info.pack(side='left')
        tk.Label(info, text='设备连接', font=(FONT, 10, 'bold'), fg=INK, bg=CARD).pack(anchor='w')
        self.address = tk.Label(info, text='', fg=MUTED, bg=CARD, font=(FONT, 9))
        self.address.pack(anchor='w', pady=(4, 0))
        self.button(row, '连接设置', self.settings).pack(side='right', padx=(8, 0))
        self.button(row, '红外遥控', self.show_remote).pack(side='right', padx=(8, 0))
        self.button(row, '查看记录', self.show_log).pack(side='right')
        footer = tk.Frame(container, bg=BG)
        footer.pack(fill='x', pady=(15, 0))
        tk.Label(footer, text='保留此软件运行，即可持续控制净化器', fg=MUTED, bg=BG, font=(FONT, 9)).pack(side='left')
        tk.Label(footer, text='原厂固件 · 无需拆机', fg=MUTED, bg=BG, font=(FONT, 9)).pack(side='right')
        root.protocol('WM_DELETE_WINDOW', self.close)
        if self.remote.path.exists():
            try:
                self.remote.start()
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.controller.event(f'红外遥控服务未启动：{exc}')
        self.refresh()

    def card(self, parent):
        return tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)

    def button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, relief='flat', bd=0,
                         bg=GREEN if primary else PALE, fg='white' if primary else GREEN,
                         activebackground='#14583F' if primary else '#D3EADD',
                         activeforeground='white' if primary else GREEN,
                         disabledforeground='#A5B1A9', cursor='hand2', padx=15, pady=11,
                         font=(FONT, 10, 'bold'))

    def draw_gauge(self, speed, on):
        c = self.gauge
        c.delete('all')
        c.create_oval(50, 30, 265, 245, outline=PALE, width=16)
        if speed is not None and on:
            c.create_arc(50, 30, 265, 245, start=90, extent=-max(2, speed / 85 * 359.9),
                         style='arc', outline=GREEN, width=16)
        c.create_text(158, 118, text='—' if speed is None else f'{speed:.0f}',
                      fill=INK if on else MUTED, font=(FONT, 45, 'bold'))
        c.create_text(158, 168, text='风速设定 · 30–85', fill=MUTED, font=(FONT, 10))

    def refresh(self):
        s = self.controller.snapshot()
        connected = s['connected']
        # Stock A1 reports state changes, rather than a periodic state heartbeat.
        ready = bool(connected)
        has_state = ready and s['mode'] is not None
        mode, speed = s['mode'], s['speed']
        on = mode is not None and mode != 0
        self.badge.config(text='● 已连接' if ready else '● 等待连接',
                          fg=GREEN if ready else MUTED)
        self.mode_text.config(text={0: '已关闭', 1: '运行中', 2: '日常净化', 4: '睡眠模式',
                                    5: '强劲模式'}.get(mode, '尚未连接'))
        if not connected:
            self.mode_text.config(text='尚未连接')
        elif mode is None:
            self.mode_text.config(text='等待状态同步')
        elif s.get('state_cached'):
            self.mode_text.config(text='上次：' + {0: '已关闭', 1: '运行中', 2: '日常净化',
                                               4: '睡眠模式', 5: '强劲模式'}.get(mode, '未知'))
        self.draw_gauge(speed if has_state else None, on and has_state and not s.get('state_cached'))
        self.updated.config(text=(('上次回报于 ' if s.get('state_cached') else '状态更新于 ')
                                  + time.strftime('%H:%M:%S', time.localtime(s['last_seen'])))
                            if s['last_seen'] else '连接后显示设备实际状态')
        self.message.config(text=s['message'])
        for button in [self.on_button, self.off_button, self.apply_button, *self.mode_buttons.values()]:
            button.config(state='normal' if ready and not self.busy and not s['command_pending'] else 'disabled')
        self.scale.config(state='normal' if ready and not self.busy and not s['command_pending'] else 'disabled')
        for key, button in self.mode_buttons.items():
            button.config(bg=GREEN if key == mode and ready else PALE,
                          fg='white' if key == mode and ready else GREEN)
        if not self.editing and speed is not None and not s['command_pending']:
            self.speed.set(speed)
            self.wind_value.config(text=f'{speed:.0f}')
        self.address.config(text=f"净化器 {s['settings']['device_ip']}    ·    电脑 {s['settings']['server_ip']}")
        self.last_state = s
        self.root.after(700, self.refresh)

    def run(self, action, success=None):
        if self.busy:
            return
        self.busy = True
        def work():
            try:
                result = action()
            except Exception as exc:
                error = str(exc)
                self.root.after(0, lambda: messagebox.showerror('操作未完成', error, parent=self.root))
            else:
                if success:
                    self.root.after(0, lambda: success(result))
            finally:
                self.busy = False
        threading.Thread(target=work, daemon=True).start()

    def control(self, **values):
        self.run(lambda: self.controller.send(**values))

    def speed_released(self, event=None):
        self.editing = False
        self.apply_speed()

    def apply_speed(self):
        if self.controller.snapshot()['command_pending']:
            return
        self.control(speed=round(self.speed.get()), mode=2)

    def settings(self):
        window = tk.Toplevel(self.root)
        window.title('连接设置')
        window.geometry('620x600')
        window.resizable(False, False)
        window.configure(bg=BG)
        body = tk.Frame(window, bg=BG)
        body.pack(fill='both', expand=True, padx=26, pady=22)
        tk.Label(body, text='连接你的 A1', font=(FONT, 17, 'bold'), fg=INK, bg=BG).pack(anchor='w')
        tk.Label(body, text='首次设置后，净化器会自动连接本软件。', fg=MUTED, bg=BG).pack(anchor='w', pady=(8, 18))
        entries = {}
        for key, title in [('device_ip', '净化器 IP'), ('server_ip', '电脑 IP'), ('gateway', '路由器 IP')]:
            row = tk.Frame(body, bg=BG)
            row.pack(fill='x', pady=6)
            tk.Label(row, text=title, width=12, anchor='w', fg=INK, bg=BG).pack(side='left')
            variable = tk.StringVar(value=self.controller.settings[key])
            ttk.Entry(row, textvariable=variable, state='readonly').pack(side='left', fill='x', expand=True)
            entries[key] = variable
        def configure():
            values = {k: v.get().strip() for k, v in entries.items()}
            if any(values[k] != self.controller.settings[k] for k in values):
                messagebox.showinfo('地址有变化', '当前版本已针对本机地址配置。请先恢复自动联网，再由维护人员调整连接地址。', parent=window)
                return
            self.run(self.controller.configure_device,
                     lambda r: messagebox.showinfo('设置已提交', '等待约半分钟，设备会自动重新连接。', parent=window))
        self.button(body, '连接到这台电脑', configure, primary=True).pack(fill='x', pady=(22, 8))
        self.button(body, '恢复自动联网', lambda: self.run(self.controller.restore_device,
                    lambda r: messagebox.showinfo('已恢复', '设备将恢复自动获取网络地址。本机控制会暂时断开。', parent=window))).pack(fill='x')
        def edit():
            changed = ask_settings(self.root, self.controller.settings,
                                   title='修改连接参数', save_label='保存并关闭软件')
            if changed is None:
                return
            self.controller.config_path.write_text(json.dumps(changed, ensure_ascii=False, indent=2), 'utf-8')
            messagebox.showinfo('已保存', '重新打开软件后使用新连接参数。', parent=window)
            self.controller.close()
            self.root.destroy()
        self.button(body, '修改设备与网络参数', edit).pack(fill='x', pady=(10, 0))
        tk.Label(body, text='恢复操作保留 Wi-Fi 名称与密码。', fg=MUTED, bg=BG, font=(FONT, 9)).pack(pady=12)

    def show_remote(self):
        if self.remote_window and self.remote_window.winfo_exists():
            self.remote_window.lift()
            return
        try:
            self.remote.start()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror('红外遥控服务未启动', str(exc), parent=self.root)
            return
        sketch = Path(__file__).parent / 'firmware' / 'a1_ir_remote'
        self.remote_window = show_remote_window(self.root, self.remote, sketch)

    def show_log(self):
        if self.log_window and self.log_window.winfo_exists():
            self.log_window.lift()
            return
        self.log_window = tk.Toplevel(self.root)
        self.log_window.title('连接记录')
        self.log_window.geometry('760x420')
        text = tk.Text(self.log_window, bg='#F8FAF8', fg=INK, padx=18, pady=18,
                       font=(FONT, 10), relief='flat', wrap='word')
        text.pack(fill='both', expand=True)
        def update():
            if not self.log_window.winfo_exists():
                return
            content = '\n'.join(f"{e['time']}  {e['text']}" for e in self.controller.snapshot()['events'])
            if text.get('1.0', 'end-1c') != content:
                text.config(state='normal')
                text.delete('1.0', 'end')
                text.insert('1.0', content)
                text.config(state='disabled')
                text.see('end')
            self.log_window.after(1200, update)
        update()

    def close(self):
        if not messagebox.askyesno('退出控制台', '退出后将暂停电脑控制，净化器会继续按当前设置运行。\n\n现在退出吗？', parent=self.root):
            return
        self.controller.close()
        self.root.destroy()


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    folder = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    data = folder / ('data' if getattr(sys, 'frozen', False) else 'runtime')
    data.mkdir(exist_ok=True)
    handler = RotatingFileHandler(data / 'controller.log', maxBytes=1_000_000, backupCount=2, encoding='utf-8')
    logging.basicConfig(handlers=[handler], level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    root = tk.Tk()
    root.withdraw()
    controller = Controller(data)
    try:
        validate_settings(controller.settings)
    except ValueError:
        configured = ask_settings(root, controller.settings)
        if configured is None:
            root.destroy()
            return
        controller.settings = configured
        controller.save()
    try:
        controller.start()
    except (OSError, ValueError) as exc:
        messagebox.showerror('无法启动控制台', '控制服务未能启动。请确认没有重复打开软件，电脑 IP 未发生变化。\n\n' + str(exc), parent=root)
        root.destroy()
        return
    root.deiconify()
    app = App(root, controller)
    try:
        root.mainloop()
    finally:
        app.remote.close()


if __name__ == '__main__':
    main()
