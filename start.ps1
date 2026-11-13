[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$Status,
    [ValidateRange(1, 65535)][int]$Port = 8765
)

$ErrorActionPreference = 'Stop'
$readerExit = 1
Push-Location -LiteralPath $PSScriptRoot
try {
    $readerPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $readerPython)) {
        throw 'Python ortami bulunamadi.'
    }
    $readerArguments = @('-X', 'utf8', '-m', 'hadis_web.launcher', '--port', [string]$Port)
    if ($NoBrowser) { $readerArguments += '--no-browser' }
    if ($Status) { $readerArguments += '--status' }
    & $readerPython @readerArguments
    $readerExit = $LASTEXITCODE
} catch {
    Write-Host 'Baslatma tamamlanamadi. app/README.md kurulum adimlarini ve Python ortamini kontrol edin.'
} finally {
    Pop-Location
}
exit $readerExit
