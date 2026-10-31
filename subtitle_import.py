#!/usr/bin/env python3
"""Import audited sentence-level SRT captions without fabricating word timings.

Only Python's standard library is used. The importer never modifies existing
projects, touches media, downloads models, or invokes a remote service.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re

_TIME = re.compile(r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})$")
_ARROW = re.compile(r"^\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2}[,.]\d{3})(?:\s+.*)?$")


def _seconds(stamp: str) -> float:
    match = _TIME.fullmatch(stamp)
    if not match:
        raise ValueError(f"Horodatage SRT invalide : {stamp!r}")
    h, m, s, ms = map(int, match.groups())
    if m > 59 or s > 59:
        raise ValueError(f"Horodatage SRT hors limites : {stamp!r}")
    return h * 3600 + m * 60 + s + ms / 1000


def parse_srt(text: str) -> list[dict]:
    """Accept standard numbered or unnumbered cues; preserve genuine cue times."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Fichier SRT vide")
    if len(text) > 2_000_000:
        raise ValueError("Fichier SRT trop grand")
    normalized = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", normalized.strip())
    if len(blocks) > 1800:
        raise ValueError("Trop de sous-titres pour une seule vidéo")
    result = []
    for index, block in enumerate(blocks, 1):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if lines and lines[0].isdigit():
            lines.pop(0)
        if len(lines) < 2:
            raise ValueError(f"Sous-titre SRT {index} incomplet")
        times = _ARROW.fullmatch(lines[0])
        if not times:
            raise ValueError(f"Sous-titre SRT {index} : ligne de temps invalide")
        start, end = _seconds(times.group(1)), _seconds(times.group(2))
        if end <= start or end - start > 12:
            raise ValueError(f"Sous-titre SRT {index} : durée invalide")
        if result and start < result[-1]["end"] - .0005:
            raise ValueError(f"Sous-titres SRT {index - 1} et {index} se chevauchent")
        # Explicitly reject embedded markup rather than silently alter the claim.
        body = " ".join(lines[1:])
        if "<" in body or ">" in body or "\\N" in body or "{" in body or "}" in body:
            raise ValueError(f"Sous-titre SRT {index} : balisage interdit; saisir du texte simple")
        body = re.sub(r"\s+", " ", body).strip()
        if not body or len(body) > 92:
            raise ValueError(f"Sous-titre SRT {index} vide ou trop long pour le mobile (92 caractères max)")
        result.append({"start": start, "end": end, "text": body})
    return result


def import_srt(project: Path, srt: Path, output: Path, *, clip_index: int,
               timebase: str = "clip", replace_existing: bool = False) -> dict:
    """Translate real SRT timestamps to source-time coordinates and save a new JSON.

    timebase='clip' => cue 00:00 starts at talking_clips[clip_index].source_in.
    timebase='source' => timestamps already refer to full original source video.
    The downstream renderer never pretends phrase cues contain word timings.
    """
    from ugc import load_project, verify

    config, root = load_project(project)
    if timebase not in {"clip", "source"}:
        raise ValueError("timebase doit être clip ou source")
    if not isinstance(clip_index, int) or not 0 <= clip_index < len(config.get("talking_clips", [])):
        raise ValueError("Numéro de clip inexistant")
    output = output.resolve()
    if output.suffix.lower() != ".json" or output.parent != root.resolve():
        raise ValueError("Le nouveau projet JSON doit rester dans le dossier du projet source")
    if output.exists():
        raise FileExistsError(f"Fichier existant non écrasé : {output}")
    if srt.resolve() == project.resolve():
        raise ValueError("Le fichier SRT ne peut pas être le projet source")
    original = verify({**config, "caption_mode": "none", "words": [], "segments": []}, root)
    t = original["talking"][clip_index]
    cues = parse_srt(srt.read_text(encoding="utf-8-sig"))
    translated = []
    for cue in cues:
        start = cue["start"] + (t["source_in"] if timebase == "clip" else 0)
        end = cue["end"] + (t["source_in"] if timebase == "clip" else 0)
        if start < t["source_in"] - 0.0005 or end > t["source_in"] + t["duration"] + 0.0005:
            raise ValueError("Sous-titre SRT hors de la portion parlée : corriger --timebase ou couper le SRT")
        translated.append({"clip": clip_index, "start": round(start, 3),
                           "end": round(end, 3), "text": cue["text"]})

    existing = config.get("segments", [])
    if (config.get("words") or any(x.get("clip") == clip_index for x in existing)) and not replace_existing:
        raise ValueError("Sous-titres existants : ajouter --replace-existing après vérification")
    updated = copy.deepcopy(config)
    updated["caption_mode"] = "segments"
    if config.get("words"):
        # A mode never mixes word and phrase timings; explicit replacement required.
        updated["words"] = []
    updated["segments"] = [x for x in existing if x.get("clip") != clip_index] + translated
    updated["segments"].sort(key=lambda x: (x["clip"], x["start"]))
    origins = [x for x in updated.get("caption_origins", []) if x.get("clip") != clip_index]
    origins.append({"clip": clip_index, "format": "srt", "timebase": timebase,
                    "srt_sha256": hashlib.sha256(srt.read_bytes()).hexdigest(),
                    "manual_review_required": True,
                    "word_level_alignment": False})
    updated["caption_origins"] = origins
    # Validate project and all local media before writing even one byte.
    checked = verify(updated, root)
    if len(checked["segments"]) != len(updated["segments"]):
        raise ValueError("Les sous-titres importés n'ont pas passé la vérification")
    with output.open("x", encoding="utf-8") as handle:
        json.dump(updated, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return {"status": "PASS", "output": str(output), "clip": clip_index,
            "phrases_imported": len(translated), "phrases_total": len(checked["segments"]),
            "timebase": timebase, "word_level_alignment": False,
            "manual_review_required": True, "credits_used": 0, "network_calls": 0}


def main():
    parser = argparse.ArgumentParser(description="Import SRT hors ligne avec timings réels (aucune API)")
    parser.add_argument("project", type=Path)
    parser.add_argument("srt", type=Path)
    parser.add_argument("--clip", type=int, required=True)
    parser.add_argument("--timebase", choices=["clip", "source"], default="clip")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replace-existing", action="store_true")
    args = parser.parse_args()
    result = import_srt(args.project, args.srt, args.output, clip_index=args.clip,
                        timebase=args.timebase, replace_existing=args.replace_existing)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
