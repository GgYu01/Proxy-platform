<#
Verifies the local Windows mihomo and Clash Verge deployment. This script can be
run without administrator rights, but TUN adapter creation requires the elevated
startup task installed by install-mihomo-tun.ps1.
#>

[CmdletBinding()]
param(
    [string]$ConfigPath = 'C:\ProgramData\mihomo\mihomo-universal.yaml'
)

$ErrorActionPreference = 'Continue'
$script:VerificationFailures = New-Object System.Collections.Generic.List[string]
$script:ProbeResults = New-Object System.Collections.Generic.List[string]

function Get-MihomoRules {
    return (Invoke-RestMethod -Uri 'http://127.0.0.1:9090/rules' -Method Get -TimeoutSec 10).rules
}

function Get-MihomoConnections {
    return @((Invoke-RestMethod -Uri 'http://127.0.0.1:9090/connections' -Method Get -TimeoutSec 5).connections)
}

function Get-RuleHitMap {
    param([array]$Rules)

    $map = @{}
    foreach ($rule in $Rules) {
        $map[[string]$rule.index] = [int64]$rule.extra.hitCount
    }
    return $map
}

function ConvertTo-ObservedProxy {
    param($Connection, $Rule)

    if ($Connection -and $Connection.chains) {
        $chainText = ($Connection.chains -join '>')
        if ($Connection.chains -contains 'PROXY') { return 'PROXY' }
        if ($Connection.chains -contains 'DIRECT') { return 'DIRECT' }
        return $chainText
    }
    if ($Rule) {
        return $Rule.proxy
    }
    return 'UNKNOWN'
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
        $script:VerificationFailures.Add("${Source}_openai_domain_proxy_count=$($domainProxyRules.Count)") | Out-Null
    }
    if ($forbiddenKeywordRules.Count -gt 0) {
        $forbiddenKeywordRules | Select-Object index, type, payload, proxy | Format-Table -AutoSize
        $script:VerificationFailures.Add("${Source}_forbidden_openai_keyword_count=$($forbiddenKeywordRules.Count)") | Out-Null
    }
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

function Invoke-MihomoPolicyProbe {
    param(
        [string]$Name,
        [string]$Url,
        [string]$ExpectedProxy,
        [string[]]$ExpectedPayloads = @()
    )

    $uri = [Uri]$Url
    $hostName = $uri.Host
    $beforeRules = @()
    $beforeHits = @{}
    try {
        $beforeRules = @(Get-MihomoRules)
        $beforeHits = Get-RuleHitMap -Rules $beforeRules
    } catch {
        Write-Host "probe=$Name status=ERROR reason=rules_before_failed message=$($_.Exception.Message)"
        $script:ProbeResults.Add('ERROR') | Out-Null
        $script:VerificationFailures.Add("probe:$Name status=ERROR") | Out-Null
        return 'ERROR'
    }

    $outFile = Join-Path $env:TEMP "mihomo-policy-probe-$Name.bin"
    Remove-Item -LiteralPath $outFile -ErrorAction SilentlyContinue
    $curlArgs = @(
        '--proxy', 'http://127.0.0.1:7890',
        '-L',
        '--http1.1',
        '--max-time', '20',
        '--connect-timeout', '8',
        '--limit-rate', '64',
        '-o', $outFile,
        $Url
    )

    $process = $null
    try {
        $process = Start-Process -FilePath 'curl.exe' -ArgumentList $curlArgs -PassThru -WindowStyle Hidden
    } catch {
        Write-Host "probe=$Name host=$hostName expected=$ExpectedProxy status=ERROR reason=curl_start_failed message=$($_.Exception.Message)"
        $script:ProbeResults.Add('ERROR') | Out-Null
        $script:VerificationFailures.Add("probe:$Name status=ERROR") | Out-Null
        return 'ERROR'
    }

    $matchedConnection = $null
    for ($i = 0; $i -lt 32 -and -not $matchedConnection; $i++) {
        Start-Sleep -Milliseconds 250
        try {
            $connections = Get-MihomoConnections
            $matchedConnection = $connections |
                Where-Object {
                    $_.metadata.process -eq 'curl.exe' -and
                    ($_.metadata.host -eq $hostName -or $_.metadata.host -like "*.$hostName")
                } |
                Select-Object -First 1
        } catch {
            # The hit-count fallback below still gives useful rule evidence.
        }
    }

    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
    if ($process) {
        try { $process.WaitForExit(3000) | Out-Null } catch {}
    }

    $afterRules = @()
    try {
        $afterRules = @(Get-MihomoRules)
    } catch {
        Write-Host "probe=$Name host=$hostName expected=$ExpectedProxy status=ERROR reason=rules_after_failed message=$($_.Exception.Message)"
        $script:ProbeResults.Add('ERROR') | Out-Null
        $script:VerificationFailures.Add("probe:$Name status=ERROR") | Out-Null
        return 'ERROR'
    }

    $changedRules = @($afterRules | Where-Object {
        $before = 0
        if ($beforeHits.ContainsKey([string]$_.index)) { $before = [int64]$beforeHits[[string]$_.index] }
        [int64]$_.extra.hitCount -gt $before
    })
    $matchedRule = $null
    foreach ($payload in $ExpectedPayloads) {
        $matchedRule = $changedRules | Where-Object { $_.payload -eq $payload } | Select-Object -First 1
        if ($matchedRule) { break }
    }
    if (-not $matchedRule -and $matchedConnection) {
        $matchedRule = $afterRules |
            Where-Object {
                $_.type -eq $matchedConnection.rule -and
                ([string]$_.payload) -eq ([string]$matchedConnection.rulePayload)
            } |
            Select-Object -First 1
    }
    if (-not $matchedRule) {
        $matchedRule = $changedRules | Select-Object -First 1
    }

    $observedProxy = ConvertTo-ObservedProxy -Connection $matchedConnection -Rule $matchedRule
    $status = if ($observedProxy -eq $ExpectedProxy) { 'PASS' } else { 'CHECK' }
    $ruleName = if ($matchedConnection) { $matchedConnection.rule } elseif ($matchedRule) { $matchedRule.type } else { '' }
    $rulePayload = if ($matchedConnection) { $matchedConnection.rulePayload } elseif ($matchedRule) { $matchedRule.payload } else { '' }
    $chains = if ($matchedConnection -and $matchedConnection.chains) { $matchedConnection.chains -join '>' } else { '' }

    Write-Host "probe=$Name host=$hostName expected=$ExpectedProxy observed=$observedProxy rule=$ruleName payload=$rulePayload chains=$chains status=$status"
    $script:ProbeResults.Add($status) | Out-Null
    if ($status -ne 'PASS') {
        $script:VerificationFailures.Add("probe:$Name status=$status") | Out-Null
    }
    return $status
}

function Get-MihomoProcessStartTime {
    $latest = $null

    try {
        $cimProcesses = @(Get-CimInstance Win32_Process -Filter "Name='mihomo-windows-amd64.exe'" -ErrorAction Stop)
        foreach ($process in $cimProcesses) {
            if (-not $process.CreationDate) {
                continue
            }
            $candidate = [datetime]$process.CreationDate
            if (-not $latest -or $candidate -gt $latest) {
                $latest = $candidate
            }
        }
    } catch {
        # Non-admin shells can still continue with the guarded Get-Process fallback.
    }

    if ($latest) {
        return $latest
    }

    try {
        $processes = @(Get-Process mihomo-windows-amd64 -ErrorAction Stop)
        foreach ($process in $processes) {
            try {
                $candidate = $process.StartTime
            } catch {
                continue
            }
            if (-not $latest -or $candidate -gt $latest) {
                $latest = $candidate
            }
        }
    } catch {
        # StartTime can be denied for elevated/SYSTEM-owned mihomo processes.
    }

    return $latest
}

Write-Host 'administrator:'
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Write-Host "is_admin=$isAdmin"

Write-Host 'mihomo executable:'
Get-Item 'C:\Tools\mihomo\mihomo-windows-amd64.exe' -ErrorAction SilentlyContinue |
    Select-Object FullName, Length, LastWriteTime | Format-List

Write-Host 'Clash Verge executable:'
Get-Item 'C:\Program Files\Clash Verge\clash-verge.exe' -ErrorAction SilentlyContinue |
    Select-Object FullName, Length, LastWriteTime | Format-List

Write-Host 'configuration:'
Get-Item $ConfigPath -ErrorAction SilentlyContinue |
    Select-Object FullName, Length, LastWriteTime | Format-List

Write-Host 'editable process switch marker:'
Select-String -Path $ConfigPath -Pattern 'USER-EDITABLE PROCESS|PROCESS-NAME,QQ.exe|MATCH,PROXY' -ErrorAction SilentlyContinue

Write-Host 'file routing guardrails:'
$aiProxyName = 'AI' + '-PROXY'
$fileAiProxyCount = @(Select-String -Path $ConfigPath -Pattern ([regex]::Escape($aiProxyName)) -ErrorAction SilentlyContinue).Count
$fileDisallowedProcessProxyRules = @(
    Select-String -Path $ConfigPath -Pattern '^\s*-\s*([^,]+),(.+),PROXY\s*$' -ErrorAction SilentlyContinue |
        Where-Object {
            $ruleType = $_.Matches[0].Groups[1].Value
            $payload = $_.Matches[0].Groups[2].Value
            (Test-ProcessProxyRule -Type $ruleType -Payload $payload) -and
            -not (Test-AllowedProcessProxyRule -Type $ruleType -Payload $payload)
        }
)
$fileAllowedProcessProxyRules = @(
    Select-String -Path $ConfigPath -Pattern '^\s*-\s*([^,]+),(.+),PROXY\s*$' -ErrorAction SilentlyContinue |
        Where-Object {
            $ruleType = $_.Matches[0].Groups[1].Value
            $payload = $_.Matches[0].Groups[2].Value
            Test-AllowedProcessProxyRule -Type $ruleType -Payload $payload
        }
)
$fileMatchRule = Select-String -Path $ConfigPath -Pattern '^\s*- MATCH,' -ErrorAction SilentlyContinue | Select-Object -Last 1
Write-Host "file_ai_proxy_count=$fileAiProxyCount"
Write-Host "file_allowed_process_proxy_count=$($fileAllowedProcessProxyRules.Count)"
Write-Host "file_disallowed_process_proxy_count=$($fileDisallowedProcessProxyRules.Count)"
if ($fileMatchRule) { Write-Host "file_match_rule=$($fileMatchRule.Line.Trim())" }
$fileAllowedProcessProxyRules | Select-Object LineNumber, Line | Format-Table -AutoSize
$fileDisallowedProcessProxyRules | Select-Object LineNumber, Line | Format-Table -AutoSize
Assert-OpenAIDomainProxyGuardrails -Source 'file' -Rules (Convert-ConfigRuleLines -Path $ConfigPath)
if ($fileDisallowedProcessProxyRules.Count -gt 0) {
    $script:VerificationFailures.Add("file_disallowed_process_proxy_count=$($fileDisallowedProcessProxyRules.Count)") | Out-Null
}
if ($fileAiProxyCount -gt 0) {
    $script:VerificationFailures.Add("file_ai_proxy_count=$fileAiProxyCount") | Out-Null
}

Write-Host 'scheduled tasks:'
Get-ScheduledTask -ErrorAction SilentlyContinue |
    Where-Object { $_.TaskName -in @('Mihomo TUN Transparent Proxy', 'Clash Verge Rev Admin Startup') } |
    Select-Object TaskName, State, TaskPath | Format-List

Write-Host 'services:'
Get-Service | Where-Object { $_.Name -match 'mihomo|clash|verge' -or $_.DisplayName -match 'mihomo|clash|verge' } |
    Select-Object Name, DisplayName, Status, StartType | Format-List

Write-Host 'processes:'
Get-Process | Where-Object { $_.ProcessName -match 'mihomo|clash|verge' } |
    Select-Object Id, ProcessName, Path, MainWindowTitle | Format-List

Write-Host 'listeners:'
Get-NetTCPConnection -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in 7890, 9090, 1053 } |
    Select-Object LocalAddress, LocalPort, State, OwningProcess | Format-Table -AutoSize

Write-Host 'runtime routing guardrails:'
try {
    $runtimeRules = Invoke-RestMethod -Uri 'http://127.0.0.1:9090/rules' -Method Get -TimeoutSec 10
    $runtimeMatch = $runtimeRules.rules | Where-Object { $_.type -eq 'Match' } | Select-Object -Last 1
    $runtimeAiProxyRules = @($runtimeRules.rules | Where-Object {
        $_.proxy -eq $aiProxyName -or $_.payload -match ([regex]::Escape($aiProxyName))
    })
    $runtimeBadProcessProxyRules = @($runtimeRules.rules | Where-Object {
        $_.proxy -eq 'PROXY' -and
        (Test-ProcessProxyRule -Type $_.type -Payload $_.payload) -and
        -not (Test-AllowedProcessProxyRule -Type $_.type -Payload $_.payload)
    })
    $runtimeAllowedProcessProxyRules = @($runtimeRules.rules | Where-Object {
        $_.proxy -eq 'PROXY' -and
        (Test-AllowedProcessProxyRule -Type $_.type -Payload $_.payload)
    })
    Write-Host "runtime_match_proxy=$($runtimeMatch.proxy)"
    Write-Host "runtime_ai_proxy_count=$($runtimeAiProxyRules.Count)"
    Write-Host "runtime_allowed_process_proxy_count=$($runtimeAllowedProcessProxyRules.Count)"
    Write-Host "runtime_disallowed_process_proxy_count=$($runtimeBadProcessProxyRules.Count)"
    $runtimeAllowedProcessProxyRules | Select-Object index, type, payload, proxy | Format-Table -AutoSize
    $runtimeBadProcessProxyRules | Select-Object index, type, payload, proxy | Format-Table -AutoSize
    Assert-OpenAIDomainProxyGuardrails -Source 'runtime' -Rules $runtimeRules.rules
    if ($runtimeBadProcessProxyRules.Count -gt 0) {
        $script:VerificationFailures.Add("runtime_disallowed_process_proxy_count=$($runtimeBadProcessProxyRules.Count)") | Out-Null
    }
    if ($runtimeAiProxyRules.Count -gt 0) {
        $script:VerificationFailures.Add("runtime_ai_proxy_count=$($runtimeAiProxyRules.Count)") | Out-Null
    }
} catch {
    Write-Host "runtime_rules_error=$($_.Exception.Message)"
}

Write-Host 'Clash Verge pipe routing guardrails:'
try {
    $client = [System.IO.Pipes.NamedPipeClientStream]::new('.', 'verge-mihomo', [System.IO.Pipes.PipeDirection]::InOut)
    $client.Connect(3000)
    $request = "GET /rules HTTP/1.1`r`nHost: pipe`r`nConnection: close`r`n`r`n"
    $bytes = [Text.Encoding]::ASCII.GetBytes($request)
    $client.Write($bytes, 0, $bytes.Length)
    $client.Flush()
    $buffer = New-Object byte[] 65536
    $ms = [IO.MemoryStream]::new()
    do {
        $read = $client.Read($buffer, 0, $buffer.Length)
        if ($read -gt 0) { $ms.Write($buffer, 0, $read) }
    } while ($read -gt 0)
    $client.Close()

    $raw = [Text.Encoding]::UTF8.GetString($ms.ToArray())
    $parts = $raw -split "`r`n`r`n", 2
    $head = $parts[0]
    $body = $parts[1]
    if ($head -match 'Transfer-Encoding:\s*chunked') {
        $decoded = [Text.StringBuilder]::new()
        $pos = 0
        while ($pos -lt $body.Length) {
            $lineEnd = $body.IndexOf("`r`n", $pos)
            if ($lineEnd -lt 0) { break }
            $sizeText = ($body.Substring($pos, $lineEnd - $pos) -split ';', 2)[0]
            $size = [Convert]::ToInt32($sizeText.Trim(), 16)
            $pos = $lineEnd + 2
            if ($size -eq 0) { break }
            [void]$decoded.Append($body.Substring($pos, $size))
            $pos += $size + 2
        }
        $body = $decoded.ToString()
    }

    $rules = ($body | ConvertFrom-Json).rules
    $match = $rules | Where-Object { $_.type -eq 'Match' } | Select-Object -Last 1
    $aiProxyRules = @($rules | Where-Object {
        $_.proxy -eq $aiProxyName -or $_.payload -match ([regex]::Escape($aiProxyName))
    })
    $bad = @($rules | Where-Object {
        $_.proxy -eq 'PROXY' -and
        (Test-ProcessProxyRule -Type $_.type -Payload $_.payload) -and
        -not (Test-AllowedProcessProxyRule -Type $_.type -Payload $_.payload)
    })
    $allowed = @($rules | Where-Object {
        $_.proxy -eq 'PROXY' -and
        (Test-AllowedProcessProxyRule -Type $_.type -Payload $_.payload)
    })
    Write-Host "clash_pipe_match_proxy=$($match.proxy)"
    Write-Host "clash_pipe_ai_proxy_count=$($aiProxyRules.Count)"
    Write-Host "clash_pipe_allowed_process_proxy_count=$($allowed.Count)"
    Write-Host "clash_pipe_disallowed_process_proxy_count=$($bad.Count)"
    $allowed | Select-Object index, type, payload, proxy | Format-Table -AutoSize
    $bad | Select-Object index, type, payload, proxy | Format-Table -AutoSize
    if ($bad.Count -gt 0) {
        $script:VerificationFailures.Add("clash_pipe_disallowed_process_proxy_count=$($bad.Count)") | Out-Null
    }
    if ($aiProxyRules.Count -gt 0) {
        $script:VerificationFailures.Add("clash_pipe_ai_proxy_count=$($aiProxyRules.Count)") | Out-Null
    }
} catch {
    Write-Host "clash_pipe_rules_error=$($_.Exception.Message)"
}

Write-Host 'tun adapters:'
Get-NetAdapter | Where-Object {
    $_.Name -match 'tun|tap|wintun|clash|mihomo|meta|verge' -or
    $_.InterfaceDescription -match 'tun|tap|wintun|clash|mihomo|meta|verge'
} | Select-Object Name, InterfaceDescription, Status | Format-Table -AutoSize

Write-Host 'policy probe summary:'
$null = Invoke-MihomoPolicyProbe -Name 'qwen_no_ai_proxy' -Url 'https://chat.qwen.ai/' -ExpectedProxy 'DIRECT' -ExpectedPayloads @('cn')
$null = Invoke-MihomoPolicyProbe -Name 'google_global' -Url 'https://www.google.com/' -ExpectedProxy 'PROXY' -ExpectedPayloads @('proxy', 'gfw', 'tld-proxy')
$null = Invoke-MihomoPolicyProbe -Name 'baidu_default' -Url 'https://www.baidu.com/' -ExpectedProxy 'DIRECT' -ExpectedPayloads @('cn')
$null = Invoke-MihomoPolicyProbe -Name 'qq_default' -Url 'https://im.qq.com/' -ExpectedProxy 'DIRECT' -ExpectedPayloads @('cn')
$null = Invoke-MihomoPolicyProbe -Name 'wechat_default' -Url 'https://weixin.qq.com/' -ExpectedProxy 'DIRECT' -ExpectedPayloads @('cn')
$null = Invoke-MihomoPolicyProbe -Name 'wps_update' -Url 'https://update.wps.cn/' -ExpectedProxy 'DIRECT' -ExpectedPayloads @('cn', 'wps.cn', 'kingsoft')
$null = Invoke-MihomoPolicyProbe -Name 'wps_drive' -Url 'https://drive.wps.cn/' -ExpectedProxy 'DIRECT' -ExpectedPayloads @('cn', 'wps.cn', 'kingsoft')
$null = Invoke-MihomoPolicyProbe -Name 'wps_account' -Url 'https://account.wps.cn/' -ExpectedProxy 'DIRECT' -ExpectedPayloads @('cn', 'wps.cn', 'kingsoft')
Write-Host ''

Write-Host 'current mihomo log summary:'
$currentLogPath = 'C:\ProgramData\mihomo\mihomo-current.out.log'
$mihomoStartTime = Get-MihomoProcessStartTime
if (-not (Test-Path -LiteralPath $currentLogPath)) {
    Write-Host 'current_log_unavailable_reason=log_missing'
} elseif (-not $mihomoStartTime) {
    Write-Host 'current_log_unavailable_reason=start_time_unavailable'
} else {
    $recentCurrentLogLines = @(
        Get-Content -LiteralPath $currentLogPath -Tail 2000 -ErrorAction SilentlyContinue |
            Where-Object {
                if ($_ -match 'time="([^"]+)"') {
                    try {
                        ([datetimeoffset]::Parse($Matches[1])).LocalDateTime -ge $mihomoStartTime
                    } catch {
                        $false
                    }
                } else {
                    $false
                }
            }
    )
    Write-Host "current_log_line_count=$($recentCurrentLogLines.Count)"
    Write-Host "current_log_ai_proxy_count=$(@($recentCurrentLogLines | Select-String -Pattern ([regex]::Escape($aiProxyName))).Count)"
    $recentCurrentLogLines | Select-Object -Last 40
}

Write-Host 'install log:'
Get-Content 'C:\ProgramData\mihomo\install-mihomo-tun.log' -Tail 120 -ErrorAction SilentlyContinue

Write-Host ''
Write-Host 'verification summary:'
if ($script:VerificationFailures.Count -eq 0) {
    Write-Host 'verification_verdict=PASS'
    exit 0
}

Write-Host 'verification_verdict=FAIL'
foreach ($failure in $script:VerificationFailures) {
    Write-Host "verification_failure=$failure"
}
exit 1
