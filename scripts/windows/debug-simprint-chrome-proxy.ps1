<#
Proves whether Simprint's launched Chrome profile browser is process-proxied.

Run this after opening a Simprint browser profile. The script uses the profile
browser's Chrome DevTools Protocol port to open one probe tab, then checks the
local mihomo API for connections from:

  C:\Users\*\AppData\Local\Simprint\data\profiles\Chrome *\simprint.exe

It deliberately does not target C:\Users\...\Simprint\simprint.exe,
simprint-runtime.exe, or Simprint's fixed WebView2 UI runtime.
#>

[CmdletBinding()]
param(
    [string]$MihomoController = 'http://127.0.0.1:9090',
    [string]$ProbeUrl = '',
    [int]$PollSeconds = 15,
    [switch]$SkipOpenTab
)

$ErrorActionPreference = 'Stop'

$AllowedProfilePayloads = @(
    'C:\Users\*\AppData\Local\Simprint\data\profiles\Chrome *\chrome_proxy.exe',
    'C:\Users\*\AppData\Local\Simprint\data\profiles\Chrome *\simprint.exe'
)

function Get-MihomoRules {
    return @((Invoke-RestMethod -Uri "$MihomoController/rules" -Method Get -TimeoutSec 10).rules)
}

function Get-MihomoConnections {
    try {
        return @((Invoke-RestMethod -Uri "$MihomoController/connections" -Method Get -TimeoutSec 5).connections)
    } catch {
        Write-Host "mihomo_connections_error=$($_.Exception.Message)"
        return @()
    }
}

function Get-RuleHitCount {
    param($Rule)

    if ($Rule.extra -and $null -ne $Rule.extra.hitCount) {
        return [int64]$Rule.extra.hitCount
    }
    return 0
}

function Test-AllowedSimprintProfilePayload {
    param([string]$Payload = '')

    return $AllowedProfilePayloads -contains $Payload
}

function Get-SimprintChromeProfileProcess {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.ExecutablePath -like "$env:LOCALAPPDATA\Simprint\data\profiles\Chrome *\simprint.exe" -and
            $_.CommandLine -match '--remote-debugging-port=(\d+)'
        } |
        Select-Object -First 1
}

function Get-SimprintProcessInventory {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -match 'simprint|msedgewebview2|chrome_proxy|chrome' -and
            ($_.ExecutablePath -match 'Simprint' -or $_.CommandLine -match 'Simprint|simprint')
        } |
        Select-Object ProcessId, ParentProcessId, Name, ExecutablePath
}

function Get-HostNameForUrl {
    param([Parameter(Mandatory)] [string]$Url)

    return ([Uri]$Url).Host
}

function Open-SimprintProbeTab {
    param(
        [Parameter(Mandatory)] [int]$Port,
        [Parameter(Mandatory)] [string]$Url
    )

    $encoded = [uri]::EscapeDataString($Url)
    return Invoke-RestMethod -Method Put -Uri "http://127.0.0.1:$Port/json/new?$encoded" -TimeoutSec 8
}

function Get-SimprintProfileProxyRules {
    Get-MihomoRules |
        Where-Object { $_.proxy -eq 'PROXY' -and (Test-AllowedSimprintProfilePayload -Payload $_.payload) }
}

if (-not $ProbeUrl) {
    $ProbeUrl = 'https://chat.qwen.ai/?codex_simprint_proxy_probe=' + (Get-Date -Format 'yyyyMMddHHmmss')
}
$probeHost = Get-HostNameForUrl -Url $ProbeUrl

$profileProcess = Get-SimprintChromeProfileProcess
if (-not $profileProcess) {
    Write-Host 'simprint_chrome_profile_found=false'
    Write-Host 'Open a Simprint Chrome profile browser first, then rerun this script.'
    Write-Host 'simprint_process_inventory:'
    Get-SimprintProcessInventory | Format-Table -AutoSize
    exit 2
}

$cdpPort = [int]([regex]::Match($profileProcess.CommandLine, '--remote-debugging-port=(\d+)').Groups[1].Value)

Write-Host 'simprint_process_inventory:'
Get-SimprintProcessInventory | Format-Table -AutoSize
Write-Host "simprint_chrome_profile_found=true"
Write-Host "simprint_chrome_profile_pid=$($profileProcess.ProcessId)"
Write-Host "simprint_chrome_profile_path=$($profileProcess.ExecutablePath)"
Write-Host "cdp_port=$cdpPort"
Write-Host "probe_url=$ProbeUrl"
Write-Host "probe_host=$probeHost"

try {
    Invoke-RestMethod -Uri "http://127.0.0.1:$cdpPort/json/version" -TimeoutSec 5 |
        Select-Object Browser, webSocketDebuggerUrl |
        Format-List
} catch {
    throw "Simprint profile CDP port $cdpPort is not reachable: $($_.Exception.Message)"
}

$beforeRules = @(Get-SimprintProfileProxyRules)
$beforeHits = @{}
foreach ($rule in $beforeRules) {
    $beforeHits[[string]$rule.index] = Get-RuleHitCount -Rule $rule
}

if (-not $SkipOpenTab) {
    Write-Host 'opening_probe_tab=true'
    Open-SimprintProbeTab -Port $cdpPort -Url $ProbeUrl |
        Select-Object id, type, url |
        Format-List
} else {
    Write-Host 'opening_probe_tab=false'
}

$observed = New-Object System.Collections.Generic.List[object]
$deadline = (Get-Date).AddSeconds($PollSeconds)
while ((Get-Date) -lt $deadline) {
    foreach ($connection in (Get-MihomoConnections)) {
        $processPath = [string]$connection.metadata.processPath
        $processName = [string]$connection.metadata.process
        $hostName = [string]$connection.metadata.host
        $isSimprintProfile = (
            $processPath -like '*\Simprint\data\profiles\Chrome *\simprint.exe' -or
            $processPath -like '*\Simprint\data\profiles\Chrome *\chrome_proxy.exe'
        )
        $isProbeHost = $hostName -eq $probeHost -or $hostName -like "*.$probeHost"

        if ($isSimprintProfile -and $isProbeHost) {
            $observed.Add([pscustomobject]@{
                Time = (Get-Date).ToString('s')
                Process = $processName
                Path = $processPath
                Host = $hostName
                Rule = $connection.rule
                RulePayload = $connection.rulePayload
                Chains = ($connection.chains -join '>')
                Remote = $connection.metadata.remoteDestination
            })
        }
    }
    Start-Sleep -Milliseconds 300
}

$afterRules = @(Get-SimprintProfileProxyRules)
$deltas = foreach ($rule in $afterRules) {
    $before = 0
    if ($beforeHits.ContainsKey([string]$rule.index)) {
        $before = [int64]$beforeHits[[string]$rule.index]
    }
    $after = Get-RuleHitCount -Rule $rule
    [pscustomobject]@{
        index = $rule.index
        type = $rule.type
        payload = $rule.payload
        proxy = $rule.proxy
        before = $before
        after = $after
        delta = $after - $before
    }
}

Write-Host ''
Write-Host 'simprint_profile_proxy_rule_deltas:'
$deltas | Format-Table -AutoSize

Write-Host ''
Write-Host 'observed_simprint_profile_probe_connections:'
$observed |
    Sort-Object Process, Path, Host, Rule, RulePayload, Chains, Remote -Unique |
    Format-List

$matchedProcessRule = @($observed | Where-Object {
    $_.Rule -match 'ProcessPath' -and
    (Test-AllowedSimprintProfilePayload -Payload $_.RulePayload) -and
    $_.Chains -match '(^|>)PROXY($|>)'
})
$deltaHit = @($deltas | Where-Object {
    $_.payload -eq 'C:\Users\*\AppData\Local\Simprint\data\profiles\Chrome *\simprint.exe' -and
    $_.delta -gt 0
})

if ($matchedProcessRule.Count -gt 0 -or $deltaHit.Count -gt 0) {
    Write-Host 'result=PASS'
    Write-Host 'reason=Simprint launched Chrome profile process matched the narrow ProcessPathWildcard PROXY rule.'
    exit 0
}

Write-Host 'result=CHECK'
Write-Host 'reason=No probe connection was observed through the narrow Simprint Chrome profile PROXY rule.'
exit 1
