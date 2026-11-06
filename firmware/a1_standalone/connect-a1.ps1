#requires -Version 7.2
# SPDX-License-Identifier: GPL-3.0-only
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ipaddress]$A1Ip,
    [Parameter(Mandatory)][string]$A1Mac,
    [Parameter(Mandatory)][ipaddress]$EspIp,
    [Parameter(Mandatory)][ipaddress]$Gateway,
    [ipaddress]$Netmask = '255.255.255.0',
    [ValidateSet('Check', 'Connect', 'Restore')][string]$Action = 'Check'
)

$ErrorActionPreference = 'Stop'
if (@($A1Ip, $EspIp, $Gateway, $Netmask).Where({ $_.AddressFamily -ne 'InterNetwork' }).Count) {
    throw '请填写 IPv4 地址和 IPv4 子网掩码。'
}
if ($A1Ip.Equals($EspIp) -or $A1Ip.Equals($Gateway) -or $EspIp.Equals($Gateway)) {
    throw 'A1、ESP32 和路由器需要三个不同的 IPv4 地址。'
}
$maskBytes = $Netmask.GetAddressBytes()
$bits = ($maskBytes | ForEach-Object { [Convert]::ToString([int]$_, 2).PadLeft(8, '0') }) -join ''
if ($bits -notmatch '^1+0{3,}$') { throw '请填写实际的连续 IPv4 子网掩码。' }
$routerBytes = $Gateway.GetAddressBytes()
foreach ($address in @($A1Ip, $EspIp, $Gateway)) {
    $bytes = $address.GetAddressBytes()
    $hostSum = 0
    $maskSum = 0
    for ($i = 0; $i -lt 4; $i++) {
        if (($bytes[$i] -band $maskBytes[$i]) -ne ($routerBytes[$i] -band $maskBytes[$i])) {
            throw 'A1、ESP32 和路由器应位于同一个子网。'
        }
        $hostMask = 255 -bxor $maskBytes[$i]
        $hostSum += $bytes[$i] -band $hostMask
        $maskSum += $hostMask
    }
    if ($bytes[0] -in (0, 127) -or $bytes[0] -ge 224 -or $hostSum -in (0, $maskSum)) {
        throw '请填写该子网内可用的主机地址。'
    }
}
$mac = ($A1Mac.Trim() -replace '[:-]', '').ToUpperInvariant()
if ($mac -notmatch '^[0-9A-F]{12}$' -or $mac -eq '000000000000' -or
    ([Convert]::ToByte($mac.Substring(0, 2), 16) -band 1)) {
    throw '请填写 A1 的完整单播 MAC 地址。'
}

function Invoke-DeviceRequest([string]$Path, [hashtable]$Settings) {
    # Use HTTP/1.0 for the stock MiCO configuration server.
    $request = [Net.HttpWebRequest]::Create("http://${A1Ip}:8000/$Path")
    $request.Proxy = $null
    $request.ProtocolVersion = [Version]'1.0'
    $request.KeepAlive = $false
    $request.AllowAutoRedirect = $false
    $request.Timeout = 6000
    $request.ReadWriteTimeout = 6000
    if ($null -ne $Settings) {
        $request.Method = 'POST'
        $request.ContentType = 'application/json'
        $bytes = [Text.Encoding]::UTF8.GetBytes(($Settings | ConvertTo-Json -Compress))
        $request.ContentLength = $bytes.Length
        $stream = $request.GetRequestStream()
        try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
    }
    $response = $request.GetResponse()
    try {
        if ([int]$response.StatusCode -ne 200) { throw "A1 接口返回 HTTP $([int]$response.StatusCode)。" }
        if ($null -eq $Settings) {
            if ($response.ContentLength -lt 1 -or $response.ContentLength -gt 65536) {
                throw 'A1 身份回报的长度不符合预期。'
            }
            $reader = [IO.StreamReader]::new($response.GetResponseStream())
            try { $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
        }
    } finally { $response.Dispose() }
}

$identity = Invoke-DeviceRequest 'config-read'
$expectedName = '^(EMW3080B|MK3080B)\(' + $mac.Substring(6) + '\)$'
if ($identity.PO -cne 'com.phicomm.basic' -or $identity.FW -cne 'v1.47' -or
    $identity.HD -cne '3080B' -or $identity.N -notmatch $expectedName) {
    throw '设备型号、固件或 MAC 后六位不匹配，已停止。'
}
if ($Action -eq 'Check') {
    Write-Output "已核对 A1 $($identity.N)，原厂 $($identity.FW)，本次仅读取。"
    return
}
if ($Action -eq 'Connect') {
    try {
        # The unauthenticated ESP32 controller responds with a Basic login challenge.
        $page = Invoke-WebRequest -Uri "http://${EspIp}:8080/" -NoProxy -SkipHttpErrorCheck `
            -MaximumRedirection 0 -TimeoutSec 5
        $challenge = [string]($page.Headers['WWW-Authenticate'] -join ', ')
        if ($page.StatusCode -ne 401 -or $challenge -notmatch '^Basic\b') {
            throw '预期 ESP32 返回网页登录提示。'
        }
    } catch { throw "无法确认 ESP32 的网页可访问，请核对 ESP32 地址并先用浏览器登录。$($_.Exception.Message)" }
    Invoke-DeviceRequest 'config-write' @{
        DHCP = $false; 'IP address' = "$A1Ip"; 'Net Mask' = "$Netmask";
        Gateway = "$Gateway"; 'DNS Server' = "$EspIp"
    }
    Write-Output 'A1 已接收配置。请回到 ESP32 网页等待设备回报。'
} else {
    Invoke-DeviceRequest 'config-write' @{ DHCP = $true; 'DNS Server' = "$Gateway" }
    Write-Output 'A1 已接收恢复 DHCP 的设置。重新联网后的 IP 请到路由器查看。'
}
