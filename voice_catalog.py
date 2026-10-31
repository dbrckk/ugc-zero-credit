#!/usr/bin/env python3
"""Validated, immutable local Piper voice catalog for French/English studio TTS.

Never guesses the spoken language or translates user text. Models are explicitly
configured, verified at startup and kept server-side. No runtime downloads.
"""
from __future__ import annotations
from pathlib import Path
from offline_presenter import voice_model, required_reference

SUPPORTED = {"fr": "Français", "en": "English"}


def configure_voices(*, legacy_model: Path | None = None,
                     legacy_license: str = "",
                     french_model: Path | None = None,
                     french_license: str = "",
                     english_model: Path | None = None,
                     english_license: str = "") -> dict[str, dict]:
    voices: dict[str, dict] = {}
    for requested, model, license_ref in (
        (None, legacy_model, legacy_license),
        ("fr", french_model, french_license),
        ("en", english_model, english_license),
    ):
        if model is None:
            if license_ref.strip():
                raise ValueError("Référence de licence fournie sans modèle Piper")
            continue
        license_ref = required_reference(license_ref, "Licence vocale")
        details = voice_model(Path(model))
        code = details["language"]
        if not isinstance(code, str):
            raise ValueError("Code de langue invalide dans le modèle Piper")
        code = code.replace("-", "_")
        language = code.split("_", 1)[0].lower()
        if language not in SUPPORTED:
            raise ValueError(f"Voix non prise en charge (fr/en uniquement) : {code}")
        if requested and language != requested:
            raise ValueError(f"Voix {requested} configurée avec un modèle {code} : refus de synthèse")
        if language in voices:
            raise ValueError(f"Deux modèles pour {language} : utiliser une seule configuration")
        voices[language] = {"model": details["model"], "license_ref": license_ref,
                            "locale": code}
    if voices:
        try:
            import piper
        except ImportError as exc:
            raise RuntimeError("Installer Piper avant de démarrer : pip install piper-tts") from exc
    return voices


def pick_voice(voices: dict[str, dict], language: str | None) -> tuple[str, dict]:
    """Choose explicitly when two languages are installed; keep V11 one-voice API."""
    if not voices:
        raise LookupError("Aucun modèle Piper local installé")
    if language is None:
        if len(voices) == 1:
            code = next(iter(voices))
            return code, voices[code]
        raise ValueError("Choisir explicitement language='fr' ou 'en'")
    if not isinstance(language, str) or language not in SUPPORTED:
        raise ValueError("Langue invalide : fr ou en uniquement")
    if language not in voices:
        raise LookupError(f"Voix {language} non installée sur ce serveur")
    return language, voices[language]


def available_languages(voices: dict[str, dict]) -> list[str]:
    return [lang for lang in ("fr", "en") if lang in voices]
