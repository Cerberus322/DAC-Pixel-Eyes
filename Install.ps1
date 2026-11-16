$ErrorActionPreference = 'Stop'
$eyeSource = Join-Path $PSScriptRoot 'DACPixelEyes'
if (-not (Test-Path -LiteralPath (Join-Path $eyeSource 'DACPixelEyes.exe'))) { $eyeSource = Join-Path $PSScriptRoot 'dist\DACPixelEyes' }
if (-not (Test-Path -LiteralPath (Join-Path $eyeSource 'DACPixelEyes.exe'))) { throw 'Extract the entire release ZIP before running this installer.' }
if (Get-Process -Name DACPixelEyes -ErrorAction SilentlyContinue) { throw 'Exit DAC Pixel Eyes from its tray icon before updating.' }
$eyeTarget = Join-Path $env:LOCALAPPDATA 'Programs\DACPixelEyes'
New-Item -ItemType Directory -Force -Path $eyeTarget | Out-Null
Copy-Item -Path (Join-Path $eyeSource '*') -Destination $eyeTarget -Recurse -Force
$eyeShell = New-Object -ComObject WScript.Shell
$eyeStartMenu = Join-Path ($eyeShell.SpecialFolders.Item('Programs')) 'DAC Pixel Eyes'
New-Item -ItemType Directory -Force -Path $eyeStartMenu | Out-Null
foreach ($eyeLink in @((Join-Path ($eyeShell.SpecialFolders.Item('Desktop')) 'DAC Pixel Eyes.lnk'),(Join-Path $eyeStartMenu 'DAC Pixel Eyes.lnk'))) {
    $eyeShortcut = $eyeShell.CreateShortcut($eyeLink)
    $eyeShortcut.TargetPath = Join-Path $eyeTarget 'DACPixelEyes.exe'
    $eyeShortcut.WorkingDirectory = $eyeTarget
    $eyeShortcut.Description = 'Animated eyes, games and a clock for GameDAC'
    $eyeShortcut.IconLocation = (Join-Path $eyeTarget 'DACPixelEyes.exe') + ',0'
    $eyeShortcut.Save()
}
Write-Output ('Installed to ' + $eyeTarget)
Start-Process -FilePath (Join-Path $eyeTarget 'DACPixelEyes.exe') -WindowStyle Normal
