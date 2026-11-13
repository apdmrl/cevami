[CmdletBinding()]
param(
    [string]$Primary,
    [string]$Mirror,
    [string]$Verify,
    [string]$TrustedSha256,
    [switch]$Help
)
$ErrorActionPreference = 'Stop'
$backupExit = 1
Push-Location -LiteralPath $PSScriptRoot
try {
    $backupPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $backupPython)) { throw 'Python ortami bulunamadi.' }
    $backupArguments = @('-X', 'utf8', '-m', 'hadis_web.backup')
    if ($Primary) { $backupArguments += @('--primary', $Primary) }
    if ($Mirror) { $backupArguments += @('--mirror', $Mirror) }
    if ($Verify) { $backupArguments += @('--verify', $Verify) }
    if ($TrustedSha256) { $backupArguments += @('--trusted-sha256', $TrustedSha256) }
    if ($Help) { $backupArguments += '--help' }
    & $backupPython @backupArguments
    $backupExit = $LASTEXITCODE
} catch {
    Write-Host 'Yedek baslatilamadi. Python ortamini ve app/README.md adimlarini kontrol edin.'
} finally { Pop-Location }
exit $backupExit
