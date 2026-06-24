<#
Installs and starts Windows mihomo TUN plus Clash Verge Rev with elevated
startup defaults. Run this script from an elevated PowerShell session.
#>

[CmdletBinding()]
param(
    [string]$MihomoExe = 'C:\Tools\mihomo\mihomo-windows-amd64.exe',
    [string]$ConfigPath = 'C:\ProgramData\mihomo\mihomo-universal.yaml',
    [string]$SubscriptionUrl = 'https://subs.sea.prod.gglohh.top/subscriptions/mihomo-universal.yaml',
    [string]$MihomoTaskName = 'Mihomo TUN Transparent Proxy',
    [string]$ClashTaskName = 'Clash Verge Rev Admin Startup',
    [string]$ClashExe = 'C:\Program Files\Clash Verge\clash-verge.exe',
    [string]$ClashServiceInstallExe = 'C:\Program Files\Clash Verge\resources\clash-verge-service-install.exe'
)

$ErrorActionPreference = 'Stop'

$LogPath = 'C:\ProgramData\mihomo\install-mihomo-tun.log'
New-Item -ItemType Directory -Path (Split-Path -Parent $LogPath) -Force | Out-Null
Start-Transcript -Path $LogPath -Append | Out-Null

try {
    function Assert-Administrator {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = [Security.Principal.WindowsPrincipal]::new($identity)
        if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
            throw 'This script must be run from an elevated PowerShell session because TUN and Clash service setup require administrator rights.'
        }
    }

    function Stop-ProxyProcesses {
        Get-Process mihomo-windows-amd64, clash-verge, verge-mihomo -ErrorAction SilentlyContinue | Stop-Process -Force
    }

    function Register-SystemStartupTask {
        param(
            [Parameter(Mandatory)] [string]$TaskName,
            [Parameter(Mandatory)] [string]$Execute,
            [string]$Arguments = '',
            [string]$WorkingDirectory = ''
        )

        $actionArgs = @{ Execute = $Execute }
        if ($Arguments) { $actionArgs.Argument = $Arguments }
        if ($WorkingDirectory) { $actionArgs.WorkingDirectory = $WorkingDirectory }

        $action = New-ScheduledTaskAction @actionArgs
        $trigger = New-ScheduledTaskTrigger -AtStartup
        $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries `
            -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
            -RestartCount 3 `
            -RestartInterval (New-TimeSpan -Minutes 1)

        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
        Start-ScheduledTask -TaskName $TaskName
    }

    function Register-UserLogonAdminTask {
        param(
            [Parameter(Mandatory)] [string]$TaskName,
            [Parameter(Mandatory)] [string]$Execute,
            [string]$Arguments = '',
            [string]$WorkingDirectory = ''
        )

        $user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        $actionArgs = @{ Execute = $Execute }
        if ($Arguments) { $actionArgs.Argument = $Arguments }
        if ($WorkingDirectory) { $actionArgs.WorkingDirectory = $WorkingDirectory }

        $action = New-ScheduledTaskAction @actionArgs
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
        $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
        Start-ScheduledTask -TaskName $TaskName
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
        Assert-OpenAIDomainProxyGuardrails -Source 'file' -Rules (Convert-ConfigRuleLines -Path $Path)
    }

    function Write-RuntimeRoutingSummary {
        try {
            $runtimeRules = (Invoke-RestMethod -Uri 'http://127.0.0.1:9090/rules' -Method Get -TimeoutSec 10).rules
            $runtimeBadProcessProxyRules = @($runtimeRules | Where-Object {
                $_.proxy -eq 'PROXY' -and
                (Test-ProcessProxyRule -Type $_.type -Payload $_.payload) -and
                -not (Test-AllowedProcessProxyRule -Type $_.type -Payload $_.payload)
            })
            $runtimeAllowedProcessProxyRules = @($runtimeRules | Where-Object {
                $_.proxy -eq 'PROXY' -and
                (Test-AllowedProcessProxyRule -Type $_.type -Payload $_.payload)
            })
            Write-Host "runtime_allowed_process_proxy_count=$($runtimeAllowedProcessProxyRules.Count)"
            Write-Host "runtime_disallowed_process_proxy_count=$($runtimeBadProcessProxyRules.Count)"
            $runtimeAllowedProcessProxyRules | Select-Object index, type, payload, proxy | Format-Table -AutoSize
            Assert-OpenAIDomainProxyGuardrails -Source 'runtime' -Rules $runtimeRules
            if ($runtimeBadProcessProxyRules.Count -gt 0) {
                $runtimeBadProcessProxyRules | Select-Object index, type, payload, proxy | Format-Table -AutoSize
                throw "runtime still has $($runtimeBadProcessProxyRules.Count) disallowed process-level PROXY rules"
            }
        } catch {
            Write-Warning "runtime routing summary failed: $($_.Exception.Message)"
        }
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

        Set-Content -LiteralPath (Join-Path $ClashConfigRoot 'clash-verge.yaml') -Value $profile -Encoding UTF8
        Set-Content -LiteralPath (Join-Path $ClashConfigRoot 'clash-verge-check.yaml') -Value $profile -Encoding UTF8
    }

    function Configure-ClashVergeProfile {
        param([Parameter(Mandatory)] [string]$SourceConfigPath)

        $base = Join-Path $env:APPDATA 'io.github.clash-verge-rev.clash-verge-rev'
        if (-not (Test-Path -LiteralPath $base)) {
            Write-Host "Clash Verge config directory not found yet: $base"
            return
        }

        $profilesDir = Join-Path $base 'profiles'
        New-Item -ItemType Directory -Path $profilesDir -Force | Out-Null
        Copy-Item -LiteralPath $SourceConfigPath -Destination (Join-Path $profilesDir 'mihomo-universal.yaml') -Force
        Write-ClashCoreProfile -SourceConfigPath $SourceConfigPath -ClashConfigRoot $base

        @"
# Clash Verge

current: mihomo-universal
items:
- uid: mihomo-universal
  type: local
  name: mihomo-universal
  file: mihomo-universal.yaml
  desc: Universal mihomo config from https://subs.sea.prod.gglohh.top/subscriptions/mihomo-universal.yaml
  updated: 1780574400
"@ | Set-Content -LiteralPath (Join-Path $base 'profiles.yaml') -Encoding UTF8

        Set-ClashVergeTunDisabled -ClashConfigRoot $base
        Update-ClashRuntimeConfig -ClashConfigRoot $base
    }

    function Sync-MihomoSafeConfig {
        param([Parameter(Mandatory)] [string]$SourceConfigPath)

        $safeDir = 'C:\Windows\System32\config\systemprofile\.config\mihomo'
        $safeConfigPath = Join-Path $safeDir 'mihomo-universal.yaml'
        New-Item -ItemType Directory -Path $safeDir -Force | Out-Null
        Copy-Item -LiteralPath $SourceConfigPath -Destination $safeConfigPath -Force
        return $safeConfigPath
    }

    Assert-Administrator

    if (-not (Test-Path -LiteralPath $MihomoExe)) {
        throw "mihomo executable not found: $MihomoExe"
    }

    $configDir = Split-Path -Parent $ConfigPath
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null

    Write-Host "Downloading subscription: $SubscriptionUrl"
    curl.exe -fsSL $SubscriptionUrl -o $ConfigPath
    if ($LASTEXITCODE -ne 0) {
        throw "subscription download failed with exit code $LASTEXITCODE"
    }

    Write-Host 'Validating mihomo configuration'
    & $MihomoExe -t -f $ConfigPath
    if ($LASTEXITCODE -ne 0) {
        throw "mihomo configuration validation failed with exit code $LASTEXITCODE"
    }
    Assert-PolicyFileGuardrails -Path $ConfigPath

    Stop-ProxyProcesses
    Configure-ClashVergeProfile -SourceConfigPath $ConfigPath
    $safeConfigPath = Sync-MihomoSafeConfig -SourceConfigPath $ConfigPath

    Write-Host "Registering elevated mihomo startup task: $MihomoTaskName"
    Register-SystemStartupTask -TaskName $MihomoTaskName -Execute $MihomoExe -Arguments "-f `"$safeConfigPath`"" -WorkingDirectory (Split-Path -Parent $MihomoExe)

    if (Test-Path -LiteralPath $ClashServiceInstallExe) {
        Write-Host "Installing Clash Verge service: $ClashServiceInstallExe"
        & $ClashServiceInstallExe
        Write-Host "Clash service installer exit code: $LASTEXITCODE"
    } else {
        Write-Host "Clash service installer not found: $ClashServiceInstallExe"
    }

    if (Test-Path -LiteralPath $ClashExe) {
        Write-Host "Registering elevated Clash Verge logon task: $ClashTaskName"
        Register-UserLogonAdminTask -TaskName $ClashTaskName -Execute $ClashExe -WorkingDirectory (Split-Path -Parent $ClashExe)
    } else {
        Write-Host "Clash Verge executable not found: $ClashExe"
    }

    Start-Sleep -Seconds 10

    $mihomoProc = Get-Process mihomo-windows-amd64 -ErrorAction SilentlyContinue | Select-Object -First 1
    $clashProc = Get-Process clash-verge -ErrorAction SilentlyContinue | Select-Object -First 1
    $listeners = Get-NetTCPConnection -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in 7890, 7897, 9090, 9097, 1053 }
    $tunAdapters = Get-NetAdapter | Where-Object {
        $_.Name -match 'tun|tap|wintun|clash|mihomo|meta|verge' -or
        $_.InterfaceDescription -match 'tun|tap|wintun|clash|mihomo|meta|verge'
    }

    Write-Host 'processes:'
    $mihomoProc, $clashProc | Where-Object { $_ } | Select-Object Id, ProcessName, Path | Format-Table -AutoSize
    Write-Host 'listeners:'
    $listeners | Select-Object LocalAddress, LocalPort, State, OwningProcess | Format-Table -AutoSize
    Write-Host 'tun adapters:'
    $tunAdapters | Select-Object Name, InterfaceDescription, Status | Format-Table -AutoSize
    Write-Host 'runtime routing guardrails:'
    Write-RuntimeRoutingSummary

    Write-Host 'mihomo proxy egress:'
    curl.exe -fsSL --proxy http://127.0.0.1:7890 https://api.ipify.org
    Write-Host ''

    if (-not $tunAdapters) {
        throw 'No TUN/Wintun adapter was detected. Check this transcript and Clash Verge service status.'
    }

    Write-Host 'Elevated mihomo TUN and Clash Verge admin startup defaults are installed and running.'
} finally {
    Stop-Transcript | Out-Null
}
