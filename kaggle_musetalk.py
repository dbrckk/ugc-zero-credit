#!/usr/bin/env python3
"""Kaggle T4 x2 batch adapter for the real UGC/Piper/MuseTalk pipeline.

No public server, tunnels, GPU quotas bypass, fake generated frames, or paid API.
Installs into /kaggle/temp; only user-approved outputs enter /kaggle/working.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

from offline_presenter import clean_text, digest, required_reference

KAGGLE_WORK = Path("/kaggle/working")
SCRATCH = Path("/kaggle/temp/ugc-zero-credit")
REPO = Path(__file__).resolve().parent
MT_COMMIT = "0a89dec45a0192b824e3cf4daf96c239440c5ed8"
FR_LICENSE = "https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/siwis/medium/MODEL_CARD"
EN_LICENSE = "https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/lessac/medium/MODEL_CARD"
LANGUAGES = {
    "fr": ("fr_FR-siwis-medium", FR_LICENSE),
    "en": ("en_US-lessac-medium", EN_LICENSE),
}


def run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None):
    # No shell=True and no token/API key passed to subprocesses.
    subprocess.run(cmd, check=True, cwd=cwd, env=env)


def assets(input_root: Path) -> dict:
    if not input_root.is_dir() or input_root.is_symlink():
        raise ValueError("Ajouter un dataset Kaggle privé comme entrée /kaggle/input")
    videos = []
    for extension in ("mp4", "mov", "mkv"):
        videos.extend(input_root.rglob("presenter." + extension))
    videos = [p for p in videos if p.is_file() and not p.is_symlink()]
    if len(videos) != 1:
        raise ValueError("Il faut exactement un presenter.mp4/MOV/MKV dans les datasets attachés")
    video = videos[0]
    if any(p.is_symlink() for p in video.parents if p != input_root.parent):
        raise ValueError("Dataset avec liens symboliques interdit")
    directory = video.parent
    script_file = directory / "script.txt"
    language_file = directory / "language.txt"
    rights_file = directory / "portrait_rights.txt"
    for source in (script_file, language_file, rights_file):
        if source.is_symlink() or not source.is_file() or source.stat().st_size > 4096:
            raise ValueError("Fichiers requis dans le même dataset : script.txt, language.txt et portrait_rights.txt (4 Ko maximum)")
    language = language_file.read_text(encoding="utf-8-sig").strip().lower()
    if language not in LANGUAGES:
        raise ValueError("language.txt doit contenir exactement fr ou en")
    script = clean_text(script_file.read_text(encoding="utf-8-sig"))
    if len(script) > 350:
        raise ValueError("Script de publicité trop long : 350 caractères maximum pour le premier essai Kaggle")
    rights = required_reference(rights_file.read_text(encoding="utf-8-sig"), "Droits et consentement du sujet")
    if not 8 <= len(rights) <= 500 or "\n" in rights or "\r" in rights:
        raise ValueError("Une référence de droits explicite, sur une seule ligne (8–500 caractères), est requise")
    if video.stat().st_size > 120 * 1024 * 1024:
        raise ValueError("Clip source > 120 Mo : utiliser un clip plus court")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                            "-of", "json", str(video)], text=True, capture_output=True, check=True)
    info = json.loads(probe.stdout)
    stream = next(s for s in info["streams"] if s.get("codec_type") == "video")
    width, height = int(stream.get("width", 0)), int(stream.get("height", 0))
    duration = float(info["format"].get("duration", 0))
    if not math.isfinite(duration) or not .8 <= duration <= 60 or min(width, height) < 256 or height < width:
        raise ValueError("Clip invalide : vertical, 0,8 à 60 s et largeur/hauteur >= 256 requis")
    print("INPUT_OK", {"name": video.name, "size_mb": round(video.stat().st_size / 1048576, 1),
                        "duration": round(duration, 2), "resolution": [width, height],
                        "language": language, "script_characters": len(script)})
    return {"video": video, "script": script_file, "language": language, "rights": rights}


def gpu_preflight():
    if not KAGGLE_WORK.is_dir() or not Path("/kaggle/input").is_dir():
        raise RuntimeError("Exécution Kaggle requise : /kaggle/input et /kaggle/working absents")
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("KAGGLE_GPU_UNAVAILABLE : Settings > Accelerator > GPU T4 x2")
    count = torch.cuda.device_count()
    props = torch.cuda.get_device_properties(0)
    free, total = torch.cuda.mem_get_info(0)
    if props.total_memory < 8 * 1024**3 or free < 4 * 1024**3:
        raise RuntimeError("GPU0 : VRAM insuffisante pour le pipeline ; fermer les autres tâches")
    print("GPU_READY", {"count": count, "name": props.name, "vram_gib": round(props.total_memory / 1024**3, 1),
                        "free_gib": round(free / 1024**3, 1)})
    # A T4x2 exposes two separate 16 GiB cards. Do not pretend the memory pools combine.
    return props.name


def initialize():
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None or shutil.which("git") is None:
        raise RuntimeError("FFmpeg/ffprobe/Git absents de l'image Kaggle")
    scratch = SCRATCH
    scratch.mkdir(parents=True, exist_ok=True)
    toolenv = scratch / "uv-tools"
    if not (toolenv / "bin/uv").is_file():
        run([sys.executable, "-m", "venv", str(toolenv)])
        run([str(toolenv / "bin/python"), "-m", "pip", "install", "--disable-pip-version-check",
             "--quiet", "uv==0.9.18"])
    uv = str(toolenv / "bin/uv")
    run([uv, "python", "install", "3.10", "3.11"])
    gpuenv = scratch / "gpuenv"
    cpuenv = scratch / "cpuenv"
    if not (gpuenv / "bin/python").exists():
        run([uv, "venv", "--seed", "--python", "3.10", str(gpuenv)])
    if not (cpuenv / "bin/python").exists():
        run([uv, "venv", "--seed", "--python", "3.11", str(cpuenv)])
    gpu_python, cpu_python = str(gpuenv / "bin/python"), str(cpuenv / "bin/python")
    upstream = scratch / "musetalk"
    if not upstream.exists():
        run(["git", "clone", "--quiet", "https://github.com/TMElyralab/MuseTalk.git", str(upstream)])
        run(["git", "checkout", "--quiet", "--detach", MT_COMMIT], cwd=upstream)
    if not (upstream / ".git").is_dir() or subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=upstream, text=True).strip() != MT_COMMIT:
        raise RuntimeError("MuseTalk upstream non épinglé : refus de lancer une version inconnue")
    if not (scratch / ".dependencies-ok").is_file():
        run([uv, "pip", "install", "--python", gpu_python,
             "--index-url", "https://download.pytorch.org/whl/cu118",
             "torch==2.0.1", "torchvision==0.15.2", "torchaudio==2.0.2"])
        run([uv, "pip", "install", "--python", gpu_python, "-r", str(upstream / "requirements.txt"),
             "openmim==0.3.9"])
        mim = str(gpuenv / "bin/mim")
        limited = {**os.environ, "MAX_JOBS": "2", "CMAKE_BUILD_PARALLEL_LEVEL": "2"}
        for package in ("mmengine", "mmcv==2.0.1", "mmdet==3.1.0", "mmpose==1.1.0"):
            run([mim, "install", package], env=limited)
        run([uv, "pip", "install", "--python", cpu_python, "piper-tts==1.8.0"])
        (scratch / ".dependencies-ok").write_text("musetalk-v1.5\n", encoding="utf-8")
    # Source weights are fetched only during notebook setup, never during inference.
    run([gpu_python, str(REPO / "gpu_fetch_weights.py"), "--musetalk-dir", str(upstream)])
    voices = scratch / "voices"
    if not (voices / "fr_FR-siwis-medium.onnx").is_file() or not (voices / "en_US-lessac-medium.onnx").is_file():
        voices.mkdir(exist_ok=True)
        run([cpu_python, "-m", "piper.download_voices",
             "fr_FR-siwis-medium", "en_US-lessac-medium", "--data-dir", str(voices)])
    # Validate full MuseTalk import & available GPU memory before using private assets.
    run([cpu_python, str(REPO / "offline_presenter.py"), "doctor",
         "--musetalk-dir", str(upstream), "--musetalk-python", gpu_python])
    return {"gpu_python": gpu_python, "cpu_python": cpu_python, "upstream": upstream, "voices": voices}


def render(input_data: dict, installed: dict):
    from offline_presenter import inspect_video
    language = input_data["language"]
    voice_name, license_ref = LANGUAGES[language]
    out = KAGGLE_WORK / "ugc-v25-results"
    if out.is_symlink():
        raise ValueError("Dossier de résultats symbolique interdit")
    out.mkdir(parents=True, exist_ok=True)
    work_id = secrets.token_hex(4)
    wav = out / ("narration_" + work_id + ".wav")
    output = out / ("presenter_" + work_id + ".mp4")
    cpu_python = installed["cpu_python"]
    run([cpu_python, str(REPO / "offline_presenter.py"), "voice",
         "--text-file", str(input_data["script"]),
         "--voice-model", str(installed["voices"] / (voice_name + ".onnx")),
         "--voice-license-ref", license_ref, "--confirm-voice-rights",
         "--output", str(wav)])
    run([cpu_python, str(REPO / "offline_presenter.py"), "presenter",
         "--existing-narration", str(wav), "--source", str(input_data["video"]),
         "--voice-license-ref", license_ref, "--image-rights-ref", input_data["rights"],
         "--confirm-voice-rights", "--confirm-image-rights",
         "--musetalk-dir", str(installed["upstream"]),
         "--musetalk-python", installed["gpu_python"], "--output", str(output)])
    report = json.loads(output.with_suffix(".presenter.json").read_text(encoding="utf-8"))
    assert report["gpu_inference_executed"] is True and report["ffmpeg_full_decode"] is True
    assert report["publication_allowed_automatically"] is False
    assert report["sha256"] == digest(output)
    checked = inspect_video(output)
    assert checked["audio_stream"] and checked["video_stream"]
    print("REAL_GPU_RENDER_COMPLETED_NEEDS_HUMAN_REVIEW", str(output))
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description="Kaggle GPU T4 batch lip-sync, no paid credits")
    parser.add_argument("--stage", choices=["check-assets", "preflight", "all"], default="all")
    parser.add_argument("--input-root", type=Path, default=Path("/kaggle/input"))
    args = parser.parse_args(argv)
    source = assets(args.input_root)
    if args.stage == "check-assets":
        return
    gpu_preflight()
    if args.stage == "preflight":
        return
    installed = initialize()
    render(source, installed)


if __name__ == "__main__":
    main()
