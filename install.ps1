# HaramMute Anywhere - installer
#   irm https://raw.githubusercontent.com/MohamedAmr51/harammute-anywhere/main/install.ps1 | iex
# or download the repo and double-click install.bat
#
# Installs to %LOCALAPPDATA%\HaramMute-Anywhere (outside HaramMute's folder, so its updates can't remove it),
# adds the `hm` command to your user PATH, and adds a right-click "Send to" entry.

$HmaSourceDir = $PSScriptRoot   # empty when piped through iex -> download from GitHub instead

& {
    $ErrorActionPreference = 'Stop'
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $Repo  = 'https://raw.githubusercontent.com/MohamedAmr51/harammute-anywhere/main'
    $HmDir = Join-Path $env:LOCALAPPDATA 'HaramMute'
    $Py    = Join-Path $HmDir 'python\python.exe'
    $Dest  = Join-Path $env:LOCALAPPDATA 'HaramMute-Anywhere'

    Write-Host ''
    Write-Host 'HaramMute Anywhere - installer' -ForegroundColor Cyan

    # 1. HaramMute desktop app must be installed (we use its Python, ffmpeg and yt-dlp)
    if (-not (Test-Path $Py)) {
        Write-Host "  HaramMute desktop app not found at $HmDir" -ForegroundColor Red
        Write-Host '  Install it from https://haram-mute.com, then run this installer again.'
        return
    }
    Write-Host "  [ok] HaramMute found"

    # 2. Copy / download files
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    foreach ($f in 'hm.py', 'uninstall.ps1') {
        $local = if ($HmaSourceDir) { Join-Path $HmaSourceDir $f } else { $null }
        if ($local -and (Test-Path $local)) {
            Copy-Item $local (Join-Path $Dest $f) -Force
        } else {
            Invoke-WebRequest "$Repo/$f" -OutFile (Join-Path $Dest $f) -UseBasicParsing
        }
    }
    Write-Host "  [ok] Files installed to $Dest"

    # 3. `hm` command
    Set-Content -Path (Join-Path $Dest 'hm.cmd') -Encoding ASCII -Value "@`"$Py`" `"%~dp0hm.py`" %*"

    # 4. Add to user PATH (read raw value so %VARS% in the user's PATH stay unexpanded)
    $key = 'HKCU:\Environment'
    $cur = (Get-Item $key).GetValue('Path', '', 'DoNotExpandEnvironmentNames')
    $parts = @($cur -split ';' | Where-Object { $_ })
    if ($parts -notcontains $Dest) {
        $new = (@($parts) + $Dest) -join ';'
        Set-ItemProperty -Path $key -Name Path -Value $new -Type ExpandString
        try {
            if (-not ('HmaWin32.Native' -as [type])) {
                Add-Type -Namespace HmaWin32 -Name Native -MemberDefinition '[DllImport("user32.dll", CharSet=CharSet.Auto)] public static extern IntPtr SendMessageTimeout(IntPtr h, uint m, UIntPtr w, string l, uint f, uint t, out UIntPtr r);'
            }
            $r = [UIntPtr]::Zero
            [HmaWin32.Native]::SendMessageTimeout([IntPtr]0xffff, 0x1A, [UIntPtr]::Zero, 'Environment', 2, 5000, [ref]$r) | Out-Null
        } catch { }
        Write-Host "  [ok] Added 'hm' command to PATH"
    } else {
        Write-Host "  [ok] 'hm' command already on PATH"
    }
    if (($env:Path -split ';') -notcontains $Dest) { $env:Path += ";$Dest" }

    # 5. Right-click > Send to (shortcut with HaramMute's icon)
    & $Py (Join-Path $Dest 'hm.py') --install-sendto | ForEach-Object { Write-Host "  [ok] $_" }

    # 6. Old manual install inside HaramMute\extras (from earlier instructions) is no longer needed
    $oldCopy = Join-Path $HmDir 'extras\hm.py'
    if (Test-Path $oldCopy) {
        Write-Host "  Note: an older copy exists at $oldCopy - you can delete the extras folder."
    }

    Write-Host ''
    Write-Host 'Done!' -ForegroundColor Green
    Write-Host '  Open a NEW terminal, then:   hm "D:\path\to\video.mp4"'
    Write-Host '  Or right-click a video  >  Send to  >  HaramMute (remove music)'
    Write-Host "  Uninstall:  powershell -ExecutionPolicy Bypass -File `"$Dest\uninstall.ps1`""
    Write-Host ''
}
