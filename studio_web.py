#!/usr/bin/env python3
"""Offline authenticated mobile web UI for UGC Zero Credit.

No packages, external API calls, code execution endpoints or paid generators.
Binds only to loopback by default. Keeps user-owned media on disk.
"""
from __future__ import annotations

import argparse
import hmac
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import secrets
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlparse, quote

from ugc import build, probe, verify
from subtitle_import import parse_srt
from studio_scheduling import admission, is_active
from offline_presenter import clean_text, synthesize, presenter, require_musetalk
from voice_catalog import configure_voices, pick_voice, available_languages
from narrated_short import clean_title, inspect_narration, inspect_photos, render_short, MAX_IMAGES

ROOT = Path(__file__).resolve().parent
UI = ROOT / "studio_web"
SAFE_ID = re.compile(r"^[a-f0-9]{16}$")
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,100}$")
ALLOWED_UPLOADS = {".mp4", ".mov", ".mkv", ".webm", ".jpg", ".jpeg", ".png", ".webp", ".wav", ".mp3", ".m4a", ".srt"}
VIDEO = {".mp4", ".mov", ".mkv", ".webm"}
IMAGE = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO = {".wav", ".mp3", ".m4a"}
MAX_UPLOAD = 350 * 1024 * 1024
MAX_JSON = 512 * 1024
MAX_FILES = 40
MAX_PROJECT_BYTES = 2 * 1024 * 1024 * 1024
MIN_FREE_BYTES = 256 * 1024 * 1024
DISCLOSURE = "PUBLICITÉ · LIEN AFFILIÉ · INFLUENCEUSE IA"


def store_json(path: Path, obj: dict) -> None:
    """Write atomically to avoid losing last valid configuration on errors."""
    tmp = path.with_name("." + path.name + "." + secrets.token_hex(4) + ".tmp")
    try:
        with tmp.open("x", encoding="utf-8") as handle:
            json.dump(obj, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def safe_project(data: Path, project_id: str) -> Path:
    if not SAFE_ID.fullmatch(project_id):
        raise ValueError("Identifiant de projet invalide")
    result = data / project_id
    if not result.is_dir() or result.is_symlink():
        raise FileNotFoundError("Projet introuvable")
    return result


def safe_uploaded_file(project: Path, name: str) -> Path:
    if not isinstance(name, str) or not name.startswith("media/"):
        raise ValueError("Sélectionner un fichier importé dans le projet")
    leaf = name.removeprefix("media/")
    if not SAFE_NAME.fullmatch(leaf) or leaf.startswith(".") or leaf.lower().endswith(".tmp"):
        raise ValueError("Nom de média interdit")
    file = project / "media" / leaf
    if file.is_symlink() or not file.is_file() or not file.resolve().is_relative_to((project / "media").resolve()):
        raise FileNotFoundError("Média absent")
    return file


def summarize_media(file: Path) -> dict:
    if file.suffix.lower() == ".srt":
        parse_srt(file.read_text(encoding="utf-8-sig"))
        return {"type": "subtitle"}
    info = probe(file)
    stream = info.get("streams", [])
    if file.suffix.lower() in VIDEO and not any(s.get("codec_type") == "video" for s in stream):
        raise ValueError("Le fichier déclaré vidéo ne contient pas de piste vidéo")
    if file.suffix.lower() in IMAGE and not any(s.get("codec_type") == "video" for s in stream):
        raise ValueError("Image non reconnue")
    if file.suffix.lower() in AUDIO and not any(s.get("codec_type") == "audio" for s in stream):
        raise ValueError("Le fichier déclaré audio ne contient pas de piste audio")
    video = next((s for s in stream if s.get("codec_type") == "video"), None)
    audio = next((s for s in stream if s.get("codec_type") == "audio"), None)
    kind = "video" if file.suffix.lower() in VIDEO else "image" if file.suffix.lower() in IMAGE else "audio"
    return {"type": kind, "duration": round(float(info.get("format", {}).get("duration", 0) or 0), 3),
            "width": int(video.get("width", 0)) if video else 0,
            "height": int(video.get("height", 0)) if video else 0,
            "has_audio": audio is not None}


def assemble_config(project: Path, request: dict) -> tuple[dict, dict]:
    """Turn a browser form into the existing audited JSON contract."""
    if not isinstance(request, dict):
        raise ValueError("Formulaire invalide")
    product = request.get("product")
    clips = request.get("talking_clips")
    overlays = request.get("overlays", [])
    if not isinstance(product, dict) or not isinstance(clips, list) or not isinstance(overlays, list):
        raise ValueError("Produit, clips ou inserts invalides")
    name = product.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 150:
        raise ValueError("Nom du produit obligatoire (150 caractères max)")
    refs = product.get("evidence_urls", [])
    if not isinstance(refs, list) or len(refs) > 8 or any(not isinstance(u, str) or len(u) > 500 or not u.startswith("https://") for u in refs):
        raise ValueError("Les preuves doivent être des liens HTTPS valides")
    reference = product.get("product_reference", "")
    if reference:
        if safe_uploaded_file(project, reference).suffix.lower() not in IMAGE:
            raise ValueError("La référence produit doit être une image importée")
    config = {"version": 1, "forbidden_paid_services": True,
              "product": {"name": name.strip(), "claims_verified": product.get("claims_verified") is True,
                          "disclosure": DISCLOSURE, "evidence_urls": refs,
                          "product_reference": reference},
              "talking_clips": [], "overlays": [], "caption_mode": "none", "words": [], "segments": [],
              "editorial_policy": "review", "face_policy": "review"}
    for idx, clip in enumerate(clips):
        if not isinstance(clip, dict):
            raise ValueError("Clip invalide")
        file = clip.get("file")
        if safe_uploaded_file(project, file).suffix.lower() not in VIDEO:
            raise ValueError(f"Clip {idx} : vidéo requise")
        rights = clip.get("rights")
        if rights not in {"owned", "licensed", "ai_generated"}:
            raise ValueError(f"Clip {idx} : droits à renseigner")
        output = {"file": file, "source_in": clip.get("source_in", 0),
                  "duration": clip.get("duration"), "rights": rights, "sync": "native",
                  "smart_crop": clip.get("smart_crop", "off")}
        if rights == "licensed":
            output["license_ref"] = clip.get("license_ref", "")
        config["talking_clips"].append(output)
    for idx, overlay in enumerate(overlays):
        if not isinstance(overlay, dict):
            raise ValueError("Insert invalide")
        file = overlay.get("file")
        if safe_uploaded_file(project, file).suffix.lower() not in IMAGE | VIDEO:
            raise ValueError(f"Insert {idx} : image ou vidéo requise")
        rights = overlay.get("rights")
        if rights not in {"owned", "licensed", "ai_generated"}:
            raise ValueError(f"Insert {idx} : droits manquants")
        output = {"file": file, "start": overlay.get("start"), "duration": overlay.get("duration"),
                  "rights": rights, "motion": overlay.get("motion", "static"),
                  "layout": overlay.get("layout", "full"), "fade": overlay.get("fade", 0.12)}
        if file.rsplit(".", 1)[-1].lower() in {"mp4", "mov", "mkv", "webm"}:
            output["source_in"] = overlay.get("source_in", 0)
        if rights == "licensed":
            output["license_ref"] = overlay.get("license_ref", "")
        config["overlays"].append(output)
    music = request.get("music")
    if music:
        if not isinstance(music, dict) or safe_uploaded_file(project, music.get("file")).suffix.lower() not in AUDIO:
            raise ValueError("Musique invalide")
        if music.get("rights") not in {"owned", "licensed", "ai_generated"}:
            raise ValueError("Droits musique non déclarés")
        config["music"] = {"file": music["file"], "rights": music["rights"],
                           "volume": music.get("volume", 0.12)}
        if music["rights"] == "licensed":
            config["music"]["license_ref"] = music.get("license_ref", "")
    assignments = request.get("srt_assignments", [])
    if not isinstance(assignments, list) or len(assignments) > len(clips):
        raise ValueError("Affectations SRT incorrectes")
    used = set()
    for a in assignments:
        if not isinstance(a, dict) or not isinstance(a.get("clip"), int) or isinstance(a.get("clip"), bool):
            raise ValueError("Numéro de clip SRT invalide")
        idx = a["clip"]
        if idx < 0 or idx >= len(clips) or idx in used:
            raise ValueError("Un seul SRT par clip")
        used.add(idx)
        srt_path = safe_uploaded_file(project, a.get("file"))
        if srt_path.suffix.lower() != ".srt":
            raise ValueError("Sous-titres : fichier .srt requis")
        timebase = a.get("timebase", "clip")
        if timebase not in {"clip", "source"}:
            raise ValueError("Base temporelle SRT inconnue")
        clip = config["talking_clips"][idx]
        initial = float(clip["source_in"])
        end = initial + float(clip["duration"])
        offset = initial if timebase == "clip" else 0
        cues = parse_srt(srt_path.read_text(encoding="utf-8-sig"))
        for cue in cues:
            begin, finish = cue["start"] + offset, cue["end"] + offset
            if begin < initial - .0005 or finish > end + .0005:
                raise ValueError(f"SRT {idx} : horaires hors de la partie conservée du clip")
            config["segments"].append({"clip": idx, "start": round(begin, 3), "end": round(finish, 3), "text": cue["text"]})
        config.setdefault("caption_origins", []).append({"clip": idx, "format": "srt", "timebase": timebase,
            "srt_sha256": hashlib.sha256(srt_path.read_bytes()).hexdigest(),
            "manual_review_required": True, "word_level_alignment": False})
    if config["segments"]:
        config["caption_mode"] = "segments"
        config["segments"].sort(key=lambda s: (s["clip"], s["start"]))
    checked = verify(config, project)
    return config, {"duration": checked["total_duration"], "warnings": checked["warnings"] + checked["editorial_review"],
                    "captions": len(checked["segments"]), "clips": len(clips)}


class Studio(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, root: Path, token: str,
                 voice_model: Path | None = None, voice_license_ref: str = "",
                 voice_model_fr: Path | None = None, voice_license_ref_fr: str = "",
                 voice_model_en: Path | None = None, voice_license_ref_en: str = "",
                 musetalk_dir: Path | None = None, musetalk_python: Path | None = None):
        # Validate all models and language codes before opening a listening socket.
        self.voice_models = configure_voices(
            legacy_model=voice_model, legacy_license=voice_license_ref,
            french_model=voice_model_fr, french_license=voice_license_ref_fr,
            english_model=voice_model_en, english_license=voice_license_ref_en)
        self.voice_language = next(iter(self.voice_models.values()))["locale"] if len(self.voice_models) == 1 else ""
        self.musetalk_dir = musetalk_dir
        self.musetalk_python = musetalk_python
        super().__init__(address, handler)
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.token = token
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ugc-render")
        self.jobs: dict[str, dict] = {}
        self.jobs_lock = threading.Lock()
        self.upload_lock = threading.Lock()
        # Limit expensive CUDA diagnostics to a single request and cache briefly.
        self.presenter_status_lock = threading.Lock()
        self.presenter_diagnostic_cache: tuple[float, dict] | None = None
        self.presenter_diagnostic_running = False

    def presenter_readiness(self) -> dict:
        if not self.musetalk_dir or not self.musetalk_python:
            return {"configured": False, "ready": False, "code": "not_configured",
                    "message": "Configurer MuseTalk et Python CUDA sur le serveur."}
        with self.presenter_status_lock:
            cache = self.presenter_diagnostic_cache
            if cache and time.monotonic() - cache[0] < 120:
                return cache[1].copy()
            if self.presenter_diagnostic_running:
                return {"configured": True, "ready": False, "code": "checking",
                        "message": "Diagnostic GPU déjà en cours : relancer dans quelques secondes."}
            self.presenter_diagnostic_running = True
        try:
            require_musetalk(self.musetalk_dir, self.musetalk_python)
            result = {"configured": True, "ready": True, "code": "ready",
                      "message": "CUDA, modèles MuseTalk et interface CLI vérifiés. La qualité de sortie reste à contrôler."}
        except (FileNotFoundError, ValueError) as exc:
            result = {"configured": True, "ready": False, "code": "missing_installation",
                      "message": "Installation MuseTalk ou modèles locaux incomplets."}
        except RuntimeError as exc:
            code = "incompatible_cli" if "Interface MuseTalk incompatible" in str(exc) else "cuda_unavailable"
            result = {"configured": True, "ready": False, "code": code,
                      "message": "Interface MuseTalk incompatible." if code == "incompatible_cli"
                      else "CUDA ou PyTorch GPU indisponible."}
        except (subprocess.TimeoutExpired, OSError) as exc:
            result = {"configured": True, "ready": False, "code": "diagnostic_failed",
                      "message": "Diagnostic GPU impossible ou trop lent."}
        finally:
            with self.presenter_status_lock:
                if "result" in locals():
                    self.presenter_diagnostic_cache = (time.monotonic(), result.copy())
                self.presenter_diagnostic_running = False
        return result

    def shutdown(self):
        super().shutdown()
        self.executor.shutdown(wait=False, cancel_futures=True)


class Handler(BaseHTTPRequestHandler):
    server: Studio
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        # Never log tokens, query parameters, product scripts or private filenames.
        sys.stderr.write("[ugc-web] request\n")

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; base-uri 'none'; form-action 'none'")
        super().end_headers()

    def json_response(self, status: int, content: dict):
        body = json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def error_response(self, status: int, reason: str):
        self.json_response(status, {"ok": False, "error": reason})

    def signed_url(self, project_id: str, category: str, filename: str) -> str:
        expires = int(time.time()) + 3600
        payload = f"{project_id}|{category}|{filename}|{expires}".encode()
        signature = hmac.new(self.server.token.encode(), payload, hashlib.sha256).hexdigest()
        return f"/api/projects/{project_id}/{category}/{quote(filename)}?expires={expires}&sig={signature}"

    def ticket_valid(self, project_id: str, category: str, filename: str, query: dict) -> bool:
        try:
            expires = int(query.get("expires", ["0"])[0])
            signature = query.get("sig", [""])[0]
            if expires < int(time.time()) or expires > int(time.time()) + 3600 or len(signature) != 64:
                return False
            payload = f"{project_id}|{category}|{filename}|{expires}".encode()
            expected = hmac.new(self.server.token.encode(), payload, hashlib.sha256).hexdigest()
            return hmac.compare_digest(signature, expected)
        except (TypeError, ValueError):
            return False

    def authorized(self) -> bool:
        auth = self.headers.get("Authorization", "")
        return secrets.compare_digest(auth, "Bearer " + self.server.token)

    def route(self):
        url = urlparse(self.path)
        return url.path.split("/"), parse_qs(url.query)

    def authenticated(self) -> bool:
        if not self.authorized():
            self.error_response(401, "Jeton d'accès incorrect")
            return False
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host", ""):
            self.error_response(403, "Origine non autorisée")
            return False
        return True

    def bytes_response(self, path: Path, *, media=False):
        size = path.stat().st_size
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        rang = self.headers.get("Range") if media else None
        begin, end = 0, size - 1
        if rang:
            matched = re.fullmatch(r"bytes=(\d+)-(\d*)", rang.strip())
            if not matched:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            begin = int(matched.group(1))
            end = min(size - 1, int(matched.group(2))) if matched.group(2) else size - 1
            if begin >= size or begin > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        self.send_response(206 if rang else 200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(end - begin + 1))
        self.send_header("Accept-Ranges", "bytes")
        if rang:
            self.send_header("Content-Range", f"bytes {begin}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as handle:
            handle.seek(begin)
            remaining = end - begin + 1
            while remaining:
                chunk = handle.read(min(262144, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def length(self, maximum: int) -> int:
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("Transfer-Encoding non pris en charge")
        try:
            raw = self.headers["Content-Length"]
            n = int(raw)
        except (KeyError, ValueError, TypeError):
            raise ValueError("Content-Length requis") from None
        if n < 1 or n > maximum:
            raise ValueError("Fichier/requête trop grand ou vide")
        return n

    def json_request(self) -> dict:
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            raise ValueError("Content-Type JSON requis")
        return json.loads(self.rfile.read(self.length(MAX_JSON)))

    def do_GET(self):
        try:
            parts, query = self.route()
            if parts == ["", ""]:
                return self.bytes_response(UI / "index.html")
            if parts == ["", "studio.js"]:
                return self.bytes_response(UI / "studio.js")
            if parts == ["", "studio.css"]:
                return self.bytes_response(UI / "studio.css")
            # Short-lived, path-scoped, read-only tickets permit Android video playback,
            # including seeking through Range requests, without exposing the API token.
            if len(parts) == 6 and parts[:3] == ["", "api", "projects"] and parts[4] in {"outputs", "media"}:
                project_id, category, leaf = parts[3], parts[4], parts[5]
                if not (self.authorized() or self.ticket_valid(project_id, category, leaf, query)):
                    return self.error_response(401, "Lien expiré ou accès refusé")
                project = safe_project(self.server.root, project_id)
                if category == "outputs":
                    if leaf not in {"final.mp4", "preview.mp4", "final.srt", "preview.srt", "final.qa.json", "preview.qa.json", "final.report.json", "preview.report.json", "narrated.mp4", "narrated_preview.mp4", "narrated.report.json", "narrated_preview.report.json"}:
                        return self.error_response(404, "Fichier absent")
                    candidate = project / "renders" / leaf
                else:
                    candidate = safe_uploaded_file(project, "media/" + leaf)
                if not candidate.is_file() or candidate.is_symlink():
                    return self.error_response(404, "Fichier absent")
                return self.bytes_response(candidate, media=True)
            if not self.authenticated():
                return
            if parts == ["", "api", "health"]:
                return self.json_response(200, {"ok": True, "service": "ugc-zero-credit-web", "paid_generators": False,
                                                "voice_generation_enabled": bool(self.server.voice_models),
                                                "voice_language": self.server.voice_language,
                                                "voice_languages": available_languages(self.server.voice_models),
                                                "presenter_gpu_configured": bool(self.server.musetalk_dir and self.server.musetalk_python),
                                                "presenter_gpu_verified": bool(
                                                    self.server.presenter_diagnostic_cache
                                                    and time.monotonic() - self.server.presenter_diagnostic_cache[0] < 120
                                                    and self.server.presenter_diagnostic_cache[1]["ready"])})
            if parts == ["", "api", "presenter", "readiness"]:
                return self.json_response(200, {"ok": True, **self.server.presenter_readiness()})
            if parts == ["", "api", "projects"]:
                data = self.server.root
                entries = []
                for p in sorted(data.iterdir()):
                    if SAFE_ID.fullmatch(p.name) and p.is_dir() and not p.is_symlink():
                        metadata = json.loads((p / "meta.json").read_text())
                        entries.append({"id": p.name, "name": metadata.get("name", p.name)})
                return self.json_response(200, {"ok": True, "projects": entries})
            if len(parts) >= 4 and parts[:3] == ["", "api", "projects"]:
                project_id = parts[3]
                project = safe_project(self.server.root, project_id)
                if len(parts) == 4:
                    media = json.loads((project / "media.json").read_text(encoding="utf-8"))
                    media = [{**item, "url": self.signed_url(project_id, "media", item["file"].removeprefix("media/"))} for item in media]
                    cfg = json.loads((project / "project.json").read_text(encoding="utf-8")) if (project / "project.json").is_file() else None
                    with self.server.jobs_lock:
                        state = self.server.jobs.get(project_id, {"status": "idle"}).copy()
                    results = sorted([p.name for p in (project / "renders").iterdir() if p.is_file() and p.suffix in {".mp4", ".json", ".srt", ".ass"}])
                    draft = json.loads((project / "studio_draft.json").read_text(encoding="utf-8")) if (project / "studio_draft.json").is_file() else None
                    return self.json_response(200, {"ok": True, "id": project_id,
                        "name": json.loads((project / "meta.json").read_text())["name"], "media": media,
                        "config": cfg, "draft": draft, "job": state,
                        "outputs": [{"name": x, "url": self.signed_url(project_id, "outputs", x)} for x in results]})
            return self.error_response(404, "Route inconnue")
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            self.error_response(400, str(exc))
        except FileNotFoundError as exc:
            self.error_response(404, str(exc))
        except Exception as exc:
            self.error_response(500, "Erreur interne (vérifier les logs du serveur)")

    def do_POST(self):
        try:
            if not self.authenticated():
                return
            parts, query = self.route()
            if parts == ["", "api", "projects"]:
                data = self.json_request()
                name = data.get("name")
                if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
                    return self.error_response(400, "Nom de projet invalide")
                with self.server.jobs_lock:
                    pid = secrets.token_hex(8)
                    directory = self.server.root / pid
                    directory.mkdir(mode=0o700)
                    (directory / "media").mkdir(mode=0o700)
                    (directory / "renders").mkdir(mode=0o700)
                    store_json(directory / "meta.json", {"name": name.strip()})
                    store_json(directory / "media.json", [])
                return self.json_response(201, {"ok": True, "id": pid})
            if len(parts) == 5 and parts[:3] == ["", "api", "projects"]:
                pid, action = parts[3:5]
                project = safe_project(self.server.root, pid)
                if action == "media":
                    return self.upload(project, query)
                if action == "configure":
                    return self.configure(project)
                if action == "check":
                    if not (project / "project.json").is_file():
                        return self.error_response(409, "Projet non configuré")
                    cfg = json.loads((project / "project.json").read_text(encoding="utf-8"))
                    checked = verify(cfg, project)
                    return self.json_response(200, {"ok": True, "duration": checked["total_duration"],
                        "warnings": checked["warnings"] + checked["editorial_review"],
                        "captions": len(checked["segments"]), "clips": len(checked["talking"])})
                if action == "voice":
                    request = self.json_request()
                    if not isinstance(request, dict):
                        raise ValueError("Formulaire vocal invalide")
                    if not self.server.voice_models:
                        return self.error_response(503, "Aucun modèle Piper installé : configurer une voix locale")
                    if request.get("confirm_voice_rights") is not True:
                        return self.error_response(400, "Confirmer les droits d'usage de la voix")
                    try:
                        lang, voice = pick_voice(self.server.voice_models, request.get("language"))
                    except LookupError as exc:
                        return self.error_response(409, str(exc))
                    script = clean_text(request.get("text"))
                    with self.server.jobs_lock:
                        decision = admission(self.server.jobs, pid)
                        if decision == "already_running":
                            return self.error_response(409, "Un travail existe déjà pour ce projet")
                        if decision == "server_busy":
                            return self.error_response(429, "Serveur occupé : attendre la fin du travail")
                        self.server.jobs[pid] = {"status": "queued", "kind": "voice", "language": lang}
                    voice_file = project / "media" / ("narration_" + lang + "_" + secrets.token_hex(5) + ".wav")
                    def work_voice():
                        with self.server.jobs_lock:
                            self.server.jobs[pid] = {"status": "running", "kind": "voice", "language": lang}
                        try:
                            result = synthesize(script, voice["model"], voice_file,
                                                voice_license_ref=voice["license_ref"],
                                                confirmed=True)
                            with self.server.upload_lock:
                                current = json.loads((project / "media.json").read_text(encoding="utf-8"))
                                size = voice_file.stat().st_size
                                if len(current) >= MAX_FILES or sum(item.get("bytes", 0) for item in current) + size > MAX_PROJECT_BYTES:
                                    raise ValueError("Quota de stockage atteint : narration non enregistrée")
                                if shutil.disk_usage(project).free < MIN_FREE_BYTES:
                                    raise ValueError("Réserve disque insuffisante après génération")
                                item = {"file": "media/" + voice_file.name, "bytes": size,
                                        **summarize_media(voice_file), "generated_by": "piper_local",
                                        "language": lang, "voice_locale": result["language"],
                                        "voice_sha256": result["wav_sha256"]}
                                current.append(item)
                                store_json(project / "media.json", current)
                            with self.server.jobs_lock:
                                self.server.jobs[pid] = {"status": "completed", "kind": "voice",
                                                         "language": lang,
                                                         "output": item["file"], "duration": result["duration"]}
                        except Exception:
                            voice_file.unlink(missing_ok=True)
                            voice_file.with_suffix(".voice.json").unlink(missing_ok=True)
                            with self.server.jobs_lock:
                                self.server.jobs[pid] = {"status": "failed", "kind": "voice",
                                                         "language": lang,
                                                         "error": "Échec de génération vocale ; consulter les journaux privés"}
                    self.server.executor.submit(work_voice)
                    return self.json_response(202, {"ok": True, "status": "queued", "kind": "voice", "language": lang})
                if action == "presenter":
                    return self.create_presenter(project, pid)
                if action == "narrated":
                    request = self.json_request()
                    if not isinstance(request, dict):
                        raise ValueError("Formulaire de Short narré invalide")
                    if request.get("confirm_image_rights") is not True or request.get("claims_verified") is not True:
                        return self.error_response(400, "Confirmer les droits des photos et l'exactitude du titre")
                    preview = request.get("preview", False)
                    if type(preview) is not bool:
                        raise ValueError("Aperçu invalide")
                    title = clean_title(request.get("title"))
                    photos = request.get("images")
                    if not isinstance(photos, list) or not 1 <= len(photos) <= MAX_IMAGES:
                        raise ValueError("Sélectionner 1 à 6 photos")
                    if len(photos) != len(set(str(v) for v in photos)):
                        raise ValueError("Photos en doublon")
                    media = json.loads((project / "media.json").read_text(encoding="utf-8"))
                    indexed = {item["file"]: item for item in media}
                    audio_name = request.get("audio")
                    voice = indexed.get(audio_name) if isinstance(audio_name, str) else None
                    if not voice or voice.get("generated_by") != "piper_local" or voice.get("type") != "audio":
                        raise ValueError("Générer d'abord une narration Piper dans le projet")
                    narration = safe_uploaded_file(project, audio_name)
                    narration_info = inspect_narration(narration, voice.get("voice_sha256"))
                    image_paths = []
                    for name in photos:
                        if not isinstance(name, str) or name not in indexed or indexed[name].get("type") != "image":
                            raise ValueError("Utiliser uniquement des photos importées dans ce projet")
                        image_paths.append(safe_uploaded_file(project, name))
                    inspect_photos(image_paths)
                    if not (project / "renders").is_dir():
                        raise FileNotFoundError("Dossier de rendu manquant")
                    with self.server.jobs_lock:
                        decision = admission(self.server.jobs, pid)
                        if decision == "already_running":
                            return self.error_response(409, "Un travail existe déjà pour ce projet")
                        if decision == "server_busy":
                            return self.error_response(429, "Serveur occupé : réessayer après les rendus")
                        self.server.jobs[pid] = {"status": "queued", "kind": "narrated",
                                                 "preview": preview, "language": narration_info["language"]}
                    output = project / "renders" / ("narrated_preview.mp4" if preview else "narrated.mp4")
                    def work_narrated():
                        with self.server.jobs_lock:
                            self.server.jobs[pid] = {"status": "running", "kind": "narrated",
                                                     "preview": preview, "language": narration_info["language"]}
                        try:
                            report = render_short(image_paths, narration, output,
                                title=title, narration_sha=narration_info["sha256"],
                                image_rights_confirmed=True, claims_verified=True,
                                preview=preview)
                            with self.server.jobs_lock:
                                self.server.jobs[pid] = {"status": "completed", "kind": "narrated",
                                    "preview": preview, "output": output.name,
                                    "duration": report["duration"], "language": report["language"]}
                        except Exception as exc:
                            with self.server.jobs_lock:
                                self.server.jobs[pid] = {"status": "failed", "kind": "narrated",
                                    "preview": preview, "error": "Échec du Short narré : " + str(exc)[-650:]}
                    self.server.executor.submit(work_narrated)
                    return self.json_response(202, {"ok": True, "kind": "narrated",
                        "status": "queued", "language": narration_info["language"]})
                if action == "render":
                    inp = self.json_request()
                    if type(inp.get("preview", False)) is not bool:
                        raise ValueError("preview doit être booléen")
                    preview = inp.get("preview", False)
                    cfg_file = project / "project.json"
                    if not cfg_file.is_file():
                        return self.error_response(409, "Projet non configuré")
                    # Validate a snapshot outside the queue lock, then compare
                    # inside it. A concurrent save cannot silently replace the
                    # configuration while an export is being admitted.
                    config_snapshot = cfg_file.read_bytes()
                    cfg = json.loads(config_snapshot.decode("utf-8"))
                    verify(cfg, project)
                    with self.server.jobs_lock:
                        if cfg_file.read_bytes() != config_snapshot:
                            return self.error_response(409, "Configuration modifiée pendant la vérification ; réessayer")
                        decision = admission(self.server.jobs, pid)
                        if decision == "already_running":
                            return self.error_response(409, "Un export existe déjà pour ce projet")
                        if decision == "server_busy":
                            return self.error_response(429, "Serveur occupé : attendre la fin d'un export")
                        self.server.jobs[pid] = {"status": "queued", "preview": preview}
                    output = project / "renders" / ("preview.mp4" if preview else "final.mp4")
                    def work():
                        with self.server.jobs_lock:
                            self.server.jobs[pid] = {"status": "running", "preview": preview}
                        try:
                            report = build(cfg, project, output, preview=preview)
                            with self.server.jobs_lock:
                                self.server.jobs[pid] = {"status": "completed", "preview": preview, "output": output.name,
                                    "duration": report["duration"]}
                        except Exception as exc:
                            with self.server.jobs_lock:
                                self.server.jobs[pid] = {"status": "failed", "preview": preview,
                                    "error": str(exc)[-1000:]}
                    self.server.executor.submit(work)
                    return self.json_response(202, {"ok": True, "status": "queued"})
            return self.error_response(404, "Route inconnue")
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            self.error_response(400, str(exc))
        except FileNotFoundError as exc:
            self.error_response(404, str(exc))
        except Exception:
            self.error_response(500, "Erreur interne (vérifier les logs du serveur)")

    def create_presenter(self, project: Path, pid: str):
        """Private, opt-in GPU renderer. No remote inference or public exposure."""
        request = self.json_request()
        if not isinstance(request, dict):
            raise ValueError("Formulaire de présentatrice invalide")
        if not self.server.musetalk_dir or not self.server.musetalk_python:
            return self.error_response(503, "MuseTalk GPU non configuré sur ce serveur")
        if (request.get("confirm_portrait_rights") is not True
                or request.get("confirm_voice_rights") is not True
                or request.get("confirm_subject_consent") is not True):
            return self.error_response(400, "Confirmer droits du portrait, voix et consentement du sujet")
        rights_ref = request.get("portrait_rights_ref")
        if not isinstance(rights_ref, str) or not 8 <= len(rights_ref.strip()) <= 500:
            raise ValueError("Fournir une référence de droits du portrait (8–500 caractères)")
        indexed = {m["file"]: m for m in json.loads((project / "media.json").read_text(encoding="utf-8"))}
        voice_name = request.get("audio")
        portrait_name = request.get("portrait")
        voice_item = indexed.get(voice_name) if isinstance(voice_name, str) else None
        portrait_item = indexed.get(portrait_name) if isinstance(portrait_name, str) else None
        if not voice_item or voice_item.get("generated_by") != "piper_local" or voice_item.get("type") != "audio":
            raise ValueError("Choisir un WAV Piper produit dans ce projet")
        if not portrait_item or portrait_item.get("type") != "image":
            raise ValueError("Choisir un portrait autorisé du projet")
        wav = safe_uploaded_file(project, voice_name)
        photo = safe_uploaded_file(project, portrait_name)
        if photo.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            raise ValueError("Portrait MuseTalk : JPEG ou PNG uniquement")
        inspect_photos([photo])
        voice_info = inspect_narration(wav, voice_item.get("voice_sha256"))
        if (len(indexed) >= MAX_FILES
                or sum(item.get("bytes", 0) for item in indexed.values()) >= MAX_PROJECT_BYTES
                or shutil.disk_usage(project).free < MIN_FREE_BYTES + 64 * 1024 * 1024):
            return self.error_response(409, "Quota du projet ou réserve disque insuffisant pour MuseTalk")
        if not (project / "media").is_dir() or (project / "media").is_symlink():
            raise ValueError("Dossier média invalide")
        # Fail before admission; never queue fictitious GPU work.
        readiness = self.server.presenter_readiness()
        if not readiness["ready"]:
            return self.error_response(503, readiness["message"])
        with self.server.jobs_lock:
            decision = admission(self.server.jobs, pid)
            if decision == "already_running":
                return self.error_response(409, "Un travail existe déjà pour ce projet")
            if decision == "server_busy":
                return self.error_response(429, "Serveur occupé : attendre la fin du travail")
            self.server.jobs[pid] = {"status": "queued", "kind": "presenter", "language": voice_info["language"]}
        video_file = project / "media" / ("presenter_" + secrets.token_hex(8) + ".mp4")
        def work_presenter():
            with self.server.jobs_lock:
                self.server.jobs[pid] = {"status": "running", "kind": "presenter", "language": voice_info["language"]}
            try:
                report = presenter(text="", model=None, image=photo,
                    musetalk=self.server.musetalk_dir, interpreter=self.server.musetalk_python,
                    output=video_file, voice_license_ref=voice_info["voice_license_ref"],
                    image_rights_ref=rights_ref.strip(), confirm_voice_rights=True,
                    confirm_image_rights=True, existing_narration=wav)
                with self.server.upload_lock:
                    media = json.loads((project / "media.json").read_text(encoding="utf-8"))
                    size = video_file.stat().st_size
                    if (len(media) >= MAX_FILES
                            or sum(item.get("bytes", 0) for item in media) + size > MAX_PROJECT_BYTES
                            or shutil.disk_usage(project).free < MIN_FREE_BYTES):
                        raise ValueError("Quota média / réserve disque insuffisants")
                    item = {"file": "media/" + video_file.name, "bytes": size,
                            **summarize_media(video_file), "generated_by": "musetalk_local",
                            "language": voice_info["language"], "lip_sync_verified": False,
                            "human_review_required": True}
                    media.append(item)
                    store_json(project / "media.json", media)
                with self.server.jobs_lock:
                    self.server.jobs[pid] = {"status": "completed", "kind": "presenter",
                        "output": item["file"], "duration": report["video_seconds"],
                        "human_review_required": True, "language": voice_info["language"]}
            except Exception:
                video_file.unlink(missing_ok=True)
                video_file.with_suffix(".presenter.json").unlink(missing_ok=True)
                with self.server.jobs_lock:
                    self.server.jobs[pid] = {"status": "failed", "kind": "presenter",
                        "language": voice_info["language"],
                        "error": "Échec MuseTalk local : consulter les journaux privés"}
        self.server.executor.submit(work_presenter)
        return self.json_response(202, {"ok": True, "status": "queued",
            "kind": "presenter", "language": voice_info["language"]})

    def upload(self, project: Path, query: dict):
        name = query.get("filename", [""])[0]
        if not SAFE_NAME.fullmatch(name) or name.startswith(".") or Path(name).suffix.lower() not in ALLOWED_UPLOADS:
            raise ValueError("Nom ou type de fichier non autorisé")
        amount = self.length(MAX_UPLOAD)
        # Serialize uploads for this process: no collisions and bounded quota.
        with self.server.upload_lock:
            return self._upload_serialized(project, name, amount)

    def _upload_serialized(self, project: Path, name: str, amount: int):
        current = json.loads((project / "media.json").read_text(encoding="utf-8"))
        if Path(name).suffix.lower() == ".srt" and amount > 2_000_000:
            raise ValueError("SRT trop grand : maximum 2 Mo")
        if len(current) >= MAX_FILES:
            raise ValueError("Trop de médias dans ce projet")
        total = sum(item.get("bytes", 0) for item in current)
        if total + amount > MAX_PROJECT_BYTES:
            raise ValueError("Quota local du projet dépassé : 2 Gio")
        if shutil.disk_usage(project).free < amount + MIN_FREE_BYTES:
            raise ValueError("Espace disque insuffisant ; conserver 256 Mio libres")
        target = project / "media" / name
        if target.exists() or target.is_symlink():
            name = secrets.token_hex(3) + "_" + name
            target = project / "media" / name
        temporary = project / "media" / ("." + secrets.token_hex(8) + ".tmp")
        remaining = amount
        try:
            with temporary.open("xb") as handle:
                while remaining:
                    block = self.rfile.read(min(1048576, remaining))
                    if not block:
                        raise ValueError("Transfert interrompu")
                    handle.write(block)
                    remaining -= len(block)
            # ffprobe can read temporary files regardless of their extension.
            metadata_file = project / "media" / name
            os.replace(temporary, metadata_file)
            try:
                info = summarize_media(metadata_file)
            except Exception:
                metadata_file.unlink(missing_ok=True)
                raise
            item = {"file": "media/" + name, "bytes": amount, **info}
            current.append(item)
            store_json(project / "media.json", current)
            return self.json_response(201, {"ok": True, "media": item})
        finally:
            temporary.unlink(missing_ok=True)

    def configure(self, project: Path):
        payload = self.json_request()
        # Keep configuration consistent with the snapshot used by the renderer.
        # The same lock guards admission, so a render cannot queue mid-update.
        with self.server.jobs_lock:
            if is_active(self.server.jobs.get(project.name, {})):
                return self.error_response(409, "Modification interdite pendant un export")
            config, details = assemble_config(project, payload)
            store_json(project / "project.json", config)
            store_json(project / "studio_draft.json", payload)
        return self.json_response(200, {"ok": True, "config": config, **details})


def main(argv=None):
    parser = argparse.ArgumentParser(description="UGC Zero Credit — studio web mobile sécurisé, local, sans crédits")
    parser.add_argument("--host", default="127.0.0.1", help="Défaut local uniquement ; ne pas exposer sans HTTPS/VPN")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--data", type=Path, default=ROOT / "ugc_projects")
    parser.add_argument("--token", default=os.environ.get("UGC_STUDIO_TOKEN"))
    parser.add_argument("--voice-model", type=Path, help="Modèle Piper ONNX local (facultatif)")
    parser.add_argument("--voice-license-ref", default="", help="Référence des droits de la voix (mode V11)")
    parser.add_argument("--voice-model-fr", type=Path, help="Modèle ONNX de voix française")
    parser.add_argument("--voice-license-ref-fr", default="", help="Référence de droits française")
    parser.add_argument("--voice-model-en", type=Path, help="Modèle ONNX de voix anglaise")
    parser.add_argument("--voice-license-ref-en", default="", help="Référence de droits anglaise")
    parser.add_argument("--musetalk-dir", type=Path, default=Path(os.environ["UGC_MUSETALK_DIR"]) if os.environ.get("UGC_MUSETALK_DIR") else None,
                        help="Dossier MuseTalk local (NVIDIA GPU uniquement)")
    parser.add_argument("--musetalk-python", type=Path, default=Path(os.environ["UGC_MUSETALK_PYTHON"]) if os.environ.get("UGC_MUSETALK_PYTHON") else None,
                        help="Python CUDA local dédié à MuseTalk")
    a = parser.parse_args(argv)
    # Docker publishes 127.0.0.1 on the HOST, but requires binding to all
    # interfaces INSIDE its isolated bridge network. Never permit this mode
    # outside Docker or without an explicit opt-in.
    docker_private = (a.host == "0.0.0.0" and
                      os.environ.get("UGC_PRIVATE_DOCKER_BIND") == "1" and
                      Path("/.dockerenv").is_file())
    if a.host not in {"127.0.0.1", "localhost", "::1"} and not docker_private:
        print("REFUS: serveur HTTP non local. Utiliser le Docker Compose privé ou le tunnel SSH.", file=sys.stderr)
        raise SystemExit(2)
    token = a.token or secrets.token_urlsafe(24)
    if len(token) < 24:
        raise SystemExit("Token trop court : 24 caractères minimum")
    httpd = Studio((a.host, a.port), Handler, a.data, token,
                   voice_model=a.voice_model, voice_license_ref=a.voice_license_ref,
                   voice_model_fr=a.voice_model_fr, voice_license_ref_fr=a.voice_license_ref_fr,
                   voice_model_en=a.voice_model_en, voice_license_ref_en=a.voice_license_ref_en,
                   musetalk_dir=a.musetalk_dir, musetalk_python=a.musetalk_python)
    print(f"Studio UGC (sans générateur payant) : http://{a.host}:{a.port}", flush=True)
    if docker_private:
        # The private token is available in the server's chmod-600 .env file.
        # Avoid copying long-lived secrets to Docker's persistent logs.
        print("Jeton : consulter le fichier local .env de l'installateur.", flush=True)
    else:
        print(f"Jeton de connexion (à saisir dans le navigateur) : {token}", flush=True)
    try:
        httpd.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        httpd.executor.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    main()
