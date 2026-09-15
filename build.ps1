$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
python -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
python -m PyInstaller --noconfirm --clean --onefile --windowed --name PitchScope --collect-all pyaudiowpatch main.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
Write-Host 'Build ready: dist\PitchScope.exe'
