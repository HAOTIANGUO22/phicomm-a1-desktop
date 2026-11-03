# SPDX-License-Identifier: GPL-3.0-only
"""Double-click Windows EasyLink provisioning application."""
from __future__ import annotations
import ctypes
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from provisioning import Provisioner, discover
from windows_wifi import WindowsWifi, WifiError, subnet_for

BG, CARD, INK, MUTED, GREEN, PALE, LINE = '#F3F6F3', '#FFFFFF', '#173B30', '#74847B', '#176A4B', '#E7F3EC', '#DCE5DF'
FONT = 'Microsoft YaHei UI'


class ProvisionApp:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.adapters = []
        self.busy = False
        self.cancel = threading.Event()
        self.job_id = 0
        root.title('A1 自动配网')
        root.geometry('1100x980')
        root.minsize(1020, 720)
        root.configure(bg=BG)
        root.option_add('*Font', (FONT, 10))
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('A1.Horizontal.TProgressbar', background=GREEN, troughcolor=PALE)
        style.configure('Treeview', rowheight=34, font=(FONT, 9), background=CARD, fieldbackground=CARD)
        style.configure('Treeview.Heading', font=(FONT, 9, 'bold'))
        # Keep every control reachable on smaller displays and at high DPI.
        viewport = tk.Canvas(root, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(root, orient='vertical', command=viewport.yview)
        viewport.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        viewport.pack(side='left', fill='both', expand=True)
        outer = tk.Frame(viewport, bg=BG)
        content = viewport.create_window((0, 0), window=outer, anchor='nw')
        outer.bind('<Configure>', lambda e: viewport.configure(scrollregion=viewport.bbox('all')))
        viewport.bind('<Configure>', lambda e: viewport.itemconfigure(content, width=e.width))
        def wheel(event):
            if not isinstance(event.widget, (ttk.Combobox, ttk.Treeview)):
                viewport.yview_scroll(-int(event.delta / 120), 'units')
        root.bind('<MouseWheel>', wheel)
        inner = tk.Frame(outer, bg=BG)
        inner.pack(fill='both', expand=True, padx=30, pady=24)
        outer = inner
        header = tk.Frame(outer, bg=BG)
        header.pack(fill='x')
        tk.Label(header, text='A1', fg=INK, bg=BG, font=(FONT, 29, 'bold')).pack(side='left')
        title = tk.Frame(header, bg=BG)
        title.pack(side='left', padx=18)
        tk.Label(title, text='自动配网', fg=INK, bg=BG, font=(FONT, 20, 'bold')).pack(anchor='w')
        tk.Label(title, text='Windows · 原厂 A1 · 无需手机 App', fg=MUTED, bg=BG).pack(anchor='w', pady=(4, 0))
        self.badge = tk.Label(header, text='● 检测网络', fg=GREEN, bg=PALE, padx=14, pady=9)
        self.badge.pack(side='right')
        steps = tk.Frame(outer, bg=BG)
        steps.pack(fill='x', pady=(24, 18))
        for number, text in [('01', '选择家庭 Wi-Fi'), ('02', '按一下机身 Wi-Fi 键'), ('03', '自动验证设备')]:
            item = tk.Frame(steps, bg=BG)
            item.pack(side='left', fill='x', expand=True)
            tk.Label(item, text=number, fg=GREEN, bg=PALE, font=(FONT, 11, 'bold'), padx=9, pady=5).pack(side='left')
            tk.Label(item, text=text, fg=INK, bg=BG, font=(FONT, 10)).pack(side='left', padx=9)
        body = tk.Frame(outer, bg=BG)
        body.pack(fill='both', expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        left, right = self.card(body), self.card(body)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 9))
        right.grid(row=0, column=1, sticky='nsew', padx=(9, 0))
        self.label(left, '家庭网络', 13, True).pack(anchor='w', padx=24, pady=(24, 18))
        self.label(left, '无线网卡', 10, False, MUTED).pack(anchor='w', padx=24)
        self.adapter_choice = tk.StringVar()
        self.adapter_combo = ttk.Combobox(left, textvariable=self.adapter_choice, state='readonly')
        self.adapter_combo.pack(fill='x', padx=24, pady=(7, 15))
        self.adapter_combo.bind('<<ComboboxSelected>>', lambda e: self.adapter_selected())
        self.label(left, '要连接的家庭 Wi-Fi', 10, False, MUTED).pack(anchor='w', padx=24)
        self.profile = tk.StringVar()
        self.profile_combo = ttk.Combobox(left, textvariable=self.profile, state='readonly')
        self.profile_combo.pack(fill='x', padx=24, pady=(7, 14))
        self.network_info = self.label(left, '正在读取无线网卡和已保存的 Wi-Fi…', 9, False, MUTED)
        self.network_info.config(wraplength=370, justify='left')
        self.network_info.pack(fill='x', padx=24, pady=(0, 16))
        self.use_saved = tk.BooleanVar(value=True)
        self.saved_check = tk.Checkbutton(left, text='使用 Windows 已保存的密码', variable=self.use_saved,
                            command=self.password_mode, bg=CARD, fg=INK, activebackground=CARD,
                            selectcolor=CARD, anchor='w', font=(FONT, 10))
        self.saved_check.pack(fill='x', padx=18)
        self.password = tk.StringVar()
        self.password_entry = ttk.Entry(left, textvariable=self.password, show='●', state='disabled')
        self.password_entry.pack(fill='x', padx=24, pady=(8, 5))
        self.label(left, '无法读取已保存密码时，可取消勾选并在此输入。', 9, False, MUTED).pack(anchor='w', padx=24)
        self.allow_unknown = tk.BooleanVar(value=False)
        self.band_check = tk.Checkbutton(left, text='频段读不到时：我已确认这是 2.4 GHz', variable=self.allow_unknown,
                           bg=CARD, fg=MUTED, activebackground=CARD, selectcolor=CARD,
                           anchor='w', font=(FONT, 9))
        self.band_check.pack(fill='x', padx=18, pady=(14, 16))
        self.start_button = self.button(left, '开始自动配网', self.start, True)
        self.start_button.pack(fill='x', padx=24, pady=(0, 10))
        self.scan_button = self.button(left, '只查找已联网的 A1', self.scan)
        self.scan_button.pack(fill='x', padx=24, pady=(0, 10))
        buttons = tk.Frame(left, bg=CARD)
        buttons.pack(fill='x', padx=24)
        self.refresh_button = self.button(buttons, '刷新网络', self.refresh)
        self.refresh_button.pack(side='left', fill='x', expand=True, padx=(0, 5))
        self.cancel_button = self.button(buttons, '停止', self.cancel_job)
        self.cancel_button.pack(side='left', fill='x', expand=True, padx=(5, 0))
        self.label(left, 'Wi-Fi 密码只在内存中使用，不保存到文件。', 9, False, MUTED).pack(padx=20, pady=(18, 14))

        self.label(right, '配网进度', 13, True).pack(anchor='w', padx=24, pady=(24, 18))
        self.phase_title = self.label(right, '先选择家庭 Wi-Fi', 18, True)
        self.phase_title.config(wraplength=370, justify='left')
        self.phase_title.pack(fill='x', padx=24)
        self.detail = self.label(right, '程序会自动检测网络，并在需要时发送配网数据。', 10, False, MUTED)
        self.detail.config(wraplength=370, justify='left')
        self.detail.pack(fill='x', padx=24, pady=(12, 20))
        self.progress = ttk.Progressbar(right, style='A1.Horizontal.TProgressbar', maximum=100)
        self.progress.pack(fill='x', padx=24, pady=(0, 16))
        tk.Frame(right, bg=LINE, height=1).pack(fill='x', padx=24, pady=(0, 20))
        self.label(right, '已验证的设备', 11, True).pack(anchor='w', padx=24, pady=(0, 12))
        self.results = ttk.Treeview(right, columns=('ip', 'mac'), show='headings', height=4)
        self.results.heading('ip', text='IP 地址')
        self.results.heading('mac', text='MAC 地址')
        self.results.column('ip', width=150, stretch=True)
        self.results.column('mac', width=195, stretch=True)
        self.results.pack(fill='x', padx=24)
        self.copy_button = self.button(right, '复制选中设备的信息', self.copy_result)
        self.copy_button.pack(fill='x', padx=24, pady=(12, 18))
        note = self.label(right, '只有读取到原厂 A1 身份后才显示联网成功。\n设备版本：原厂 v1.47。', 9, False, MUTED)
        note.config(justify='left', wraplength=370)
        note.pack(anchor='w', padx=24, pady=(0, 15))
        footer = tk.Frame(outer, bg=BG)
        footer.pack(fill='x', pady=(15, 0))
        self.button(footer, '打开 Windows Wi-Fi', self.open_wifi).pack(side='left')
        tk.Label(footer, text='2.4 GHz · 配网时保留电脑无线连接', fg=MUTED, bg=BG, font=(FONT, 9)).pack(side='right')
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.after(100, self.poll)
        self.root.after(200, self.refresh)

    def label(self, parent, text, size=10, bold=False, color=INK):
        return tk.Label(parent, text=text, bg=CARD, fg=color, font=(FONT, size, 'bold' if bold else 'normal'))

    def card(self, parent): return tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)

    def button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, relief='flat', bd=0,
                         bg=GREEN if primary else PALE, fg='white' if primary else GREEN,
                         activebackground='#14583F' if primary else '#D3EADD',
                         activeforeground='white' if primary else GREEN, disabledforeground='#A6B2AA',
                         cursor='hand2', padx=13, pady=10, font=(FONT, 10, 'bold'))

    def selected(self):
        index = self.adapter_combo.current()
        return self.adapters[index] if 0 <= index < len(self.adapters) else None

    def password_mode(self):
        self.password_entry.config(state='disabled' if self.use_saved.get() or self.busy else 'normal')
        if self.use_saved.get(): self.password.set('')

    def controls(self):
        available = bool(self.adapters)
        self.start_button.config(state='normal' if available and not self.busy else 'disabled')
        self.scan_button.config(state='normal' if available and not self.busy else 'disabled')
        self.refresh_button.config(state='disabled' if self.busy else 'normal')
        self.cancel_button.config(state='normal' if self.busy else 'disabled')
        self.adapter_combo.config(state='disabled' if self.busy else 'readonly')
        self.profile_combo.config(state='disabled' if self.busy else 'readonly')
        self.saved_check.config(state='disabled' if self.busy else 'normal')
        self.band_check.config(state='disabled' if self.busy else 'normal')
        self.copy_button.config(state='normal' if self.results.get_children() else 'disabled')
        self.password_mode()

    def job(self, action):
        if self.busy: return
        self.busy = True
        self.job_id += 1
        job_id = self.job_id
        self.cancel = threading.Event()
        self.controls()
        def notify(kind, value): self.events.put((job_id, kind, value))
        def work():
            try:
                kind, value = action(notify, self.cancel)
                notify(kind, value)
            except (WifiError, ValueError) as exc:
                notify('error', str(exc))
            except Exception:
                # Do not display raw socket destinations or exception tracebacks.
                notify('error', '操作未完成，请检查无线连接后重试。未保存 Wi-Fi 密码。')
            finally:
                notify('idle', None)
        threading.Thread(target=work, daemon=True).start()

    def refresh(self):
        self.phase_title.config(text='正在检测无线网络')
        self.detail.config(text='读取实体无线网卡、当前连接及已保存的 Wi-Fi。')
        def action(notify, cancel):
            with WindowsWifi() as wifi:
                return 'adapters', wifi.adapters()
        self.job(action)

    def adapter_selected(self):
        adapter = self.selected()
        if not adapter: return
        current = self.profile.get()
        self.profile_combo.config(values=adapter.profiles)
        self.profile.set(adapter.profile if adapter.connected else (current if current in adapter.profiles else ''))
        state = '已连接' if adapter.connected else '未连接'
        self.network_info.config(text=f'{state} · {adapter.band}\n无线 IPv4：{adapter.ip or "尚未取得"}')
        if adapter.issue: self.detail.config(text=adapter.issue)

    def start(self):
        adapter, profile = self.selected(), self.profile.get()
        if not adapter or not profile:
            messagebox.showinfo('请选择 Wi-Fi', '选择家庭 Wi-Fi；若列表没有，请先在 Windows 中连接一次，再刷新。', parent=self.root)
            return
        options = {'guid': adapter.guid, 'profile': profile, 'use_saved': self.use_saved.get(),
                   'password': self.password.get() if not self.use_saved.get() else None,
                   'allow_unknown_band': self.allow_unknown.get()}
        self.password.set('')
        self.progress['value'] = 0
        self.results.delete(*self.results.get_children())
        def action(notify, cancel):
            return 'result', Provisioner().run(cancel=cancel, notify=notify, **options)
        self.job(action)

    def scan(self):
        adapter = self.selected()
        if not adapter or not adapter.ip:
            messagebox.showinfo('尚未取得地址', '请先连接家庭 Wi-Fi，再刷新网络。', parent=self.root)
            return
        try:
            network = subnet_for(adapter.ip, adapter.prefix)
        except (WifiError, ValueError):
            messagebox.showinfo('地址尚不可用', '请先连接家庭 Wi-Fi 并取得有效地址，再刷新网络。', parent=self.root)
            return
        self.progress['value'] = 0
        self.phase_title.config(text='正在查找已联网的 A1')
        self.detail.config(text='读取局域网中的原厂身份信息，不发送配网数据。')
        def action(notify, cancel):
            devices = discover(network, cancel)
            return 'result', {'status': 'cancelled' if cancel.is_set() else ('already_online' if devices else 'not_found'),
                              'devices': devices}
        self.job(action)

    def cancel_job(self):
        self.cancel.set()
        self.detail.config(text='正在停止，请稍候。')

    def poll(self):
        try:
            while True:
                job_id, kind, value = self.events.get_nowait()
                if job_id != self.job_id: continue
                if kind == 'adapters':
                    self.adapters = value
                    self.adapter_combo.config(values=[a.name for a in value])
                    if value:
                        index = next((i for i, a in enumerate(value) if a.connected), 0)
                        self.adapter_combo.current(index)
                        self.adapter_selected()
                        self.phase_title.config(text='选择家庭 Wi-Fi 后开始')
                        self.detail.config(text='开始后自动连接网络、读取密码和查找设备。需要配网时，会提示按机身 Wi-Fi 键。')
                    else:
                        self.phase_title.config(text='没有发现实体无线网卡')
                        self.detail.config(text='请检查无线网卡、驱动和 Windows WLAN 服务。')
                    self.badge.config(text='● 等待开始')
                elif kind == 'network':
                    for i, adapter in enumerate(self.adapters):
                        if adapter.guid == value.guid: self.adapters[i] = value
                    self.adapter_selected()
                elif kind == 'phase':
                    self.phase_title.config(text=value['title'])
                    self.detail.config(text=value['detail'])
                    self.badge.config(text='● 正在处理')
                elif kind == 'progress':
                    self.progress['value'] = value['percent']
                    self.detail.config(text=value['detail'])
                elif kind == 'result':
                    self.show_result(value)
                elif kind == 'error':
                    self.phase_title.config(text='需要检查网络设置')
                    self.detail.config(text=value)
                    self.badge.config(text='● 等待处理')
                elif kind == 'idle':
                    self.busy = False
                    self.controls()
        except queue.Empty:
            pass
        self.root.after(120, self.poll)

    def show_result(self, result):
        status = result['status']
        self.results.delete(*self.results.get_children())
        for device in result.get('devices', []):
            raw = device.get('mac', '')
            mac = ':'.join(raw[i:i + 2] for i in range(0, len(raw), 2)).upper() if raw else '未读取到完整 MAC'
            self.results.insert('', 'end', values=(device['ip'], mac))
        if status in ('verified', 'already_online'):
            self.progress['value'] = 100
            self.phase_title.config(text='配网成功' if status == 'verified' else 'A1 已经联网')
            self.detail.config(text='已读取到原厂 A1 身份，可将下方设备信息用于控制台。'
                               if status == 'verified' else '找到已联网的 A1，已保留现有网络设置，可直接使用控制台。')
            self.badge.config(text='● 已验证')
            rows = self.results.get_children()
            if rows: self.results.selection_set(rows[0])
        elif status == 'cancelled':
            self.phase_title.config(text='已停止')
            self.detail.config(text='已停止发送。设备是否已经收到配置，可用“只查找已联网的 A1”确认。')
            self.badge.config(text='● 已停止')
        else:
            self.phase_title.config(text='尚未确认 A1 联网')
            self.detail.config(text='请核对 2.4 GHz、密码和按键时机，再试一轮；也可在路由器中查看设备租约。')
            self.badge.config(text='● 未确认')

    def copy_result(self):
        rows = self.results.selection()
        if not rows: return
        ip, mac = self.results.item(rows[0], 'values')
        self.root.clipboard_clear()
        self.root.clipboard_append(f'A1 IP: {ip}\nMAC: {mac}')

    def open_wifi(self):
        if os.name == 'nt': os.startfile('ms-settings:network-wifi')

    def close(self):
        if self.busy and not messagebox.askyesno('停止并退出', '正在处理网络操作，确定停止并退出吗？', parent=self.root):
            return
        self.cancel.set()
        self.root.destroy()


def main():
    try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception: pass
    root = tk.Tk()
    ProvisionApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
