# HaramMute Anywhere - uninstaller
#   powershell -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\HaramMute-Anywhere\uninstall.ps1"
# Removes the `hm` command, the Send to entry and the install folder. HaramMute itself is not touched.

& {
    $Dest   = Join-Path $env:LOCALAPPDATA 'HaramMute-Anywhere'
    $SendTo = Join-Path $env:APPDATA 'Microsoft\Windows\SendTo'

    foreach ($ext in '.lnk', '.cmd') {
        Remove-Item (Join-Path $SendTo "HaramMute (remove music)$ext") -Force -ErrorAction SilentlyContinue
    }

    $key = 'HKCU:\Environment'
    $cur = (Get-Item $key).GetValue('Path', '', 'DoNotExpandEnvironmentNames')
    $parts = @($cur -split ';' | Where-Object { $_ -and $_ -ne $Dest })
    Set-ItemProperty -Path $key -Name Path -Value ($parts -join ';') -Type ExpandString

    Remove-Item $Dest -Recurse -Force -ErrorAction SilentlyContinue

    Write-Host 'HaramMute Anywhere removed. (Open a new terminal for the PATH change to apply.)' -ForegroundColor Green
}
