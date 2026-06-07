<#
Refreshes the reviewed mihomo routing policy and verifies Simprint-specific
browser routing.

Run from an elevated PowerShell session. This script deliberately does not add
PROCESS-NAME rules for simprint.exe, simprint-runtime.exe, or msedgewebview2.exe.
Only reviewed app install paths may use process-level PROXY: Simprint's Chrome
profile browser, Antigravity, ChatGPT, ChatGPT Atlas, and Codex. Comment those
lines out in the profile to route an app by destination rules only.
#>

[CmdletBinding()]
param(
    [string]$WorkspaceRoot = '',
    [int]$WatchSeconds = 60,
    [switch]$SkipWatch,
    [switch]$IncludeWingetCheck
)

$ErrorActionPreference = 'Stop'

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run this script from an elevated PowerShell session.'
    }
}

function Write-Section {
    param([string]$Title)
    Write-Host ''
    Write-Host "=== $Title ==="
}

function Get-ProxyClientUninstallEntries {
    $roots = @(
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    Get-ItemProperty -Path $roots -ErrorAction SilentlyContinue |
        Where-Object {
            $_.DisplayName -match 'Hiddify|ProxyBridge' -or
            $_.InstallLocation -match 'Hiddify|ProxyBridge' -or
            $_.UninstallString -match 'Hiddify|ProxyBridge'
        } |
        Select-Object DisplayName, DisplayVersion, Publisher, InstallLocation, UninstallString
}

function Get-ProxyClientAppxPackages {
    try {
        return @(Get-AppxPackage -AllUsers -ErrorAction Stop | Where-Object {
            $_.Name -match 'Hiddify|ProxyBridge' -or $_.PackageFullName -match 'Hiddify|ProxyBridge'
        })
    } catch {
        Write-Warning "AllUsers Appx query failed, falling back to current user: $($_.Exception.Message)"
        return @(Get-AppxPackage -ErrorAction SilentlyContinue | Where-Object {
            $_.Name -match 'Hiddify|ProxyBridge' -or $_.PackageFullName -match 'Hiddify|ProxyBridge'
        })
    }
}

function Assert-NoProcessProxyRules {
    $rules = (Invoke-RestMethod -Uri 'http://127.0.0.1:9090/rules' -TimeoutSec 10).rules
    $badRules = @($rules | Where-Object {
        $_.proxy -eq 'PROXY' -and
        (Test-ProcessProxyRule -Type $_.type -Payload $_.payload) -and
        -not (Test-AllowedProcessProxyRule -Type $_.type -Payload $_.payload)
    })
    $allowedRules = @($rules | Where-Object {
        $_.proxy -eq 'PROXY' -and
        (Test-AllowedProcessProxyRule -Type $_.type -Payload $_.payload)
    })
    if ($badRules.Count -gt 0) {
        $badRules | Select-Object index, type, payload, proxy | Format-Table -AutoSize
        throw "found $($badRules.Count) disallowed process-level PROXY rules"
    }

    Write-Host "runtime_allowed_process_proxy_count=$($allowedRules.Count)"
    Write-Host "runtime_disallowed_process_proxy_count=$($badRules.Count)"
    $allowedRules |
        Select-Object index, type, payload, proxy, @{Name = 'hitCount'; Expression = { $_.extra.hitCount } } |
        Format-Table -AutoSize

    $rules |
        Where-Object {
            $_.payload -match 'Simprint|chrome_proxy|Chrome \*' -or
            ($_.proxy -eq 'PROXY' -and
                (Test-ProcessProxyRule -Type $_.type -Payload $_.payload) -and
                -not (Test-AllowedProcessProxyRule -Type $_.type -Payload $_.payload))
        } |
        Select-Object index, type, payload, proxy, @{Name = 'hitCount'; Expression = { $_.extra.hitCount } } |
        Format-Table -AutoSize
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
        'C:\Users\*\AppData\Local\OpenAI\Codex\bin\*\codex.exe',
        'C:\Program Files\WindowsApps\OpenAI.Codex_*\app\*',
        'C:\Program Files\OpenAI\ChatGPT\*',
        'C:\Users\*\AppData\Local\Programs\ChatGPT\*',
        'C:\Program Files\OpenAI\ChatGPT Atlas\*',
        'C:\Users\*\AppData\Local\Programs\ChatGPT Atlas\*',
        '/Applications/Antigravity.app/Contents/*',
        '/Applications/ChatGPT.app/Contents/*',
        '/Applications/ChatGPT Atlas.app/Contents/*',
        '/Applications/Codex.app/Contents/*',
        '/Users/*/Applications/Antigravity.app/Contents/*',
        '/Users/*/Applications/ChatGPT.app/Contents/*',
        '/Users/*/Applications/ChatGPT Atlas.app/Contents/*',
        '/Users/*/Applications/Codex.app/Contents/*',
        '/opt/Antigravity/*',
        '/opt/antigravity/*',
        '/usr/bin/antigravity*',
        '/opt/chatgpt/*',
        '/usr/bin/chatgpt*',
        '/opt/chatgpt-atlas/*',
        '/usr/bin/chatgpt-atlas*',
        '/usr/bin/chatgptatlas*',
        '/opt/codex/*',
        '/usr/bin/codex'
    )
    return $allowedPayloads -contains $Payload
}

Assert-Administrator

if (-not $WorkspaceRoot) {
    $WorkspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}
Set-Location -LiteralPath $WorkspaceRoot

Write-Section 'Hiddify / ProxyBridge uninstall verification'
$entries = @(Get-ProxyClientUninstallEntries)
if ($entries.Count -eq 0) {
    Write-Host 'uninstall_entries=none'
} else {
    $entries | Format-Table -AutoSize
    Write-Warning 'Uninstall entries still exist. Run the listed UninstallString manually if these are not intentional.'
}

$appx = @(Get-ProxyClientAppxPackages)
if ($appx.Count -eq 0) {
    Write-Host 'appx_packages=none'
} else {
    $appx | Select-Object Name, PackageFullName, InstallLocation | Format-Table -AutoSize
}

$leftovers = @(
    'C:\Program Files\ProxyBridge',
    "$env:APPDATA\ProxyBridge",
    "$env:APPDATA\Hiddify",
    'C:\Program Files\Hiddify',
    'C:\Program Files (x86)\Hiddify'
) | ForEach-Object {
    [pscustomobject]@{ Path = $_; Exists = (Test-Path -LiteralPath $_) }
}
$leftovers | Format-Table -AutoSize

Get-Process | Where-Object { $_.ProcessName -match 'hiddify|proxybridge' } |
    Select-Object Id, ProcessName, Path |
    Format-Table -AutoSize

if ($IncludeWingetCheck) {
    Write-Section 'winget check'
    winget list --accept-source-agreements | Select-String -Pattern 'Hiddify|ProxyBridge'
}

Write-Section 'Refresh mihomo SYSTEM TUN runtime'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\apply-mihomo-routing-policy-admin.ps1

Write-Section 'Runtime process proxy guardrails'
Assert-NoProcessProxyRules

Write-Section 'Simprint process tree'
Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -match 'simprint|msedgewebview2|chrome_proxy|chrome' -and
        ($_.ExecutablePath -match 'Simprint' -or $_.CommandLine -match 'Simprint|simprint')
    } |
    Select-Object ProcessId, ParentProcessId, Name, ExecutablePath |
    Format-Table -AutoSize

if (-not $SkipWatch) {
    Write-Section 'Watch Simprint routing'
    Write-Host 'Open or refresh the target page inside Simprint while this watcher is running.'
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\watch-simprint-routing.ps1 -Seconds $WatchSeconds -IntervalSeconds 2
}
