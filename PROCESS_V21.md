# V21 — générer une vidéo parlante via MuseTalk local depuis Android

## Réalisation

Le studio privé accepte un portrait JPEG/PNG autorisé et un **WAV Piper déjà généré dans le même projet**, français ou anglais. Le portrait et le WAV sont vérifiés avant le lancement. Une fois le GPU MuseTalk prêt, l'API privée lance une génération, conserve la narration originale sans la synthétiser une seconde fois, vérifie le décodage du MP4 et la concordance approximative des durées, puis enregistre la vidéo et son rapport dans la bibliothèque du projet.

Le formulaire Android exige :
- Le WAV Piper dont la provenance et le SHA-256 sont conservés.
- Un portrait autorisé avec référence écrite des droits.
- Une confirmation explicite des droits vocaux, du portrait et du consentement du sujet ou du caractère fictif autorisé.
- Un contrôle humain systématique du rendu avant toute publicité.

L'API `POST /api/projects/{id}/presenter` nécessite le jeton privé existant. Les contrôles de la file d'attente, de quotas, de droits des fichiers et des médias sont conservés. Un seul rendu gourmand est exécuté à la fois. Aucune API cloud de génération n'est utilisée.

## GPU : désactivé par défaut

Le conteneur CPU Docker du studio n'installe pas MuseTalk ni PyTorch CUDA. Le formulaire indique que la fonction est indisponible tant que le serveur ne dispose pas d'une installation MuseTalk 1.5 avec modèles, d'un GPU NVIDIA compatible et d'un interpréteur Python CUDA. Aucune génération GPU n'a été exécutée dans GitHub Actions.

Pour activer le pont sur un hôte Linux disposant **déjà** d'une installation MuseTalk fonctionnelle, lancer `studio_web.py` avec les paramètres habituels Piper et ces deux paramètres supplémentaires :

```bash
python3 studio_web.py --host 127.0.0.1 --port 8787 \
  --data "$HOME/ugc-studio-data" \
  --musetalk-dir "$HOME/MuseTalk" \
  --musetalk-python "$HOME/musetalk-venv/bin/python" \
  --voice-model-fr "$HOME/ugc-voices/fr_FR-siwis-medium.onnx" \
  --voice-license-ref-fr "https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/siwis/medium/MODEL_CARD" \
  --voice-model-en "$HOME/ugc-voices/en_US-lessac-medium.onnx" \
  --voice-license-ref-en "https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/lessac/medium/MODEL_CARD"
```

Les variables `UGC_MUSETALK_DIR` et `UGC_MUSETALK_PYTHON` sont également reconnues. Aucune exposition HTTP publique ; utiliser le tunnel SSH Android existant. Les droits commerciaux des modèles annexes, des voix et des images doivent être revus.

## Vérification

GitHub Actions teste un vrai parcours Piper → narration → Short FFmpeg et vérifie que l'API MuseTalk n'accepte aucune génération GPU sur un serveur CPU sans configuration, ne divulgue aucun média anonyme et expose les contrôles Android.

**Limites :** la seule concordance de durée ne prouve pas le lip-sync. MuseTalk peut produire des erreurs de visage ou de bouche et ne génère ni gestuelle naturelle, ni vidéo complète d'une influenceuse photoréaliste. L'essai final avec un GPU local, la vérification des lèvres et l'installation sur le serveur personnel restent nécessaires.
