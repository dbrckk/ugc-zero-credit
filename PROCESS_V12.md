# V12 — choix de langue Français / English (Piper entièrement local)

Le studio Android propose désormais **Français** ou **English**, sans jamais modifier le texte ni le traduire automatiquement. Chaque sélection correspond à un modèle Piper ONNX local distinct ; les voix absentes sont indiquées et désactivées.

## Installation (une seule fois, sur ton serveur Linux)

```bash
cd ugc-zero-credit
git pull origin main
python3 -m venv .venv-tts
. .venv-tts/bin/activate
python -m pip install piper-tts
python -m piper.download_voices fr_FR-siwis-medium en_US-lessac-medium --data-dir "$HOME/ugc-voices"
```

**Attention aux droits :** le modèle `fr_FR-siwis-medium` indique une source de données CC-BY 4.0 ; le modèle `en_US-lessac-medium` renvoie à la licence du corpus Blizzard 2013. Vérifier les conditions respectives avant tout usage commercial ; une fiche de modèle ne constitue pas une autorisation automatique pour tous les contenus.

Fiches officielles :
- Français : https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/siwis/medium/MODEL_CARD
- Anglais : https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/lessac/medium/MODEL_CARD

## Lancer le studio en mode bilingue

```bash
python3 studio_web.py --host 127.0.0.1 --port 8787 --data "$HOME/ugc-studio-data" \
  --voice-model-fr "$HOME/ugc-voices/fr_FR-siwis-medium.onnx" \
  --voice-license-ref-fr "https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/siwis/medium/MODEL_CARD" \
  --voice-model-en "$HOME/ugc-voices/en_US-lessac-medium.onnx" \
  --voice-license-ref-en "https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/lessac/medium/MODEL_CARD"
```

L'interface reste privée sur `127.0.0.1`. Depuis Android, utiliser un tunnel SSH comme dans `PROCESS_V8.md` ; ouvrir `http://127.0.0.1:8787`, saisir le jeton du serveur, créer/choisir un projet, puis sélectionner la langue dans **Voix IA locale** et cliquer sur **Générer la narration**.

Les fichiers deviennent `narration_fr_....wav` ou `narration_en_....wav`. Chaque fichier WAV est accompagné de son manifeste local `.voice.json` (licence déclarée, hash du modèle et hash du fichier). La langue et le code régional sont enregistrés dans les métadonnées de la bibliothèque.

## Comportement et sécurité

- Si une seule langue est installée, seul son choix est disponible.
- Un modèle français configuré dans l'option anglaise (ou inversement) fait échouer le démarrage.
- Une langue non installée est refusée : pas de bascule silencieuse, pas de voix erronée.
- Avec deux modèles, `language` est exigé dans l'API ; avec un seul, les anciennes requêtes V11 sans champ langue restent acceptées.
- Le serveur ne télécharge aucun modèle lors de la génération ; seule l'installation explicite téléchargera les fichiers ONNX.
- Aucun lip-sync MuseTalk réel n'a été validé sur GPU. Les WAV seuls ne deviennent pas automatiquement des clips parlants.
- Le choix de langue ne traduit pas les paroles ; l'utilisateur saisit son script dans la langue choisie.
- Les médias sont privés et nécessitent un jeton, ou une URL de lecture signée limitée dans le temps.

## Tests d'acceptation

```bash
UGC_TEST_PIPER_MODEL="$HOME/ugc-voices/fr_FR-siwis-medium.onnx" \
UGC_TEST_PIPER_MODEL_EN="$HOME/ugc-voices/en_US-lessac-medium.onnx" \
python3 functional_checks_v12.py
```

Le workflow CI V12 installe Piper, télécharge explicitement ces deux modèles une seule fois pour la validation, teste de vrais WAV français/anglais et la sélection HTTP depuis l'interface ; il vérifie aussi les régressions V8 à V11. Aucune API de synthèse distante ni crédits commerciaux ne sont utilisés.
