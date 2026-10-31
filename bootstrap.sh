#!/usr/bin/env bash
# One-command bootstrap for an existing Linux server (never a cloud purchase).
# Download this file from your OWN GitHub repository, inspect it if desired,
# then run it once. It checks origin before modifying an existing checkout.
set -Eeuo pipefail
umask 077

PROJECT_URL="https://github.com/dbrckk/ugc-zero-credit.git"
PROJECT_DIR="${UGC_INSTALL_DIR:-$HOME/ugc-zero-credit}"

if ! command -v git >/dev/null 2>&1; then
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "ÉCHEC : installer Git sur cette distribution Linux." >&2
    exit 2
  fi
  if [[ "$EUID" -eq 0 ]]; then
    privilege=()
  elif command -v sudo >/dev/null 2>&1; then
    privilege=(sudo)
  else
    echo "ÉCHEC : Git absent ; sudo ou root est nécessaire." >&2
    exit 2
  fi
  "${privilege[@]}" apt-get update -qq
  "${privilege[@]}" apt-get install -y git ca-certificates
fi

if [[ -e "$PROJECT_DIR" || -L "$PROJECT_DIR" ]]; then
  if [[ -L "$PROJECT_DIR" ]] || [[ ! -d "$PROJECT_DIR/.git" ]]; then
    echo "ÉCHEC : dossier existant non Git ou lien symbolique. Refus de le remplacer." >&2
    exit 2
  fi
  origin="$(git -C "$PROJECT_DIR" remote get-url origin)"
  if [[ "$origin" != "$PROJECT_URL" && "$origin" != "git@github.com:dbrckk/ugc-zero-credit.git" ]]; then
    echo "ÉCHEC : ce dossier ne correspond pas au dépôt attendu : $origin" >&2
    exit 2
  fi
  if [[ "$(git -C "$PROJECT_DIR" branch --show-current)" != "main" ]]; then
    echo "ÉCHEC : checkout existant hors branche main, aucune modification effectuée." >&2
    exit 2
  fi
  if [[ -n "$(git -C "$PROJECT_DIR" status --porcelain --untracked-files=no)" ]]; then
    echo "ÉCHEC : modifications locales présentes, refus de les écraser." >&2
    exit 2
  fi
  git -C "$PROJECT_DIR" pull --ff-only origin main
else
  git clone --depth 1 --branch main "$PROJECT_URL" "$PROJECT_DIR"
fi

if [[ "${1:-}" == "--prepare-only" ]]; then
  echo "Dépôt prêt : $PROJECT_DIR"
  exit 0
fi
cd "$PROJECT_DIR"
exec bash ./install_studio.sh
