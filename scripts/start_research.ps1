param(
    [Parameter(Mandatory=$true)][string]$Config,
    [Parameter(Mandatory=$true)][string]$Workspace,
    [string]$Goal,
    [switch]$Resume,
    [switch]$AllowLive
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) { throw 'Create the documented project .venv first.' }
if (-not $AllowLive) { throw 'Live access is disabled. Use -AllowLive only after model access and cost bounds are confirmed.' }
$operatorConfigPath = (Resolve-Path -LiteralPath $Config).Path
$operatorConfig = Get-Content -LiteralPath $operatorConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$credentialName = $operatorConfig.connection.api_key_env
if ([string]::IsNullOrWhiteSpace($credentialName)) { $credentialName = 'AUTORESEARCH_API_KEY' }
if ($credentialName -notmatch '^[A-Za-z_][A-Za-z0-9_]{0,127}$') { throw 'Invalid API key environment variable name.' }
$previousCredential = [Environment]::GetEnvironmentVariable($credentialName, 'Process')
$keyBuffer = [IntPtr]::Zero
$operatorSecret = $null
try {
    if ([string]::IsNullOrWhiteSpace($previousCredential)) {
        $operatorSecret = Read-Host 'Enter model API key locally (hidden; not saved)' -AsSecureString
        $keyBuffer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($operatorSecret)
        [Environment]::SetEnvironmentVariable($credentialName, [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyBuffer), 'Process')
    }
    $runArguments = @('-m','autoresearch','research','--workspace',$Workspace,'--config',$operatorConfigPath,'--allow-live')
    if ($Goal) { $runArguments += @('--goal',$Goal) }
    if ($Resume) { $runArguments += '--resume' }
    & $projectPython @runArguments
    if ($LASTEXITCODE -ne 0) { throw 'Research command failed. Review the sanitized error; no automatic retry was made.' }
}
finally {
    [Environment]::SetEnvironmentVariable($credentialName, $previousCredential, 'Process')
    if ($keyBuffer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyBuffer) }
    if ($operatorSecret) { $operatorSecret.Dispose() }
}
