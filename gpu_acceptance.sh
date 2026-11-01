#!/usr/bin/env bash
# Real GPU acceptance: user-authorized moving footage + signed Piper WAV.
set -Eeuo pipefail
umask 077
cd "$(dirname "$0")"
if (( $# != 3 )); then
  echo 'Utilisation : bash gpu_acceptance.sh /chemin/clip.mp4 /chemin/voix_piper.wav "REFERENCE_DROITS_DU_CLIP"' >&2
  exit 2
fi
source="$1"
voice="$2"
rights="$3"
[[ -f "$source" && ! -L "$source" ]] || { echo "Clip absent ou symbolique" >&2; exit 2; }
[[ -f "$voice" && ! -L "$voice" ]] || { echo "WAV absent ou symbolique" >&2; exit 2; }
(( $(printf %s "$rights" | wc -c) >= 8 )) || { echo "Référence d'autorisation trop courte" >&2; exit 2; }
bash gpu_host.sh --doctor
home="$HOME"
py="$home/ugc-studio-venv/bin/python"
licence="$("$py" - "$voice" <<'PY'
from pathlib import Path
from narrated_short import inspect_narration, sha256
import sys
source = Path(sys.argv[1])
meta = inspect_narration(source, sha256(source))
assert meta["duration"] <= 60, "Narration de plus de 60 secondes : choisir une version courte"
print(meta["voice_license_ref"])
PY
)"
review="$home/ugc-gpu-reviews"
[[ ! -L "$review" ]] || { echo "Dossier de revue symbolique" >&2; exit 2; }
mkdir -p "$review"
name="$("$py" -c 'import secrets;print(secrets.token_hex(8))')"
output="$review/presenter_$name.mp4"
"$py" offline_presenter.py presenter \
  --source "$source" \
  --existing-narration "$voice" \
  --voice-license-ref "$licence" \
  --image-rights-ref "$rights" \
  --confirm-voice-rights --confirm-image-rights \
  --musetalk-dir "$home/ugc-musetalk-v15" \
  --musetalk-python "$home/ugc-musetalk-venv/bin/python" \
  --output "$output"
"$py" - "$output" <<'PY'
from pathlib import Path
import json, sys
from offline_presenter import digest
video = Path(sys.argv[1])
report = json.loads(video.with_suffix(".presenter.json").read_text(encoding="utf-8"))
assert video.is_file() and video.stat().st_size > 1024
assert report["sha256"] == digest(video)
assert report["gpu_inference_executed"] is True and report["ffmpeg_full_decode"] is True
assert report["reused_existing_narration"] is True
assert report["publication_allowed_automatically"] is False
print("GPU_OUTPUT_VERIFIED", video)
print("AUDIT_REPORT", video.with_suffix(".presenter.json"))
print("REVIEW_REQUIRED: écouter voix, inspecter bouche, gestes, consentement et produit avant publication.")
PY
