$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    py -3.13 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment.' }
}
& .\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name A1Controller --icon app.ico app.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name A1Provisioner --icon app.ico provision_app.py
if ($LASTEXITCODE -ne 0) { throw 'Provisioner build failed.' }
Write-Output 'Created dist\A1Controller.exe and dist\A1Provisioner.exe. Runtime settings are not included.'
