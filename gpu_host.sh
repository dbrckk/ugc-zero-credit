#!/usr/bin/env bash
# Opt-in NVIDIA GPU host; never edits or exposes the CPU Docker instance.
set -Eeuo pipefail
umask 077
cd "$(dirname "$0")"
mode="--doctor"; if (( $# )); then mode="$1"; fi
home="$HOME"
mt="$home/ugc-musetalk-v15"
gpu="$home/ugc-musetalk-venv"
studio="$home/ugc-studio-venv"
voices="$home/ugc-voices"
data="$home/ugc-studio-gpu-data"
keyfile="$home/.ugc-gpu-studio-token"
port=8788
pinned=0a89dec45a0192b824e3cf4daf96c239440c5ed8
fr_license=https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/siwis/medium/MODEL_CARD
en_license=https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/lessac/medium/MODEL_CARD
fail() { printf 'ERREUR GPU : %s\n' "$*" >&2; exit 2; }
case "$mode" in --install|--doctor|--run|--enable-service) ;; *) fail "Utiliser --install, --doctor, --run ou --enable-service" ;; esac
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || fail "Serveur Linux x86_64 requis."
for path in "$home" "$mt" "$gpu" "$studio" "$voices" "$data" "$keyfile"; do
  [[ "$path" =~ ^[A-Za-z0-9_./-]+$ ]] || fail "Chemin incompatible avec MuseTalk (espaces ou caractères spéciaux)."
  [[ ! -L "$path" ]] || fail "Lien symbolique interdit."
done
command -v nvidia-smi >/dev/null || fail "Pilote NVIDIA absent : utiliser un serveur réellement équipé d'un GPU."
nvidia-smi -L >/dev/null 2>&1 || fail "GPU NVIDIA non accessible."
if [[ "$mode" == --install ]]; then
  command -v apt-get >/dev/null && command -v python3 >/dev/null || fail "Debian/Ubuntu et Python 3 requis."
  apt=""; if (( EUID != 0 )); then command -v sudo >/dev/null || fail "sudo requis."; apt=sudo; fi
  free_kib="$(df -Pk "$home" | awk 'NR==2 {print $4}')"
  [[ "$free_kib" =~ ^[0-9]+$ ]] && (( free_kib >= 20*1024*1024 )) || fail "20 Gio de disque disponibles requis pour PyTorch CUDA, modèles et environnement."
  $apt apt-get update -qq
  $apt apt-get install -y --no-install-recommends git ca-certificates curl ffmpeg python3-venv python3-pip libgl1 libglib2.0-0 espeak-ng
  if command -v uv >/dev/null; then
    uv=$(command -v uv)
  else
    python3 -m venv "$home/.ugc-uv-bootstrap"
    "$home/.ugc-uv-bootstrap/bin/python" -m pip install 'uv==0.9.18'
    uv="$home/.ugc-uv-bootstrap/bin/uv"
  fi
  "$uv" python install 3.10 3.11
  if [[ ! -x "$gpu/bin/python" ]]; then "$uv" venv --seed --python 3.10 "$gpu"; fi
  if [[ ! -x "$studio/bin/python" ]]; then "$uv" venv --seed --python 3.11 "$studio"; fi
  if [[ -e "$mt" ]]; then
    [[ -d "$mt/.git" ]] || fail "Dossier MuseTalk existant non Git."
    [[ "$(git -C "$mt" remote get-url origin)" == "https://github.com/TMElyralab/MuseTalk.git" ]] || fail "Dépôt MuseTalk inattendu."
    [[ "$(git -C "$mt" rev-parse HEAD)" == "$pinned" ]] || fail "Commit MuseTalk incompatible avec version figée."
  else
    git clone --quiet https://github.com/TMElyralab/MuseTalk.git "$mt"
    git -C "$mt" checkout --quiet --detach "$pinned"
  fi
  "$gpu/bin/python" -m pip install torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cu118
  "$gpu/bin/python" -m pip install -r "$mt/requirements.txt" 'openmim==0.3.9'
  "$gpu/bin/mim" install mmengine
  "$gpu/bin/mim" install 'mmcv==2.0.1'
  "$gpu/bin/mim" install 'mmdet==3.1.0'
  "$gpu/bin/mim" install 'mmpose==1.1.0'
  "$studio/bin/python" -m pip install 'piper-tts==1.8.0'
  mkdir -p "$voices" "$data"
  if [[ ! -s "$voices/fr_FR-siwis-medium.onnx" || ! -s "$voices/en_US-lessac-medium.onnx" ]]; then
    "$studio/bin/python" -m piper.download_voices fr_FR-siwis-medium en_US-lessac-medium --data-dir "$voices"
  fi
  "$gpu/bin/python" gpu_fetch_weights.py --musetalk-dir "$mt"
  if [[ ! -e "$keyfile" ]]; then
    python3 -c 'import secrets,sys;open(sys.argv[1],"x").write(secrets.token_urlsafe(32)+"\n")' "$keyfile"
  fi
  chmod 600 "$keyfile"
fi
command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null || fail "FFmpeg ou ffprobe absent."
[[ -x "$gpu/bin/python" && -x "$studio/bin/python" ]] || fail "Environnements Python absents : lancer --install."
[[ -s "$voices/fr_FR-siwis-medium.onnx" && -s "$voices/en_US-lessac-medium.onnx" ]] || fail "Voix Piper FR/EN absentes."
[[ -d "$data" ]] || fail "Dossier de données absent : lancer --install."
(
  cd "$mt"
  "$gpu/bin/python" -c 'import torch; assert torch.cuda.is_available(); p=torch.cuda.get_device_properties(0); assert p.total_memory>=4*1024**3,"Moins de 4 Gio de VRAM"; from scripts import inference; print("CUDA_READY VRAM_GIB="+str(round(p.total_memory/1024**3,1)))'
) || fail "Dépendances MuseTalk, CUDA ou VRAM insuffisantes."
"$studio/bin/python" offline_presenter.py doctor --voice-model "$voices/fr_FR-siwis-medium.onnx" --musetalk-dir "$mt" --musetalk-python "$gpu/bin/python" >/dev/null || fail "Installation GPU invalide."
"$studio/bin/python" -c 'from offline_presenter import voice_model;from pathlib import Path;import sys;assert voice_model(Path(sys.argv[1]))["language"].startswith("en")' "$voices/en_US-lessac-medium.onnx" || fail "Voix EN non valide."
echo "Préparation GPU validée : NVIDIA CUDA + MuseTalk 1.5 + Piper FR/EN."
if [[ "$mode" == --install ]]; then echo "Démarrage privé : bash gpu_host.sh --enable-service"; exit 0; fi
if [[ "$mode" == --doctor ]]; then exit 0; fi
if [[ "$mode" == --enable-service ]]; then
  command -v systemctl >/dev/null || fail "systemd absent ; utiliser --run."
  unit="$HOME/.config/systemd/user/ugc-zero-credit-gpu.service"
  mkdir -p "$(dirname "$unit")"
  [[ ! -L "$unit" ]] || fail "Unité symbolique refusée."
  script="$(pwd -P)/gpu_host.sh"
  cat > "$unit" <<EOF
[Unit]
Description=UGC Zero Credit private GPU studio
After=network.target
[Service]
Type=simple
ExecStart=/usr/bin/env bash $script --run
Restart=on-failure
RestartSec=7
NoNewPrivileges=true
[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload
  systemctl --user enable --now ugc-zero-credit-gpu.service
  systemctl --user is-active --quiet ugc-zero-credit-gpu.service || fail "Service GPU non actif."
  echo "Serveur privé démarré sur 127.0.0.1:8788. Aucun port public."
  exit 0
fi
[[ -f "$keyfile" && ! -L "$keyfile" ]] || fail "Jeton GPU absent."
token="$(tr -d '\r\n' < "$keyfile")"
[[ "$token" =~ ^[A-Za-z0-9_-]{24,}$ ]] || fail "Jeton GPU invalide."
export UGC_STUDIO_TOKEN_FILE="$keyfile"
export UGC_STUDIO_TOKEN="$token"
exec "$studio/bin/python" studio_web.py --host 127.0.0.1 --port "$port" \
  --data "$data" \
  --voice-model-fr "$voices/fr_FR-siwis-medium.onnx" --voice-license-ref-fr "$fr_license" \
  --voice-model-en "$voices/en_US-lessac-medium.onnx" --voice-license-ref-en "$en_license" \
  --musetalk-dir "$mt" --musetalk-python "$gpu/bin/python"
