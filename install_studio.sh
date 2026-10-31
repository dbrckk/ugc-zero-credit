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
  if ! command -v apt-get >/dev/null 2>&1 || [[ ! -f /etc/os-release ]]; then
    echo "ÉCHEC : distribution non Debian/Ubuntu ; installer Docker Engine + Compose V2." >&2
    exit 2
  fi
  # Official signed Docker apt repository is supported on current Debian/Ubuntu.
  # Don't remove or replace an existing Docker installation.
  . /etc/os-release
  if [[ "${ID:-}" != "debian" && "${ID:-}" != "ubuntu" ]]; then
    echo "ÉCHEC : installation système automatique réservée à Debian/Ubuntu." >&2
    exit 2
  fi
  distro="$ID"
  codename="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
  if [[ ! "$codename" =~ ^[a-z]+$ ]]; then
    echo "ÉCHEC : version de distribution inconnue." >&2
    exit 2
  fi
  if [[ "$EUID" -eq 0 ]]; then
    privilege=()
  elif command -v sudo >/dev/null 2>&1; then
    privilege=(sudo)
  else
    echo "ÉCHEC : installation de Docker nécessite sudo ou root." >&2
    exit 2
  fi
  echo "Installation via le dépôt apt officiel signé de Docker ($distro/$codename)."
  "${privilege[@]}" apt-get update -qq
  "${privilege[@]}" apt-get install -y ca-certificates curl
  "${privilege[@]}" install -m 0755 -d /etc/apt/keyrings
  "${privilege[@]}" curl -fsSL --retry 3 "https://download.docker.com/linux/$distro/gpg" -o /etc/apt/keyrings/docker.asc
  "${privilege[@]}" chmod a+r /etc/apt/keyrings/docker.asc
  arch="$(dpkg --print-architecture)"
  printf 'Types: deb\nURIs: https://download.docker.com/linux/%s\nSuites: %s\nComponents: stable\nArchitectures: %s\nSigned-By: /etc/apt/keyrings/docker.asc\n' "$distro" "$codename" "$arch" | "${privilege[@]}" tee /etc/apt/sources.list.d/docker.sources >/dev/null
  "${privilege[@]}" apt-get update -qq
  "${privilege[@]}" apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
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
  # An existing Docker Engine must never be replaced silently. Install only
  # the missing Compose plugin if apt can do so without removing packages.
  if command -v apt-get >/dev/null 2>&1; then
    if [[ "$EUID" -eq 0 ]]; then
      privilege=()
    elif command -v sudo >/dev/null 2>&1; then
      privilege=(sudo)
    else
      echo "ÉCHEC : sudo est nécessaire pour installer Docker Compose V2." >&2
      exit 2
    fi
    if ! "${privilege[@]}" apt-get install --no-remove -y docker-compose-v2; then
      "${privilege[@]}" apt-get install --no-remove -y docker-compose-plugin || true
    fi
  fi
  if ! "${docker_cli[@]}" compose version >/dev/null 2>&1; then
    echo "ÉCHEC : Docker Compose V2 absent ; voir https://docs.docker.com/compose/install/linux/" >&2
    exit 2
  fi
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
chmod 600 .env
if ! grep -Eq '^UGC_STUDIO_TOKEN=[A-Za-z0-9_-]{24,}  echo "ÉCHEC : jeton UGC_STUDIO_TOKEN invalide dans .env." >&2
  exit 2
fi

# Reject accidental public bindings in the local Compose source.
if ! grep -Fq '127.0.0.1:${UGC_STUDIO_PORT:-8787}:8787' docker-compose.yml; then
  echo "ÉCHEC : port Docker non limité à l'interface locale." >&2
  exit 2
fi

"${docker_cli[@]}" compose -f docker-compose.yml config --quiet
"${docker_cli[@]}" compose -f docker-compose.yml up --build -d --remove-orphans

# Ensure startup and authentication really work. Don't report success merely
# because Docker started a process.
healthy=0
for attempt in $(seq 1 40); do
  if "${docker_cli[@]}" compose -f docker-compose.yml exec -T studio python -c \
    "import os,urllib.request; q=urllib.request.Request('http://127.0.0.1:8787/api/health',headers={'Authorization':'Bearer '+os.environ['UGC_STUDIO_TOKEN']}); r=urllib.request.urlopen(q,timeout=5); assert r.status==200" >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 2
done
if [[ "$healthy" != "1" ]]; then
  echo "ÉCHEC : conteneur installé mais serveur HTTP non sain. Inspecter : docker compose logs --tail 60" >&2
  "${docker_cli[@]}" compose -f docker-compose.yml ps
  exit 3
fi

echo ""
echo "Studio CPU bilingue (accès privé uniquement)."
port="$(sed -n 's/^UGC_STUDIO_PORT=//p' .env | head -1)"
echo "Depuis ce serveur : http://127.0.0.1:${port:-8787}"
echo "Depuis Android, créer d'abord le tunnel SSH indiqué dans PROCESS_V13.md."
echo "Jeton pour l'écran de connexion :"
sed -n 's/^UGC_STUDIO_TOKEN=//p' .env
echo ""
echo "Le stockage est conservé dans le volume Docker ugc-zero-credit_studio_projects."
echo "État :"
"${docker_cli[@]}" compose -f docker-compose.yml ps
 .env; then
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

# Ensure startup and authentication really work. Don't report success merely
# because Docker started a process.
healthy=0
for attempt in $(seq 1 40); do
  if "${docker_cli[@]}" compose -f docker-compose.yml exec -T studio python -c \
    "import os,urllib.request; q=urllib.request.Request('http://127.0.0.1:8787/api/health',headers={'Authorization':'Bearer '+os.environ['UGC_STUDIO_TOKEN']}); r=urllib.request.urlopen(q,timeout=5); assert r.status==200" >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 2
done
if [[ "$healthy" != "1" ]]; then
  echo "ÉCHEC : conteneur installé mais serveur HTTP non sain. Inspecter : docker compose logs --tail 60" >&2
  "${docker_cli[@]}" compose -f docker-compose.yml ps
  exit 3
fi

echo ""
echo "Studio CPU bilingue (accès privé uniquement)."
port="$(sed -n 's/^UGC_STUDIO_PORT=//p' .env | head -1)"
echo "Depuis ce serveur : http://127.0.0.1:${port:-8787}"
echo "Depuis Android, créer d'abord le tunnel SSH indiqué dans PROCESS_V13.md."
echo "Jeton pour l'écran de connexion :"
sed -n 's/^UGC_STUDIO_TOKEN=//p' .env
echo ""
echo "Le stockage est conservé dans le volume Docker ugc-zero-credit_studio_projects."
echo "État :"
"${docker_cli[@]}" compose -f docker-compose.yml ps
 .env; then
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

# Ensure startup and authentication really work. Don't report success merely
# because Docker started a process.
healthy=0
for attempt in $(seq 1 40); do
  if "${docker_cli[@]}" compose -f docker-compose.yml exec -T studio python -c \
    "import os,urllib.request; q=urllib.request.Request('http://127.0.0.1:8787/api/health',headers={'Authorization':'Bearer '+os.environ['UGC_STUDIO_TOKEN']}); r=urllib.request.urlopen(q,timeout=5); assert r.status==200" >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 2
done
if [[ "$healthy" != "1" ]]; then
  echo "ÉCHEC : conteneur installé mais serveur HTTP non sain. Inspecter : docker compose logs --tail 60" >&2
  "${docker_cli[@]}" compose -f docker-compose.yml ps
  exit 3
fi

echo ""
echo "Studio CPU bilingue (accès privé uniquement)."
port="$(sed -n 's/^UGC_STUDIO_PORT=//p' .env | head -1)"
echo "Depuis ce serveur : http://127.0.0.1:${port:-8787}"
echo "Depuis Android, créer d'abord le tunnel SSH indiqué dans PROCESS_V13.md."
echo "Jeton pour l'écran de connexion :"
sed -n 's/^UGC_STUDIO_TOKEN=//p' .env
echo ""
echo "Le stockage est conservé dans le volume Docker ugc-zero-credit_studio_projects."
echo "État :"
"${docker_cli[@]}" compose -f docker-compose.yml ps
 .env; then
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

# Ensure startup and authentication really work. Don't report success merely
# because Docker started a process.
healthy=0
for attempt in $(seq 1 40); do
  if "${docker_cli[@]}" compose -f docker-compose.yml exec -T studio python -c \
    "import os,urllib.request; q=urllib.request.Request('http://127.0.0.1:8787/api/health',headers={'Authorization':'Bearer '+os.environ['UGC_STUDIO_TOKEN']}); r=urllib.request.urlopen(q,timeout=5); assert r.status==200" >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 2
done
if [[ "$healthy" != "1" ]]; then
  echo "ÉCHEC : conteneur installé mais serveur HTTP non sain. Inspecter : docker compose logs --tail 60" >&2
  "${docker_cli[@]}" compose -f docker-compose.yml ps
  exit 3
fi

echo ""
echo "Studio CPU bilingue (accès privé uniquement)."
port="$(sed -n 's/^UGC_STUDIO_PORT=//p' .env | head -1)"
echo "Depuis ce serveur : http://127.0.0.1:${port:-8787}"
echo "Depuis Android, créer d'abord le tunnel SSH indiqué dans PROCESS_V13.md."
echo "Jeton pour l'écran de connexion :"
sed -n 's/^UGC_STUDIO_TOKEN=//p' .env
echo ""
echo "Le stockage est conservé dans le volume Docker ugc-zero-credit_studio_projects."
echo "État :"
"${docker_cli[@]}" compose -f docker-compose.yml ps
