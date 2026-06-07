<#
Runs the full Windows mihomo acceptance gate: pytest, PowerShell syntax checks,
verify-mihomo-windows.ps1, and optional WPS routing observation.
#>

[CmdletBinding()]
param(
    [string]$ConfigPath = 'C:\ProgramData\mihomo\mihomo-universal.yaml',
    [switch]$SkipRuntime,
    [switch]$SkipWpsWatch
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$PrivateRoot = Join-Path $Root 'repos\proxy_ops_private'
$Failures = New-Object System.Collections.Generic.List[string]

function Add-Failure {
    param([string]$Message)
    $Failures.Add($Message) | Out-Null
    Write-Host "acceptance_failure=$Message"
}

function Find-Python {
    $candidates = @(
        (Join-Path $Root '.venv\Scripts\python.exe'),
        'python'
    )
    foreach ($candidate in $candidates) {
        if ($candidate -eq 'python') {
            if (Get-Command python -ErrorAction SilentlyContinue) { return 'python' }
            continue
        }
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    throw 'Python interpreter not found'
}

Write-Host "acceptance_root=$Root"
$python = Find-Python
Write-Host "acceptance_python=$python"

Write-Host 'acceptance_step=pytest_proxy_platform'
$pytestArgs = @(
    '-m', 'pytest',
    (Join-Path $Root 'tests\test_proxy_subscription_artifacts.py'),
    '-q'
)
& $python @pytestArgs
if ($LASTEXITCODE -ne 0) { Add-Failure 'pytest_proxy_platform_failed' }

Write-Host 'acceptance_step=pytest_proxy_ops_private'
$pytestPrivateArgs = @(
    '-m', 'pytest',
    (Join-Path $PrivateRoot 'tests\test_render_subscription_landing_page.py'),
    '-q'
)
& $python @pytestPrivateArgs
if ($LASTEXITCODE -ne 0) { Add-Failure 'pytest_proxy_ops_private_failed' }

Write-Host 'acceptance_step=render_artifacts'
& $python (Join-Path $PrivateRoot 'scripts\render_artifacts.py')
if ($LASTEXITCODE -ne 0) { Add-Failure 'render_artifacts_failed' }

Write-Host 'acceptance_step=pytest_after_render'
& $python @pytestArgs
if ($LASTEXITCODE -ne 0) { Add-Failure 'pytest_after_render_failed' }

Write-Host 'acceptance_step=powershell_syntax'
$scriptFiles = @(
    'scripts\windows\verify-mihomo-windows.ps1',
    'scripts\windows\accept-mihomo-windows.ps1',
    'scripts\windows\refresh-mihomo-tun-config.ps1',
    'scripts\windows\apply-mihomo-routing-policy-admin.ps1',
    'scripts\windows\apply-simprint-routing-admin.ps1',
    'scripts\windows\watch-simprint-routing.ps1',
    'scripts\windows\watch-wps-routing.ps1',
    'scripts\windows\install-mihomo-tun.ps1'
)
foreach ($relativePath in $scriptFiles) {
    $file = Join-Path $Root $relativePath
    if (-not (Test-Path -LiteralPath $file)) {
        Add-Failure "missing_script=$relativePath"
        continue
    }
    $errs = $null
    [void][System.Management.Automation.PSParser]::Tokenize((Get-Content -LiteralPath $file -Raw), [ref]$errs)
    if ($errs) {
        Add-Failure "powershell_syntax_failed=$relativePath"
        $errs | Format-List
    } else {
        Write-Host "acceptance_ps_syntax_ok=$relativePath"
    }
}

if (-not $SkipRuntime) {
    Write-Host 'acceptance_step=verify_mihomo_windows'
    $verifyScript = Join-Path $Root 'scripts\windows\verify-mihomo-windows.ps1'
    & $verifyScript -ConfigPath $ConfigPath
    if ($LASTEXITCODE -ne 0) { Add-Failure 'verify_mihomo_windows_failed' }

    if (-not $SkipWpsWatch) {
        Write-Host 'acceptance_step=watch_wps_routing'
        $watchScript = Join-Path $Root 'scripts\windows\watch-wps-routing.ps1'
        if (Test-Path -LiteralPath $watchScript) {
            & $watchScript -Seconds 8
            if ($LASTEXITCODE -ne 0) { Add-Failure 'watch_wps_routing_failed' }
        } else {
            Add-Failure 'watch_wps_routing_missing'
        }
    }
} else {
    Write-Host 'acceptance_step=verify_mihomo_windows skipped'
}

Write-Host ''
if ($Failures.Count -eq 0) {
    Write-Host 'acceptance_verdict=PASS'
    exit 0
}

Write-Host 'acceptance_verdict=FAIL'
exit 1
