"""
Download audio from a YouTube URL using yt-dlp.
Returns (temp_file_path, display_name, temp_dir). Caller must unlink the file and rmdir temp_dir.
"""

import os
import re
import sys
import tempfile
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path

# Overall download timeout (extract + download)
DOWNLOAD_TIMEOUT_SEC = int(os.getenv("YOUTUBE_DOWNLOAD_TIMEOUT", "180"))


# Accept youtube.com/watch, youtu.be, youtube.com/embed, etc. (with optional query params)
YOUTUBE_PATTERN = re.compile(
    r"(youtube\.com/(watch\?v=|embed/|v/)|youtu\.be/)[\w\-]+",
    re.IGNORECASE,
)


def is_youtube_url(url: str) -> bool:
    if not url or not url.strip():
        return False
    return bool(YOUTUBE_PATTERN.search(url.strip()))


def _progress_hook(d: dict, last_pct: list) -> None:
    """Print progress to stderr (throttled to ~10% steps)."""
    status = d.get("status")
    if status == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        if total:
            pct = 100.0 * (d.get("downloaded_bytes") or 0) / total
            step = int(pct // 10)
            if step > last_pct[0]:
                last_pct[0] = step
                print(f"[DJMashAI] Downloading... {min(step * 10, 100):.0f}%", file=sys.stderr, flush=True)
        else:
            if last_pct[0] < 0:
                last_pct[0] = 0
                print("[DJMashAI] Downloading...", file=sys.stderr, flush=True)
    elif status == "finished":
        print("[DJMashAI] Download finished, finalizing...", file=sys.stderr, flush=True)


def _download_youtube_audio_impl(url: str) -> tuple[str, str, str]:
    """Actual download logic (no timeout)."""
    import yt_dlp

    tmpdir = tempfile.mkdtemp(prefix="djmash_yt_")
    last_pct: list = [-1]
    outtmpl = os.path.join(tmpdir, "audio.%(ext)s")
    socket_timeout = int(os.getenv("YOUTUBE_SOCKET_TIMEOUT", "60"))
    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
        "outtmpl": outtmpl,
        "quiet": False,
        "no_warnings": True,
        "socket_timeout": socket_timeout,
        "retries": 3,
        "fragment_retries": 3,
        "progress_hooks": [lambda d: _progress_hook(d, last_pct)],
        "noplaylist": True,  # Download only the single video, not the whole playlist/radio mix
    }

    display_name = "YouTube track"
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print("[DJMashAI] Extracting video info...", file=sys.stderr, flush=True)
            info = ydl.extract_info(url, download=True)
            if info:
                display_name = (info.get("title") or info.get("id") or display_name).strip() or display_name
        for p in Path(tmpdir).iterdir():
            if p.is_file() and p.suffix.lower() in (".mp3", ".m4a", ".webm", ".opus", ".ogg"):
                return str(p), display_name, tmpdir
        raise RuntimeError("yt-dlp did not produce an audio file")
    except Exception:
        for p in Path(tmpdir).iterdir():
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
        try:
            Path(tmpdir).rmdir()
        except Exception:
            pass
        raise


def download_youtube_audio(url: str) -> tuple[str, str, str]:
    """
    Download best audio from YouTube URL to a temp file.
    Returns (path_to_audio_file, display_name, temp_dir). Caller must unlink file and rmdir temp_dir.
    Raises on invalid URL or download failure. Uses a timeout to avoid hanging forever.
    """
    url = url.strip()
    if not is_youtube_url(url):
        raise ValueError("Invalid YouTube URL")

    try:
        import yt_dlp
    except ImportError:
        raise ImportError("Install yt-dlp: pip install yt-dlp") from None

    from concurrent.futures import ThreadPoolExecutor

    tmpdir = None
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_download_youtube_audio_impl, url)
            try:
                path, display_name, tmpdir = future.result(timeout=DOWNLOAD_TIMEOUT_SEC)
            except FuturesTimeoutError:
                raise RuntimeError(
                    f"YouTube download timed out after {DOWNLOAD_TIMEOUT_SEC}s. "
                    "Try a shorter video or set YOUTUBE_DOWNLOAD_TIMEOUT in .env."
                ) from None
        return path, display_name, tmpdir
    except Exception as e:
        if tmpdir and Path(tmpdir).exists():
            for p in Path(tmpdir).iterdir():
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass
            try:
                Path(tmpdir).rmdir()
            except Exception:
                pass
        raise e
