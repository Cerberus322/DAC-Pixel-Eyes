param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & $Python -m PyInstaller --noconfirm --windowed --onedir --name DACPixelEyes --icon "$PSScriptRoot\src\app.ico" --add-data "$PSScriptRoot\src\assets;assets" --add-data "$PSScriptRoot\src\app.ico;." --copy-metadata Pillow --copy-metadata requests --copy-metadata pystray --copy-metadata urllib3 --copy-metadata charset_normalizer --copy-metadata idna --copy-metadata certifi --copy-metadata six --distpath "$PSScriptRoot\dist" --workpath "$PSScriptRoot\build" --specpath "$PSScriptRoot\build" "$PSScriptRoot\src\app.py"
    if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
    $eyeRelease = Join-Path $PSScriptRoot 'release'
    $eyeStaging = Join-Path $PSScriptRoot ('build\package-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $eyeRelease | Out-Null
    New-Item -ItemType Directory -Force -Path $eyeStaging | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'dist\DACPixelEyes') -Destination $eyeStaging -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Install.ps1'),(Join-Path $PSScriptRoot 'README.md'),(Join-Path $PSScriptRoot 'RELEASE_NOTES.md') -Destination $eyeStaging
    $eyeZip = Join-Path $eyeRelease 'DACPixelEyes-v0.1.2-test-windows-x64.zip'
    Compress-Archive -Path (Join-Path $eyeStaging '*') -DestinationPath $eyeZip -Force
    $eyeHash = (Get-FileHash -LiteralPath $eyeZip -Algorithm SHA256).Hash.ToLowerInvariant()
    ($eyeHash + '  ' + [IO.Path]::GetFileName($eyeZip)) | Set-Content -LiteralPath (Join-Path $eyeRelease 'SHA256SUMS.txt') -Encoding ascii
    Write-Output ('Release ready: ' + $eyeZip)
} finally { Pop-Location }
