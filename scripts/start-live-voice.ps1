<#
.SYNOPSIS
  Loads .env into this terminal and starts the TravelMate backend for live voice (ADR 0008).

.DESCRIPTION
  The app never reads .env itself (SECURITY section 1), so this script copies each NAME=value line
  into this process's environment and then starts the backend from the same process. Nothing is
  written anywhere else.

  It NEVER prints a value. It reports only which names are set. Keep your key in .env, which git
  ignores; never paste it into a file that is committed.

.PARAMETER CheckOnly
  Load and check .env, say what is missing, and stop. Starts nothing and sends nothing.

.PARAMETER WithFrontend
  Also start the web interface (Vite) in a second window with live voice selected.

.EXAMPLE
  .\scripts\start-live-voice.ps1 -CheckOnly
  .\scripts\start-live-voice.ps1 -WithFrontend
#>
[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$WithFrontend,
    [string]$EnvFile = '',
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'

# The folder this script lives in. $PSScriptRoot can be empty when Windows PowerShell is started
# through -File with a path it cannot decode, so fall back to the invocation path, then to the
# current folder (run the script from the project root in that case).
$scriptDir = $PSScriptRoot
if ([string]::IsNullOrEmpty($scriptDir) -and $MyInvocation.MyCommand.Path) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if ([string]::IsNullOrEmpty($scriptDir)) {
    $scriptDir = Join-Path (Get-Location).Path 'scripts'
}
$root = (Resolve-Path (Join-Path $scriptDir '..')).Path
if ([string]::IsNullOrEmpty($EnvFile)) {
    $EnvFile = Join-Path $root '.env'
}

if (-not (Test-Path -LiteralPath $EnvFile)) {
    Write-Error "No .env file at $EnvFile. Create one (see .env.example); it is git-ignored."
}

# Load NAME=value lines. Blank lines and # comments are skipped. Values are taken as written,
# with surrounding whitespace and one pair of matching quotes removed. Nothing is echoed.
$loaded = [System.Collections.Generic.List[string]]::new()
foreach ($line in Get-Content -LiteralPath $EnvFile) {
    if ($line -match '^\s*(#|$)') { continue }
    if ($line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') { continue }
    $name = $Matches[1]
    $value = $Matches[2].Trim()
    if ($value.Length -ge 2 -and (($value[0] -eq '"' -and $value[-1] -eq '"') -or ($value[0] -eq "'" -and $value[-1] -eq "'"))) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    # A name left blank in .env stays unset, so the app's own "must be set" checks speak for it.
    if ($value -eq '') {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
        continue
    }
    [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    $loaded.Add($name)
}

function Test-IsSet([string]$Name) {
    return -not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($Name, 'Process'))
}

# Values the planning API and chat need to run the whole screen. Non-secret, and only filled in
# when .env did not already set them.
$defaults = [ordered]@{
    API_ENABLED                      = 'true'
    API_DEV_PRINCIPAL                = 'dev'
    API_CURRENCY                     = 'INR'
    API_RUN_MAX_STEPS                = '50'
    API_RUN_MAX_TOOL_CALLS           = '30'
    API_RUN_MAX_HUMAN_ROUNDS         = '5'
    API_MAX_RUNS_PER_HOUR_PER_OWNER  = '50'
    CONVERSATION_ENABLED             = 'true'
    CONVERSATION_MAX_MESSAGE_CHARS   = '500'
    CONVERSATION_LLM_MAX_OUTPUT_TOKENS = '300'
    CONVERSATION_LLM_TIMEOUT_SECONDS = '10'
}
foreach ($entry in $defaults.GetEnumerator()) {
    if (-not (Test-IsSet $entry.Key)) {
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process')
    }
}

Write-Host "Loaded $($loaded.Count) setting(s) from .env. Values are never shown."

# What live voice needs, by name only.
$required = @(
    'OPENAI_API_KEY', 'VOICE_ENABLED', 'VOICE_DEV_PRINCIPAL', 'VOICE_SESSION_MAX_SECONDS',
    'VOICE_SESSION_IDLE_SECONDS', 'VOICE_MAX_ACTIVE_SESSIONS_PER_OWNER',
    'VOICE_MAX_SESSIONS_PER_DAY_PER_OWNER', 'VOICE_REALTIME_MODEL', 'VOICE_REALTIME_VOICE',
    'VOICE_REALTIME_TRANSCRIPTION_MODEL', 'VOICE_REALTIME_SECRET_TTL_SECONDS',
    'VOICE_REALTIME_TIMEOUT_SECONDS', 'VOICE_REALTIME_MAX_OUTPUT_TOKENS',
    'VOICE_REALTIME_MAX_SECRETS_PER_HOUR'
)
$missing = @($required | Where-Object { -not (Test-IsSet $_) })
$liveOn = ([Environment]::GetEnvironmentVariable('VOICE_LIVE_ENABLED', 'Process') -eq 'true')

foreach ($name in $required) {
    $state = if (Test-IsSet $name) { 'set' } else { 'MISSING' }
    Write-Host ("  {0,-40} {1}" -f $name, $state)
}
Write-Host ("  {0,-40} {1}" -f 'VOICE_LIVE_ENABLED', $(if ($liveOn) { 'true' } else { 'false (live voice is OFF)' }))

if ($missing.Count -gt 0) {
    Write-Warning "Live voice needs these set in .env: $($missing -join ', ')"
}
if (-not $liveOn) {
    Write-Warning 'VOICE_LIVE_ENABLED is not true, so the voice button will stay on the scripted stand-in.'
}

if ($CheckOnly) {
    Write-Host 'Check only: nothing was started.'
    if ($missing.Count -gt 0 -or -not $liveOn) { exit 1 } else { exit 0 }
}
if ($missing.Count -gt 0 -and $liveOn) {
    Write-Error 'Not starting: live voice is switched on but required settings are missing (see above).'
}

# Pick the first Python that can actually import what the backend needs. A virtual environment can
# exist without the packages installed, so existing is not enough.
$python = $null
foreach ($candidate in @(
        (Join-Path $root 'backend\.venv\Scripts\python.exe'),
        (Join-Path $root 'aitravel\Scripts\python.exe'),
        'python')) {
    if ($candidate -ne 'python' -and -not (Test-Path -LiteralPath $candidate)) { continue }
    # A failed import prints a traceback; under 'Stop' that would end the script, so the probe runs
    # with errors allowed and only its exit code is used.
    $ErrorActionPreference = 'Continue'
    $null = & $candidate -c 'import fastapi, uvicorn, openai, langchain_core, pydantic_settings' 2>&1
    $works = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = 'Stop'
    if ($works) { $python = $candidate; break }
}
if (-not $python) {
    Write-Error 'No Python with the backend packages was found. Install them: pip install -e "backend[dev]"'
}

if ($WithFrontend) {
    $frontend = Join-Path $root 'frontend'
    $command = "`$env:VITE_VOICE_ADAPTER='realtime'; Set-Location -LiteralPath '$frontend'; npm run dev"
    Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoExit', '-Command', $command | Out-Null
    Write-Host 'Started the web interface in a new window: http://localhost:5173/'
} else {
    Write-Host 'Web interface: in another terminal run  $env:VITE_VOICE_ADAPTER="realtime"; cd frontend; npm run dev'
}

Write-Host "Starting the backend on http://127.0.0.1:$Port (Ctrl+C stops it)."
Set-Location -LiteralPath $root
& $python -m uvicorn app.main:app --app-dir backend --port $Port
