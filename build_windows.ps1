# Build the single-file Windows .exe. Run from the repo root on Windows:
#     powershell -ExecutionPolicy Bypass -File build_windows.ps1
# Produces dist\ImageCuller.exe (self-contained; no Python install needed).

$ErrorActionPreference = "Stop"

Write-Host "==> Creating build venv..."
py -3 -m venv .venv-build
.\.venv-build\Scripts\Activate.ps1

Write-Host "==> Installing runtime + build deps..."
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-build.txt

Write-Host "==> Running PyInstaller..."
pyinstaller --clean --noconfirm image-culler.spec

Write-Host ""
Write-Host "==> Done. Exe at: dist\ImageCuller.exe"
