# Phicomm A1 Desktop

斐讯悟净 A1 空气净化器的局域网控制项目，适配原厂固件 `v1.47`。可用 Windows 电脑控制，也可用 ESP32 提供手机网页和实体红外遥控。

| 版本 | 适合谁 | 第一步 |
| --- | --- | --- |
| **1.0 · Windows 电脑端** | 没有 ESP32，想用电脑控制 A1；使用时电脑保持开机 | [1.0 发行页](https://github.com/HAOTIANGUO22/phicomm-a1-desktop/releases/tag/v1.0.0) · [Windows 控制台说明](docs/windows-controller.md) |
| **2.0 · ESP32 独立版** | 想关电脑后用手机控制，也可以接红外接收头，学习手持遥控器 | [2.0 发行页](https://github.com/HAOTIANGUO22/phicomm-a1-desktop/releases/tag/v2.0.0) · **[从零开始的 ESP32 新手教程](docs/esp32-standalone.md)** |
| **3.0 · OLED 预览版** | 在 ESP32 独立版上增加 OLED，显示连接、开关和风速；机械修订 2 已由用户确认可安装 | **[3.0 新手指南](docs/oled-3.0.md)** · [固件源码](firmware/a1_oled/) · [打印模型](hardware/README.md) |

第一次用 **2.0**，按教程从下载安装工具开始，依次完成 **烧录 ESP32 → A1 联网 → 预留 IP → 手机配置 ESP32 → 连接 A1 → 测试开关和红外**。配置完毕后，ESP32 用 USB 电源独立供电，手机通过家庭 Wi-Fi 打开 ESP32 上的网页。运行时无需电脑或 Python。

**3.0 OLED 预览版**新增到独立的 `firmware/a1_oled` 目录，1.0 电脑端、2.0 独立版及原有发行页继续保留。3.0 的运行不依赖电脑或 Python，手机网页由 ESP32 提供；首次编译和烧录使用电脑。

3.0 沿用原 M3 底盒，只更换 OLED 盖子。[下载当前修正版 STL（底盒＋OLED 盖，同板排版）](https://raw.githubusercontent.com/HAOTIANGUO22/phicomm-a1-desktop/main/hardware/a1_oled_enclosure/a1-base-and-oled-lid-v3.stl)，或进入 [模型说明](hardware/README.md) 下载单独盖子。**已有底盒不用重打。** 旧盖曾因玻璃与 L 形插头干涉而试装失败，当前机械修订 2 已增加玻璃避让和走线空间，并于 2026-11-09 得到用户“修正的盖子可以安装”的确认；OLED 驱动和 A1 联机仍保留待实测标记。接线、编译、配网、打印与验收步骤见 [3.0 新手指南](docs/oled-3.0.md)。

**原厂 App 无法使用、A1 还没联网时，可使用图形界面自动配网：`provision_app.py`／`A1Provisioner.exe`。** 自动读取无线网卡、选择家庭 Wi-Fi、发送 EasyLink 并验证设备，详见 [Windows 电脑免 App 配网完整步骤](docs/windows-wifi.md)。

## 直接下载 Windows 软件

推荐：[下载配网＋控制台完整便携包 v0.2.0](https://github.com/HAOTIANGUO22/phicomm-a1-desktop/releases/download/v0.2.0/A1DesktopSuite-v0.2.0-Windows-x64.zip)。解压后先运行配网工具，再运行控制台，无需安装 Python。适用于 Windows 10／11 x64。

| 程序 | 直接下载 | 用途 |
| --- | --- | --- |
| 净化器控制台 | [A1Controller-Windows-x64.exe](https://github.com/HAOTIANGUO22/phicomm-a1-desktop/releases/download/v0.2.0/A1Controller-Windows-x64.exe) | 配网并完成首次连接设置后，开关、调速和切换模式 |
| 自动配网 | [A1Provisioner-Windows-x64.exe](https://github.com/HAOTIANGUO22/phicomm-a1-desktop/releases/download/v0.2.0/A1Provisioner-Windows-x64.exe) | 使用电脑无线网卡给 A1 连接家庭 2.4 GHz Wi-Fi |

控制台首次启动的设备 IP、MAC、电脑 IP 和路由器地址均需填写自己的信息。配网结果可提供设备 IP／MAC；保存后在 **连接设置 → 连接到这台电脑** 完成接入。详细步骤见 [控制台 EXE 使用指南](docs/windows-controller.md)，[发行页](https://github.com/HAOTIANGUO22/phicomm-a1-desktop/releases/tag/v0.2.0)提供源码及 SHA-256 校验文件。

公开控制台不携带构建者的网络配置、历史状态、协议头、日志或证书。运行后会在 EXE 旁创建本机 `data/`，分享软件时不要把这个目录一并发送。

### 较早的独立配网发行版

无需安装 Python：[下载 EXE](https://github.com/HAOTIANGUO22/phicomm-a1-desktop/releases/download/v0.1.0/A1Provisioner-Windows-x64.exe)，或 [下载便携 ZIP（含说明和许可）](https://github.com/HAOTIANGUO22/phicomm-a1-desktop/releases/download/v0.1.0/A1Provisioner-v0.1.0-Windows-x64.zip)。适用于 Windows 10／11 x64、有实体无线网卡的电脑。

首次使用，先用 Windows 连接家庭 Wi-Fi 一次，再打开配网软件，选择 Wi-Fi 并点击“开始自动配网”；需要时按提示按住 A1 的 Wi-Fi 键约 1–2 秒。软件会检查 2.4 GHz 并验证设备身份。已联网的 A1 会跳过重复发送。

[发行页及 SHA-256 校验文件](https://github.com/HAOTIANGUO22/phicomm-a1-desktop/releases/tag/v0.1.0)。公开 EXE 不预置个人网络配置、密码、IP 或 MAC。此附件是配网工具；开关、调速仍使用下文的控制台。

## 功能与兼容范围

也可以用 ESP32 作为 Windows 控制台的红外接收器。这条路线使用 `firmware/a1_ir_remote`，电脑需保持运行。详见 [电脑端红外桥接指南](docs/infrared-remote.md)。

手机网页遥控版把网页和 A1 控制服务放在 ESP32，初次配置后电脑可关机。见 [ESP32 独立运行指南](docs/esp32-standalone.md)。

- 原厂 A1 `v1.47`：开机、关机、手动风速、日常／睡眠／强劲模式。
- 模式指令同时明确设置风速：睡眠 `30`、强劲 `85`，日常恢复上次手动设定。
- 开机指令同时发送记忆风速，避免只发送模式编号时没有实际动作。
- 收到设备回报后再更新状态；历史状态会明确标注为“上次状态”。
- 自带本机 DNS、TCP 控制及旧设备所需的本地 HTTPS 握手服务。
- 提供恢复 DHCP 的入口，以及可选的 EasyLink 配网工具。

已在一台原厂 A1 v1.47 上验证实际开关和风速变化。其他固件版本尚未验证。项目当前不包含小爱／米家／Home Assistant 桥接。

## 安装与运行

推荐 Windows 10／11、Python 3.13。电脑需要与净化器处于同一局域网，并在控制期间保持运行。

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

首次启动会打开连接设置，请填写你自己网络中的信息：

| 字段 | 来源 |
| --- | --- |
| 净化器 IP、完整 MAC | 路由器的客户端列表或设备标签 |
| 电脑 IP | 使用有线连接或稳定的局域网地址；也可点“确定本机 IP” |
| 路由器 IP、子网掩码 | 电脑当前网络配置 |
| 上游 DNS | 留空时使用填写的路由器地址 |

仓库不内置任何人的设备信息。`settings.example.json` 仅说明字段结构，地址和 MAC 留空。

### 让 A1 连接电脑

1. 先确认 A1 已连上家庭 Wi-Fi。
2. 启动软件，完成首次连接设置；软件会在填写的电脑地址启动服务。
3. Windows 若弹出联网提示，需要在本机允许该程序接受局域网连接。
4. 在软件中打开 **连接设置 → 连接到这台电脑**。
5. 软件核对型号、固件及 MAC 后，将 A1 设为当前 IP 的静态地址，并把 A1 的 DNS 指向电脑。
6. 等待设备重新联网。首次使用若尚未取得协议报文头，请给 A1 断电再通电，等待它主动上报。

建议在路由器中为电脑和 A1 保留固定地址，避免与 DHCP 分配冲突。本机使用 UDP `53`、TCP `9000` 和 TCP `443`，应保持空闲；服务只处理配置中的设备地址及本机请求。

只会修改配置中的这一台 A1，不会修改路由器的全局 DNS。原厂 HTTP 接口仅用于识别设备和设置网络，不执行 OTA 或固件写入。

## 控制与状态

- **开启净化**：发送开机动作与记忆的手动风速，进入日常模式。
- **关闭**：发送关机动作。
- **日常**：恢复上次手动风速。
- **睡眠／强劲**：明确发送最低／最高风速。
- **风速滑块**：范围 `30–85`，松手后应用。

这里的数字是设备回报的风速设定值，不是实测风量、转速或百分比。原厂设备主要在状态变化时上报，因此重复发送相同指令可能没有新的回报。软件不会把发送成功当成实机确认。

## 配网工具（可选）

### 图形界面自动配网（推荐）

```powershell
py -3.13 provision_app.py
```

也可通过下方构建脚本生成 `dist\A1Provisioner.exe`，之后双击使用，无需安装 Python。配网程序本身只使用 Python 标准库。

1. 选择无线网卡和 Windows 已保存的家庭 Wi-Fi，点击 **开始自动配网**。尚未保存过该 Wi-Fi 时，先在 Windows 中正常连接一次。
2. 软件会尝试优先连接该网络的 2.4 GHz 接入点，核对当前频率与无线 IPv4，并先查找已联网的 A1。
3. 若 A1 尚未联网，按界面提示单独按住机身 Wi-Fi 键约 1–2 秒后松开。软件自动发送配网数据，并继续查找设备。
4. 读取到原厂 A1 v1.47 身份才显示成功，结果可复制到控制台。已联网设备会跳过发送，保留原有设置。

支持读取 Windows 已保存密码或在窗口内手动输入，密码仅在内存中使用，不保存到文件。未知频段需用户确认，已知 5／6 GHz 不会作为 2.4 GHz 发送。若双频同名仍无法连接 2.4 GHz，请先拆分 Wi-Fi 名称。配网程序不修改路由器、不改 A1 的 DNS，也不安装或替换固件。

新图形界面已在 Windows 上验证网卡识别、2.4 GHz 连接和现有 A1 发现；全新配网的发包方法沿用此前成功的 Windows EasyLink 实现，仍需按设备机身按键。

### 命令行方式

已经联网的 A1 不需要重新配网。尚未联网时，可尝试使用 Windows 电脑发送 EasyLink V2 配网数据：

```powershell
# 电脑应连接目标 2.4 GHz Wi-Fi，填写自己的无线网卡 IPv4
.\.venv\Scripts\python.exe tools\a1_easylink.py --interface-ip <Wi-Fi网卡IPv4>
```

按提示在本机输入 SSID 和密码，再单独按住 A1 的 Wi-Fi 图标键约 1–2 秒后松开。密码交互输入不回显。

也可读取 Windows 中已有的 Wi-Fi 配置。该工具只在内存中取用密码，不导出密码文件：

```powershell
.\.venv\Scripts\python.exe tools\send_saved_wifi.py --profile "自己的WiFi配置名称" --interface-ip <Wi-Fi网卡IPv4>
```

工具按 `--interface-ip` 自动查找网卡，也可通过 `--adapter` 指定名称，兼容 `WLAN`、`Wi-Fi` 等不同命名。发送前会确认该无线接口已连接指定配置。

普通 UDP 发包已在本项目的一台原厂 A1 v1.47 上使用 Windows 完成配网；其他网卡、驱动和接入点仍须验证。发送完成不等于设备配网成功，应以路由器租约和设备身份确认结果。详细过程见 [Windows 配网指南](docs/windows-wifi.md)。

扫描自己管理的局域网中的配置接口：

```powershell
.\.venv\Scripts\python.exe tools\find_a1.py --network <自己的IPv4子网/CIDR>
```

扫描器限制在最多 256 个 IPv4 地址内，仅检查原厂配置接口，不读取 Wi-Fi 密码。

## 恢复、配置与隐私

**连接设置 → 恢复自动联网** 会保留 Wi-Fi 名称和密码，并恢复 DHCP。停止软件后，A1 的本机控制连接会断开；如果不再使用本项目，可先恢复自动联网。

运行数据放在源码旁的 `runtime/`，打包后则放在 EXE 旁的 `data/`。其中可能包含设备 IP、MAC、协议报文头、状态、日志及本地证书，已在 `.gitignore` 中排除。修改网络参数会保存到本机，重新打开软件后生效。

提交源码时不要强制加入这些目录、截图、配置文件或个人构建出来的 EXE。源码仓库仅保留通用代码和空配置样例；经过隐私检查的通用配网和控制台 EXE 作为 GitHub Release 附件发布，不包含预置设备信息。

## 测试与打包

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

构建结果：`dist\A1Controller.exe`（控制台）、`dist\A1Provisioner.exe`（自动配网）。构建脚本使用项目内虚拟环境，先运行测试，再生成独立可执行文件，不打包 `data/` 或 `runtime/`。

测试覆盖 TCP 分片／粘包、目标设备 MAC、模式和开机指令、历史状态、DNS 范围，以及配网身份校验、频段检查、取消、已联网跳过和发送失败时的密码保护。自动化测试不连接真实净化器。

## 来源与许可

采用 [GPL-3.0](LICENSE)。EasyLink 工具来自社区固件项目；原厂控制协议与配置接口参考相应上游项目。来源与变更范围见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。本项目与原厂无隶属关系。
