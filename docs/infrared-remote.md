# 斐讯 A1 红外遥控上手指南

本页介绍需要 Windows 控制台运行的红外桥接。如果想关掉电脑后继续使用手机或实体遥控器，请阅读 [2.0 ESP32 独立版教程](esp32-standalone.md)。

手持遥控器 → 红外接收模块 → ESP32 → Wi-Fi → Windows 控制台 → 斐讯 A1。

电脑控制台需要保持运行。A1 沿用原项目的本机连接方式，适用范围为原厂固件 v1.47。电脑、ESP32 和 A1 需在同一可互通的局域网，ESP32 使用 2.4 GHz Wi-Fi。

## 1. 接线

先拔掉 ESP32 的 USB 电源。照片中的接收模块以板上 `S` 和 `−` 丝印为准。ESP32 使用下方三色针排标为 `27` 的那一列。

| 接收模块 | ESP32 |
| --- | --- |
| `S`（照片中黄线） | `27` 列的黄色信号针（GPIO27） |
| 中间电源脚（照片中红线） | 同列红色 `3V3` |
| `−`（照片中黑线） | 同列黑色 `G` |

## 2. 让控制台连上 A1

在本仓库目录执行 `python app.py`。首次使用时，可执行 `python -m pip install -r requirements.txt` 安装依赖。旧版控制台如果开着，先退出，以便新版使用同一组控制端口。

- 已用原控制台设置过 A1 时，可将旧版 `data/settings.json`（EXE 版）或 `runtime/settings.json`（源码版）复制到本仓库的 `runtime/settings.json`。如果电脑 IP 变了，按[原连接指南](windows-controller.md)核对连接设置。
- 初次接入时，按[原配网指南](windows-wifi.md)把 A1 接入 Wi-Fi，填入 A1 的 IP、完整 MAC、电脑 IP 等，再在 **连接设置 → 连接到这台电脑** 完成接入。

先用控制台的开关按钮验证 A1 可以操作，再点主界面的 **红外遥控**。点 **生成 ESP32 配网文件**，在本机窗口输入 Wi-Fi 信息，将 `config.h` 保存在 `firmware/a1_ir_remote`，与 `.ino` 同目录。如果 Windows 弹出网络访问提示，允许在当前可信的专用网络上访问。红外服务使用 TCP `8765`，HTTP 请求带令牌。

## 3. 编译和烧录 ESP32

从本仓库目录运行。编译目标为 `ESP32 Dev Module`，串口以 `board list` 显示为准。下面用 `COM18` 举例。

```powershell
$arduino = 'C:\ArduinoCLI\arduino-cli.exe'  # 改成 Arduino CLI 的实际路径
$buildPath = Join-Path $env:TEMP 'a1-ir-esp32'
& $arduino lib install IRremote@4.7.1
& $arduino board list
& $arduino compile --fqbn esp32:esp32:esp32 --build-path $buildPath .\firmware\a1_ir_remote
if ($LASTEXITCODE -ne 0) { throw '编译失败，请先修正错误。' }
& $arduino upload -p COM18 --fqbn esp32:esp32:esp32 --build-path $buildPath --verify .\firmware\a1_ir_remote
& $arduino monitor -p COM18 --config baudrate=115200
```

看到 `Wi-Fi connected` 后，对准接收头按一下遥控器。串口打印 `IR 协议:地址:命令`，例如 `IR NEC:0000:0045`。如果暂时只想读按键码，可先在没有 `config.h` 时烧录，固件会进入串口读码模式。

## 4. 学习按键

在 **红外遥控** 窗口，逐行点 **学习**，对准接收头短按对应的实体键。每行出现按键码后就已保存。全部学完后可以关掉学习窗口，保留控制台运行。

| 遥控键 | 净化器动作 |
| --- | --- |
| `1` / `0` | 开机 / 关机 |
| `2` / `3` / `4` | 日常 / 睡眠 / 强劲 |
| `↑` / `↓` | 按设备回报的风速加减 5，范围 30–85，并切到日常模式 |

串口显示 `HTTP 204` 表示控制台收到按键，常见于学习、尚未绑定或滤除重复码。`HTTP 202` 表示控制台已向 A1 发出指令。净化器有没有实际响应，以主界面的设备回报和净化器状态为准。`HTTP 409` 的原因可在红外窗口查看。若串口已经有码但窗口无变化，检查电脑 IP、Wi-Fi 是否隔离及 TCP `8765` 是否被防火墙拦截。

`config.h` 和 `runtime/ir-remote.json` 含本机配网信息或令牌，已列入 Git 忽略规则。切换电脑 IP 后，重新生成 `config.h` 并烧录。
