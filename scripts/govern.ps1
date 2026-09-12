. "$PSScriptRoot\python-env.ps1"
& $script:TaskPython "$PSScriptRoot\govern.py" @args
exit $LASTEXITCODE
