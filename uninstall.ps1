# Laser Photo Studio uninstall removes the Start menu shortcuts and File Explorer previews for .nc files.
# Jobs, photos and presets in Local AppData are kept.
$ErrorActionPreference = 'Stop'
$programs = [Environment]::GetFolderPath('Programs')
foreach ($n in 'Laser Photo Studio', 'Laser Perimeter Check') {
    Remove-Item -LiteralPath (Join-Path $programs "$n.lnk") -ErrorAction SilentlyContinue
}
$clsid = '{983206E5-1402-47E4-957D-D1E57EAD5DF9}'
Remove-Item -LiteralPath "HKCU:\Software\Classes\CLSID\$clsid" -Recurse -ErrorAction SilentlyContinue
foreach ($ext in '.nc', '.gcode', '.gc', '.ngc') {
    $k = "HKCU:\Software\Classes\SystemFileAssociations\$ext"
    $h = "$k\ShellEx\{e357fccd-a995-4576-b01f-234630154e96}"
    if ((Test-Path -LiteralPath $h) -and (Get-ItemProperty -LiteralPath $h).'(default)' -eq $clsid) {
        Remove-Item -LiteralPath $h
    }
    foreach ($e in "$k\ShellEx", $k) {   # remove the keys install.ps1 created, if nothing else uses them
        if ((Test-Path -LiteralPath $e) -and -not (Get-ChildItem -LiteralPath $e) -and -not (Get-Item -LiteralPath $e).Property) {
            Remove-Item -LiteralPath $e
        }
    }
}
Remove-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved' -Name $clsid -ErrorAction SilentlyContinue
Add-Type -Namespace LaserPhotoStudio -Name Shell -MemberDefinition '[DllImport("shell32.dll")] public static extern void SHChangeNotify(int e, uint f, IntPtr a, IntPtr b);'
[LaserPhotoStudio.Shell]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
Write-Output 'Removed the Start menu shortcuts and the .nc previews. Your jobs and presets are kept.'
