<#
Refreshes the reviewed mihomo routing policy and verifies Simprint-specific
browser routing.

Run from an elevated PowerShell session. This script deliberately does not add
PROCESS-NAME rules for simprint.exe, simprint-runtime.exe, or msedgewebview2.exe.
Only reviewed app install paths may use process-level PROXY: Simprint's Chrome
profile browser and Antigravity. Official OpenAI/ChatGPT/Codex destinations are
proxied by domain rules; OpenAI-family desktop app paths stay DIRECT fallback.
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

if (-not $WorkspaceRoot) {
    $WorkspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}
Set-Location -LiteralPath $WorkspaceRoot

Write-Section 'Refresh mihomo SYSTEM TUN runtime'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\apply-mihomo-routing-policy-admin.ps1

Write-Section 'Runtime process proxy guardrails'
Assert-NoProcessProxyRules
Assert-OpenAIDomainProxyGuardrails -Source 'runtime' -Rules ((Invoke-RestMethod -Uri 'http://127.0.0.1:9090/rules' -TimeoutSec 10).rules)

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
