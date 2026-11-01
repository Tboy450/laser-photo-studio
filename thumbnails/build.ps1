# Builds LaserThumbnails.dll (File Explorer previews for .nc files) with Windows' own C# compiler.
# No downloads needed. install.ps1 registers it; uninstall.ps1 removes it.
$ErrorActionPreference = 'Stop'
$csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$out = Join-Path $PSScriptRoot 'LaserThumbnails.dll'
$tmp = Join-Path ([IO.Path]::GetTempPath()) "lps-thumbnails-$PID"
New-Item -ItemType Directory -Force $tmp | Out-Null
try {
    # Compile under the final file name: .NET uses it as the assembly's identity.
    & $csc /nologo /target:library /optimize+ /r:System.Drawing.dll "/out:$tmp\LaserThumbnails.dll" (Join-Path $PSScriptRoot 'NcThumbnails.cs')
    if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
    try { Copy-Item -Force "$tmp\LaserThumbnails.dll" $out }
    catch { throw 'LaserThumbnails.dll is in use by File Explorer. Run uninstall.ps1, sign out and in, then build again.' }
}
finally { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
Write-Output "Built $out"
