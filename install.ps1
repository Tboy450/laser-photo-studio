# Laser Photo Studio 1.0 - install. Safe to run again. Per-user only: no admin rights needed.
#   * Desktop icons: "Laser Photo Studio" and "Laser Perimeter Check"
#   * Picture previews for laser G-code files (.nc .gcode .gc .ngc) in File Explorer
# uninstall.ps1 removes both again. Your jobs and presets are never touched.
$ErrorActionPreference = 'Stop'
$app = $PSScriptRoot

# 1. Python and the libraries the app uses
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python 3 is needed: install it from the Microsoft Store or python.org, then run this again.'
}
$pyw = & python -c "import os,sys; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))"
if (-not (Test-Path $pyw)) { throw "pythonw.exe not found next to python ($pyw)." }
$ErrorActionPreference = 'Continue'
& python -c "import numpy, PIL, serial" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { & python -m pip install --user --disable-pip-version-check numpy pillow pyserial }
$ErrorActionPreference = 'Stop'

# 2. Desktop icons
$desk = [Environment]::GetFolderPath('Desktop')
$ws = New-Object -ComObject WScript.Shell
function New-Icon($name, $arguments, $icon, $description) {
    $lnk = $ws.CreateShortcut((Join-Path $desk "$name.lnk"))
    $lnk.TargetPath = $pyw
    $lnk.Arguments = $arguments
    $lnk.WorkingDirectory = $app
    $lnk.IconLocation = "$icon,0"
    $lnk.Description = $description
    $lnk.Save()
    Write-Output "Desktop icon: $name"
}
New-Icon 'Laser Photo Studio' "`"$app\Laser Photo Studio.pyw`"" "$app\assets\icon.ico" `
    'Picture -> checked G-code -> safe runs on the Tronxy U20'
New-Icon 'Laser Perimeter Check' "`"$app\Laser Photo Studio.pyw`" --perimeter" "$app\assets\perimeter.ico" `
    'Check where a job will burn with the 1% positioning dot'

# 3. File Explorer previews for G-code files
$dll = Join-Path $app 'thumbnails\LaserThumbnails.dll'
if (-not (Test-Path $dll)) { & (Join-Path $app 'thumbnails\build.ps1') }
$clsid = '{983206E5-1402-47E4-957D-D1E57EAD5DF9}'
$name = 'Laser Photo Studio G-code previews'
function Set-Key($path, $values) {
    if (-not (Test-Path -LiteralPath $path)) { New-Item -Path $path -Force | Out-Null }
    foreach ($k in $values.Keys) { Set-ItemProperty -LiteralPath $path -Name $k -Value $values[$k] }
}
$com = @{ 'Class' = 'LaserPhotoStudio.Thumbnails.NcThumbnailProvider'
          'Assembly' = 'LaserThumbnails, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null'
          'RuntimeVersion' = 'v4.0.30319'
          'CodeBase' = ([Uri]$dll).AbsoluteUri }
$base = "HKCU:\Software\Classes\CLSID\$clsid"
Set-Key $base @{ '(default)' = $name }
Set-Key "$base\InprocServer32" (@{ '(default)' = 'mscoree.dll'; 'ThreadingModel' = 'Both' } + $com)
Set-Key "$base\InprocServer32\1.0.0.0" $com
Set-Key "$base\Implemented Categories\{62C8FE65-4EBB-45e7-B440-6E39B2CDBF29}" @{}
foreach ($ext in '.nc', '.gcode', '.gc', '.ngc') {
    Set-Key "HKCU:\Software\Classes\SystemFileAssociations\$ext\ShellEx\{e357fccd-a995-4576-b01f-234630154e96}" @{ '(default)' = $clsid }
}
Set-Key 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved' @{ $clsid = $name }
Add-Type -Namespace LaserPhotoStudio -Name Shell -MemberDefinition '[DllImport("shell32.dll")] public static extern void SHChangeNotify(int e, uint f, IntPtr a, IntPtr b);'
[LaserPhotoStudio.Shell]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
Write-Output 'File Explorer previews for .nc files: on (press F5 or reopen a folder to see them).'
