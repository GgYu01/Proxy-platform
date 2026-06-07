<#
Observes WPS Office routing through the local SYSTEM mihomo API on port 9090.

Run this while opening WPS, syncing cloud drive, or checking for updates. It does
not modify system state. Use the SYSTEM mihomo controller (9090), not Clash Verge
(9097), because only SYSTEM mihomo owns TUN transparent proxy traffic.

Dashboard: open http://127.0.0.1:9090/ui/ in a browser, or use Yacd/Metacubex
with external controller 127.0.0.1:9090.
#>

[CmdletBinding()]
param(
    [int]$Seconds = 45,
    [int]$IntervalSeconds = 2
)

$ErrorActionPreference = 'Continue'

function Get-WpsProcesses {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -match '^(wps|wpp|et|wpspdf|wpscloudsvr|ksolaunch|wpsupdate|ksomisc)\.exe$' -or
            $_.ExecutablePath -match 'Kingsoft\\WPS Office' -or
            $_.CommandLine -match 'Kingsoft|WPS Office|wpscloud|kso'
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

function Get-WpsRules {
    try {
        $rules = (Invoke-RestMethod -Uri 'http://127.0.0.1:9090/rules' -Method Get -TimeoutSec 10).rules
        return @($rules | Where-Object {
            $_.payload -match 'wps|kingsoft|kdocs|WPS Office|ksosoft|wpscdn' -or
            ($_.type -match 'Process' -and $_.payload -match 'wps|wpp|et\.exe|wpspdf|wpscloud|ksolaunch|wpsupdate|ksomisc')
        })
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

Write-Host "watch_seconds=$Seconds interval_seconds=$IntervalSeconds controller=127.0.0.1:9090"
Write-Host 'wps_rules:'
Get-WpsRules |
    Select-Object index, type, payload, proxy, @{Name = 'hitCount'; Expression = { Convert-RuleHitCount $_ } } |
    Format-Table -AutoSize

Write-Host 'wps_processes:'
$processes = @(Get-WpsProcesses)
$processes |
    Select-Object ProcessId, ParentProcessId, Name, ExecutablePath |
    Format-Table -AutoSize

while ((Get-Date) -lt $deadline) {
    $processes = @(Get-WpsProcesses)
    $ids = @($processes.ProcessId)

    $mihomoMatches = @(Get-MihomoConnections | Where-Object {
        $_.metadata.processPath -match 'Kingsoft\\WPS Office|wpscloud|office6\\' -or
        $_.metadata.process -match '^(wps|wpp|et|wpspdf|wpscloudsvr|ksolaunch|wpsupdate|ksomisc)\.exe$' -or
        $_.metadata.host -match 'wps\.|kdocs\.|kingsoft|ksosoft|wpscdn'
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
Write-Host 'wps_rules_after:'
Get-WpsRules |
    Select-Object index, type, payload, proxy, @{Name = 'hitCount'; Expression = { Convert-RuleHitCount $_ } } |
    Format-Table -AutoSize
