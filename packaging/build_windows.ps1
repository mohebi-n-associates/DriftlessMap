$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $projectRoot

python -m pip install --upgrade ".[czi,desktop-build]"
python -m PyInstaller --noconfirm --clean packaging/DriftlessMap.spec

$version = python -c "from driftlessmap.version import __version__; print(__version__)"
$artifact = "dist/DriftlessMap-$version-Windows-x64.zip"
if (Test-Path $artifact) {
    Remove-Item $artifact
}
Compress-Archive -Path "dist/DriftlessMap/*" -DestinationPath $artifact
Write-Host "Created $artifact"
