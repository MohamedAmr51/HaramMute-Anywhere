#!/usr/bin/env python3
"""
hm.py - Use the HaramMute desktop engine on anything, not just YouTube in the browser.

  hm "https://www.tiktok.com/@user/video/123"      -> vocals.mp3 (music removed)
  hm "https://x.com/user/status/123" --video       -> video with music removed
  hm "D:\\Lectures\\talk.mp4"                       -> talk.nomusic.mp4
  hm a.mp4 b.mkv "https://vimeo.com/123" --out D:\\Clean
  hm --install-sendto                               -> adds "HaramMute (remove music)" to right-click > Send to

Install with install.ps1 (adds the `hm` command and the Send to entry).

Needs the HaramMute tray app running (it serves the API on 127.0.0.1:8765).
Pure standard library: runs on HaramMute's bundled Python or any Python 3.8+.
"""
import argparse
import http.server
import json
import mimetypes
import os
import shutil
import socketserver
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

__version__ = "1.1.1"

HM_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "HaramMute"
API = os.environ.get("HARAMMUTE_API", "http://127.0.0.1:{}".format(
    (HM_DIR / "port.txt").read_text().strip() if (HM_DIR / "port.txt").exists() else "8765"))
FFMPEG = str(HM_DIR / "bin" / "ffmpeg.exe") if (HM_DIR / "bin" / "ffmpeg.exe").exists() else (shutil.which("ffmpeg") or "ffmpeg")
HM_PYTHON = HM_DIR / "python" / "python.exe"   # has yt_dlp installed
STALL_SECONDS = 15 * 60
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi", ".flv", ".wmv", ".ts", ".3gp"}
AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".flac", ".wma"}
FORCED_TYPES = {".mkv": "video/x-matroska", ".webm": "video/webm", ".mov": "video/quicktime",
                ".m4v": "video/mp4", ".ts": "video/mp2t", ".flv": "video/x-flv", ".opus": "audio/ogg"}


# ---------------------------------------------------------------- HTTP helpers
def api(method, path, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode()).get("detail")
        except Exception:
            detail = None
        raise RuntimeError(f"HaramMute API {e.code} on {path}: {detail or e.reason}") from None


def download(path, dest):
    with urllib.request.urlopen(API + path, timeout=120) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def check_server():
    try:
        api("GET", "/health", timeout=5)
    except Exception:
        sys.exit(f"HaramMute engine not reachable at {API}.\n"
                 f"Start it first: {HM_DIR / 'HaramMute.bat'} (or the tray app).")


# ------------------------------------------- serve a local file to the engine
class _OneFileHandler(http.server.SimpleHTTPRequestHandler):
    target: Path = None  # set per server

    def translate_path(self, path):
        return str(self.target)  # only ever serve the one file

    def guess_type(self, path):
        ext = self.target.suffix.lower()
        return FORCED_TYPES.get(ext) or mimetypes.guess_type(self.target.name)[0] or "video/mp4"

    def log_message(self, *a):
        pass


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # yt-dlp probes the file (metadata check, one try per cookie browser) and hangs up
        # mid-transfer. That's expected; don't print a traceback for it.
        if isinstance(sys.exc_info()[1], (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def serve_file(path: Path):
    handler = type("H", (_OneFileHandler,), {"target": path})
    srv = _Server(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    # Keep the real extension in the URL so yt-dlp's generic extractor recognises it.
    url = f"http://127.0.0.1:{srv.server_address[1]}/media/{urllib.parse.quote(path.stem)}{path.suffix.lower()}"
    return srv, url


# ------------------------------------------------------------- core workflow
def run_job(url, fresh=False):
    job = api("POST", "/jobs", {"url": url, "stems": 2, "skip_cache": fresh})
    job_id, last = job["job_id"], None
    last_change = time.time()
    while True:
        job = api("GET", f"/jobs/{job_id}")
        status = job["status"]
        pct = int((job.get("progress") or 0) * 100)
        chunks = f" chunks {job['chunks_completed']}/{job['total_chunks']}" if job.get("total_chunks") else ""
        line = f"  [{status}] {pct}%{chunks} {job.get('message') or ''}"
        if line != last:
            print(line, flush=True)
            last, last_change = line, time.time()
        elif time.time() - last_change > STALL_SECONDS:
            raise RuntimeError(f"no progress for {STALL_SECONDS // 60} min (job {job_id}); check HaramMute logs")
        if status == "completed":
            return job
        if status == "failed":
            raise RuntimeError(job.get("error_detail") or job.get("message") or "job failed")
        time.sleep(2)


def get_vocals(job, dest: Path):
    if job.get("preview_url"):
        download(job["preview_url"], dest)
        return dest
    # Fallback: stitch chunk MP3s if no full stem is exposed
    n = job.get("total_chunks") or 0
    if not n:
        raise RuntimeError("Job finished but returned no audio")
    parts = []
    for i in range(n):
        p = dest.with_name(f"{dest.stem}.part{i}.mp3")
        download(f"/jobs/{job['job_id']}/chunks/{i}/vocals", p)
        parts.append(p)
    lst = dest.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(dest)], check=True)
    for p in parts + [lst]:
        p.unlink(missing_ok=True)
    return dest


def mux(video: Path, vocals: Path, out: Path):
    out_ext = ".mp4" if video.suffix.lower() in {".mp4", ".mov", ".m4v"} else ".mkv"
    out = out.with_name(out.name + out_ext)
    if out.resolve() == video.resolve():
        raise RuntimeError(f"refusing to overwrite the source file {video}")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(video), "-i", str(vocals),
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                    "-movflags", "+faststart", str(out)], check=True)
    return out


def fetch_video(url, workdir: Path) -> Path:
    py = str(HM_PYTHON) if HM_PYTHON.exists() else sys.executable
    tmpl = str(workdir / "src.%(ext)s")
    subprocess.run([py, "-m", "yt_dlp", "--no-playlist", "-f", "bv*[height<=1080]+ba/b",
                    "--merge-output-format", "mkv", "--ffmpeg-location", FFMPEG, "-o", tmpl, url], check=True)
    return next(p for p in workdir.glob("src.*") if p.suffix != ".part")


def safe_name(s):
    keep = "".join(c if c.isalnum() or c in " -_." else "_" for c in s).strip()
    return (keep or "video")[:80]


def resolve_input(item):
    """Return ('url', str) or ('file', Path). Tolerates stray quotes and a missing extension."""
    s = item.strip().strip("\"'").strip()
    if s.lower().startswith(("http://", "https://")):
        return "url", s
    p = Path(s)
    if p.is_file():
        return "file", p.resolve()
    # Extension left off (Explorer hides them by default): look for name.<media ext>
    parent = p.parent if str(p.parent) not in ("", ".") else Path.cwd()
    if parent.is_dir():
        matches = [c for c in parent.iterdir()
                   if c.is_file() and c.stem == p.name and c.suffix.lower() in VIDEO_EXTS | AUDIO_EXTS]
        if len(matches) == 1:
            return "file", matches[0].resolve()
        if len(matches) > 1:
            raise RuntimeError("several files match, add the extension: " + ", ".join(m.name for m in matches))
        close = sorted(c.name for c in parent.iterdir() if c.is_file() and c.name.startswith(p.name[:12]))[:5]
        hint = ("\n    similar files here:\n      " + "\n      ".join(close)) if close else ""
        raise RuntimeError(f"file not found: {p}{hint}")
    raise RuntimeError(f"file not found (folder doesn't exist): {parent}")


def process(item, out_dir: Path, want_video: bool, fresh: bool):
    kind, target = resolve_input(item)
    is_file = kind == "file"
    p = target if is_file else Path()
    item = target if not is_file else str(target)
    print(f"\n==> {p.name if is_file else item}")
    srv = None
    try:
        if is_file:
            srv, url = serve_file(p.resolve())
            base = out_dir / p.stem
        else:
            url = item
            parsed = urllib.parse.urlparse(item)
            base = out_dir / safe_name(f"{parsed.netloc}_{parsed.path.strip('/').replace('/', '_')}")
        job = run_job(url, fresh)
    finally:
        if srv:
            srv.shutdown()

    vocals = get_vocals(job, base.with_name(base.name + ".vocals.mp3"))
    is_audio = is_file and p.suffix.lower() in AUDIO_EXTS
    if is_audio or (not is_file and not want_video):
        print(f"  done -> {vocals}")
        return vocals

    if is_file:
        out = mux(p, vocals, base.with_name(base.name + ".nomusic"))
    else:
        work = base.with_name(base.name + ".tmp")
        work.mkdir(exist_ok=True)
        try:
            print("  downloading video track...")
            out = mux(fetch_video(url, work), vocals, base.with_name(base.name + ".nomusic"))
        finally:
            shutil.rmtree(work, ignore_errors=True)
    vocals.unlink(missing_ok=True)
    print(f"  done -> {out}")
    return out


SENDTO_NAME = "HaramMute (remove music)"


def _sendto_dir():
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "SendTo"


def install_sendto():
    """Add a right-click > Send to entry: a .lnk with HaramMute's icon pointing at a small wrapper."""
    script = Path(__file__).resolve()
    py = HM_PYTHON if HM_PYTHON.exists() else Path(sys.executable)
    wrapper = script.with_name("hm-sendto.cmd")
    wrapper.write_text(f'@echo off\r\ntitle HaramMute - removing music\r\n"{py}" "{script}" %*\r\necho.\r\npause\r\n',
                       encoding="utf-8")

    sendto = _sendto_dir()
    old_cmd = sendto / f"{SENDTO_NAME}.cmd"          # from older versions of this script
    old_cmd.unlink(missing_ok=True)
    lnk = sendto / f"{SENDTO_NAME}.lnk"
    icon = HM_DIR / "icon.ico"
    q = lambda p: str(p).replace("'", "''")          # PowerShell single-quote escaping
    ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{q(lnk)}');"
          f"$s.TargetPath='{q(wrapper)}';"
          f"$s.WorkingDirectory='{q(script.parent)}';"
          + (f"$s.IconLocation='{q(icon)},0';" if icon.exists() else "")
          + "$s.Description='Remove background music with HaramMute';$s.Save()")
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       check=True, capture_output=True)
        print(f"Installed: right-click any video > Send to > {SENDTO_NAME}")
    except (OSError, subprocess.CalledProcessError):
        shutil.copyfile(wrapper, old_cmd)           # fallback: plain .cmd entry
        print(f"Installed (basic): right-click any video > Send to > {SENDTO_NAME}.cmd")


def uninstall_sendto():
    for ext in (".lnk", ".cmd"):
        (_sendto_dir() / f"{SENDTO_NAME}{ext}").unlink(missing_ok=True)
    Path(__file__).resolve().with_name("hm-sendto.cmd").unlink(missing_ok=True)
    print("Removed the Send to entry.")


def uninstall_all():
    """Run uninstall.ps1 in its own window after this process (and hm.cmd) has exited,
    so the install folder isn't in use when it gets deleted."""
    script = Path(__file__).resolve().with_name("uninstall.ps1")
    if not script.exists():
        sys.exit(f"uninstall.ps1 not found next to {Path(__file__).name}; "
                 "run: irm https://raw.githubusercontent.com/MohamedAmr51/harammute-anywhere/main/uninstall.ps1 | iex")
    q = str(script).replace("'", "''")
    cmd = f"Start-Sleep -Seconds 2; & '{q}'; Read-Host 'Press Enter to close'"
    subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0), close_fds=True)
    print("Uninstalling in a new window...")


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Remove music from any URL or local video using the HaramMute engine.")
    ap.add_argument("inputs", nargs="*", help="URLs (any yt-dlp site) and/or local video/audio files")
    ap.add_argument("--out", help="output folder (default: next to the file, or Downloads for URLs)")
    ap.add_argument("--video", action="store_true", help="for URLs: also download the video and output a full music-free video")
    ap.add_argument("--fresh", action="store_true", help="ignore HaramMute's cache and reprocess")
    ap.add_argument("--install-sendto", action="store_true", help="add a right-click 'Send to' entry (Windows)")
    ap.add_argument("--uninstall-sendto", action="store_true", help="remove the right-click 'Send to' entry")
    ap.add_argument("--uninstall", action="store_true", help="remove hm completely (command, Send to entry, files)")
    ap.add_argument("--version", action="version", version=f"hm {__version__}")
    a = ap.parse_args()

    if a.uninstall:
        return uninstall_all()
    if a.install_sendto:
        return install_sendto()
    if a.uninstall_sendto:
        return uninstall_sendto()
    if not a.inputs:
        ap.print_help()
        return
    check_server()
    failed = 0
    for item in a.inputs:
        try:
            kind, target = resolve_input(item)
            out_dir = Path(a.out) if a.out else (target.parent if kind == "file" else Path.home() / "Downloads")
            out_dir.mkdir(parents=True, exist_ok=True)
            process(item, out_dir, a.video, a.fresh)
        except (RuntimeError, subprocess.CalledProcessError, urllib.error.URLError) as e:
            failed += 1
            print(f"  FAILED: {e}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
