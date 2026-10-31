#!/usr/bin/env bash
# Single-command, idempotent installer for an existing Debian/Ubuntu Linux server.
# It never opens a public port, edits SSH rules or installs a paid service.
set -Eeuo pipefail
umask 077
cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "ÉCHEC : ce programme installe le studio sur un serveur Linux." >&2
  exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "ÉCHEC : Docker absent ; distribution non Debian/Ubuntu." >&2
    echo "Installer Docker Engine et Docker Compose V2, puis relancer ce script." >&2
    exit 2
  fi
  echo "Docker absent : installation automatique avec le gestionnaire apt."
  if [[ "$EUID" -eq 0 ]]; then
    privilege=()
  elif command -v sudo >/dev/null 2>&1; then
    privilege=(sudo)
  else
    echo "ÉCHEC : installation Docker nécessite sudo ou root." >&2
    exit 2
  fi
  "${privilege[@]}" apt-get update -qq
  "${privilege[@]}" apt-get install -y docker.io
  if ! "${privilege[@]}" apt-get install -y docker-compose-v2; then
    "${privilege[@]}" apt-get install -y docker-compose-plugin
  fi
  if command -v systemctl >/dev/null 2>&1; then
    "${privilege[@]}" systemctl enable --now docker
  fi
fi

if docker info >/dev/null 2>&1; then
  docker_cli=(docker)
elif command -v sudo >/dev/null 2>&1 && sudo docker info >/dev/null 2>&1; then
  docker_cli=(sudo docker)
else
  echo "ÉCHEC : impossible de joindre le service Docker. Contrôler son démarrage ou l'accès sudo." >&2
  exit 2
fi
if ! "${docker_cli[@]}" compose version >/dev/null 2>&1; then
  echo "ÉCHEC : Docker Compose V2 est requis (docker compose version)." >&2
  exit 2
fi

if [[ -L .env ]]; then
  echo "ÉCHEC : .env est un lien symbolique, refus de l'utiliser." >&2
  exit 2
fi
if [[ ! -e .env ]]; then
  token="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
  printf 'UGC_STUDIO_TOKEN=%s\nUGC_STUDIO_PORT=8787\n' "$token" > .env
  chmod 600 .env
  echo "Jeton sécurisé créé dans .env (non versionné)."
fi
if ! grep -Eq '^UGC_STUDIO_TOKEN=[A-Za-z0-9_-]{24,}$' .env; then
  echo "ÉCHEC : jeton UGC_STUDIO_TOKEN invalide dans .env." >&2
  exit 2
fi

# Reject accidental public bindings in the local Compose source.
if ! grep -Fq '127.0.0.1:${UGC_STUDIO_PORT:-8787}:8787' docker-compose.yml; then
  echo "ÉCHEC : port Docker non limité à l'interface locale." >&2
  exit 2
fi

"${docker_cli[@]}" compose -f docker-compose.yml config --quiet
"${docker_cli[@]}" compose -f docker-compose.yml up --build -d --remove-orphans

echo ""
echo "Studio CPU bilingue (accès privé uniquement)."
echo "Depuis ce serveur : http://127.0.0.1:8787"
echo "Depuis Android, créer d'abord le tunnel SSH indiqué dans PROCESS_V13.md."
echo "Jeton pour l'écran de connexion :"
sed -n 's/^UGC_STUDIO_TOKEN=//p' .env
echo ""
echo "Le stockage est conservé dans le volume Docker ugc-zero-credit_studio_projects."
echo "État :"
"${docker_cli[@]}" compose -f docker-compose.yml ps
