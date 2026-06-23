<#
Refreshes the SYSTEM mihomo TUN task with the current reviewed profile.

Run from an elevated PowerShell session. This is narrower than
install-mihomo-tun.ps1: it does not install Clash Verge or change the Clash
profile; it only updates the SYSTEM-safe mihomo config path, restarts the
Mihomo TUN task, and verifies the runtime routing guardrails.
#>

[CmdletBinding()]
param(
    [string]$MihomoExe = 'C:\Tools\mihomo\mihomo-windows-amd64.exe',
    [string]$SourceConfigPath = 'C:\ProgramData\mihomo\mihomo-universal.yaml',
    [string]$SafeConfigPath = 'C:\Windows\System32\config\systemprofile\.config\mihomo\mihomo-universal.yaml',
    [string]$TaskName = 'Mihomo TUN Transparent Proxy',
    [int]$WaitSeconds = 8
)

$ErrorActionPreference = 'Stop'
$LogPath = 'C:\ProgramData\mihomo\refresh-mihomo-tun-config.log'
New-Item -ItemType Directory -Path (Split-Path -Parent $LogPath) -Force | Out-Null
Start-Transcript -Path $LogPath -Append | Out-Null

try {
    function Assert-Administrator {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = [Security.Principal.WindowsPrincipal]::new($identity)
        if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
            throw 'Run this script from an elevated PowerShell session. SYSTEM TUN task refresh requires administrator rights.'
        }
    }

    function Get-RuntimeRoutingSummary {
        $runtimeRules = Invoke-RestMethod -Uri 'http://127.0.0.1:9090/rules' -Method Get -TimeoutSec 10
        $runtimeMatch = $runtimeRules.rules | Where-Object { $_.type -eq 'Match' } | Select-Object -Last 1
        $runtimeBadProcessProxyRules = @($runtimeRules.rules | Where-Object {
            $_.proxy -eq 'PROXY' -and
            (Test-ProcessProxyRule -Type $_.type -Payload $_.payload) -and
            -not (Test-AllowedProcessProxyRule -Type $_.type -Payload $_.payload)
        })
        $runtimeAllowedProcessProxyRules = @($runtimeRules.rules | Where-Object {
            $_.proxy -eq 'PROXY' -and
            (Test-AllowedProcessProxyRule -Type $_.type -Payload $_.payload)
        })
        [pscustomobject]@{
            runtime_match_proxy = $runtimeMatch.proxy
            runtime_allowed_process_proxy_count = $runtimeAllowedProcessProxyRules.Count
            runtime_disallowed_process_proxy_count = $runtimeBadProcessProxyRules.Count
            allowed_rules = $runtimeAllowedProcessProxyRules
            bad_rules = $runtimeBadProcessProxyRules
        }
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

    Assert-Administrator

    if (-not (Test-Path -LiteralPath $MihomoExe)) {
        throw "mihomo executable not found: $MihomoExe"
    }
    if (-not (Test-Path -LiteralPath $SourceConfigPath)) {
        throw "source config not found: $SourceConfigPath"
    }

    $safeDir = Split-Path -Parent $SafeConfigPath
    New-Item -ItemType Directory -Path $safeDir -Force | Out-Null
    Copy-Item -LiteralPath $SourceConfigPath -Destination $SafeConfigPath -Force
    Assert-OpenAIDomainProxyGuardrails -Source 'file' -Rules (Convert-ConfigRuleLines -Path $SafeConfigPath)

    Write-Host "Validating config: $SafeConfigPath"
    & $MihomoExe -t -f $SafeConfigPath
    if ($LASTEXITCODE -ne 0) {
        throw "mihomo configuration validation failed with exit code $LASTEXITCODE"
    }

    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Get-Process mihomo-windows-amd64 -ErrorAction SilentlyContinue | Stop-Process -Force

    $action = New-ScheduledTaskAction -Execute $MihomoExe -Argument "-f `"$SafeConfigPath`"" -WorkingDirectory (Split-Path -Parent $MihomoExe)
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

    Start-Sleep -Seconds $WaitSeconds

    $listeners = Get-NetTCPConnection -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalAddress -eq '127.0.0.1' -and $_.LocalPort -in 7890, 9090 }
    Write-Host 'listeners:'
    $listeners | Select-Object LocalAddress, LocalPort, State, OwningProcess | Format-Table -AutoSize

    $summary = Get-RuntimeRoutingSummary
    Write-Host "runtime_match_proxy=$($summary.runtime_match_proxy)"
    Write-Host "runtime_allowed_process_proxy_count=$($summary.runtime_allowed_process_proxy_count)"
    Write-Host "runtime_disallowed_process_proxy_count=$($summary.runtime_disallowed_process_proxy_count)"
    $summary.allowed_rules | Select-Object index, type, payload, proxy | Format-Table -AutoSize
    $summary.bad_rules | Select-Object index, type, payload, proxy | Format-Table -AutoSize
    $runtimeRules = (Invoke-RestMethod -Uri 'http://127.0.0.1:9090/rules' -Method Get -TimeoutSec 10).rules
    Assert-OpenAIDomainProxyGuardrails -Source 'runtime' -Rules $runtimeRules

    if ($summary.runtime_match_proxy -ne 'PROXY') {
        throw "runtime MATCH rule is $($summary.runtime_match_proxy), expected PROXY"
    }
    if ($summary.runtime_disallowed_process_proxy_count -ne 0) {
        throw "runtime still has $($summary.runtime_disallowed_process_proxy_count) disallowed process-level PROXY rules"
    }

    Write-Host 'SYSTEM mihomo TUN runtime now matches the reviewed routing policy.'
} finally {
    Stop-Transcript | Out-Null
}
