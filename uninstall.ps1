# HaramMute Anywhere - uninstaller
# Easiest:  hm --uninstall
# Or:       irm https://raw.githubusercontent.com/MohamedAmr51/harammute-anywhere/main/uninstall.ps1 | iex
# Removes the `hm` command, the Send to entry and the install folder. HaramMute itself is not touched.

& {
    $Dest   = Join-Path $env:LOCALAPPDATA 'HaramMute-Anywhere'
    $SendTo = Join-Path $env:APPDATA 'Microsoft\Windows\SendTo'

    Write-Host ''
    Write-Host 'HaramMute Anywhere - uninstaller' -ForegroundColor Cyan
    Write-Host ''

    Write-Host '  [1/3] Removing "Send to" entry... ' -NoNewline
    foreach ($ext in '.lnk', '.cmd') {
        Remove-Item (Join-Path $SendTo "HaramMute (remove music)$ext") -Force -ErrorAction SilentlyContinue
    }
    Write-Host 'done' -ForegroundColor Green

    Write-Host "  [2/3] Removing 'hm' from PATH... " -NoNewline
    $key = 'HKCU:\Environment'
    $cur = (Get-Item $key).GetValue('Path', '', 'DoNotExpandEnvironmentNames')
    $parts = @($cur -split ';' | Where-Object { $_ -and $_ -ne $Dest })
    Set-ItemProperty -Path $key -Name Path -Value ($parts -join ';') -Type ExpandString
    Write-Host 'done' -ForegroundColor Green

    Write-Host '  [3/3] Deleting files... ' -NoNewline
    Remove-Item $Dest -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $Dest) {
        Write-Host 'partly' -ForegroundColor Yellow
        Write-Host "  Some files are in use. Close any 'hm' windows and delete $Dest manually."
    } else {
        Write-Host 'done' -ForegroundColor Green
    }

    Write-Host ''
    Write-Host 'HaramMute Anywhere removed. HaramMute itself was not touched.' -ForegroundColor Green
    Write-Host ''
}
