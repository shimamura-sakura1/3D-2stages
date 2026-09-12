. "$PSScriptRoot\python-env.ps1"
Push-Location $script:ProjectRoot
try {
    & $script:TaskPython -m pytest -q @args
    $testExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $testExitCode
