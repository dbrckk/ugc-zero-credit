#!/usr/bin/env python3
"""Render a real, local, vertical photo Short from an authorized Piper narration.

This does NOT create a human face, dub an existing speaker or claim lip sync.
FFmpeg owns encoding. Inputs are local, rights-confirmed project assets.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

MAX_IMAGES = 6
MAX_SECONDS = 60
DISCLOSURE = "PUBLICITÉ  ·  CONTENU GÉNÉRÉ AVEC IA"
FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def _ffprobe(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams",
         "-of", "json", str(path)], text=True, capture_output=True,
        timeout=30, check=True)
    return json.loads(result.stdout)


def clean_title(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Titre produit requis")
    value = re.sub(r"\s+", " ", value).strip()
    if not 2 <= len(value) <= 48 or any(ord(c) < 32 for c in value):
        raise ValueError("Titre : 2 à 48 caractères, une seule ligne")
    if "<" in value or ">" in value:
        raise ValueError("Le titre ne doit pas contenir de balises")
    return value


def inspect_narration(path: Path, expected_sha: str) -> dict:
    if path.suffix.lower() != ".wav" or not path.is_file() or path.is_symlink():
        raise ValueError("Un fichier WAV Piper existant est obligatoire")
    manifest = path.with_suffix(".voice.json")
    if not manifest.is_file() or manifest.is_symlink():
        raise ValueError("Rapport de provenance Piper absent")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if (data.get("status") != "VOICE_GENERATED_NOT_LIPSYNCED"
            or data.get("rights_confirmed_by_operator") is not True
            or data.get("engine") != "Piper ONNX CPU"):
        raise ValueError("Rapport Piper incomplet ou non validé")
    locale = data.get("language", "")
    if not isinstance(locale, str) or locale.split("_")[0] not in {"fr", "en"}:
        raise ValueError("Voix française ou anglaise requise")
    computed = sha256(path)
    if not isinstance(expected_sha, str) or computed != expected_sha or computed != data.get("wav_sha256"):
        raise ValueError("La voix a été modifiée depuis sa création Piper")
    probe = _ffprobe(path)
    streams = probe.get("streams", [])
    if not any(s.get("codec_type") == "audio" for s in streams):
        raise ValueError("Narration sans piste audio")
    duration = float(probe.get("format", {}).get("duration", 0))
    if not math.isfinite(duration) or not 1.0 <= duration <= MAX_SECONDS:
        raise ValueError("La narration d'un Short doit durer de 1 à 60 secondes")
    return {"duration": duration, "language": locale, "sha256": computed,
            "model_sha256": data["model_sha256"],
            "voice_license_ref": data["voice_license_ref"]}


def inspect_photos(images: list[Path]) -> list[dict]:
    if not isinstance(images, list) or not 1 <= len(images) <= MAX_IMAGES:
        raise ValueError("Choisir entre 1 et 6 photos")
    if len({str(p.resolve()) for p in images}) != len(images):
        raise ValueError("Photos en doublon")
    result = []
    for file in images:
        if file.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"} or not file.is_file() or file.is_symlink():
            raise ValueError("Photo PNG/JPEG/WEBP valide requise")
        info = _ffprobe(file)
        video = next((x for x in info.get("streams", []) if x.get("codec_type") == "video"), None)
        if not video:
            raise ValueError("Photo illisible par FFmpeg")
        w, h = int(video.get("width", 0)), int(video.get("height", 0))
        if not 160 <= w <= 8000 or not 160 <= h <= 8000 or w * h > 24_000_000:
            raise ValueError("Photo trop petite ou trop grande (max 24 mégapixels)")
        result.append({"sha256": sha256(file), "width": w, "height": h})
    return result


def render_short(images: list[Path], narration: Path, output: Path, *,
                 title: str, narration_sha: str, image_rights_confirmed: bool,
                 claims_verified: bool, preview: bool = False) -> dict:
    """Encode and fully decode-verify output before atomic publication."""
    if image_rights_confirmed is not True or claims_verified is not True:
        raise ValueError("Déclarer les droits de chaque photo et vérifier le titre produit")
    if not isinstance(preview, bool):
        raise ValueError("Aperçu invalide")
    title = clean_title(title)
    meta = inspect_narration(narration, narration_sha)
    photos = inspect_photos(images)
    if not FONT.is_file():
        raise FileNotFoundError("Installer fonts-dejavu-core avant de rendre le Short")
    output = output.expanduser().resolve()
    if output.suffix.lower() != ".mp4" or not output.parent.is_dir():
        raise ValueError("Sortie MP4 dans le dossier de rendu obligatoire")
    if output.is_symlink() or output.with_suffix(".report.json").is_symlink():
        raise ValueError("Liens symboliques de rendu interdits")
    w, h, fps = (360, 640, 24) if preview else (1080, 1920, 30)
    transition = .3 if len(images) > 1 else 0.
    seconds = meta["duration"]
    segment = (seconds + (len(images) - 1) * transition) / len(images)
    # Every image appears for >=1.0 s; no rapid-flashing slides for short narration.
    if segment < 1:
        raise ValueError("Réduire le nombre de photos pour cette narration")
    with tempfile.TemporaryDirectory(prefix=".ugc-short-", dir=output.parent) as folder:
        work = Path(folder)
        title_file = work / "title.txt"
        disclosure_file = work / "disclosure.txt"
        title_file.write_text(title, encoding="utf-8")
        disclosure_file.write_text(DISCLOSURE, encoding="utf-8")
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
        for photo in images:
            cmd += ["-loop", "1", "-framerate", str(fps), "-t", f"{segment + .12:.4f}", "-i", str(photo)]
        cmd += ["-i", str(narration)]
        filt = []
        for i in range(len(images)):
            # Soft blurred background retains full portrait canvas; the actual
            # photo remains centered/contained, never misleadingly cropped.
            filt.append(
                f"[{i}:v]split=2[b{i}][f{i}];"
                f"[b{i}]scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},boxblur=6:1,eq=brightness=-0.15[bg{i}];"
                f"[f{i}]scale={int(w * .89)}:{int(h * .72)}:force_original_aspect_ratio=decrease,"
                f"format=rgba,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black@0[fg{i}];"
                f"[bg{i}][fg{i}]overlay=shortest=1:format=auto,"
                f"format=yuv420p,zoompan=z='min(zoom+0.00027,1.055)':"
                f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':"
                f"d=1:s={w}x{h}:fps={fps},trim=duration={segment:.5f},"
                f"setpts=PTS-STARTPTS,format=yuv420p[v{i}]")
        previous = "v0"
        for i in range(1, len(images)):
            final = f"x{i}"
            offset = i * (segment - transition)
            filt.append(f"[{previous}][v{i}]xfade=transition=fade:"
                        f"duration={transition:.3f}:offset={offset:.5f}[{final}]")
            previous = final
        title_size, disclosure_size = (24, 13) if preview else (66, 36)
        # textfile= avoids interpolating untrusted user text into FFmpeg syntax.
        filt.append(
            f"[{previous}]drawtext=fontfile={FONT}:textfile={title_file}:"
            f"fontcolor=white:fontsize={title_size}:"
            f"x=(w-text_w)/2:y=h*0.075:box=1:"
            f"boxcolor=black@0.65:boxborderw={int(w*.02)},"
            f"drawtext=fontfile={FONT}:textfile={disclosure_file}:"
            f"fontcolor=white:fontsize={disclosure_size}:"
            f"x=(w-text_w)/2:y=h*0.925-text_h:"
            f"box=1:boxcolor=black@0.8:boxborderw={int(w*.008)},"
            f"format=yuv420p[out]")
        tmp_video = work / "short.mp4"
        cmd += ["-filter_complex", ";".join(filt),
                "-map", "[out]", "-map", f"{len(images)}:a:0",
                "-t", f"{seconds:.5f}", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-c:v", "libx264", "-threads", "2", "-preset", "veryfast",
                "-crf", "23" if preview else "20", "-pix_fmt", "yuv420p",
                "-r", str(fps), "-c:a", "aac", "-b:a", "128k" if preview else "160k",
                "-movflags", "+faststart", str(tmp_video)]
        completed = subprocess.run(cmd, text=True, capture_output=True,
                                   timeout=270 if preview else 1500)
        if completed.returncode:
            raise RuntimeError("Rendu FFmpeg échoué : " + completed.stderr[-1500:])
        result = _ffprobe(tmp_video)
        streams = result.get("streams", [])
        video = next((x for x in streams if x.get("codec_type") == "video"), None)
        audio = next((x for x in streams if x.get("codec_type") == "audio"), None)
        length = float(result.get("format", {}).get("duration", 0))
        if (not video or not audio or int(video.get("width", 0)) != w
                or int(video.get("height", 0)) != h or abs(length - seconds) > .6):
            raise RuntimeError("Sortie Short non conforme : vidéo/audio/résolution/durée")
        decoded = subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(tmp_video),
                                  "-f", "null", "-"], text=True, capture_output=True,
                                 timeout=160 if preview else 420)
        if decoded.returncode:
            raise RuntimeError("Short non décodable complètement : " + decoded.stderr[-600:])
        report = {
            "status": "REQUIRES_HUMAN_REVIEW", "kind": "narrated_photo_short",
            "format": "9:16 H264 AAC", "width": w, "height": h, "fps": fps,
            "duration": round(length, 3), "language": meta["language"],
            "narration_sha256": meta["sha256"],
            "voice_model_sha256": meta["model_sha256"],
            "voice_license_ref": meta["voice_license_ref"],
            "photos": photos, "photo_count": len(photos),
            "title": title, "disclosure": DISCLOSURE,
            "image_rights_confirmed_by_operator": True,
            "claims_verified_by_operator": True,
            "no_paid_ai_api": True, "lip_sync_generated": False,
            "narration_alignment_verified": False,
            "commercial_rights_verified_by_software": False,
            "human_review_required": True,
            "full_ffmpeg_decode_passed": True, "sha256": sha256(tmp_video)
        }
        report_tmp = work / "short.report.json"
        report_tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # No incomplete .mp4 is ever exposed to Android clients.
        os.replace(tmp_video, output)
        os.replace(report_tmp, output.with_suffix(".report.json"))
    return report
