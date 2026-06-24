<#
Applies the reviewed mihomo routing policy across local Windows runtime files.

Run from an elevated PowerShell session. This is the single admin entrypoint for
the current policy:
- China/private traffic is DIRECT.
- Non-mainland fallback traffic uses PROXY.
- Edge Beta, Cursor, QQ, WeChat, WebView2, node, Code, and app-embedded
  browsers are not broadly process-proxied.
- Simprint Chrome profile and selected AI/developer app install paths are the
  only process-level PROXY overrides.
#>

[CmdletBinding()]
param(
    [string]$WorkspaceRoot = '',
    [string]$ProgramDataConfig = 'C:\ProgramData\mihomo\mihomo-universal.yaml',
    [string]$ClashConfigRoot = (Join-Path $env:APPDATA 'io.github.clash-verge-rev.clash-verge-rev'),
    [switch]$SkipClashRuntimeFiles
)

$ErrorActionPreference = 'Stop'

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run this script from an elevated PowerShell session.'
    }
}

function Resolve-SourceConfig {
    $candidates = @(
        (Join-Path $WorkspaceRoot 'repos\proxy_ops_private\generated\subscriptions\mihomo-universal.yaml'),
        (Join-Path $WorkspaceRoot 'generated\subscriptions\mihomo-universal.yaml'),
        $ProgramDataConfig
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw "No mihomo-universal.yaml source config found. Checked: $($candidates -join ', ')"
}

function Test-ProcessProxyRule {
    param(
        [string]$Type = '',
        [string]$Payload = ''
    )

    return $Type -match '^Process(Name|Path)' -or $Type -match '^PROCESS-(NAME|PATH)'
}

function Test-AllowedProcessProxyRule {
    param(
        [string]$Type = '',
        [string]$Payload = ''
    )

    if ($Type -notmatch '^ProcessPath' -and $Type -notmatch '^PROCESS-PATH') {
        return $false
    }

    $allowedPayloads = @(
        'C:\Users\*\AppData\Local\Simprint\data\profiles\Chrome *\chrome_proxy.exe',
        'C:\Users\*\AppData\Local\Simprint\data\profiles\Chrome *\simprint.exe',
        'C:\Program Files\Google\Antigravity\*',
        'C:\Program Files\Google\Antigravity*\*',
        'C:\Users\*\AppData\Local\Programs\Antigravity\*',
        '/Applications/Antigravity.app/Contents/*',
        '/Users/*/Applications/Antigravity.app/Contents/*',
        '/Applications/Microsoft Edge.app/Contents/*',
        '/Users/*/Applications/Microsoft Edge.app/Contents/*',
        '/opt/Antigravity/*',
        '/opt/antigravity/*',
        '/usr/bin/antigravity*'
    )
    return $allowedPayloads -contains $Payload
}

function Get-ExpectedOpenAIDomainProxyPayloads {
    return @(
        'openai.com',
        'chatgpt.com',
        'oaistatic.com',
        'oaiusercontent.com',
        'oaistatsig.com',
        'auth.openai.com',
        'auth0.openai.com',
        'cdn.openaimerge.com'
    )
}

function Convert-ConfigRuleLines {
    param([Parameter(Mandatory)] [string]$Path)

    return @(
        Select-String -Path $Path -Pattern '^\s*-\s*([^,]+),(.+),([^,]+)\s*$' -ErrorAction SilentlyContinue |
            ForEach-Object {
                [pscustomobject]@{
                    index = $_.LineNumber
                    type = $_.Matches[0].Groups[1].Value
                    payload = $_.Matches[0].Groups[2].Value
                    proxy = $_.Matches[0].Groups[3].Value
                }
            }
    )
}

function Assert-OpenAIDomainProxyGuardrails {
    param(
        [Parameter(Mandatory)] [string]$Source,
        [Parameter(Mandatory)] [array]$Rules
    )

    $expectedPayloads = Get-ExpectedOpenAIDomainProxyPayloads
    $domainProxyRules = @($Rules | Where-Object {
        $_.proxy -eq 'PROXY' -and
        ($_.type -eq 'DomainSuffix' -or $_.type -eq 'DOMAIN-SUFFIX') -and
        ($expectedPayloads -contains [string]$_.payload)
    })
    $forbiddenKeywordRules = @($Rules | Where-Object {
        ($_.type -eq 'DomainKeyword' -or $_.type -eq 'DOMAIN-KEYWORD') -and
        ([string]$_.payload).ToLowerInvariant() -in @('openai', 'codex', 'openaiapi')
    })

    Write-Host "${Source}_openai_domain_proxy_count=$($domainProxyRules.Count)"
    Write-Host "${Source}_forbidden_openai_keyword_count=$($forbiddenKeywordRules.Count)"
    if ($domainProxyRules.Count -ne $expectedPayloads.Count) {
        throw "${Source} missing official OpenAI domain PROXY rules: found $($domainProxyRules.Count), expected $($expectedPayloads.Count)"
    }
    if ($forbiddenKeywordRules.Count -gt 0) {
        $forbiddenKeywordRules | Select-Object index, type, payload, proxy | Format-Table -AutoSize
        throw "${Source} contains forbidden broad OpenAI keyword rules"
    }
}

function Assert-PolicyFileGuardrails {
    param([Parameter(Mandatory)] [string]$Path)

    $badProcessProxyRules = @(
        Select-String -Path $Path -Pattern '^\s*-\s*([^,]+),(.+),PROXY\s*$' -ErrorAction SilentlyContinue |
            Where-Object {
                $ruleType = $_.Matches[0].Groups[1].Value
                $payload = $_.Matches[0].Groups[2].Value
                (Test-ProcessProxyRule -Type $ruleType -Payload $payload) -and
                -not (Test-AllowedProcessProxyRule -Type $ruleType -Payload $payload)
            }
    )
    if ($badProcessProxyRules.Count -gt 0) {
        $badProcessProxyRules | Select-Object LineNumber, Line | Format-Table -AutoSize
        throw "found $($badProcessProxyRules.Count) disallowed process-level PROXY rules in $Path"
    }

    $matchRule = Select-String -Path $Path -Pattern '^\s*-\s*MATCH,PROXY\s*$' -ErrorAction SilentlyContinue |
        Select-Object -Last 1
    if (-not $matchRule) {
        throw "missing final mainland fallback rule MATCH,PROXY in $Path"
    }
    Assert-OpenAIDomainProxyGuardrails -Source 'file' -Rules (Convert-ConfigRuleLines -Path $Path)
}

function Set-YamlScalarValue {
    param(
        [Parameter(Mandatory)] [string]$Text,
        [Parameter(Mandatory)] [string]$Key,
        [Parameter(Mandatory)] [string]$Value
    )

    if ($Text -match "(?m)^$([regex]::Escape($Key)):\s*.+$") {
        return [regex]::Replace($Text, "(?m)^$([regex]::Escape($Key)):\s*.+$", "$Key`: $Value")
    }
    return $Text.TrimEnd() + "`r`n$Key`: $Value`r`n"
}

function Set-ClashVergeTunDisabled {
    param([Parameter(Mandatory)] [string]$ClashConfigRoot)

    $vergePath = Join-Path $ClashConfigRoot 'verge.yaml'
    if (-not (Test-Path -LiteralPath $vergePath)) {
        return
    }

    $verge = Get-Content -LiteralPath $vergePath -Raw
    $desiredValues = [ordered]@{
        'tun_tray_icon' = 'false'
        'enable_tun_mode' = 'false'
        'enable_system_proxy' = 'false'
        'enable_proxy_guard' = 'true'
        'enable_auto_launch' = 'true'
        'enable_silent_start' = 'true'
        'verge_mixed_port' = '7897'
        'verge_socks_port' = '7898'
        'verge_port' = '7899'
        'enable_external_controller' = 'false'
    }
    foreach ($key in $desiredValues.Keys) {
        $verge = Set-YamlScalarValue -Text $verge -Key $key -Value $desiredValues[$key]
    }
    Set-Content -LiteralPath $vergePath -Value $verge -Encoding UTF8
    Write-Host "clash_verge_tun_mode=disabled file=$vergePath"
}

function Update-ClashRuntimeConfig {
    param([Parameter(Mandatory)] [string]$ClashConfigRoot)

    $configPath = Join-Path $ClashConfigRoot 'config.yaml'
    @"
# Generated by proxy-platform. SYSTEM mihomo owns TUN; Clash Verge stays on GUI/service ports.
mixed-port: 7897
socks-port: 7898
port: 7899
log-level: info
allow-lan: false
ipv6: false
mode: rule
external-controller: 127.0.0.1:9097
external-controller-pipe: \\.\pipe\verge-mihomo
tun:
  enable: false
secret: set-your-secret
external-controller-cors:
  allow-private-network: true
  allow-origins:
  - tauri://localhost
  - http://tauri.localhost
  - https://yacd.metacubex.one
  - https://metacubex.github.io
  - https://board.zash.run.place
unified-delay: true
"@ | Set-Content -LiteralPath $configPath -Encoding UTF8
    Write-Host "clash_runtime_tun_enable=false file=$configPath"
}

function Write-ClashCoreProfile {
    param(
        [Parameter(Mandatory)] [string]$SourceConfigPath,
        [Parameter(Mandatory)] [string]$ClashConfigRoot
    )

    $profile = Get-Content -LiteralPath $SourceConfigPath -Raw
    $profile = Set-YamlScalarValue -Text $profile -Key 'mixed-port' -Value '7897'
    $profile = Set-YamlScalarValue -Text $profile -Key 'external-controller' -Value '127.0.0.1:9097'
    if ($profile -notmatch '(?m)^external-controller-pipe:') {
        $profile = [regex]::Replace(
            $profile,
            '(?m)^(external-controller:\s*127\.0\.0\.1:9097\s*)$',
            "`$1`r`nexternal-controller-pipe: \\.\pipe\verge-mihomo",
            1
        )
    }
    $profile = $profile -replace '(?m)(^tun:\s*\r?\n\s+enable:\s*)true', '${1}false'
    $profile = $profile -replace '(?m)(^dns:\s*\r?\n\s+enable:\s*)true', '${1}false'

    $runtimePath = Join-Path $ClashConfigRoot 'clash-verge.yaml'
    $checkPath = Join-Path $ClashConfigRoot 'clash-verge-check.yaml'
    Set-Content -LiteralPath $runtimePath -Value $profile -Encoding UTF8
    Set-Content -LiteralPath $checkPath -Value $profile -Encoding UTF8
    Write-Host "clash_core_profile=$runtimePath"
}

function Restart-ClashVergeServiceRuntime {
    Get-Process verge-mihomo -ErrorAction SilentlyContinue | Stop-Process -Force
    $service = Get-Service -Name 'clash_verge_service' -ErrorAction SilentlyContinue
    if ($service) {
        Restart-Service -Name 'clash_verge_service' -Force
        Start-Sleep -Seconds 5
    }
}

Assert-Administrator

if (-not $WorkspaceRoot) {
    $WorkspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}

$sourceConfig = Resolve-SourceConfig
Write-Host "source_config=$sourceConfig"
Assert-PolicyFileGuardrails -Path $sourceConfig

New-Item -ItemType Directory -Path (Split-Path -Parent $ProgramDataConfig) -Force | Out-Null
if ((Resolve-Path -LiteralPath $sourceConfig).Path -ne (Resolve-Path -LiteralPath $ProgramDataConfig -ErrorAction SilentlyContinue).Path) {
    Copy-Item -LiteralPath $sourceConfig -Destination $ProgramDataConfig -Force
}
Write-Host "programdata_config=$ProgramDataConfig"

if (Test-Path -LiteralPath $ClashConfigRoot) {
    $profilesDir = Join-Path $ClashConfigRoot 'profiles'
    New-Item -ItemType Directory -Path $profilesDir -Force | Out-Null
    Copy-Item -LiteralPath $ProgramDataConfig -Destination (Join-Path $profilesDir 'mihomo-universal.yaml') -Force
    Write-Host "clash_profile_config=$(Join-Path $profilesDir 'mihomo-universal.yaml')"
    Set-ClashVergeTunDisabled -ClashConfigRoot $ClashConfigRoot
    Update-ClashRuntimeConfig -ClashConfigRoot $ClashConfigRoot

    if (-not $SkipClashRuntimeFiles) {
        Write-ClashCoreProfile -SourceConfigPath $ProgramDataConfig -ClashConfigRoot $ClashConfigRoot
        Write-Host "clash_runtime_config=$(Join-Path $ClashConfigRoot 'clash-verge.yaml')"
    }
    Restart-ClashVergeServiceRuntime
} else {
    Write-Host "Clash config root not found, skipped: $ClashConfigRoot"
}

$refreshScript = Join-Path $PSScriptRoot 'refresh-mihomo-tun-config.ps1'
$verifyScript = Join-Path $PSScriptRoot 'verify-mihomo-windows.ps1'

Write-Host 'refreshing SYSTEM mihomo TUN runtime...'
& $refreshScript -SourceConfigPath $ProgramDataConfig

Write-Host 'verifying local routing policy...'
& $verifyScript -ConfigPath $ProgramDataConfig
if ($LASTEXITCODE -ne 0) {
    throw "verify-mihomo-windows.ps1 failed with exit code $LASTEXITCODE"
}

Write-Host ''
Write-Host 'Expected success markers from verify script:'
Write-Host 'verification_verdict=PASS'
Write-Host 'file_disallowed_process_proxy_count=0'
Write-Host 'runtime_disallowed_process_proxy_count=0'
Write-Host 'clash_pipe_disallowed_process_proxy_count=0'
