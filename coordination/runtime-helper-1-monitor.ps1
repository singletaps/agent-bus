$ErrorActionPreference = 'Continue'

$Root = 'C:\Users\laptopofzy\Documents\Agent bus'
$Coord = Join-Path $Root 'coordination'
$Bus = Join-Path $Coord 'agent-bus.ndjson'
$Feedback = Join-Path $Root 'USER_FEEDBACK.md'
$WaveGates = Join-Path $Coord 'wave-gates.md'
$LiveDb = Join-Path $Coord 'live-agent-bus.sqlite3'
$LiveEventReader = Join-Path $Coord 'runtime-helper-live-events.py'
$AgentBus = "$HOME\plugins\codex-agent-bus\scripts\agent-bus.ps1"
$Broker = 'http://127.0.0.1:8765'
$Agent = 'runtime-helper-1'
$SuppressUserFeedbackFanout = $true
$Recipients = @(
  'runtime-worker-1',
  'runtime-worker-2',
  'runtime-worker-3',
  'runtime-worker-4',
  'runtime-helper-2',
  'runtime-qa'
)
$StatePath = Join-Path $Coord 'runtime-helper-1-monitor.state.json'
$LogPath = Join-Path $Coord 'runtime-helper-1-monitor.log'

function Write-MonitorLog {
  param([string]$Text)
  $stamp = (Get-Date).ToUniversalTime().ToString('o')
  Add-Content -LiteralPath $LogPath -Value "[$stamp] $Text" -Encoding UTF8
}

function Get-RawText {
  param([string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) { return '' }
  return [IO.File]::ReadAllText($Path)
}

function Get-BusLineCount {
  if (-not (Test-Path -LiteralPath $Bus)) { return 0 }
  return [int64]((Get-Content -LiteralPath $Bus -ErrorAction SilentlyContinue | Measure-Object -Line).Lines)
}

function Get-BrokerHealthy {
  try {
    Invoke-RestMethod -Uri "$Broker/api/dashboard?limit=1" -TimeoutSec 2 | Out-Null
    return $true
  } catch {
    return $false
  }
}

function Invoke-AgentBus {
  param([string[]]$CliArgs)
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $AgentBus @CliArgs
}

function Send-AgentMessage {
  param([string]$To, [string]$Text)
  Invoke-AgentBus -CliArgs @('send', $Agent, '--bus', $Bus, '--broker', $Broker, '--to', $To, $Text) | Out-Null
}

function Send-AgentStatus {
  param([string]$State, [string]$Note)
  Invoke-AgentBus -CliArgs @('status', $Agent, '--bus', $Bus, '--broker', $Broker, '--state', $State, '--note', $Note) | Out-Null
}

function Get-LiveMaxSeq {
  if (-not (Test-Path -LiteralPath $LiveDb)) { return 0 }
  if (-not (Test-Path -LiteralPath $LiveEventReader)) { return 0 }
  try {
    $raw = & python $LiveEventReader max $LiveDb 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) { return 0 }
    return [int64]$raw.Trim()
  } catch {
    Write-MonitorLog "live max seq read failed: $($_.Exception.Message)"
    return 0
  }
}

function Get-LiveEventsAfter {
  param([int64]$Seq)
  if (-not (Test-Path -LiteralPath $LiveDb)) { return @() }
  if (-not (Test-Path -LiteralPath $LiveEventReader)) { return @() }
  try {
    $raw = & python $LiveEventReader events $LiveDb ([string]$Seq) 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) { return @() }
    return @($raw | ConvertFrom-Json)
  } catch {
    Write-MonitorLog "live events read failed after seq ${Seq}: $($_.Exception.Message)"
    return @()
  }
}

function New-State {
  [pscustomobject]@{
    busLines = Get-BusLineCount
    feedbackChars = (Get-RawText $Feedback).Length
    liveSeq = Get-LiveMaxSeq
    lastHeartbeat = ''
    lastBrokerStartAttempt = ''
    updated = (Get-Date).ToString('o')
  }
}

function Read-State {
  if (Test-Path -LiteralPath $StatePath) {
    try {
      $state = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
      Write-MonitorLog "state read failed: $($_.Exception.Message)"
      $state = New-State
    }
  } else {
    $state = New-State
  }
  if ($null -eq $state.busLines) { $state | Add-Member -NotePropertyName busLines -NotePropertyValue (Get-BusLineCount) }
  if ($null -eq $state.feedbackChars) { $state | Add-Member -NotePropertyName feedbackChars -NotePropertyValue ((Get-RawText $Feedback).Length) }
  if ($null -eq $state.liveSeq) { $state | Add-Member -NotePropertyName liveSeq -NotePropertyValue (Get-LiveMaxSeq) }
  if ($null -eq $state.lastHeartbeat) { $state | Add-Member -NotePropertyName lastHeartbeat -NotePropertyValue '' }
  if ($null -eq $state.lastBrokerStartAttempt) { $state | Add-Member -NotePropertyName lastBrokerStartAttempt -NotePropertyValue '' }
  if ($null -eq $state.updated) { $state | Add-Member -NotePropertyName updated -NotePropertyValue (Get-Date).ToString('o') }
  return $state
}

function Write-State {
  param($State)
  $State.updated = (Get-Date).ToString('o')
  $State | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $StatePath -Encoding UTF8
}

function Test-InterruptText {
  param([string]$Text)
  return $Text -match '(?i)\b(interrupt|stop|hold|wait|blocker|urgent|do not|rollback|revert|change direction|NEED_USER_DECISION|redo|wrong)\b|\u6682\u505c|\u505c\u6b62|\u7b49\u5f85|\u5148\u522b|\u4e0d\u8981|\u522b\u505a|\u4e2d\u65ad|\u7d27\u6025|\u63a8\u7ffb|\u6539\u4e3a|\u91cd\u505a|\u4e0d\u5bf9|\u9519\u8bef|\u9519\u4e86|\u7b49\u6211\u7684\u6307\u4ee4'
}

function Test-InternalFeedbackOnly {
  param([string]$Text)
  $trimmed = $Text.Trim()
  if ([string]::IsNullOrWhiteSpace($trimmed)) { return $true }
  $hasUserMarker = $trimmed -match '(?im)^\s*User feedback\s*:|(?im)^>\s+|(?im)^##\s+.*(Chat|Bus|User|Live).*Feedback'
  if ($hasUserMarker) { return $false }
  return $trimmed -match '(?im)^\s*-\s*(Forwarded to|Helper1 forwarded|runtime-helper|runtime-worker|runtime-qa)|runtime-helper-1-forward-log|Forwarding log:'
}

function Forward-Feedback {
  param(
    [string]$Kind,
    [string]$Text,
    [bool]$Interrupt,
    [string]$Source
  )
  $stamp = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')
  $prefix = if ($Interrupt) { "HIGH_PRIORITY_INTERRUPT_$Kind" } else { $Kind }
  $snippet = ($Text -replace '\s+', ' ').Trim()
  if ($snippet.Length -gt 1200) { $snippet = $snippet.Substring(0, 1200) + '...' }
  $message = "$prefix runtime-helper-1 forwarding ${Source} at ${stamp}: $snippet. Interpretation: synchronize with all runtime agents; helper1 has no product-code scope unless explicitly assigned."

  if ($SuppressUserFeedbackFanout) {
    if ($Interrupt) {
      Add-Content -LiteralPath $WaveGates -Value "`n- [$stamp] USER_FEEDBACK_OBSERVED_NO_FANOUT from ${Source}: $snippet" -Encoding UTF8
    }
    Write-MonitorLog "observed ${Source}; fan-out suppressed per latest user/QA directive"
    return
  }

  foreach ($recipient in $Recipients) {
    Send-AgentMessage $recipient $message
    Add-Content -LiteralPath $Feedback -Value "- Helper1 forwarded ${Source} to $recipient at $((Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz'))." -Encoding UTF8
  }
  if ($Interrupt) {
    Add-Content -LiteralPath $WaveGates -Value "`n- [$stamp] HIGH_PRIORITY_INTERRUPT from ${Source}: $snippet" -Encoding UTF8
  }
  Write-MonitorLog "forwarded ${Source} to $($Recipients.Count) recipients; interrupt=$Interrupt"
}

function Append-UserFeedbackSection {
  param(
    [string]$Title,
    [string]$Text,
    [string]$Interpretation
  )
  $stamp = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')
  $section = @"

## $stamp $Title

User feedback: $Text

Helper1 interpretation: $Interpretation

Forwarding log:
"@
  Add-Content -LiteralPath $Feedback -Value $section -Encoding UTF8
}

function Ensure-Broker {
  param($State)
  if (Get-BrokerHealthy) { return $true }
  $now = (Get-Date).ToUniversalTime()
  $last = [datetime]::MinValue
  if (-not [string]::IsNullOrWhiteSpace([string]$State.lastBrokerStartAttempt)) {
    try { $last = [datetime]::Parse([string]$State.lastBrokerStartAttempt).ToUniversalTime() } catch { $last = [datetime]::MinValue }
  }
  if (($now - $last).TotalSeconds -ge 60) {
    try {
      Start-Process -WindowStyle Hidden -FilePath powershell.exe -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $AgentBus, 'serve', '--bus', $Bus, '--host', '127.0.0.1', '--port', '8765') | Out-Null
      $State.lastBrokerStartAttempt = $now.ToString('o')
      Write-State $State
      Write-MonitorLog 'broker unhealthy; attempted hidden serve restart'
    } catch {
      Write-MonitorLog "broker restart attempt failed: $($_.Exception.Message)"
    }
  }
  return $false
}

New-Item -ItemType Directory -Force -Path $Coord | Out-Null
if (-not (Test-Path -LiteralPath $Feedback)) { New-Item -ItemType File -Path $Feedback | Out-Null }
if (-not (Test-Path -LiteralPath $Bus)) { Invoke-AgentBus -CliArgs @('init', '--bus', $Bus) | Out-Null }

$state = Read-State
Send-AgentStatus 'waiting' 'runtime-helper-1 quiet monitor active; no user-message fan-out; watching bus and USER_FEEDBACK.md'
Write-MonitorLog 'monitor started'

while ($true) {
  try {
    $brokerHealthy = Ensure-Broker $state

    $currentBusLines = Get-BusLineCount
    if ([int64]$state.busLines -gt $currentBusLines) {
      $state.busLines = $currentBusLines
      Write-State $state
    }
    if ($currentBusLines -gt [int64]$state.busLines) {
      $newLines = Get-Content -LiteralPath $Bus | Select-Object -Skip ([int]$state.busLines)
      foreach ($line in $newLines) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        try {
          $event = $line | ConvertFrom-Json -ErrorAction Stop
        } catch {
          Write-MonitorLog "skipped unparsable bus line: $($_.Exception.Message)"
          continue
        }
        if ([string]$event.type -ne 'msg') { continue }
        $from = [string]$event.from
        $to = [string]$event.to
        $text = [string]$event.text
        if ($from -eq 'user' -and -not [string]::IsNullOrWhiteSpace($text)) {
          Append-UserFeedbackSection 'Bus Feedback From User' $text 'observed from Agent Bus user message. Automatic fan-out is suppressed per latest user/QA directive; runtime-qa is canonical relay unless it explicitly asks helper1 to forward.'
          Forward-Feedback 'USER_BUS_FEEDBACK_FORWARD' $text (Test-InterruptText $text) "bus user message $($event.id)"
        } elseif (($to -eq $Agent -or $to -eq '*') -and $text -match '(?i)\b(BLOCKED|BLOCKER|NEED_USER_DECISION)\b') {
          Write-MonitorLog "observed blocker-related message from $from to ${to}: $text"
        }
      }
      $state.busLines = Get-BusLineCount
      $state.feedbackChars = (Get-RawText $Feedback).Length
      Write-State $state
    }

    $feedbackText = Get-RawText $Feedback
    $feedbackChars = $feedbackText.Length
    if ([int64]$state.feedbackChars -gt $feedbackChars) {
      $state.feedbackChars = $feedbackChars
      Write-State $state
    }
    if ($feedbackChars -gt [int64]$state.feedbackChars) {
      $delta = $feedbackText.Substring([int]$state.feedbackChars)
      if (-not (Test-InternalFeedbackOnly $delta)) {
        Forward-Feedback 'USER_FEEDBACK_FILE_NEW' $delta (Test-InterruptText $delta) 'USER_FEEDBACK.md addition'
      } else {
        Write-MonitorLog 'ignored USER_FEEDBACK.md internal forwarding-log delta'
      }
      $state.feedbackChars = (Get-RawText $Feedback).Length
      $state.busLines = Get-BusLineCount
      Write-State $state
    }

    $maxLiveSeq = Get-LiveMaxSeq
    if ([int64]$state.liveSeq -gt $maxLiveSeq) {
      $state.liveSeq = $maxLiveSeq
      Write-State $state
    }
    $liveEvents = Get-LiveEventsAfter -Seq ([int64]$state.liveSeq)
    foreach ($liveEvent in $liveEvents) {
      if ([int64]$liveEvent.seq -gt [int64]$state.liveSeq) {
        $state.liveSeq = [int64]$liveEvent.seq
      }
      $payload = $liveEvent.payload
      $source = [string]$payload.source
      $actor = [string]$liveEvent.actor
      $text = [string]$payload.text
      if ([string]$liveEvent.type -eq 'user.interrupt_created' -and ($actor -eq 'operations-console' -or $source -eq 'operations-console') -and -not [string]::IsNullOrWhiteSpace($text)) {
        Append-UserFeedbackSection "Live Feedback seq$($liveEvent.seq)" $text "forwarded from live operations-console event seq=$($liveEvent.seq)."
        Forward-Feedback 'USER_FEEDBACK_FORWARD_LIVE' $text $true "live operations-console event seq$($liveEvent.seq)"
        $state.feedbackChars = (Get-RawText $Feedback).Length
        $state.busLines = Get-BusLineCount
      }
    }
    Write-State $state

    $now = (Get-Date).ToUniversalTime()
    $lastHeartbeat = [datetime]::MinValue
    if (-not [string]::IsNullOrWhiteSpace([string]$state.lastHeartbeat)) {
      try { $lastHeartbeat = [datetime]::Parse([string]$state.lastHeartbeat).ToUniversalTime() } catch { $lastHeartbeat = [datetime]::MinValue }
    }
    if (($now - $lastHeartbeat).TotalSeconds -ge 60) {
      $health = if ($brokerHealthy) { 'broker healthy' } else { 'broker unavailable; file fallback active' }
      Send-AgentStatus 'waiting' "quiet monitor heartbeat; $health; no user-message fan-out"
      $state.lastHeartbeat = $now.ToString('o')
      Write-State $state
      Write-MonitorLog "heartbeat sent; $health"
    }
  } catch {
    Write-MonitorLog "loop error: $($_.Exception.Message)"
  }
  Start-Sleep -Seconds 5
}
