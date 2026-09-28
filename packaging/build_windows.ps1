$ErrorActionPreference = "Stop"

# Native commands do not raise PowerShell errors; stop on any failure.
function Invoke-Checked {
    param([scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Command"
    }
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $projectRoot

# Exact versions keep release bundles reproducible.
Invoke-Checked {
    python -m pip install --upgrade `
        --constraint packaging/constraints-desktop.txt ".[czi,desktop-build]"
}
Invoke-Checked { python -m PyInstaller --noconfirm --clean packaging/DriftlessMap.spec }

$version = python -c "from driftlessmap.version import __version__; print(__version__)"
if ($LASTEXITCODE -ne 0 -or -not $version) {
    throw "Could not read the DriftlessMap version."
}

if ($env:WINDOWS_CERTIFICATE_PFX_BASE64) {
    $workDir = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
    $pfx = Join-Path $workDir "driftlessmap-signing.pfx"
    [IO.File]::WriteAllBytes($pfx, [Convert]::FromBase64String($env:WINDOWS_CERTIFICATE_PFX_BASE64))
    try {
        $signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" `
            -Recurse -Filter signtool.exe |
            Where-Object { $_.FullName -match "\\x64\\" } |
            Sort-Object FullName | Select-Object -Last 1
        if (-not $signtool) { throw "signtool.exe was not found." }
        Invoke-Checked {
            & $signtool.FullName sign /f $pfx /p $env:WINDOWS_CERTIFICATE_PASSWORD `
                /tr http://timestamp.digicert.com /td sha256 /fd sha256 `
                "dist/DriftlessMap/DriftlessMap.exe"
        }
    }
    finally {
        Remove-Item $pfx -ErrorAction SilentlyContinue
    }
}
else {
    Write-Host "Signing secrets are not configured; the executable is unsigned."
}

$artifact = "dist/DriftlessMap-$version-Windows-x64.zip"
if (Test-Path $artifact) {
    Remove-Item $artifact
}
Compress-Archive -Path "dist/DriftlessMap/*" -DestinationPath $artifact
Write-Host "Created $artifact"
