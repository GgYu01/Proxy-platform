<#
Observes Simprint process routing through the local mihomo API.

Run this while opening or refreshing a page inside Simprint. It does not modify
system state. The expected proxied processes are Simprint's Chrome profile
browser launchers, not C:\Users\...\Simprint\simprint.exe,
simprint-runtime.exe, or the fixed WebView2 UI runtime.
#>

[CmdletBinding()]
param(
    [int]$Seconds = 45,
    [int]$IntervalSeconds = 2
)

$ErrorActionPreference = 'Continue'

function Get-SimprintProcesses {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -match 'simprint|msedgewebview2|chrome_proxy|chrome' -and
            ($_.ExecutablePath -match 'Simprint' -or $_.CommandLine -match 'Simprint|simprint')
        } |
        Select-Object ProcessId, ParentProcessId, Name, ExecutablePath, CommandLine
}

function Get-MihomoConnections {
    try {
        return @((Invoke-RestMethod -Uri 'http://127.0.0.1:9090/connections' -Method Get -TimeoutSec 5).connections)
    } catch {
        Write-Host "mihomo_connections_error=$($_.Exception.Message)"
        return @()
    }
}

function Get-SimprintRules {
    try {
        $rules = (Invoke-RestMethod -Uri 'http://127.0.0.1:9090/rules' -Method Get -TimeoutSec 10).rules
        return @($rules | Where-Object { $_.payload -match 'Simprint|chrome_proxy|Chrome \*' })
    } catch {
        Write-Host "mihomo_rules_error=$($_.Exception.Message)"
        return @()
    }
}

function Convert-RuleHitCount {
    param($Rule)

    if ($Rule.extra -and $null -ne $Rule.extra.hitCount) {
        return $Rule.extra.hitCount
    }
    return $null
}

$deadline = (Get-Date).AddSeconds($Seconds)
$observed = New-Object System.Collections.Generic.List[object]

Write-Host "watch_seconds=$Seconds interval_seconds=$IntervalSeconds"
Write-Host 'simprint_rules:'
Get-SimprintRules |
    Select-Object index, type, payload, proxy, @{Name = 'hitCount'; Expression = { Convert-RuleHitCount $_ } } |
    Format-Table -AutoSize

Write-Host 'simprint_processes:'
$processes = @(Get-SimprintProcesses)
$processes |
    Select-Object ProcessId, ParentProcessId, Name, ExecutablePath |
    Format-Table -AutoSize

while ((Get-Date) -lt $deadline) {
    $processes = @(Get-SimprintProcesses)
    $ids = @($processes.ProcessId)

    $mihomoMatches = @(Get-MihomoConnections | Where-Object {
        $_.metadata.processPath -match 'Simprint|webview-fixed|data\\profiles\\Chrome' -or
        $_.metadata.process -match 'simprint|msedgewebview2|chrome_proxy|chrome'
    })

    $tcpMatches = @()
    if ($ids.Count -gt 0) {
        $tcpMatches = @(Get-NetTCPConnection -ErrorAction SilentlyContinue | Where-Object {
            $ids -contains $_.OwningProcess -and $_.RemoteAddress -and $_.RemoteAddress -ne '0.0.0.0' -and $_.RemoteAddress -ne '::'
        })
    }

    foreach ($conn in $mihomoMatches) {
        $observed.Add([pscustomobject]@{
            Source = 'mihomo'
            Time = (Get-Date).ToString('s')
            Process = $conn.metadata.process
            Path = $conn.metadata.processPath
            Host = $conn.metadata.host
            Rule = $conn.rule
            RulePayload = $conn.rulePayload
            Chains = ($conn.chains -join '>')
            Remote = $conn.metadata.remoteDestination
        })
    }
    foreach ($conn in $tcpMatches) {
        $proc = $processes | Where-Object { $_.ProcessId -eq $conn.OwningProcess } | Select-Object -First 1
        $observed.Add([pscustomobject]@{
            Source = 'tcp'
            Time = (Get-Date).ToString('s')
            Process = $proc.Name
            Path = $proc.ExecutablePath
            Host = ''
            Rule = $conn.State
            RulePayload = ''
            Chains = ''
            Remote = "$($conn.RemoteAddress):$($conn.RemotePort)"
        })
    }

    Start-Sleep -Seconds $IntervalSeconds
}

Write-Host ''
Write-Host "observed_count=$($observed.Count)"
if ($observed.Count -gt 0) {
    $observed |
        Sort-Object Time, Source, Process, Host, Remote -Unique |
        Format-List
}

Write-Host ''
Write-Host 'simprint_rules_after:'
Get-SimprintRules |
    Select-Object index, type, payload, proxy, @{Name = 'hitCount'; Expression = { Convert-RuleHitCount $_ } } |
    Format-Table -AutoSize
