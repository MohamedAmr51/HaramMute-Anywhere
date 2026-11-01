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
    $Total = 5
    $script:step = 0

    function Step([string]$text) {
        $script:step++
        Write-Host ("  [{0}/{1}] {2}... " -f $script:step, $Total, $text) -NoNewline
    }
    function Ok([string]$note = 'done') { Write-Host $note -ForegroundColor Green }

    Write-Host ''
    Write-Host 'HaramMute Anywhere - installer' -ForegroundColor Cyan
    Write-Host '  Installing, please keep this window open until you see "Done!"' -ForegroundColor Yellow
    Write-Host ''

    try {
        # 1. HaramMute desktop app must be installed (we use its Python, ffmpeg and yt-dlp)
        Step 'Checking for HaramMute'
        if (-not (Test-Path $Py)) {
            Write-Host 'not found' -ForegroundColor Red
            Write-Host ''
            Write-Host "  HaramMute desktop app not found at $HmDir" -ForegroundColor Red
            Write-Host '  Install it from https://haram-mute.com, then run this installer again.'
            return
        }
        Ok 'found'

        # 2. Copy / download files
        Step $(if ($HmaSourceDir) { 'Copying files' } else { 'Downloading files' })
        New-Item -ItemType Directory -Force -Path $Dest | Out-Null
        foreach ($f in 'hm.py', 'uninstall.ps1') {
            $local = if ($HmaSourceDir) { Join-Path $HmaSourceDir $f } else { $null }
            if ($local -and (Test-Path $local)) {
                Copy-Item $local (Join-Path $Dest $f) -Force
            } else {
                Invoke-WebRequest "$Repo/$f" -OutFile (Join-Path $Dest $f) -UseBasicParsing
            }
        }
        Ok

        # 3. `hm` command
        Step "Creating the 'hm' command"
        Set-Content -Path (Join-Path $Dest 'hm.cmd') -Encoding ASCII -Value "@`"$Py`" `"%~dp0hm.py`" %*"
        Ok

        # 4. Add to user PATH (read raw value so %VARS% in the user's PATH stay unexpanded)
        Step 'Adding it to PATH'
        $key = 'HKCU:\Environment'
        $cur = (Get-Item $key).GetValue('Path', '', 'DoNotExpandEnvironmentNames')
        $parts = @($cur -split ';' | Where-Object { $_ })
        if ($parts -notcontains $Dest) {
            Set-ItemProperty -Path $key -Name Path -Value ((@($parts) + $Dest) -join ';') -Type ExpandString
            try {
                if (-not ('HmaWin32.Native' -as [type])) {
                    Add-Type -Namespace HmaWin32 -Name Native -MemberDefinition '[DllImport("user32.dll", CharSet=CharSet.Auto)] public static extern IntPtr SendMessageTimeout(IntPtr h, uint m, UIntPtr w, string l, uint f, uint t, out UIntPtr r);'
                }
                $r = [UIntPtr]::Zero
                [HmaWin32.Native]::SendMessageTimeout([IntPtr]0xffff, 0x1A, [UIntPtr]::Zero, 'Environment', 2, 5000, [ref]$r) | Out-Null
            } catch { }
            Ok
        } else {
            Ok 'already there'
        }
        if (($env:Path -split ';') -notcontains $Dest) { $env:Path += ";$Dest" }

        # 5. Right-click > Send to (shortcut with HaramMute's icon)
        Step 'Adding right-click "Send to" entry'
        $ErrorActionPreference = 'Continue'   # PS 5.1 turns native stderr into errors under 'Stop'
        $out = & $Py (Join-Path $Dest 'hm.py') --install-sendto 2>&1
        $code = $LASTEXITCODE
        $ErrorActionPreference = 'Stop'
        if ($code -ne 0) { throw "Send to setup failed: $out" }
        Ok
    } catch {
        Write-Host 'failed' -ForegroundColor Red
        Write-Host ''
        Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host '  Please report it at https://github.com/MohamedAmr51/harammute-anywhere/issues'
        return
    }

    $oldCopy = Join-Path $HmDir 'extras\hm.py'
    if (Test-Path $oldCopy) {
        Write-Host ''
        Write-Host "  Note: an older copy exists in $HmDir\extras - you can delete that folder."
    }

    Write-Host ''
    Write-Host 'Done!' -ForegroundColor Green
    Write-Host '  Open a NEW terminal, then:   hm "D:\path\to\video.mp4"'
    Write-Host '  Or right-click a video  >  Send to  >  HaramMute (remove music)'
    Write-Host '  To uninstall later:          hm --uninstall'
    Write-Host ''
}
