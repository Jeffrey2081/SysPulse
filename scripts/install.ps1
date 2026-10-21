# ==============================================================================
# SysPulse Windows Setup & Installer (PowerShell)
# Sets up Python virtual environment, dependencies, startup shortcut, and firewall.
# ==============================================================================

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "          ⚡ SYSPULSE WINDOWS INSTALLER ⚡                     " -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# 1. Detect Windows Version
$os = (Get-CimInstance Win32_OperatingSystem).Caption
Write-Host "✓ Detected OS: $os" -ForegroundColor Green

# 2. Check Python
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command py -ErrorAction SilentlyContinue
}

if (-not $pythonCmd) {
    Write-Host "✗ Python not found. Installing Python via winget..." -ForegroundColor Yellow
    winget install Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

$pyExe = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "py" }
Write-Host "✓ Using Python: $pyExe" -ForegroundColor Green

# 3. Directories
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$venvDir = Join-Path $projectRoot "venv"
$serverDir = Join-Path $projectRoot "server"

# 4. Set Up Virtual Environment
Write-Host "→ Setting up Python virtual environment..." -ForegroundColor Cyan
& $pyExe -m venv $venvDir
$venvPython = Join-Path $venvDir "Scripts\python.exe"

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $serverDir "requirements.txt")
Write-Host "✓ Dependencies installed." -ForegroundColor Green

# 5. Create Silent VBS Startup Launcher
$vbsPath = Join-Path $projectRoot "scripts\run_silent.vbs"
$vbsContent = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "$serverDir"
WshShell.Run """$venvPython"" main.py", 0, False
"@
Set-Content -Path $vbsPath -Value $vbsContent

# 6. Add to Windows Startup
$startupFolder = [System.Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startupFolder "SysPulse.lnk"
$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "wscript.exe"
$shortcut.Arguments = """$vbsPath"""
$shortcut.WorkingDirectory = $serverDir
$shortcut.Save()
Write-Host "✓ Added to Windows Startup ($shortcutPath)" -ForegroundColor Green

# 7. Add Windows Firewall Rule for Port 8888 (Optional)
try {
    New-NetFirewallRule -DisplayName "SysPulse Agent" -Direction Inbound -LocalPort 8888 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null
    Write-Host "✓ Windows Firewall rule configured for port 8888." -ForegroundColor Green
} catch {
    Write-Host "! Note: Run as Administrator to automatically open firewall port 8888." -ForegroundColor Yellow
}

# 8. Start Background Agent
Start-Process -FilePath "wscript.exe" -ArgumentList """$vbsPath""" -WorkingDirectory $serverDir
Start-Sleep -Seconds 1

# 9. Display Pairing QR Code
& $venvPython (Join-Path $serverDir "pairing.py")

Write-Host "`nSetup Complete! SysPulse is running in the background." -ForegroundColor Green
