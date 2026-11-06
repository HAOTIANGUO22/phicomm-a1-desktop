#requires -Version 7.2
# SPDX-License-Identifier: GPL-3.0-only
[CmdletBinding()]
param(
    [switch]$Reconfigure,
    [switch]$Unconfigured,
    [switch]$PrepareOnly,
    [string]$ArduinoCli,
    [string]$BuildPath = (Join-Path $env:TEMP 'a1-standalone-build')
)

$ErrorActionPreference = 'Stop'
$defaultArduinoCli = 'D:\Arduinocli\arduino-cli.exe'
if (-not $ArduinoCli -and -not $PrepareOnly) {
    if (Test-Path -LiteralPath $defaultArduinoCli -PathType Leaf) {
        $ArduinoCli = $defaultArduinoCli
    } else {
        $ArduinoCli = (Get-Command arduino-cli -CommandType Application -ErrorAction SilentlyContinue).Source
    }
}
if (-not $PrepareOnly -and (-not $ArduinoCli -or
    -not (Get-Command $ArduinoCli -CommandType Application -ErrorAction SilentlyContinue))) {
    throw '找不到 Arduino CLI。请使用 -ArduinoCli 指定 arduino-cli.exe 的完整路径。'
}
$localConfig = Join-Path $PSScriptRoot 'config.h'
$utf8 = [Text.UTF8Encoding]::new($false)

function Read-IPv4([string]$Prompt) {
    $entry = Read-Host $Prompt
    $parsed = $null
    if ($entry -notmatch '^\d{1,3}(\.\d{1,3}){3}$' -or
        -not [Net.IPAddress]::TryParse($entry, [ref]$parsed)) {
        throw "无效的 IPv4 地址。请重新运行配置。"
    }
    return $parsed
}

function Write-CString([string]$Name, [string]$Value) {
    $escaped = ($utf8.GetBytes($Value) | ForEach-Object {
        '\' + [Convert]::ToString([int]$_, 8).PadLeft(3, '0')
    }) -join ''
    return ('constexpr char {0}[] = "{1}";' -f $Name, $escaped)
}

function Write-ByteArray([string]$Name, [byte[]]$Bytes) {
    return ('constexpr uint8_t {0}[] = {{{1}}};' -f $Name, ($Bytes -join ','))
}

if ($Reconfigure -or -not (Test-Path -LiteralPath $localConfig)) {
    if ($Unconfigured) {
        $ssid = $wifiPassword = $espAddress = $deviceAddress = $mac = $router = $netmask = $dns = ''
    } else {
        $ssid = Read-Host '2.4 GHz Wi-Fi 名称'
        if ($utf8.GetByteCount($ssid) -notin (1..32) -or $ssid.Contains([char]0)) {
            throw 'Wi-Fi 名称长度应为 1–32 字节。'
        }
        $wifiPassword = Read-Host 'Wi-Fi 密码（输入时隐藏）' -MaskInput
        $espAddress = Read-IPv4 '分配给 ESP32 的固定 IP（未被占用）'
        $deviceAddress = Read-IPv4 'A1 当前 IP'
        $router = Read-IPv4 '路由器 IP'
        $netmask = Read-IPv4 '子网掩码（常见为 255.255.255.0）'
        $mac = (Read-Host 'A1 的完整 MAC') -replace '[:-]', ''
        if ($mac -notmatch '^[0-9a-f]{12}$' -or $mac -eq '000000000000' -or
            ([Convert]::ToByte($mac.Substring(0, 2), 16) -band 1)) {
            throw '请填写 A1 的完整单播 MAC 地址。'
        }
        $dns = Read-Host '上游 DNS IPv4（留空使用路由器）'
        if ([string]::IsNullOrWhiteSpace($dns)) {
            $dns = $router
        } else {
            $parsed = $null
            if ($dns -notmatch '^\d{1,3}(\.\d{1,3}){3}$' -or
                -not [Net.IPAddress]::TryParse($dns, [ref]$parsed)) {
                throw '无效的上游 DNS IPv4。'
            }
            $dns = $parsed
        }
        if ($dns.Equals($espAddress) -or $dns.Equals($deviceAddress)) {
            throw '上游 DNS 不能使用 ESP32 或 A1 的地址。'
        }
        $maskBytes = $netmask.GetAddressBytes()
        $bits = ($maskBytes | ForEach-Object { [Convert]::ToString([int]$_, 2).PadLeft(8, '0') }) -join ''
        if ($bits -notmatch '^1+0{3,}$') {
            throw '请使用实际的连续子网掩码。'
        }
        $devices = @($espAddress, $deviceAddress, $router)
        if (($devices | ForEach-Object ToString | Sort-Object -Unique).Count -ne 3) {
            throw 'ESP32、A1 和路由器必须使用不同的 IP。'
        }
        $gatewayBytes = $router.GetAddressBytes()
        foreach ($address in $devices) {
            $bytes = $address.GetAddressBytes()
            $hostBits = 0
            $allHostBits = 0
            for ($index = 0; $index -lt 4; $index++) {
                if (($bytes[$index] -band $maskBytes[$index]) -ne ($gatewayBytes[$index] -band $maskBytes[$index])) {
                    throw 'ESP32、A1 和路由器应位于同一个子网。'
                }
                $hostMask = 255 -bxor $maskBytes[$index]
                $hostBits += $bytes[$index] -band $hostMask
                $allHostBits += $hostMask
            }
            if ($bytes[0] -in (0, 127) -or $bytes[0] -ge 224 -or $hostBits -in (0, $allHostBits)) {
                throw '请填写该子网内可用的主机地址。'
            }
        }
    }

    $webPassword = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(8)).ToLowerInvariant()
    $rsa = [Security.Cryptography.RSA]::Create(2048)
    try {
        $request = [Security.Cryptography.X509Certificates.CertificateRequest]::new(
            'CN=phicloudsym.phicomm.com', $rsa, [Security.Cryptography.HashAlgorithmName]::SHA256,
            [Security.Cryptography.RSASignaturePadding]::Pkcs1)
        $names = [Security.Cryptography.X509Certificates.SubjectAlternativeNameBuilder]::new()
        $names.AddDnsName('phicloudsym.phicomm.com')
        $names.AddDnsName('aircleaner.phicomm.com')
        $names.AddDnsName('aircleanerconnecter.phicomm.com')
        $request.CertificateExtensions.Add($names.Build())
        $now = [DateTimeOffset]::UtcNow
        $certificate = $request.CreateSelfSigned($now.AddDays(-1), $now.AddYears(10))
        try {
            $lines = @(
                '#pragma once'
                '#include <stdint.h>'
                (Write-CString WIFI_SSID $ssid)
                (Write-CString WIFI_PASSWORD $wifiPassword)
                (Write-CString ESP_IP $espAddress)
                (Write-CString A1_IP $deviceAddress)
                (Write-CString A1_MAC $mac.ToLowerInvariant())
                (Write-CString GATEWAY $router)
                (Write-CString NETMASK $netmask)
                (Write-CString UPSTREAM_DNS $dns)
                "constexpr char WEB_PASSWORD[] = `"$webPassword`";"
                (Write-ByteArray TLS_CERT $certificate.RawData)
                (Write-ByteArray TLS_KEY $rsa.ExportRSAPrivateKey())
            )
            [IO.File]::WriteAllLines($localConfig, $lines, $utf8)
        } finally {
            $certificate.Dispose()
        }
    } finally {
        $rsa.Dispose()
    }
    if ($Unconfigured) {
        Write-Host '烧录后连接 ESP32 的 A1-Setup 热点，打开 http://192.168.4.1:8080/'
        Write-Host '配置热点密码与网页密码相同。'
    } else {
        Write-Host "手机网页 http://${espAddress}:8080/"
    }
    Write-Host "网页登录用户名 a1，密码 $webPassword"
    Write-Host '请在本机记录网页登录密码。它也保存在 config.h 的 WEB_PASSWORD。'
}

$page = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'control.html'), $utf8)
if ($page.Contains(')A1WEB"')) {
    throw 'HTML 中出现了嵌入分隔符。'
}
$pageHeader = "#pragma once`nconst char CONTROL_PAGE[] PROGMEM = R`"A1WEB($page)A1WEB`";`n"
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'web_page.h'), $pageHeader, $utf8)

if (-not $PrepareOnly) {
    & $ArduinoCli compile --fqbn esp32:esp32:esp32 --build-path $BuildPath $PSScriptRoot
    if ($LASTEXITCODE -ne 0) { throw 'ESP32 固件编译失败。' }
}
