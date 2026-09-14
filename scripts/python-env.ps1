$ErrorActionPreference = 'Stop'
$script:ProjectRoot = Split-Path -Parent $PSScriptRoot
$script:TaskPython = Join-Path $script:ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $script:TaskPython)) {
    $script:PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($script:PythonCommand) {
        $script:TaskPython = $script:PythonCommand.Source
    } else {
        $script:TaskPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    }
}
if (-not (Test-Path -LiteralPath $script:TaskPython)) {
    throw 'Python 3.11+ is required. Install Python and the project dependencies first.'
}
$env:PYTHONPATH = "$script:ProjectRoot\.deps;$script:ProjectRoot" + $(if ($env:PYTHONPATH) { ";$env:PYTHONPATH" } else { '' })
