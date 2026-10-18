# Points Blender Lab desktop shortcuts at assets\blender-lab.ico.
# Run once from PowerShell:  powershell -ExecutionPolicy Bypass -File D:\Blender-Lab\tools\set-shortcut-icon.ps1
# It only changes the icon of shortcuts whose target is Start-Blender-Lab.bat.
param([string]$RepoRoot = (Split-Path -Parent $PSScriptRoot))

$icon = Join-Path $RepoRoot 'assets\blender-lab.ico'
if (-not (Test-Path $icon)) { throw "Icon not found: $icon. Run git pull in the Blender-Lab folder first." }

$shell = New-Object -ComObject WScript.Shell
$changed = 0
foreach ($folder in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('CommonDesktopDirectory'))) {
  Get-ChildItem -Path $folder -Filter *.lnk -ErrorAction SilentlyContinue | ForEach-Object {
    $link = $shell.CreateShortcut($_.FullName)
    if ($link.TargetPath -like '*Start-Blender-Lab.bat') {
      $link.IconLocation = "$icon,0"
      $link.Save()
      $changed++
      Write-Host "Updated icon for $($_.Name)"
    }
  }
}
if ($changed -eq 0) { Write-Warning 'No desktop shortcut to Start-Blender-Lab.bat was found.' }
else { Write-Host 'If the old icon still shows, sign out and back in, or restart Explorer.' }
