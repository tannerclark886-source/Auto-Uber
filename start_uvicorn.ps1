param(
    [string]$ProjectDir = "C:\Auto Uber API"
)

$python = Join-Path $ProjectDir '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Error "Python executable not found at $python. Activate venv or adjust path."
    exit 1
}

# Start uvicorn detached so the PowerShell session can be used for other tasks
Start-Process -FilePath $python -ArgumentList ('-m','uvicorn','main:app','--reload') -WorkingDirectory $ProjectDir
Write-Output "Started uvicorn using $python (working dir: $ProjectDir)"
