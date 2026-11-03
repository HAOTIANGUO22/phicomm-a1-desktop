# SPDX-License-Identifier: GPL-3.0-only
"""First-run configuration. All fields are supplied locally by the operator."""
import socket
import tkinter as tk
from tkinter import ttk, messagebox
from backend import validate_settings

FIELDS = [('device_ip', '净化器 IP'), ('device_mac', '净化器 MAC'),
          ('server_ip', '电脑 IP'), ('gateway', '路由器 IP'),
          ('netmask', '子网掩码'), ('dns_upstream', '上游 DNS（可留空）')]


def ask_settings(root, settings, title='首次连接设置', save_label='保存设置'):
    window = tk.Toplevel(root)
    window.title(title)
    window.geometry('670x610')
    window.minsize(650, 580)
    window.configure(bg='#F3F6F3')
    if root.winfo_viewable():
        window.transient(root)
    body = tk.Frame(window, bg='#F3F6F3')
    body.pack(fill='both', expand=True, padx=28, pady=22)
    font = 'Microsoft YaHei UI'
    tk.Label(body, text=title, font=(font, 18, 'bold'), fg='#173B30', bg='#F3F6F3').pack(anchor='w')
    tk.Label(body, text='从路由器客户端列表取得设备地址与 MAC。\n这些信息仅保存在本机，不随源码分发。',
             justify='left', font=(font, 10), fg='#74847B', bg='#F3F6F3').pack(anchor='w', pady=(8, 18))
    variables = {}
    for key, label in FIELDS:
        row = tk.Frame(body, bg='#F3F6F3')
        row.pack(fill='x', pady=7)
        tk.Label(row, text=label, anchor='w', width=19, bg='#F3F6F3', fg='#173B30', font=(font, 10)).pack(side='left')
        variable = tk.StringVar(value=settings.get(key, ''))
        ttk.Entry(row, textvariable=variable, font=(font, 10)).pack(side='left', fill='x', expand=True)
        variables[key] = variable
    def detect_ip():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
                route.connect((variables['device_ip'].get().strip(), 8000))
                variables['server_ip'].set(route.getsockname()[0])
        except OSError:
            messagebox.showerror('无法确定地址', '请先填写净化器 IP，并确认电脑已连接家庭网络。', parent=window)
    ttk.Button(body, text='按净化器地址确定本机 IP', command=detect_ip).pack(anchor='e', pady=(8, 14))
    result = []
    def save():
        try:
            values = {**settings, **{k: v.get().strip() for k, v in variables.items()}}
            checked = validate_settings(values)
        except ValueError as exc:
            messagebox.showerror('请检查连接信息', str(exc), parent=window)
            return
        if checked['device_mac'] != settings.get('device_mac'):
            checked.pop('control_header', None)
        result.append(checked)
        window.destroy()
    ttk.Button(body, text=save_label, command=save).pack(fill='x', pady=6)
    ttk.Button(body, text='取消', command=window.destroy).pack(fill='x', pady=6)
    window.grab_set()
    root.wait_window(window)
    return result[0] if result else None
