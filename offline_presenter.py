#!/usr/bin/env python3
"""Local real-voice speech generation and an optional GPU MuseTalk 1.5 bridge.

No external API calls, no model downloads, no automatic publishing. This module
does not generate an influencer's original appearance and does not assert that
its output achieves phoneme-perfect lip sync.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import wave

MAX_TEXT = 1200
SAFE_UPSTREAM_PATH = re.compile(r"^[A-Za-z0-9_./-]+$")
MODEL_REQUIRED = (
    "models/musetalkV15/unet.pth",
    "models/musetalkV15/musetalk.json",
    "models/sd-vae/config.json",
    "models/sd-vae/diffusion_pytorch_model.bin",
    "models/whisper/config.json",
    "models/whisper/pytorch_model.bin",
    "models/whisper/preprocessor_config.json",
    "models/face-parse-bisent/79999_iter.pth",
    "models/face-parse-bisent/resnet18-5c106cde.pth",
)
IMAGE_FORMATS = frozenset({".png", ".jpg", ".jpeg"})


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for part in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def clean_text(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("Le script vocal doit être une chaîne")
    text = re.sub(r"\s+", " ", text).strip()
    if not 2 <= len(text) <= MAX_TEXT:
        raise ValueError(f"Texte de narration : 2 à {MAX_TEXT} caractères")
    if any(ord(ch) < 32 for ch in text) or "<" in text or ">" in text:
        raise ValueError("Ne pas fournir de contrôle ou de HTML au synthétiseur")
    return text


def required_reference(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value.strip()) < 8:
        raise ValueError(f"{label} : référence de droits / licence obligatoire")
    return value.strip()


def voice_model(model: Path) -> dict:
    model = model.expanduser().resolve(strict=True)
    if model.suffix.lower() != ".onnx" or not model.is_file() or model.stat().st_size < 1000:
        raise ValueError("Modèle Piper .onnx local non valide")
    cfg = model.with_suffix(".onnx.json")
    if not cfg.is_file():
        raise FileNotFoundError(f"Configuration de la voix absente : {cfg}")
    info = json.loads(cfg.read_text(encoding="utf-8"))
    if not isinstance(info, dict) or not info.get("phoneme_type"):
        raise ValueError("Configuration Piper incomplète")
    language = info.get("language", {})
    code = language.get("code", "unknown") if isinstance(language, dict) else "unknown"
    return {"model": model, "config": cfg, "language": code, "config_data": info}


def audio_info(path: Path) -> dict:
    with wave.open(str(path), "rb") as wav:
        rate, channels, frames = wav.getframerate(), wav.getnchannels(), wav.getnframes()
        if not 8000 <= rate <= 96000 or not 1 <= channels <= 2 or frames < rate // 8:
            raise ValueError("Voix WAV invalide, vide ou extrêmement courte")
        return {"sample_rate": rate, "channels": channels,
                "duration": round(frames / rate, 3), "frames": frames}


def synthesize(text: str, model: Path, output: Path, *,
               voice_license_ref: str, confirmed: bool) -> dict:
    """Run actual Piper ONNX inference and publish WAV atomically without overwrite."""
    text = clean_text(text)
    if confirmed is not True:
        raise ValueError("Confirmer les droits et conditions de la voix avant synthèse")
    voice_license_ref = required_reference(voice_license_ref, "Licence vocale")
    details = voice_model(model)
    out = output.expanduser().resolve()
    if out.suffix.lower() != ".wav":
        raise ValueError("La sortie vocale doit être un fichier .wav")
    if out.exists() or out == details["model"] or out == details["config"]:
        raise FileExistsError(f"Sortie existante ou protégée : {out}")
    if not out.parent.is_dir():
        raise FileNotFoundError("Créer le dossier de sortie avant génération")
    try:
        from piper import PiperVoice
    except ImportError as exc:
        raise RuntimeError("Installer localement la dépendance gratuite : pip install piper-tts") from exc
    # The pinned local files are used; no remote voice inference is requested.
    piper = PiperVoice.load(str(details["model"]), use_cuda=False)
    with tempfile.TemporaryDirectory(prefix=".ugc-voice-", dir=out.parent) as tmpname:
        tmp = Path(tmpname) / "narration.wav"
        with wave.open(str(tmp), "wb") as wave_out:
            piper.synthesize_wav(text, wave_out)
        sound = audio_info(tmp)
        if sound["duration"] > 180:
            raise ValueError("Narration supérieure à trois minutes : raccourcir le script")
        meta = {
            "status": "VOICE_GENERATED_NOT_LIPSYNCED",
            "engine": "Piper ONNX CPU",
            "language": details["language"],
            "sample_rate": sound["sample_rate"],
            "duration": sound["duration"],
            "model_sha256": digest(details["model"]),
            "voice_license_ref": voice_license_ref,
            "rights_confirmed_by_operator": True,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "wav_sha256": digest(tmp),
            "no_paid_api": True,
            "no_model_download": True,
            "human_listening_required": True,
            "human_lip_sync_proven": False,
        }
        # Both files are staged on the output's filesystem, and never overwrite.
        manifest = out.with_suffix(".voice.json")
        if manifest.exists():
            raise FileExistsError(f"Rapport vocal existant : {manifest}")
        report_tmp = Path(tmpname) / "narration.voice.json"
        report_tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.link(tmp, out)
        try:
            os.link(report_tmp, manifest)
        except Exception:
            out.unlink(missing_ok=True)
            raise
    return {"output": str(out), "report": str(manifest), **meta}


def require_musetalk(musetalk: Path, interpreter: Path) -> dict:
    """Fail closed before attempting any expensive generation."""
    root = musetalk.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Dossier MuseTalk manquant")
    # MuseTalk upstream builds some FFmpeg commands via shell concatenation.
    if not SAFE_UPSTREAM_PATH.fullmatch(str(root)):
        raise ValueError("Chemin MuseTalk dangereux : utiliser lettres, chiffres, /, _ et - uniquement")
    inference_script = root / "scripts" / "inference.py"
    if not inference_script.is_file():
        raise FileNotFoundError("Installer le dépôt officiel TMElyralab/MuseTalk")
    # Check the real upstream command interface before loading CUDA or running
    # a costly GPU job. Reject an old or incompatible MuseTalk checkout.
    supported_flags = ("--inference_config", "--result_dir", "--unet_model_path",
                       "--unet_config", "--version", "--fps", "--batch_size",
                       "--output_vid_name", "--use_float16", "--ffmpeg_path")
    source = inference_script.read_text(encoding="utf-8")
    absent_flags = [flag for flag in supported_flags if flag not in source]
    if absent_flags:
        raise RuntimeError("Interface MuseTalk incompatible : " + ", ".join(absent_flags))
    missing = [p for p in MODEL_REQUIRED if not (root / p).is_file()]
    for group in ("models/sd-vae", "models/whisper", "models/face-parse-bisent"):
        if not (root / group).is_dir() or not any((root / group).iterdir()):
            missing.append(group + "/(poids absents)")
    if missing:
        raise FileNotFoundError("Poids MuseTalk manquants (aucun téléchargement auto) : " + ", ".join(missing))
    py = interpreter.expanduser().resolve(strict=True)
    if not py.is_file():
        raise FileNotFoundError(f"Python de MuseTalk manquant : {py}")
    check = subprocess.run(
        [str(py), "-c", "import torch; print('CUDA_AVAILABLE='+str(torch.cuda.is_available()))"],
        cwd=root, text=True, capture_output=True, timeout=30,
        env={**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"},
    )
    if check.returncode or "CUDA_AVAILABLE=True" not in check.stdout:
        raise RuntimeError("MuseTalk 1.5 indisponible : GPU NVIDIA CUDA / PyTorch CUDA fonctionnel requis")
    return {"root": root, "python": py, "missing_weights": []}


def inspect_video(path: Path) -> dict:
    try:
        p = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                            "-of", "json", str(path)], text=True, capture_output=True,
                           check=True, timeout=30)
        meta = json.loads(p.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Vidéo MuseTalk illisible : {exc}") from exc
    streams = meta.get("streams", [])
    if not any(v.get("codec_type") == "video" for v in streams):
        raise RuntimeError("MuseTalk n'a pas produit de piste vidéo")
    if not any(v.get("codec_type") == "audio" for v in streams):
        raise RuntimeError("MuseTalk n'a pas produit de piste audio")
    video = next(v for v in streams if v.get("codec_type") == "video")
    audio = next(v for v in streams if v.get("codec_type") == "audio")
    duration = float(meta.get("format", {}).get("duration", 0))
    if not math.isfinite(duration) or duration < .2:
        raise RuntimeError("Vidéo MuseTalk vide ou durée invalide")
    width, height = int(video.get("width", 0)), int(video.get("height", 0))
    if width < 160 or height < 160:
        raise RuntimeError("Vidéo MuseTalk de résolution insuffisante")
    def stream_duration(stream):
        value = stream.get("duration")
        try:
            result = float(value)
        except (ValueError, TypeError):
            return duration
        return result if math.isfinite(result) and result > 0 else duration
    video_seconds = stream_duration(video)
    audio_seconds = stream_duration(audio)
    if abs(video_seconds - audio_seconds) > .45:
        raise RuntimeError("Pistes audio et vidéo désynchronisées en durée")
    return {"duration": round(duration, 3), "video_stream": True, "audio_stream": True,
            "width": width, "height": height, "video_seconds": round(video_seconds, 3),
            "audio_seconds": round(audio_seconds, 3),
            "av_track_gap_ms": round(abs(video_seconds - audio_seconds) * 1000)}


def audible_audio_peak(path: Path) -> float:
    """Reject silent, empty or unreadable final audio using real FFmpeg decoding."""
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path), "-vn",
         "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, timeout=150)
    if result.returncode:
        raise RuntimeError("Impossible de décoder la piste audio MuseTalk")
    matched = re.search(r"max_volume:\\s*([-+]?\\d+(?:\\.\\d+)?) dB", result.stderr)
    if not matched or float(matched.group(1)) < -55:
        raise RuntimeError("Piste audio MuseTalk muette ou trop faible")
    return round(float(matched.group(1)), 2)


def presenter(*, text: str, model: Path, image: Path, musetalk: Path,
              interpreter: Path, output: Path, voice_license_ref: str,
              image_rights_ref: str, confirm_voice_rights: bool,
              confirm_image_rights: bool,
              existing_narration: Path | None = None) -> dict:
    """Synthesize actual speech and invoke preinstalled MuseTalk 1.5 locally."""
    if not confirm_voice_rights or not confirm_image_rights:
        raise ValueError("Les droits de la voix et du portrait doivent être confirmés")
    voice_license_ref = required_reference(voice_license_ref, "Licence vocale")
    image_rights_ref = required_reference(image_rights_ref, "Droits du portrait")
    if existing_narration is None:
        text = clean_text(text)
    if image.is_symlink():
        raise ValueError("Lien symbolique de portrait interdit")
    image = image.expanduser().resolve(strict=True)
    if image.suffix.lower() not in IMAGE_FORMATS or not image.is_file():
        raise ValueError("MuseTalk image : fournir un PNG/JPEG de portrait autorisé")
    # Never resolve a destination before checking whether it is a symlink.
    # A dangling link could otherwise redirect a generated commercial asset.
    out = output.expanduser().absolute()
    if out.is_symlink() or out.parent.is_symlink() or out.with_suffix(".presenter.json").is_symlink():
        raise ValueError("Liens symboliques de destination interdits")
    if out.suffix.lower() != ".mp4" or out.exists() or not out.parent.is_dir():
        raise ValueError("Sortie MP4 absente ou déjà existante / dossier introuvable")
    if out.with_suffix(".presenter.json").exists():
        raise FileExistsError("Le manifeste du futur MP4 existe déjà")
    # Reuse a signed Piper WAV when available; never resynthesize it.
    if existing_narration is not None:
        from narrated_short import inspect_narration, sha256
        if existing_narration.is_symlink():
            raise ValueError("Lien symbolique de narration interdit")
        existing_narration = existing_narration.expanduser().resolve(strict=True)
        source_voice = inspect_narration(existing_narration, sha256(existing_narration))
        if source_voice["voice_license_ref"] != voice_license_ref:
            raise ValueError("La référence de licence de voix doit correspondre au WAV Piper")
    else:
        voice_model(model)
    info = require_musetalk(musetalk, interpreter)
    with tempfile.TemporaryDirectory(prefix="ugc_presenter_") as tmpname:
        tmp = Path(tmpname).resolve()
        if not SAFE_UPSTREAM_PATH.fullmatch(str(tmp)):
            raise ValueError("Chemin temporaire non compatible avec MuseTalk")
        picture = tmp / ("avatar" + image.suffix.lower())
        shutil.copyfile(image, picture)
        sound = tmp / "voice.wav"
        if existing_narration is None:
            voice_meta = synthesize(text, model, sound, voice_license_ref=voice_license_ref,
                                    confirmed=True)
        else:
            shutil.copyfile(existing_narration, sound)
            voice_meta = {"duration": source_voice["duration"],
                          "model_sha256": source_voice["model_sha256"],
                          "wav_sha256": source_voice["sha256"],
                          "language": source_voice["language"]}
        yaml = tmp / "inference.yaml"
        yaml.write_text(f"ugc_presenter:\n  video_path: {picture}\n  audio_path: {sound}\n  result_name: presenter.mp4\n", encoding="utf-8")
        render_dir = tmp / "musetalk_result"
        render_dir.mkdir()
        py = str(info["python"])
        root = info["root"]
        cmd = [py, "-m", "scripts.inference", "--inference_config", str(yaml),
               "--result_dir", str(render_dir),
               "--unet_model_path", "models/musetalkV15/unet.pth",
               "--unet_config", "models/musetalkV15/musetalk.json",
               "--version", "v15", "--fps", "25", "--batch_size", "4",
               "--use_float16",
               "--ffmpeg_path", str(Path(shutil.which("ffmpeg") or "/usr/bin/ffmpeg").parent),
               "--output_vid_name", "presenter.mp4"]
        # MuseTalk upstream may use a shared 'temp.mp4' in its working folder.
        # Serialize all invocations made through this adapter to avoid overlap.
        import fcntl
        with (root / ".ugc_presenter.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            completed = subprocess.run(
                cmd, cwd=root, text=True, capture_output=True, timeout=1800,
                env={**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                     "HF_DATASETS_OFFLINE": "1", "WANDB_MODE": "offline"},
            )
            fcntl.flock(lock, fcntl.LOCK_UN)
        candidate = render_dir / "v15" / "presenter.mp4"
        if completed.returncode or not candidate.is_file():
            raise RuntimeError("MuseTalk n'a pas produit de fichier vidéo : " + (completed.stderr or completed.stdout)[-1800:])
        meta = inspect_video(candidate)
        # FFmpeg full decoding; never publish an MP4 corrupt or unfinished.
        decode = subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i",
                                 str(candidate), "-f", "null", "-"],
                                capture_output=True, text=True, timeout=240)
        if decode.returncode:
            raise RuntimeError("Décodage de la vidéo produite échoué : " + decode.stderr[-500:])
        if (abs(meta["audio_seconds"] - voice_meta["duration"]) > .45
                or abs(meta["video_seconds"] - voice_meta["duration"]) > .45):
            raise RuntimeError("Durée voix et pistes MP4 trop différente pour validation de production")
        audio_peak = audible_audio_peak(candidate)
        report = {
            "status": "GENERATED_NEEDS_HUMAN_REVIEW",
            "backend": "MuseTalk 1.5 local GPU + Piper CPU",
            "sha256": digest(candidate),
            "portrait_sha256": digest(image),
            "voice_model_sha256": voice_meta["model_sha256"],
            "voice_license_ref": voice_license_ref,
            "portrait_rights_ref": image_rights_ref,
            "rights_confirmed_by_operator": True,
            "voice_seconds": voice_meta["duration"],
            "language": voice_meta["language"],
            "narration_wav_sha256": voice_meta["wav_sha256"],
            "reused_existing_narration": existing_narration is not None,
            "video_seconds": meta["duration"],
            "video_track_seconds": meta["video_seconds"],
            "audio_track_seconds": meta["audio_seconds"],
            "av_track_gap_ms": meta["av_track_gap_ms"],
            "voice_peak_db": audio_peak,
            "ffmpeg_full_decode": True,
            "human_lip_sync_proven": False,
            "phoneme_sync_metric": None,
            "publication_allowed_automatically": False,
            "commercial_rights_verified_by_software": False,
            "gpu_inference_executed": True,
            "paid_api_requests": 0,
            "model_downloads": 0,
        }
        report_tmp = tmp / "presenter.json"
        report_tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if out.is_symlink() or out.parent.is_symlink() or out.with_suffix(".presenter.json").is_symlink():
            raise ValueError("Lien symbolique de destination avant publication")
        os.link(candidate, out)
        try:
            os.link(report_tmp, out.with_suffix(".presenter.json"))
        except Exception:
            out.unlink(missing_ok=True)
            raise
    return {"output": str(out), "report": str(out.with_suffix(".presenter.json")), **report}


def main(argv=None):
    p = argparse.ArgumentParser(description="Narration Piper et MuseTalk locaux, sans API payante")
    sub = p.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="Pré-requis locaux ; aucune génération")
    doctor.add_argument("--voice-model", type=Path)
    doctor.add_argument("--musetalk-dir", type=Path)
    doctor.add_argument("--musetalk-python", type=Path, default=Path(sys.executable))
    for name in ("voice", "presenter"):
        sp = sub.add_parser(name)
        choice = sp.add_mutually_exclusive_group(required=True)
        choice.add_argument("--text")
        choice.add_argument("--text-file", type=Path)
        sp.add_argument("--voice-model", required=True, type=Path)
        sp.add_argument("--voice-license-ref", required=True)
        sp.add_argument("--confirm-voice-rights", action="store_true")
        sp.add_argument("--output", required=True, type=Path)
        if name == "presenter":
            sp.add_argument("--image", required=True, type=Path)
            sp.add_argument("--image-rights-ref", required=True)
            sp.add_argument("--confirm-image-rights", action="store_true")
            sp.add_argument("--musetalk-dir", required=True, type=Path)
            sp.add_argument("--musetalk-python", type=Path, default=Path(sys.executable))
    a = p.parse_args(argv)
    try:
        if a.command == "doctor":
            result = {"engine": "Piper CPU + MuseTalk 1.5 CUDA",
                      "piper_model": voice_model(a.voice_model)["language"] if a.voice_model else "not configured",
                      "musetalk": "not configured",
                      "no_paid_api": True}
            if a.musetalk_dir:
                require_musetalk(a.musetalk_dir, a.musetalk_python)
                result["musetalk"] = "CUDA_AVAILABLE"
        else:
            text = a.text if a.text is not None else a.text_file.read_text(encoding="utf-8")
            if a.command == "voice":
                result = synthesize(text, a.voice_model, a.output,
                                    voice_license_ref=a.voice_license_ref,
                                    confirmed=a.confirm_voice_rights)
            else:
                result = presenter(text=text, model=a.voice_model, image=a.image,
                                   musetalk=a.musetalk_dir, interpreter=a.musetalk_python,
                                   output=a.output, voice_license_ref=a.voice_license_ref,
                                   image_rights_ref=a.image_rights_ref,
                                   confirm_voice_rights=a.confirm_voice_rights,
                                   confirm_image_rights=a.confirm_image_rights)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, FileNotFoundError, FileExistsError, RuntimeError,
            OSError, subprocess.TimeoutExpired) as exc:
        print("ÉCHEC :", exc, file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
