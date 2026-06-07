<#
Uninstalls and verifies removal of Hiddify / ProxyBridge on Windows.

Run from an elevated PowerShell session. The script only targets explicit
Hiddify / ProxyBridge registry entries, packages, services, tasks, shortcuts,
Run keys, and allowlisted leftover paths. It does not remove mihomo,
Clash Verge Rev, Edge, WebView2, Simprint, or generic proxy/browser directories.
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [switch]$RunUninstallers,
    [switch]$RemoveLeftovers,
    [switch]$IncludeWinget
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

function Test-ProxyClientText {
    param([string]$Text = '')

    return $Text -match 'Hiddify|ProxyBridge|app\.hiddify\.com|interceptsuite'
}

function Get-ProxyClientUninstallEntries {
    $roots = @(
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    Get-ItemProperty -Path $roots -ErrorAction SilentlyContinue |
        Where-Object {
            (Test-ProxyClientText -Text $_.DisplayName) -or
            (Test-ProxyClientText -Text $_.InstallLocation) -or
            (Test-ProxyClientText -Text $_.UninstallString) -or
            (Test-ProxyClientText -Text $_.QuietUninstallString)
        }
}

function Split-UninstallCommand {
    param([Parameter(Mandatory)] [string]$Command)

    $trimmed = $Command.Trim()
    if ($trimmed.StartsWith('"')) {
        $end = $trimmed.IndexOf('"', 1)
        if ($end -gt 1) {
            return [pscustomobject]@{
                FilePath = $trimmed.Substring(1, $end - 1)
                Arguments = $trimmed.Substring($end + 1).Trim()
            }
        }
    }

    $parts = $trimmed -split '\s+', 2
    return [pscustomobject]@{
        FilePath = $parts[0]
        Arguments = if ($parts.Count -gt 1) { $parts[1] } else { '' }
    }
}

function Invoke-UninstallEntry {
    param($Entry)

    $command = if ($Entry.QuietUninstallString) { $Entry.QuietUninstallString } else { $Entry.UninstallString }
    if (-not $command) {
        Write-Warning "No uninstall command for $($Entry.DisplayName)"
        return
    }

    $parsed = Split-UninstallCommand -Command $command
    if (-not (Test-ProxyClientText -Text "$($Entry.DisplayName) $($Entry.InstallLocation) $command")) {
        Write-Warning "Skipped uninstall command without Hiddify/ProxyBridge marker: $command"
        return
    }

    Write-Host "running_uninstaller=$($Entry.DisplayName)"
    Write-Host "uninstaller_file=$($parsed.FilePath)"
    Write-Host "uninstaller_args=$($parsed.Arguments)"
    if ($PSCmdlet.ShouldProcess($Entry.DisplayName, 'run uninstaller')) {
        $process = Start-Process -FilePath $parsed.FilePath -ArgumentList $parsed.Arguments -Wait -PassThru
        Write-Host "uninstaller_exit_code=$($process.ExitCode)"
    }
}

function Remove-ProxyClientAppxPackages {
    $packages = @()
    try {
        $packages = @(Get-AppxPackage -AllUsers -ErrorAction Stop | Where-Object {
            (Test-ProxyClientText -Text $_.Name) -or (Test-ProxyClientText -Text $_.PackageFullName)
        })
    } catch {
        Write-Warning "AllUsers Appx query failed, falling back to current user: $($_.Exception.Message)"
        $packages = @(Get-AppxPackage -ErrorAction SilentlyContinue | Where-Object {
            (Test-ProxyClientText -Text $_.Name) -or (Test-ProxyClientText -Text $_.PackageFullName)
        })
    }

    foreach ($package in $packages) {
        Write-Host "appx_package=$($package.PackageFullName)"
        if ($PSCmdlet.ShouldProcess($package.PackageFullName, 'remove Appx package')) {
            Remove-AppxPackage -Package $package.PackageFullName -AllUsers -ErrorAction SilentlyContinue
            Remove-AppxPackage -Package $package.PackageFullName -ErrorAction SilentlyContinue
        }
    }
    return $packages
}

function Remove-ProxyClientServices {
    $services = @(Get-Service | Where-Object {
        (Test-ProxyClientText -Text $_.Name) -or (Test-ProxyClientText -Text $_.DisplayName)
    })
    foreach ($service in $services) {
        Write-Host "service=$($service.Name)"
        if ($PSCmdlet.ShouldProcess($service.Name, 'stop and delete service')) {
            Stop-Service -Name $service.Name -Force -ErrorAction SilentlyContinue
            sc.exe delete $service.Name | Out-Host
        }
    }
    return $services
}

function Remove-ProxyClientScheduledTasks {
    $tasks = @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
        (Test-ProxyClientText -Text $_.TaskName) -or (Test-ProxyClientText -Text $_.TaskPath)
    })
    foreach ($task in $tasks) {
        Write-Host "scheduled_task=$($task.TaskPath)$($task.TaskName)"
        if ($PSCmdlet.ShouldProcess("$($task.TaskPath)$($task.TaskName)", 'unregister scheduled task')) {
            Unregister-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath -Confirm:$false -ErrorAction SilentlyContinue
        }
    }
    return $tasks
}

function Remove-ProxyClientRunKeys {
    $roots = @(
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run',
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce',
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run',
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\RunOnce'
    )

    $hits = New-Object System.Collections.Generic.List[object]
    foreach ($root in $roots) {
        $item = Get-ItemProperty -LiteralPath $root -ErrorAction SilentlyContinue
        if (-not $item) {
            continue
        }
        foreach ($property in $item.PSObject.Properties) {
            if ($property.Name -like 'PS*') {
                continue
            }
            if ((Test-ProxyClientText -Text $property.Name) -or (Test-ProxyClientText -Text ([string]$property.Value))) {
                $hits.Add([pscustomobject]@{ Path = $root; Name = $property.Name; Value = $property.Value })
                Write-Host "run_key=$root name=$($property.Name)"
                if ($PSCmdlet.ShouldProcess("$root\$($property.Name)", 'remove Run key value')) {
                    Remove-ItemProperty -LiteralPath $root -Name $property.Name -ErrorAction SilentlyContinue
                }
            }
        }
    }
    return $hits
}

function Get-LeftoverPaths {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $programs = [Environment]::GetFolderPath('Programs')
    $commonPrograms = [Environment]::GetFolderPath('CommonPrograms')
    return @(
        "$env:APPDATA\Hiddify",
        "$env:LOCALAPPDATA\Hiddify",
        "$env:APPDATA\ProxyBridge",
        "$env:LOCALAPPDATA\ProxyBridge",
        "$env:APPDATA\app.hiddify.com",
        "$env:LOCALAPPDATA\app.hiddify.com",
        "$env:LOCALAPPDATA\Programs\Hiddify",
        "$env:LOCALAPPDATA\Programs\ProxyBridge",
        'C:\ProgramData\Hiddify',
        'C:\ProgramData\ProxyBridge',
        'C:\ProgramData\app.hiddify.com',
        'C:\Program Files\Hiddify',
        'C:\Program Files (x86)\Hiddify',
        'C:\Program Files\ProxyBridge',
        'C:\Program Files (x86)\ProxyBridge',
        (Join-Path $desktop 'Hiddify.lnk'),
        (Join-Path $desktop 'ProxyBridge.lnk'),
        (Join-Path $desktop 'ProxyBridge-Rules.json'),
        (Join-Path $programs 'Hiddify'),
        (Join-Path $programs 'ProxyBridge'),
        (Join-Path $commonPrograms 'Hiddify'),
        (Join-Path $commonPrograms 'ProxyBridge')
    )
}

function Remove-AllowlistedLeftovers {
    $hits = New-Object System.Collections.Generic.List[object]
    foreach ($path in (Get-LeftoverPaths)) {
        if (-not (Test-Path -LiteralPath $path)) {
            continue
        }

        $resolved = (Resolve-Path -LiteralPath $path).Path
        if (-not (Test-ProxyClientText -Text $resolved)) {
            throw "Refusing to remove path without Hiddify/ProxyBridge marker: $resolved"
        }

        $hits.Add([pscustomobject]@{ Path = $resolved })
        Write-Host "leftover_path=$resolved"
        if ($PSCmdlet.ShouldProcess($resolved, 'remove leftover path')) {
            Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    return $hits
}

function Get-ProxyClientPorts {
    Get-NetTCPConnection -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in 12334, 12335 -or $_.RemotePort -in 12334, 12335 } |
        Select-Object LocalAddress, LocalPort, RemoteAddress, RemotePort, State, OwningProcess
}

Assert-Administrator

Write-Section 'Stop running Hiddify / ProxyBridge processes'
$processes = @(Get-Process | Where-Object { Test-ProxyClientText -Text $_.ProcessName })
$processes | Select-Object Id, ProcessName, Path | Format-Table -AutoSize
foreach ($process in $processes) {
    if ($PSCmdlet.ShouldProcess($process.ProcessName, 'stop process')) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
}

Write-Section 'Uninstall entries'
$entries = @(Get-ProxyClientUninstallEntries)
$entries | Select-Object DisplayName, DisplayVersion, Publisher, InstallLocation, UninstallString, QuietUninstallString | Format-List
if ($RunUninstallers) {
    foreach ($entry in $entries) {
        Invoke-UninstallEntry -Entry $entry
    }
} elseif ($entries.Count -gt 0) {
    Write-Host 'run_uninstallers=false'
    Write-Host 'Re-run with -RunUninstallers to execute the listed uninstall commands.'
}

Write-Section 'Appx packages'
$appx = @(Remove-ProxyClientAppxPackages)

Write-Section 'Services'
$services = @(Remove-ProxyClientServices)

Write-Section 'Scheduled tasks'
$tasks = @(Remove-ProxyClientScheduledTasks)

Write-Section 'Startup Run keys'
$runKeys = @(Remove-ProxyClientRunKeys)

Write-Section 'Allowlisted leftover paths'
if ($RemoveLeftovers) {
    $leftovers = @(Remove-AllowlistedLeftovers)
} else {
    $leftovers = @(Get-LeftoverPaths | Where-Object { Test-Path -LiteralPath $_ } | ForEach-Object {
        [pscustomobject]@{ Path = (Resolve-Path -LiteralPath $_).Path }
    })
    $leftovers | Format-Table -AutoSize
    if ($leftovers.Count -gt 0) {
        Write-Host 'remove_leftovers=false'
        Write-Host 'Re-run with -RemoveLeftovers to delete only the listed allowlisted paths.'
    }
}

if ($IncludeWinget) {
    Write-Section 'winget check'
    winget list --accept-source-agreements | Select-String -Pattern 'Hiddify|ProxyBridge|interceptsuite'
}

Write-Section 'Port check'
$ports = @(Get-ProxyClientPorts)
$ports | Format-Table -AutoSize

Write-Section 'Verification summary'
$remainingProcesses = @(Get-Process | Where-Object { Test-ProxyClientText -Text $_.ProcessName })
$remainingEntries = @(Get-ProxyClientUninstallEntries)
$remainingPaths = @(Get-LeftoverPaths | Where-Object { Test-Path -LiteralPath $_ })
Write-Host "process_hits=$($remainingProcesses.Count)"
Write-Host "uninstall_hits=$($remainingEntries.Count)"
Write-Host "appx_hits=$($appx.Count)"
Write-Host "service_hits=$($services.Count)"
Write-Host "task_hits=$($tasks.Count)"
Write-Host "run_key_hits=$($runKeys.Count)"
Write-Host "leftover_path_hits=$($remainingPaths.Count)"
Write-Host "proxybridge_port_hits=$($ports.Count)"

if ($remainingProcesses.Count -eq 0 -and $remainingEntries.Count -eq 0 -and $remainingPaths.Count -eq 0 -and $ports.Count -eq 0) {
    Write-Host 'result=PASS'
} else {
    Write-Host 'result=CHECK'
}
