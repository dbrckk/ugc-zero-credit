# V13 — installation automatique privée CPU (FR + EN)

Cette version installe le studio et ses dépendances sans reconfigurer Python manuellement :
**Docker, Piper 1.8.0, FFmpeg, les deux modèles ONNX, un volume de projets persistant et un jeton sécurisé**.

## Une seule commande, même sans clone préalable

Sur un serveur Linux Debian/Ubuntu ayant accès à Internet, lancer **une seule ligne** depuis son terminal SSH :

```bash
curl -fsSLo /tmp/ugc-bootstrap.sh https://raw.githubusercontent.com/dbrckk/ugc-zero-credit/main/bootstrap.sh && bash /tmp/ugc-bootstrap.sh
```

La commande récupère uniquement le script de **ton dépôt** GitHub, vérifie l'origine d'un éventuel clone existant puis lance l'installation automatiquement. Elle ne fait aucune modification à distance si le dossier Git existant contient des changements locaux ou se trouve sur une autre branche.

## Une seule commande une fois le dépôt présent sur le serveur

Sur un serveur **Linux Debian ou Ubuntu** (Docker déjà présent ou accès sudo pour l'installer) :

```bash
cd ugc-zero-credit
git pull origin main
bash install_studio.sh
```

Le script :
1. Installe Docker et Compose V2 via apt si nécessaire (demande éventuellement le mot de passe sudo).
2. Crée `.env` avec un jeton aléatoire cryptographiquement fort et des permissions `600`, sans jamais remplacer un ancien jeton.
3. Construit le conteneur et télécharge les **deux voix au build uniquement**, dans des couches Docker réutilisables. Le modèle anglais utilise `en_US-lessac-medium`, le français `fr_FR-siwis-medium`.
4. Lance le studio sur le **port local** `127.0.0.1:8787` uniquement (jamais `0.0.0.0` sur l'hôte).
5. Conserve les fichiers dans le volume Docker nommé `ugc-zero-credit_studio_projects`, même après arrêt et mise à jour du conteneur.
6. Affiche le jeton privé et l'état du service.

Il ne crée ni serveur cloud facturé, ni tunnel réseau public, ni service d'inférence payant.

**Pré-requis :** Linux x86_64, au moins 3–4 Go libres pour le build, 2 Go RAM recommandés, une connexion Internet uniquement pour la première installation. Le CPU peut rendre des vidéos plus lentement qu'un GPU. Le serveur doit être une machine de confiance : Docker est un système privilégié.

## Utilisation depuis Android

Depuis **Termux** sur Android :

```bash
pkg install openssh
ssh -N -L 8787:127.0.0.1:8787 utilisateur@ip-du-serveur
```

Ouvrir `http://127.0.0.1:8787` dans un navigateur Android, coller le jeton affiché par l'installateur (ou présent dans `.env` du serveur), sélectionner Français ou English et générer un WAV.

**Ne jamais ouvrir publiquement le port 8787.** Un tunnel SSH ou un VPN privé est nécessaire pour accéder au studio distant. L'application n'est pas conçue pour être accessible directement sur Internet.

## Mises à jour et sauvegarde

```bash
cd ugc-zero-credit
git pull origin main
bash install_studio.sh
```

Le jeton et les médias sont conservés. Ne pas lancer `docker compose down -v` : cette commande **supprimerait les médias**.

Sauvegarde manuelle chiffrable du volume (à placer ensuite dans un stockage privé) :

```bash
docker run --rm -v ugc-zero-credit_studio_projects:/data:ro -v "$PWD":/backup \
  alpine tar -C /data -czf /backup/ugc-studio-backup.tar.gz .
```

Les WAV, MP4 et informations de licence sont privés : ne pas déposer la sauvegarde sur un dépôt public. Une sauvegarde réelle et régulière reste nécessaire.

## Sécurité et limites

- L'interface écoute toutes les interfaces **dans le conteneur uniquement**, afin que le port Docker redirige vers elle ; Docker publie ce port **sur l'adresse loopback de l'hôte uniquement**.
- Processus non-root UID 10001, filesystem en lecture seule sauf `/data`, répertoire temporaire en RAM, pas de capacités Linux, démarrage automatique et contrôle de santé authentifié.
- L'installation remplace l'exécution manuelle sur l'hôte, mais ne permet pas d'accéder à une machine dont les identifiants SSH n'ont jamais été fournis. Le dépôt GitHub Actions vérifie le même conteneur sans accès à ton serveur privé.
- Le WAV reste une voix synthétique ; aucune génération photoréaliste ni lip-sync GPU n'est prétendue.
- Le code Piper est GPL et les voix ont des licences **distinctes**. Lessac se fonde sur les données Blizzard 2013 dont les conditions commerciales sont discutées ; Siwis est affiné depuis Lessac. Vérifier les autorisations et mentions avant de commercialiser des publicités ; l'installateur n'accorde pas de licence.
- Render Free n'est pas un hébergement compatible sans autre stockage persistant : ses fichiers locaux disparaissent aux redémarrages.

## Tests exécutables

Le workflow `v13-turnkey-docker-validation.yml` utilise GitHub Actions pour :
- Construire réellement l'image (FFmpeg + Piper + les 2 modèles).
- Lancer un conteneur privé, puis générer une narration française et une narration anglaise via les vraies API authentifiées.
- Vérifier WAV, `Range`, autorisations, voix/langues et conservation des médias après redémarrage.

Aucune donnée utilisateur ou clé privée n'est requise pour ces tests synthétiques.
