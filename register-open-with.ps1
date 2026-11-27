# Offer Studio in Explorer's Open with menu. Never replaces UserChoice or existing defaults.
param(
    [Parameter(Mandatory)][string]$Pythonw,
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'

function Ensure-RegistryKey([string]$key) {
    if (-not (Test-Path -LiteralPath $key)) {
        New-Item -Path $key -Force | Out-Null
    }
}
$pythonPath = (Get-Item -LiteralPath $Pythonw).FullName
$scriptPath = Join-Path $PSScriptRoot 'Laser Photo Studio.pyw'
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) { throw 'Studio entry point is missing.' }
if ([IO.Path]::GetFileName($pythonPath) -ine 'pythonw.exe') { throw 'Use the Pythonw.exe from the Studio shortcut.' }
$openCommand = '"{0}" "{1}" -- "%1"' -f $pythonPath, $scriptPath
$progId = 'LaserPhotoStudio.Open'
$base = 'HKCU:\Software\Classes'
$types = '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tif', '.tiff', '.webp', '.heic', '.heif', '.lpsjob'
if (-not $Apply) {
    Write-Output "Preview only. Open With registration for $($types -join ', ')"
    Write-Output $openCommand
    return
}

function Set-DefaultValue([string]$key, [string]$value) {
    Ensure-RegistryKey $key
    Set-Item -LiteralPath $key -Value $value
}
Set-DefaultValue "$base\$progId" 'Laser Photo Studio'
Set-DefaultValue "$base\$progId\DefaultIcon" ('"{0}",0' -f (Join-Path $PSScriptRoot 'assets\job.ico'))
Set-DefaultValue "$base\$progId\shell\open\command" $openCommand
foreach ($ext in $types) {
    $key = "$base\$ext\OpenWithProgids"
    Ensure-RegistryKey $key
    New-ItemProperty -LiteralPath $key -Name $progId -PropertyType None -Value ([byte[]]@()) -Force | Out-Null
}
Write-Output 'Studio is available under Open with. If Explorer already showed the menu, close and reopen it.'
