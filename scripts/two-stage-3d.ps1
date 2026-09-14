. "$PSScriptRoot\python-env.ps1"
& $script:TaskPython -m runtime.cli @args
exit $LASTEXITCODE
