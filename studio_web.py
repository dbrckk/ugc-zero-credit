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
                  "fade": overlay.get("fade", 0.12)}
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

    def __init__(self, address, handler, root: Path, token: str):
        super().__init__(address, handler)
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.token = token
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ugc-render")
        self.jobs: dict[str, dict] = {}
        self.jobs_lock = threading.Lock()
        self.upload_lock = threading.Lock()

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
                    if leaf not in {"final.mp4", "preview.mp4", "final.srt", "preview.srt", "final.qa.json", "preview.qa.json", "final.report.json", "preview.report.json"}:
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
                return self.json_response(200, {"ok": True, "service": "ugc-zero-credit-web", "paid_generators": False})
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
                if action == "render":
                    inp = self.json_request()
                    if type(inp.get("preview", False)) is not bool:
                        raise ValueError("preview doit être booléen")
                    preview = inp.get("preview", False)
                    cfg_file = project / "project.json"
                    if not cfg_file.is_file():
                        return self.error_response(409, "Projet non configuré")
                    cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
                    verify(cfg, project)
                    with self.server.jobs_lock:
                        previous = self.server.jobs.get(pid, {})
                        if previous.get("status") in {"queued", "running"}:
                            return self.error_response(409, "Un export existe déjà")
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
    a = parser.parse_args(argv)
    if a.host not in {"127.0.0.1", "localhost", "::1"}:
        print("ATTENTION: accès réseau non local; utiliser uniquement derrière HTTPS/VPN, jamais en HTTP public", file=sys.stderr)
        raise SystemExit(2)
    token = a.token or secrets.token_urlsafe(24)
    if len(token) < 24:
        raise SystemExit("Token trop court : 24 caractères minimum")
    httpd = Studio((a.host, a.port), Handler, a.data, token)
    print(f"Studio UGC (sans générateur payant) : http://{a.host}:{a.port}", flush=True)
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
