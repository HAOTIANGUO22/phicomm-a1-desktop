# Windows 电脑给原厂 A1 配网

本文记录本项目使用 Windows 11、电脑无线网卡和 EasyLink V2，让原厂 A1 v1.47 连接家庭 Wi-Fi 的方法。成功过程已经脱敏，没有保留当时的 SSID、密码、IP、MAC 或用户目录。

普通 Windows UDP 配网已在一台 A1 上成功。不同网卡、驱动、路由器及固件仍可能有差异，不能保证每台设备都适用。

先分清两个步骤：

| 步骤 | 用途 | 完成标志 |
| --- | --- | --- |
| Wi-Fi 配网 | 把家庭 Wi-Fi 名称和密码传给 A1 | 路由器给 A1 分配 IP |
| 连接控制软件 | 让 A1 把原厂服务连接转到电脑 | 桌面软件收到 A1 连接和状态 |

仅修改电脑的 hosts 文件，不会自动改变 A1 的 DNS。第二步由桌面软件的“连接到这台电脑”完成。

## 1. 准备

- 一台有实体无线网卡的 Windows 10／11 电脑；仅插网线不能代替无线配网。
- 下载本仓库，在解压后的项目目录打开 PowerShell。
- 安装 Python，确认 `py -3.13 --version` 可用。配网脚本只依赖 Python 标准库，不必先安装桌面软件依赖。
- A1 正常通电，放在电脑、路由器附近。
- 准备自己的 **2.4 GHz、WPA2-Personal/AES** Wi-Fi。初次验证可用短英文名称，避免 WPA3-only。

电脑可以保留网线连接，同时用无线网卡连接目标 Wi-Fi。配网数据要从无线网卡发送；不需要为了配网拔掉网线。

## 2. 让电脑连接目标 2.4 GHz Wi-Fi

查看无线网卡和已保存的 Wi-Fi 配置：

```powershell
netsh wlan show interfaces
netsh wlan show profiles
Get-NetAdapter | Select-Object Name, InterfaceDescription, Status
```

记下真正的无线网卡名称，可能是 `WLAN`、`Wi-Fi` 或其他名称。不要选择以太网、蓝牙网络、VMware、WSL、vEthernet 或 VPN 虚拟网卡。

如果目标 Wi-Fi 已保存在 Windows 中，可以连接它：

```powershell
$A1WifiAdapter = Read-Host "无线网卡名称"
$A1WifiProfile = Read-Host "已保存的 Wi-Fi 配置名称"
netsh wlan connect "name=$A1WifiProfile" "interface=$A1WifiAdapter"
netsh wlan show interfaces
```

尚未保存过时，先通过 Windows 的 Wi-Fi 面板正常连接一次，由你在系统界面输入密码。

检查当前无线接口满足：

- `State`／状态为 `connected`／已连接。
- SSID 是要给 A1 使用的网络。
- `Band`／频段为 **2.4 GHz**。

双频同名时，电脑可能实际连在 5 GHz。可在路由器里临时分开 2.4／5 GHz 名称，再让电脑连接 2.4 GHz 名称。不要只凭 Wi-Fi 名称推断频段。旧系统不显示频段时，也优先使用明确独立的 2.4 GHz 网络。

## 3. 确认无线网卡 IPv4

```powershell
Get-NetIPAddress -InterfaceAlias $A1WifiAdapter -AddressFamily IPv4 |
    Select-Object IPAddress, PrefixLength, AddressState
$A1WifiIp = Read-Host "上面无线网卡的 IPv4 地址"
```

填写无线网卡当前使用的 IPv4。不要填电脑的以太网 IP、路由器 IP、净化器 IP、回环地址或虚拟网卡地址。`169.254.*` 通常表示尚未正常取得局域网地址，应先解决电脑联网问题。

**配网使用的无线 IP，与之后桌面控制使用的电脑 IP 可以不同。** 例如电脑同时接网线时，配网从无线网卡发送，桌面控制服务则可以使用更稳定的有线网卡地址；两者都应在 A1 所在局域网内。

## 4. 发送配网数据

两种方式选择一种即可。不要同时运行多个配网发送器。

### 方式 A：使用 Windows 已保存的 Wi-Fi 密码

先进行一次检查，不发送配网组播数据：

```powershell
py -3.13 tools\send_saved_wifi.py --profile "$A1WifiProfile" --interface-ip "$A1WifiIp" --check-only
```

出现 `"status": "ready"` 表示：工具已按 IPv4 找到网卡，确认其连接的是指定 Wi-Fi 配置，Windows 返回了可用密码，配网编码也已完成。它不表示 A1 已经联网。

默认按 IPv4 查找网卡，没有硬编码为 `WLAN`。如果需要同时限定网卡名称：

```powershell
py -3.13 tools\send_saved_wifi.py --profile "$A1WifiProfile" --interface-ip "$A1WifiIp" --adapter "$A1WifiAdapter" --check-only
```

检查通过后开始发送：

```powershell
py -3.13 tools\send_saved_wifi.py --profile "$A1WifiProfile" --interface-ip "$A1WifiIp" --duration 55
```

看到开始发送的提示后，**立即单独按住 A1 面板的 Wi-Fi 图标键约 1–2 秒，再松开**。原厂接收窗口约 60 秒，发送器持续约 55 秒。保持通电，等发送结束。

此路径监听无线配网包，不需要先在电脑上找到或连接 A1 自己的热点。不要把 M1 空气检测仪的热点配网教程套到 A1 上。

工具通过 Windows Native Wi-Fi API 在内存中读取指定配置的密码，不导出明文配置文件，也不打印密码。若 Windows 没有返回可用密码，可以采用下面的手动输入方式。

### 方式 B：手动输入 Wi-Fi 名称与密码

电脑仍需先连接目标 2.4 GHz Wi-Fi，然后运行：

```powershell
py -3.13 tools\a1_easylink.py --interface-ip "$A1WifiIp" --duration 55
```

在本机终端按提示输入 SSID 和密码。密码输入不回显，不需要把密码写进命令行、源码或配置文件。看到发送提示后，同样按住 A1 的 Wi-Fi 图标键约 1–2 秒后松开。

如果先按了设备键，但准备命令花了太久，可等本次发送结束，再重新进行一轮配网；避免重复启动多个发送进程。

## 5. 验证 A1 是否真正联网

**发送了多少包，只代表电脑进行了发送，不代表 A1 接收成功。** 请按下面顺序确认。

### 路由器租约与设备身份

在路由器的已连接设备／DHCP 客户端列表里查找新设备，核对其 MAC 或标签。原厂庆科模块可能以 `EMW3080B`、模块厂商或未知设备名称出现。

取得候选 IP 后，读取原厂身份字段：

```powershell
$A1DeviceIp = Read-Host "路由器里找到的 A1 IPv4 地址"
curl.exe --noproxy "*" --connect-timeout 3 --max-time 5 "http://${A1DeviceIp}:8000/config-read" |
    ConvertFrom-Json | Select-Object N, PO, HD, FW, RF
```

本项目验证的设备返回原厂身份 `PO=com.phicomm.basic`、硬件 `HD=3080B`、固件 `FW=v1.47`，设备名中带有 MAC 后缀。核对它与路由器或机身标签中的设备一致。

原厂配置接口可能需要等待片刻才可访问。有 DHCP 租约但端口暂时不通时，先核对 IP、客户端隔离和设备启动状态，不要仅因这一个接口超时就认定配网失败。

也可只扫描自己管理的子网，辅助寻找这个接口：

```powershell
$A1Subnet = Read-Host "自己的局域网子网，例如 192.168.50.0/24"
py -3.13 tools\find_a1.py --network "$A1Subnet"
```

### 标签看不清时，用断电对照确认

1. A1 通电时执行 `ping -n 3 $A1DeviceIp`。
2. 只拔掉 A1 电源，稍等后再次 ping，检查候选设备是否停止响应。
3. 插回电源，正常通电即可，**不要再按 Wi-Fi 配网键**。
4. 检查同一设备是否自动重新联网，再读取身份或查看路由器 MAC。

ping 结果必须是目标 IP 自己回复并包含 TTL；不能只看命令退出码，也不要把网关返回的“目标主机不可达”当成设备在线。断电后电源余量和网络超时可能使变化稍有延迟。

本项目的 Windows 配网过程，使用了新 DHCP 地址、配置接口身份以及断电／重新通电后的离线／重连来交叉确认，未保留真实地址和 MAC。

Wi-Fi 灯继续闪烁还可能表示原厂云服务不可用，不能单凭指示灯断言配网失败。

## 6. 继续使用电脑控制

确认 A1 已联网后，按 [主文档](../README.md#安装与运行) 启动桌面软件，填写设备和电脑地址，再点击 **连接设置 → 连接到这台电脑**。

配网阶段用无线网卡发送凭据；控制阶段让 A1 主动连接电脑上的本地服务。完成配网本身，不会自动获得米家、小爱或桌面控制能力。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| 没有无线接口 | 确认电脑有实体无线网卡、驱动和 WLAN 服务；仅网线连接不够 |
| 无线网卡有旧 IP，但显示 disconnected | 先连上目标 Wi-Fi。工具会阻止使用断开的无线连接发送 |
| 当前连接配置与 `--profile` 不一致 | 使用 `netsh wlan show profiles` 找到准确配置名，并先连接它 |
| `--adapter` 无法匹配 | 使用 `Get-NetAdapter` 查到的实际名称，且 IPv4 必须属于这张网卡 |
| 读取连接信息出现权限错误 | 按 Windows 本机提示检查 Wi-Fi／位置权限；无法读取密码时可用手动输入方案 |
| 电脑连在 5／6 GHz | 分开频段名称后连接明确的 2.4 GHz 网络，再确认当前频段 |
| A1 没有拿到 IP | 核对密码、WPA2/AES、按键时机和信号；重新尝试一轮。也可能是驱动不适合普通 UDP 配网 |
| 已拿到 IP，但控制台仍未连接 | 配网与控制接入是两步，继续完成桌面软件的本机连接设置 |

## 来源与隐私

本方法建立在上游 EasyLink V2 发送器上；项目增加了 Windows 已保存配置读取、网卡选择检查和本次实机经验说明。上游来源及 GPL-3.0 许可见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。

Microsoft 参考：[netsh wlan](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/netsh-wlan)、[WlanQueryInterface](https://learn.microsoft.com/en-us/windows/win32/api/wlanapi/nf-wlanapi-wlanqueryinterface)、[WlanGetProfile](https://learn.microsoft.com/en-us/windows/win32/api/wlanapi/nf-wlanapi-wlangetprofile)。

命令输出中的 SSID、IP、MAC 和截图仍可能暴露自己的网络信息。提交问题时可隐藏这些具体值；不要把密码、明文 Wi-Fi 配置、抓包或运行目录提交到仓库。
