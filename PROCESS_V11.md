# V11 — voix française réelle sur CPU et pont MuseTalk GPU

Cette version introduit une **vraie synthèse vocale locale avec Piper** et un point d'entrée pour **MuseTalk 1.5**. Elle ne télécharge aucun modèle pendant une génération ; elle n'appelle aucune API payante.

## Architecture et capacités

1. **Voix (CPU, testable partout)** : `offline_presenter.py voice` charge un modèle Piper ONNX **déjà installé** et produit un WAV PCM ainsi qu'un manifeste d'origine (SHA-256, licence déclarée, durée).
2. **Portrait parlant (GPU CUDA seulement)** : `offline_presenter.py presenter` produit le WAV, transmet un portrait local autorisé à MuseTalk 1.5 et vérifie le MP4 final (audio+vidéo, décodage et durée). Toutes les entrées sont confinées à un espace temporaire aux noms sûrs.
3. **Montage** : le MP4 résultat peut être importé dans le studio Android et utilisé comme `talking_clip` à audio/vidéo natifs. Les étapes V10 (sous-titres, cartes produit, QA) restent inchangées.

**Important :** l'image statique d'origine doit être déjà créée, possédée ou licenciée. MuseTalk anime la bouche ; il ne génère pas une nouvelle personne photoréaliste, ne garantit pas le réalisme général, ne teste pas les correspondances phonème/lèvres et ne dispense pas d'une revue humaine. Aucun rendu GPU MuseTalk n'est revendiqué si le matériel n'est pas disponible.

## Installation minimale du moteur vocal

```bash
python3 -m venv .venv-tts
. .venv-tts/bin/activate
python -m pip install piper-tts
python -m piper.download_voices fr_FR-siwis-medium --data-dir "$HOME/ugc-voices"
python offline_presenter.py doctor --voice-model "$HOME/ugc-voices/fr_FR-siwis-medium.onnx"
```

La voix `fr_FR-siwis-medium` (~63 Mo) utilise le jeu de données indiqué **CC-BY 4.0** dans sa fiche : conserver les mentions nécessaires. Les **licences de chaque modèle vocal** doivent être lues et acceptées pour le cas d'utilisation commercial précis. Le programme ne déduit pas une autorisation juridique d'un modèle qui se charge.

Sources :
- Piper Python/CLI (licence du logiciel et commandes) : https://github.com/OHF-Voice/piper1-gpl
- Voix française et modèle : https://huggingface.co/rhasspy/piper-voices/tree/main/fr/fr_FR/siwis/medium
- Fiche de voix : https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/siwis/medium/MODEL_CARD

## Générer la narration en français

```bash
python offline_presenter.py voice \
  --voice-model "$HOME/ugc-voices/fr_FR-siwis-medium.onnx" \
  --text "Découvrez une façon plus simple de présenter votre produit." \
  --voice-license-ref "https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/siwis/medium/MODEL_CARD" \
  --confirm-voice-rights --output narration_fr.wav
```

Le fichier `narration_fr.voice.json` est produit en plus du WAV. Le pipeline ne peut pas prétendre avoir réalisé une synchronisation des lèvres à cette étape. Le WAV peut être écouté et corrigé sans vidéo.

## Activer MuseTalk 1.5 (serveur Linux avec GPU NVIDIA)

MuseTalk dépend de PyTorch CUDA et de plusieurs modèles externes, parfois lourds. Installer le dépôt officiel ainsi que tous ses poids selon son README. Ne pas utiliser les images de démonstration tierces sans droits commerciaux.

- Code et conditions : https://github.com/TMElyralab/MuseTalk
- Poids et instructions : https://huggingface.co/TMElyralab/MuseTalk

```bash
# Dépendances et poids installés préalablement dans $HOME/MuseTalk
python offline_presenter.py doctor \
  --voice-model "$HOME/ugc-voices/fr_FR-siwis-medium.onnx" \
  --musetalk-dir "$HOME/MuseTalk" --musetalk-python "$HOME/musetalk-venv/bin/python"

python offline_presenter.py presenter \
  --voice-model "$HOME/ugc-voices/fr_FR-siwis-medium.onnx" \
  --voice-license-ref "https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/siwis/medium/MODEL_CARD" \
  --confirm-voice-rights \
  --image ./portrait_autorise.png \
  --image-rights-ref "Licence ou origine documentée du portrait" \
  --confirm-image-rights \
  --musetalk-dir "$HOME/MuseTalk" --musetalk-python "$HOME/musetalk-venv/bin/python" \
  --text "Bonjour, voici notre présentation." \
  --output presenter_fr.mp4
```

Attention : MuseTalk utilise des chemins dans certaines commandes shell upstream. Ce connecteur refuse les chemins du dépôt contenant des espaces, des caractères spéciaux ou des métacaractères et copie les fichiers d'entrée dans un dossier temporaire sûr. Il refuse l'absence de GPU ou de poids sans fabriquer de faux MP4.

Le produit final nécessite encore des contrôles humains : exactitude du script, accent et voix, naturalité, lèvres et visage, identité du produit, mentions publicité / influenceuse IA, autorisations de diffusion.

## Validation

```bash
python3 functional_checks_v11.py
```

L'exécution CI de la branche V11 peut installer Piper et télécharger **uniquement une voix française de test**, sans générateur commercial. Elle doit générer réellement un WAV et le vérifier avec FFprobe. **Le chemin MuseTalk est testé pour refuser les installations incomplètes ; aucun test vidéo MuseTalk réel n'est promis sans GPU CUDA et poids disponibles.**
