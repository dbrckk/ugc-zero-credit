#!/usr/bin/env python3
"""Fetch official MuseTalk 1.5 inference weights once during explicit install.

No web call is made by the runtime studio. Uses upstream repositories rather
than the unverified mirror configured by MuseTalk's download_weights.sh.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import os
import urllib.request

from huggingface_hub import hf_hub_download
import gdown

# Official MuseTalk README + download_weights.sh, pinned to repo commit
# 0a89dec45a0192b824e3cf4daf96c239440c5ed8.
FILES = (
    ("TMElyralab/MuseTalk", "musetalkV15/musetalk.json", ""),
    ("TMElyralab/MuseTalk", "musetalkV15/unet.pth", ""),
    ("stabilityai/sd-vae-ft-mse", "config.json", "sd-vae"),
    ("stabilityai/sd-vae-ft-mse", "diffusion_pytorch_model.bin", "sd-vae"),
    ("openai/whisper-tiny", "config.json", "whisper"),
    ("openai/whisper-tiny", "pytorch_model.bin", "whisper"),
    ("openai/whisper-tiny", "preprocessor_config.json", "whisper"),
    ("yzd-v/DWPose", "dw-ll_ucoco_384.pth", "dwpose"),
    ("ByteDance/LatentSync", "latentsync_syncnet.pt", "syncnet"),
)

def fetch(root: Path) -> None:
    if root.is_symlink() or not (root / "scripts" / "inference.py").is_file():
        raise ValueError("Dossier MuseTalk officiel invalide")
    models = root / "models"
    if models.is_symlink():
        raise ValueError("Dossier models symbolique refusé")
    models.mkdir(exist_ok=True)
    for repo_id, filename, subdir in FILES:
        target = models / subdir / filename
        if target.is_symlink():
            raise ValueError("Lien symbolique de poids interdit : " + str(target))
        minimum = 100_000 if target.suffix in {".pth", ".bin"} else 10
        if target.is_file() and target.stat().st_size >= minimum:
            continue
        local_dir = models / subdir
        local_dir.mkdir(parents=True, exist_ok=True)
        print("Téléchargement officiel :", repo_id, filename, flush=True)
        hf_hub_download(repo_id=repo_id, filename=filename,
                        local_dir=str(local_dir), local_dir_use_symlinks=False)
        if not target.is_file() or target.stat().st_size < minimum:
            raise RuntimeError("Fichier de modèle incomplet : " + str(target))

    face = models / "face-parse-bisent"
    face.mkdir(exist_ok=True)
    parsing = face / "79999_iter.pth"
    if parsing.is_symlink():
        raise ValueError("Lien symbolique de poids interdit")
    if not parsing.is_file() or parsing.stat().st_size < 1_000_000:
        print("Téléchargement officiel Google Drive du parsing facial", flush=True)
        tmp = face / ".79999_iter.pth.download"
        try:
            result = gdown.download(id="154JgKpzCPW82qINcVieuPH3fZ2e0P812",
                                    output=str(tmp), quiet=False)
            if not result or not tmp.is_file() or tmp.stat().st_size < 1_000_000:
                raise RuntimeError("Google Drive a refusé les poids de parsing facial")
            os.replace(tmp, parsing)
        finally:
            tmp.unlink(missing_ok=True)
    resnet = face / "resnet18-5c106cde.pth"
    if resnet.is_symlink():
        raise ValueError("Lien symbolique de poids interdit")
    if not resnet.is_file() or resnet.stat().st_size < 1_000_000:
        print("Téléchargement officiel resnet18 depuis download.pytorch.org", flush=True)
        tmp = face / ".resnet18.download"
        try:
            urllib.request.urlretrieve(
                "https://download.pytorch.org/models/resnet18-5c106cde.pth", tmp)
            if tmp.stat().st_size < 1_000_000:
                raise RuntimeError("Téléchargement resnet18 incomplet")
            os.replace(tmp, resnet)
        finally:
            tmp.unlink(missing_ok=True)
    print("Tous les fichiers MuseTalk nécessaires sont présents ; droits et licences à vérifier.")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--musetalk-dir", required=True, type=Path)
    args = p.parse_args()
    fetch(args.musetalk_dir.expanduser().resolve(strict=True))

if __name__ == "__main__":
    main()
