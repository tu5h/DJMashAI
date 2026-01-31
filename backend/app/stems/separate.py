"""
Stem separation — split a track into vocals, drums, bass, other.
Uses demucs (Python 3.12–compatible). Spleeter is not used (incompatible with Python 3.12).
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

STEM_NAMES = ("vocals", "drums", "bass", "other")


def _run_demucs(audio_path: Path, out_dir: Path, timeout: int = 600) -> dict[str, Path]:
    """Run demucs; return dict stem_name -> wav path."""
    # python -m demucs -n htdemucs -o out_dir audio_path
    # Output: out_dir/htdemucs/{track}/{drums,bass,other,vocals}.wav
    cmd = [
        shutil.which("python") or "python",
        "-m", "demucs",
        "-n", "htdemucs",
        "-o", str(out_dir),
        str(audio_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True, timeout=timeout)
    model_out = out_dir / "htdemucs"
    track_name = audio_path.stem
    stem_dir = model_out / track_name
    if not stem_dir.exists():
        subdirs = list(model_out.iterdir()) if model_out.exists() else []
        stem_dir = subdirs[0] if subdirs else stem_dir
    result: dict[str, Path] = {}
    for name in STEM_NAMES:
        wav = stem_dir / f"{name}.wav"
        if wav.exists():
            result[name] = wav
    return result


def separate_into_stems(audio_path: str | Path, timeout: int = 600) -> tuple[dict[str, Path], str]:
    """
    Separate audio into 4 stems (vocals, drums, bass, other).
    Uses demucs (works on Python 3.12+). Returns (stem_name -> wav_path, temp_dir).
    Caller must clean up temp_dir.
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio not found: {path}")
    tmpdir = tempfile.mkdtemp(prefix="djmash_stems_")
    out_dir = Path(tmpdir) / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        stems = _run_demucs(path, out_dir, timeout=timeout)
        if not stems:
            raise RuntimeError(
                "Stem separation failed. Install demucs: pip install demucs"
            )
        return stems, tmpdir
    except subprocess.CalledProcessError as e:
        import shutil as sh
        sh.rmtree(tmpdir, ignore_errors=True)
        raise RuntimeError(
            "Stem separation failed (demucs error). Install with: pip install demucs"
        ) from e
    except FileNotFoundError:
        import shutil as sh
        sh.rmtree(tmpdir, ignore_errors=True)
        raise RuntimeError(
            "Stem separation requires demucs. Install with: pip install demucs"
        ) from None
    except Exception:
        import shutil as sh
        sh.rmtree(tmpdir, ignore_errors=True)
        raise
