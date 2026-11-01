#!/usr/bin/env python3
"""Private, quota-respecting Kaggle GPU one-command launcher.

Two real workflows:
  - run --dataset owner/private-dataset : submit existing private input, wait,
    optionally retrieve genuine MuseTalk outputs. GitHub Actions uses this.
  - run --media-dir DIR : validate four local files, create a PRIVATE Kaggle
    dataset, run and retrieve. Suitable for local Linux/Termux.

Never bypass GPU quotas, submit public media, print API tokens, publish clips,
or report success based only on Kaggle's COMPLETE status.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

from kaggle_musetalk import assets
from offline_presenter import clean_text, required_reference

REF = re.compile(r"^[a-zA-Z0-9_-]{2,40}/[a-zA-Z0-9_-]{3,50}$")
SLUG = re.compile(r"^[a-z][a-z0-9-]{2,49}$")
STATUS = re.compile(r"KernelWorkerStatus\.(QUEUED|RUNNING|COMPLETE|ERROR|CANCEL_REQUESTED|CANCEL_ACKNOWLEDGED|NEW_SCRIPT)")
REPO = Path(__file__).resolve().parent
NOTEBOOK = REPO / "kaggle" / "ugc_musetalk_gpu.ipynb"
KAGGLE_ID = "NvidiaTeslaT4"


def ref(value: str, label: str) -> str:
    if not REF.fullmatch(value) or ".." in value:
        raise ValueError(f"{label} invalide (attendu utilisateur/slug)")
    return value


def command(args: list[str], *, timeout: int = 180) -> str:
    proc = subprocess.run(["kaggle", *args], text=True, capture_output=True,
                          timeout=timeout, check=False)
    if proc.returncode:
        # CLI errors may echo request metadata; never display raw Kaggle logs.
        raise RuntimeError("Commande Kaggle refusée : " + " ".join(args[:2])
                           + ". Vérifier autorisations, quota ou statut sur kaggle.com.")
    return proc.stdout


def check_auth() -> None:
    # Kaggle's CLI also accepts local token files, or kaggle auth login.
    if shutil.which("kaggle") is None:
        raise RuntimeError("Installer l'outil officiel : python -m pip install kaggle")
    token = os.getenv("KAGGLE_API_TOKEN", "")
    if not token and not (Path.home() / ".kaggle" / "access_token").is_file() \
            and not (Path.home() / ".kaggle" / "kaggle.json").is_file():
        raise RuntimeError("Connexion Kaggle absente : définir KAGGLE_API_TOKEN (sans le publier)")
    if token and len(token) < 16:
        raise RuntimeError("Jeton Kaggle trop court ; vérifier sa configuration")


def private_dataset_from_media(media_dir: Path, user: str, workspace: Path) -> str:
    media = media_dir.expanduser().resolve(strict=True)
    source = assets(media)  # real ffprobe validation + signed rights, before upload
    folder = source["video"].parent
    inputs = [source["video"], folder / "script.txt",
              folder / "language.txt", folder / "portrait_rights.txt"]
    if any(f.is_symlink() for f in inputs):
        raise ValueError("Dataset avec lien symbolique refusé")
    dataset_slug = "ugc-private-" + os.urandom(5).hex()
    dataset_ref = ref(user + "/" + dataset_slug, "Référence du dataset")
    staging = workspace / "dataset"
    staging.mkdir()
    for path in inputs:
        shutil.copyfile(path, staging / path.name)
    (staging / "dataset-metadata.json").write_text(
        json.dumps({
            "title": "UGC private video " + dataset_slug,
            "id": dataset_ref,
            "description": "Private authorized video inputs. All rights reserved; no redistribution.",
            "licenses": [{"name": "other"}]
        }, indent=2) + "\n", encoding="utf-8")
    # Kaggle datasets create defaults to PRIVATE; NEVER use --public.
    command(["datasets", "create", "-p", str(staging), "-q", "-t", "-r", "skip"],
            timeout=600)
    print("Dataset privé envoyé à Kaggle :", dataset_ref, flush=True)
    return dataset_ref


def notebook_kernel(folder: Path, *, user: str, slug: str, dataset: str) -> str:
    if not NOTEBOOK.is_file():
        raise FileNotFoundError("Notebook Kaggle du dépôt absent")
    if not SLUG.fullmatch(slug):
        raise ValueError("Slug de notebook invalide")
    kernel_ref = ref(user + "/" + slug, "Référence du notebook")
    folder.mkdir()
    shutil.copyfile(NOTEBOOK, folder / NOTEBOOK.name)
    config = {
        "id": kernel_ref,
        "title": slug,
        "code_file": NOTEBOOK.name,
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": True,
        "enable_internet": True,
        "machine_shape": KAGGLE_ID,
        "dataset_sources": [dataset],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": []
    }
    (folder / "kernel-metadata.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return kernel_ref


def status_value(output: str) -> str:
    matches = STATUS.findall(output)
    if len(matches) != 1:
        raise ValueError("État Kaggle ambigu ou inconnu ; aucune réussite présumée")
    return matches[0]


def wait(kernel: str, *, minutes: int, interval: int) -> None:
    deadline = time.monotonic() + minutes * 60
    errors = 0
    while time.monotonic() < deadline:
        try:
            state = status_value(command(["kernels", "status", kernel], timeout=90))
            errors = 0
        except (ValueError, RuntimeError, subprocess.TimeoutExpired):
            errors += 1
            if errors >= 3:
                raise RuntimeError("État Kaggle inaccessible trois fois ; consulter le notebook privé")
            time.sleep(interval)
            continue
        print("Kaggle GPU :", state, flush=True)
        if state == "COMPLETE":
            return
        if state in {"ERROR", "CANCEL_REQUESTED", "CANCEL_ACKNOWLEDGED"}:
            raise RuntimeError("Notebook Kaggle en échec ou annulé ; consulter les logs privés")
        time.sleep(interval)
    raise TimeoutError("Temps de suivi atteint : le notebook Kaggle peut encore fonctionner. "
                       "Ne pas relancer un calcul avant d'inspecter son état.")


def check_results(folder: Path) -> list[Path]:
    from offline_presenter import inspect_video
    root = folder.resolve(strict=True)
    matches = []
    for file in root.rglob("*.presenter.json"):
        if file.is_symlink() or not file.resolve().is_relative_to(root):
            raise ValueError("Sortie Kaggle inattendue : lien ou chemin hors du répertoire")
        video = file.with_name(file.name.removesuffix(".presenter.json") + ".mp4")
        if not video.is_file() or video.is_symlink() or not video.resolve().is_relative_to(root):
            raise ValueError("MP4 manquant ou invalide pour " + file.name)
        report = json.loads(file.read_text(encoding="utf-8"))
        with video.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if (report.get("sha256") != digest
                or report.get("gpu_inference_executed") is not True
                or report.get("ffmpeg_full_decode") is not True
                or report.get("publication_allowed_automatically") is not False
                or not video.stat().st_size > 1024):
            raise ValueError("Preuve de génération GPU invalide : " + file.name)
        # Independently decode downloaded bytes: do not trust the remote
        # report's claim of FFmpeg validation on its own.
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            raise RuntimeError("FFmpeg/ffprobe sont nécessaires pour valider le MP4 téléchargé")
        inspect_video(video)
        decoded = subprocess.run(
            ["ffmpeg", "-v", "error", "-xerror", "-i", str(video),
             "-f", "null", "-"], capture_output=True, text=True, timeout=240)
        if decoded.returncode:
            raise RuntimeError("Décodage complet du MP4 Kaggle téléchargé échoué")
        matches.append(video)
    if not matches:
        raise RuntimeError("Kaggle a terminé sans manifeste GPU réel vérifiable. Pas de réussite déclarée.")
    return matches


def main(argv=None):
    parser = argparse.ArgumentParser(description="Automatiser Kaggle T4 sans crédit ni diffusion publique")
    parser.add_argument("--user", required=True, help="Identifiant Kaggle (jamais un mot de passe)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dataset", help="Dataset Kaggle privé préexistant, format utilisateur/slug")
    group.add_argument("--media-dir", type=Path, help="Répertoire local des quatre médias autorisés")
    group.add_argument("--video", type=Path, help="Clip source local : génère automatiquement le dataset privé")
    parser.add_argument("--text", help="Narration à prononcer (avec --video)")
    parser.add_argument("--language", choices=["fr", "en"], help="Langue de la narration (avec --video)")
    parser.add_argument("--rights", help="Référence d’autorisation du clip (avec --video)")
    parser.add_argument("--kernel-slug", default="ugc-zero-credit-private")
    parser.add_argument("--wait-minutes", type=int, default=120)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--download-dir", type=Path, help="Télécharger les MP4 privés en local après succès")
    args = parser.parse_args(argv)
    user = args.user
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,40}", user):
        parser.error("Identifiant utilisateur Kaggle invalide")
    if not 5 <= args.wait_minutes <= 240 or not 10 <= args.poll_seconds <= 120:
        parser.error("Durée de suivi/polling invalide")
    if args.video:
        if not args.text or not args.language or not args.rights:
            parser.error("--video nécessite aussi --text, --language et --rights")
        clean_text(args.text)
        required_reference(args.rights, "Autorisation du portrait")
    if args.dataset:
        dataset = ref(args.dataset, "Dataset Kaggle")
        # Fail closed on cross-user datasets: anonymous public datasets are
        # unsuitable for commercial/consented faces without explicit review.
        if dataset.split("/")[0].lower() != user.lower():
            parser.error("Dataset privé : le propriétaire doit être le même compte Kaggle")
    check_auth()
    with tempfile.TemporaryDirectory(prefix="ugc-kaggle-private-") as temp:
        workspace = Path(temp)
        if args.video:
            media = workspace / "media-from-phone"
            media.mkdir()
            source = args.video.expanduser()
            if source.is_symlink() or not source.is_file() or source.suffix.lower() not in {".mp4", ".mov", ".mkv"}:
                raise ValueError("Fichier vidéo absent, symbolique ou format non pris en charge")
            shutil.copyfile(source, media / ("presenter" + source.suffix.lower()))
            (media / "script.txt").write_text(args.text, encoding="utf-8")
            (media / "language.txt").write_text(args.language, encoding="utf-8")
            (media / "portrait_rights.txt").write_text(args.rights, encoding="utf-8")
            dataset = private_dataset_from_media(media, user, workspace)
        elif args.media_dir:
            dataset = private_dataset_from_media(args.media_dir, user, workspace)
        kernel = notebook_kernel(workspace / "notebook",
                                 user=user, slug=args.kernel_slug, dataset=dataset)
        print("Création du Notebook privé, GPU T4 x2 :", kernel, flush=True)
        command(["kernels", "push", "-p", str(workspace / "notebook"),
                 "--accelerator", KAGGLE_ID], timeout=600)
        print("Notebook : https://www.kaggle.com/code/" + kernel, flush=True)
        wait(kernel, minutes=args.wait_minutes, interval=args.poll_seconds)
        # COMPLETE is never enough: verify the actual downloaded MP4 even when
        # invoked from GitHub Actions. Runner copies are ephemeral and never
        # published as artifacts. Kaggle retains the original privately.
        if args.download_dir:
            dest = args.download_dir.expanduser().absolute()
            if dest.is_symlink() or dest.exists():
                raise FileExistsError("Pour éviter l'écrasement, fournir un dossier de sortie neuf et non symbolique")
            dest.mkdir(parents=True)
        else:
            dest = workspace / "ephemeral-result"
            dest.mkdir()
        try:
            command(["kernels", "output", kernel, "-p", str(dest)], timeout=900)
            validated = check_results(dest)
        except Exception:
            print("Sortie non validée ; ne pas diffuser les fichiers.", file=sys.stderr)
            raise
        for video in validated:
            print("MP4 GPU vérifié avec son manifeste :", video.name, flush=True)
        if not args.download_dir:
            print("Copie temporaire validée puis supprimée ; résultat privé conservé sur Kaggle.", flush=True)
        else:
            print("Vidéo privée conservée localement dans :", dest, flush=True)
        print("Revue humaine obligatoire avant toute utilisation commerciale.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, TimeoutError, subprocess.TimeoutExpired) as exc:
        print("ÉCHEC AUTOMATISATION :", str(exc), file=sys.stderr)
        raise SystemExit(2)
