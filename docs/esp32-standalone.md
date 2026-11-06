# 斐讯 A1 2.0｜ESP32 手机网页与红外遥控，从零开始

这份教程适用于 Windows 10／11、经典 ESP32 开发板和原厂固件 **v1.47** 的斐讯悟净 A1。完成设置后，ESP32 用 USB 电源独立运行。手机连接家里的 Wi-Fi 就能开关 A1、切换模式、调风速。接上红外接收头后，也能使用学过的实体遥控器。

> **你需要先完成一次烧录和配网。** GitHub 上的源码包含固件和网页。构建脚本在你的电脑上为本次安装生成网页密码和证书，所以每个人都从自己的源码副本编译。电脑完成设置后就可以关机。整个 2.0 流程无需安装 Python。

| 你要做的事 | 在哪里完成 | 完成的标志 |
| --- | --- | --- |
| 安装工具、编译和烧录 | Windows 电脑 | ESP32 开出 `A1-Setup-…` Wi-Fi |
| 让 A1 接入家庭 Wi-Fi，给设备预留地址 | A1、电脑、路由器 | 路由器能找到 A1 的 IPv4 和 MAC |
| 填写 ESP32 的网络参数 | 手机浏览器 | 切回家庭 Wi-Fi 后能打开控制页 |
| 让 A1 连到 ESP32，测试控制 | 手机浏览器 | A1 实际改变状态，网页收到回报 |
| 学习实体遥控器（可选） | 接收模块、手机网页 | 对准 ESP32 短按可控制 A1 |
| 给 ESP32 独立供电 | USB 充电头 | 电脑关机后，手机仍能控制 A1 |

## 第 1 步：准备硬件与下载源码

- **ESP32**：教程以经典 ESP32-WROOM-32 系列（如 ESP32-WROOM-32E、32EA）、4 MB Flash 的开发板为例，编译目标是 **ESP32 Dev Module**。ESP32-C3、S3 等芯片没有在这套教程里验证。
- **USB 数据线**：电脑需要用它识别串口，只有充电功能的线无法烧录。配置好后另备 USB 充电头供电。
- **网络**：A1 和 ESP32 使用 **2.4 GHz Wi-Fi**。手机即使连在 5 GHz，也要与两台设备在同一个可互访的家庭局域网。访客网络、AP 隔离和公司网络可能阻断设备之间的通信。
- **可选红外硬件**：3.3 V 兼容的红外接收模块、三根杜邦线、有电池的红外遥控器。首次只测试手机的话，可以暂时不接。

从 [GitHub 2.0 发行页](https://github.com/HAOTIANGUO22/phicomm-a1-desktop/releases/tag/v2.0.0) 下载 **Source code (zip)** 并完整解压。也可以在 [仓库首页](https://github.com/HAOTIANGUO22/phicomm-a1-desktop) 点 **Code → Download ZIP**。解压后打开能同时看到 `README.md`、`docs` 和 `firmware` 的那一层。下文的命令都在这个目录运行。

## 第 2 步：安装 Windows 构建工具

1. 安装 [PowerShell 7](https://learn.microsoft.com/powershell/scripting/install/install-powershell-on-windows)，至少需要 7.2。从开始菜单打开 **PowerShell 7**，程序名是 `pwsh`。运行 `$PSVersionTable.PSVersion` 检查版本。
2. 从 [Arduino CLI 官方安装页](https://arduino.github.io/arduino-cli/latest/installation/) 下载 Windows 对应架构的压缩包，解压出 `arduino-cli.exe`。记下它的完整路径，例如 `C:\ArduinoCLI\arduino-cli.exe`。
3. 在 PowerShell 7 中进入刚解压的项目目录。把下面两行的路径换成你的实际路径。

~~~powershell
Set-Location 'C:\A1\phicomm-a1-desktop-2.0.0'
$arduino = 'C:\ArduinoCLI\arduino-cli.exe'
& $arduino version
~~~

4. 安装 Espressif 的板卡支持和三个库。首次下载和编译可能要几分钟。看到错误先解决，再执行后续命令。

~~~powershell
$esp32Index = 'https://espressif.github.io/arduino-esp32/package_esp32_index.json'
& $arduino core update-index --additional-urls $esp32Index
& $arduino core install esp32:esp32@3.3.12 --additional-urls $esp32Index
& $arduino lib update-index
& $arduino lib install 'IRremote@4.7.1' 'ArduinoJson@7.4.3' 'ESP_SSLClient@3.1.3'
& $arduino core list
& $arduino lib list
~~~

在输出里确认 `esp32:esp32` 为 `3.3.12`，三个库的版本也与上面一致。这组版本用于本项目验证。[Espressif 安装说明](https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html)

如果 PowerShell 提示 ZIP 解压出的脚本来自互联网，先确认源码来自本仓库，再对要运行的脚本解除下载标记。下面两条命令只处理本项目这两个文件。

~~~powershell
Unblock-File -LiteralPath .\firmware\a1_standalone\build.ps1
Unblock-File -LiteralPath .\firmware\a1_standalone\connect-a1.ps1
~~~

## 第 3 步：编译并烧录 ESP32

1. 用 USB 数据线连接开发板。执行 `& $arduino board list`。拔插一次可以确认新出现的是哪个 `COM` 端口。显示 `Unknown` 但有串口时，可以继续用下文的手动板卡型号。没有新串口时，在 Windows **设备管理器 → 端口 (COM 和 LPT)** 检查，并确认 USB 转串口芯片所需的驱动已经安装。
2. 编译**待配置固件**。这一步还不需要 A1 或家里的 Wi-Fi 密码。

~~~powershell
$buildPath = Join-Path $env:TEMP 'a1-standalone-build'
& .\firmware\a1_standalone\build.ps1 -Unconfigured -ArduinoCli $arduino -BuildPath $buildPath
~~~

脚本把 `control.html` 嵌入固件，在本机生成 `config.h` 和 `web_page.h`，并显示随机登录密码。**把密码存好。** 配置热点和网页使用同一个密码，网页用户名为 `a1`。如果重新执行编译，脚本会复用已生成的 `config.h`。此前编译过直连 Wi-Fi 版本、确实想重新生成待配置文件时，才加上 `-Reconfigure`。这会重新生成网页密码和证书，ESP32 Flash 中此前保存的网络参数仍优先使用。

3. 将下方的 `COM5` 换成第 1 小步看到的串口。关闭任何占用该串口的监视器，再烧录并校验。

~~~powershell
$port = 'COM5'
& $arduino upload -p $port --fqbn esp32:esp32:esp32 --build-path $buildPath --verify .\firmware\a1_standalone
~~~

如果自动烧录停在 `Connecting…` 或提示 `Wrong boot mode`，按你的开发板选择一种方式，再执行同一条上传命令。

- 有 **BOOT** 和 **RESET／EN** 的板。按住 BOOT，短按并松开 RESET，再松开 BOOT。
- 只有 **RESET** 的经典 ESP32 板。按丝印把 **GPIO0** 临时接到 **GND**，短按 RESET，保持跳线直到上传校验完成。烧录后拔掉 GPIO0 到 GND 的跳线，再按 RESET。三色针排的板接标着 `0` 的信号针和标着 `G` 的地针。
- 这些步骤针对经典 ESP32。只有烧录时需要将 GPIO0 拉低。[Espressif 下载模式说明](https://docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/boot-mode-selection.html)

4. 用串口监视器检查启动。打开后如无新输出，短按一下 RESET。按 **Ctrl+C** 可退出。

~~~powershell
& $arduino monitor -p $port --config baudrate=115200
~~~

首次启动会显示 `Setup Wi-Fi: A1-Setup-…` 和 `http://192.168.4.1:8080/`。如果要找 ESP32 的完整 MAC，可以查看本次烧录日志里打印的 MAC。路由器要用这个**联网用的 MAC**，热点名称末尾的四位字符只用于辨认热点。

## 第 4 步：让 A1 联网，在路由器里记录和预留地址

1. **A1 已联网**时，从路由器的「终端管理」「已连接设备」或「DHCP 客户端」找到 A1，记录当前 IPv4 和完整 MAC。设备可能显示为 `EMW3080B` 或匿名设备。
2. **A1 尚未联网**时，下载 [Windows 自动配网工具](https://github.com/HAOTIANGUO22/phicomm-a1-desktop/releases/download/v0.2.0/A1Provisioner-Windows-x64.exe)，按 [A1 首次联网图文步骤](windows-wifi.md) 操作。电脑先连目标 2.4 GHz Wi-Fi，然后在工具内选同一网络。按工具提示短时间按住 A1 机身的 Wi-Fi 键，等待它显示设备身份和 IP。工具的任务到 **A1 加入家里 Wi-Fi** 为止。
3. 在路由器里找到「静态 IP 地址绑定」或「DHCP 地址保留」。为 **ESP32 的 MAC** 预留一个同网段、未被使用且路由器允许绑定的 IPv4。也建议为 **A1 的 MAC** 保留它当前的 IPv4。两个设备各用自己的地址。
4. 记录路由器的局域网地址和实际子网掩码。Windows 可用 `ipconfig` 查看当前 Wi-Fi 的 IPv4、默认网关和掩码。若路由器拒绝某个地址，先核对「局域网 IP」和「IP 地址分配范围」，清空输入框重新手输；保持 DHCP 正常开启。

下面是一组**示例**，用你自己的地址替换。三台设备的地址应各不相同。

| 字段 | 示例 | 到哪里找 |
| --- | --- | --- |
| 家庭 Wi-Fi 名称、密码 | 自己家的 2.4 GHz Wi-Fi | 路由器或你已有的联网设置 |
| 路由器 IPv4 | `192.168.50.1` | 路由器局域网地址、电脑默认网关 |
| 子网掩码 | `255.255.255.0` | 路由器或电脑 `ipconfig` |
| ESP32 固定 IPv4 | `192.168.50.20` | 为 ESP32 预留的地址 |
| A1 当前 IPv4 | `192.168.50.31` | 路由器终端列表或配网工具 |
| A1 完整 MAC | `02:00:00:00:00:31` | 路由器终端列表或配网工具 |
| 上游 DNS | 留空 | 留空时使用路由器地址 |

## 第 5 步：用手机配置 ESP32

1. 手机打开 Wi-Fi，选择 ESP32 刚开出的 **`A1-Setup-…`**，输入第 3 步生成的密码。手机提示这个热点「无互联网」时，选择继续连接。
2. 在浏览器地址栏输入 **`http://192.168.4.1:8080/`**。登录用户名 `a1`，密码与热点密码相同。
3. 根据第 4 步的记录填写所有字段。**Wi-Fi 名称、密码填家里的 Wi-Fi。A1 MAC 填净化器的 MAC。** 保存后 ESP32 重启，手机与配置热点断开是正常现象。
4. 让手机切回家庭 Wi-Fi，用浏览器访问 `http://ESP32的固定IPv4:8080/`，例如 `http://192.168.50.20:8080/`。使用原来的用户名和密码。记得输入 `http://` 和端口 `:8080`。
5. 打开控制页后，如果显示「A1 未连接」，继续下一步。如果 ESP32 启动后始终连不上已保存的 Wi-Fi，约 25 秒后会重新开启配置热点，可以回来改参数。

## 第 6 步：让 A1 切换到 ESP32，确认真实设备有响应

1. 在手机遥控页展开 **「连接设置」**，点 **「连接到 ESP32」** 并确认。固件先通过 A1 原厂的局域网配置接口核对型号、固件和 MAC 后缀，然后给这台 A1 保留它的当前 IPv4、网关和掩码，并把这台 A1 的 DNS 指向 ESP32。路由器的全网 DNS 无需改动。
2. 等待 A1 重连和上报。若等了一会儿还没有状态，可给 **A1** 断电再通电一次。网页显示「运行状态已同步」或能看到 A1 回报的模式、风速时，先分别试 **开机、关机**。看到网页状态变化的同时，观察净化器实际是否响应。然后再试三种模式和风速滑块。
3. 如果网页提示「无法读取 A1」，先核对 A1 地址和完整 MAC，确认 ESP32 与 A1 在同一个可互访的局域网。如果电脑能访问 A1 而网页按钮仍失败，可用下面的一次性 PowerShell 方案完成接入。后续仍由 ESP32 控制。

~~~powershell
# 把以下示例值替换为你自己的设备信息
$a1Network = @{
    A1Ip    = '192.168.50.31'
    A1Mac   = '02:00:00:00:00:31'
    EspIp   = '192.168.50.20'
    Gateway = '192.168.50.1'
    Netmask = '255.255.255.0'
}
# 第一条只读，看到身份核对通过后再执行第二条
& .\firmware\a1_standalone\connect-a1.ps1 @a1Network
& .\firmware\a1_standalone\connect-a1.ps1 @a1Network -Action Connect
~~~

电脑工具与原 Windows 程序使用同一个 A1 本地配置接口。它先核对设备身份，然后把 A1 的 DNS 指向刚刚配置的 ESP32。工具提示已接收后，回到手机网页等 A1 上报。首次开机时 A1 可能先恢复自己的原有风速，网页的指令确认可能比机器动作晚。等待状态同步后再发下一条。

## 第 7 步（可选）：接红外模块并逐个学习按键

拔掉 ESP32 的 USB 电源，再接线。三色针排示例用板上标着 **`27`** 的同一列。其他型号开发板按信号名称找针脚。模块要支持 **3.3 V 供电和信号**，以模块丝印为准。

| 红外接收模块 | ESP32 | 三色针排示例 |
| --- | --- | --- |
| `S`／`OUT` 信号 | `GPIO27` | `27` 列黄色信号针 |
| `VCC`（示例模块为中间脚） | `3V3` | 同列红色针 |
| `GND`／`−` | `GND` | 同列黑色 `G` 针 |

接好再通电，打开手机遥控页并展开 **「实体遥控器学习」**。先点 **「1 · 开机」** 那一行的 **「学习」**，等它显示 **「等待短按」**，对准 **ESP32 上的红外接收头**，短按实体遥控器的 `1`。看到 **「按键已保存」** 后，再短按一次确认 A1 能开机。然后按下表逐项学习。

| 网页中的学习项 | 建议按下的实体键 | 学完后的作用 |
| --- | --- | --- |
| `1 · 开机` | `1` | 开机 |
| `0 · 关机` | `0` | 关机 |
| `2 · 日常` | `2` | 日常模式 |
| `3 · 睡眠` | `3` | 睡眠模式 |
| `4 · 强劲` | `4` | 强劲模式 |
| `↑ · 风速` | 上箭头 | 运行时风速 +5 |
| `↓ · 风速` | 下箭头 | 运行时风速 −5 |

上下键会切到日常模式，风速设定范围是 `30–85`。表格是推荐映射，可以在学习时选另一枚实体键。每个红外键只能绑定一个动作，出现「这枚按键已绑定」时请选择另一枚键，或先给原来的动作学一个替代键。按错了可取消学习，也可重新学习同一行覆盖。学好的键保存在 ESP32 的闪存里，重启会保留。

## 第 8 步：验证电脑关机后也能用

1. 先用手机确认遥控页正常、A1 实际响应。
2. 把 ESP32 的 USB 从电脑移到独立 USB 充电头。等 ESP32 重新连 Wi-Fi，手机刷新同一个网页地址。
3. 确认手机和 A1 仍在家里的网络，关电脑再从手机点一次开关。网页状态和机器动作都成功，就可以把网页加入手机主屏幕或书签。已学习的遥控器也可以在这时复测。
4. 以后 ESP32、路由器和 A1 保持供电即可。更换 Wi-Fi 或地址时，从控制页点 **「修改 ESP32 和 A1 的网络参数」**。如果要停用这套控制，在 **「连接设置 → 恢复自动联网」** 恢复 A1 的 DHCP，再从路由器查看新地址。网页恢复失败时，可用第 6 步的 PowerShell 命令改成 `-Action Restore`，它会保留 A1 已有的 Wi-Fi 凭据。

## 常见问题

| 现象 | 优先检查 |
| --- | --- |
| 编译报找不到库 | 重跑第 2 步，核对库名和版本。在仓库根目录运行脚本。 |
| 串口打不开或端口不存在 | 换数据线，核对设备管理器，关闭其他串口监视器。 |
| 手机找不到 `A1-Setup-…` | 核对 GPIO0 跳线已拔掉，按 RESET 看串口。已经连上家庭 Wi-Fi 的 ESP32 会显示正常控制页地址。 |
| 手机连上热点，网页却打不开 | 手输 `http://192.168.4.1:8080/`。确认手机还连着热点，浏览器没有把地址自动升级成 HTTPS。 |
| 保存后打不开新地址 | 确认手机已切回家庭 Wi-Fi，地址带 `:8080`。用串口检查 ESP32 是否连上；检查地址冲突和访客网络隔离。 |
| 网页能打开，A1 一直不连接 | 核对 A1 的 IPv4、完整 MAC、原厂 v1.47。重新连接或给 A1 断电再通电，必要时按第 6 步从电脑接入。 |
| 红外显示「等待短按」很久 | 短按且靠近接收头，核对 `S→GPIO27`、电源和地线，确认遥控器电池有电。 |
| 红外已经学到，但按键不动作 | 先用网页验证 A1 已连接且能控制。风速键需要 A1 在运行并回报过风速。 |

## 固件、网页和电脑工具分别做什么

| 文件 | 用途 |
| --- | --- |
| [a1_standalone.ino](../firmware/a1_standalone/a1_standalone.ino) | ESP32 主程序，负责联网、配置热点、控制网页、A1 状态与红外学习。 |
| [control.html](../firmware/a1_standalone/control.html) | 单文件手机界面，构建时嵌入固件。直接在电脑打开只适合看界面，操作 A1 时应从 ESP32 的地址打开。 |
| [protocol.h](../firmware/a1_standalone/protocol.h) 和 [legacy_tls.h](../firmware/a1_standalone/legacy_tls.h) | 实现原厂 A1 使用的本地控制报文、DNS 应答和旧版 HTTPS 握手。 |
| [build.ps1](../firmware/a1_standalone/build.ps1) | 在本机生成网页密码、证书及固件配置，把网页嵌入并调用 Arduino CLI 编译。 |
| [connect-a1.ps1](../firmware/a1_standalone/connect-a1.ps1) | Windows 一次性接入工具，用于检查 A1 身份、将 A1 切到 ESP32 或恢复 DHCP。 |
| `firmware/a1_ir_remote` | Windows 控制台的可选红外桥接固件。2.0 手机独立版使用 `firmware/a1_standalone`。[电脑端桥接说明](infrared-remote.md) |

手机访问 ESP32 的 TCP `8080`。A1 访问 ESP32 的 UDP `53`、TCP `9000` 和 TCP `443`。网页使用家庭局域网 HTTP 登录，请放在可信的家庭网络使用。保管好生成的 `config.h` 和本地编译出来的固件文件，它们带有本次安装生成的密码和密钥。仓库提供通用源码，个人 Wi-Fi、IP、密码和私钥留在本机或 ESP32 上。

本项目实机验证了经典 ESP32 烧录、配置热点、家庭网络配置，以及一台原厂 v1.47 A1 接入后由 ESP32 控制开关并收到状态回报。红外接线后请按第 7 步实测，电脑关机和独立供电请按第 8 步在你的环境验证。
