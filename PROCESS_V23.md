# V23 — influenceuse en mouvement avec MuseTalk local, sans crédits IA

## Amélioration fonctionnelle

Le studio Android accepte désormais un **clip vertical réel de présentatrice** en MP4, MOV ou MKV, en plus du portrait JPEG/PNG déjà pris en charge.

MuseTalk 1.5 est officiellement compatible avec les sources vidéo. Le studio remplace l'audio du clip par le WAV Piper français ou anglais **déjà généré dans le projet**, sans resynthèse vocale ni appel API. Contrairement à un simple portrait statique, les mouvements filmés (tête, épaules, mains, arrière-plan) restent présents dans la source servant à la génération. MuseTalk anime principalement la région faciale. Les gestes ne sont **pas** inventés par ce moteur : ils viennent du clip source.

## Préparation locale automatique

Avant le calcul GPU, la source vidéo passe par le véritable FFmpeg :

- Format vertical ; résolution minimale de 256 pixels, durée 0,8–60 s et taille maximale de 120 Mo.
- Correction en **25 images/s**, compression H.264 et réduction éventuelle à 720 × 1280 pour limiter mémoire, disque et temps GPU.
- Conservation des mouvements d'origine ; la piste sonore de la vidéo d'origine est écartée.
- La durée préparée est limitée à 15 secondes : si la voix dure plus longtemps, MuseTalk peut répéter les images du clip. Les meilleurs résultats UGC sont attendus avec un clip et une narration courts et de durées proches, idéalement 10–15 secondes.
- Validation ffprobe des dimensions, images et fréquence d'images converties.

Le manifeste de rendu précise si la source est un portrait fixe ou une vidéo animée, le SHA-256 d'origine, la fréquence source et préparée, les dimensions et la durée utilisée. Les règles V22 (audio réellement audible, durée audio/vidéo, décodage intégral, revue humaine) restent obligatoires.

## Utilisation Android

Depuis ton studio privé (CPU + MuseTalk GPU correctement configuré), importer **la vidéo autorisée** dans les médias du projet puis générer ou sélectionner un WAV Piper FR/EN. Dans la section *Influenceuse animée*, sélectionner le clip, préciser l'autorisation du média et le consentement du sujet, vérifier le GPU, puis demander la vidéo parlante. Le MP4 apparaît dans la médiathèque après une exécution GPU réelle et reste à contrôler avant intégration à la publicité.

Les vidéos importées sont maintenant prévisualisables dans la médiathèque Android, même avant la génération MuseTalk.

## Commande de validation GPU privée et reproductible

La CLI peut désormais **réutiliser un WAV Piper signé** : pas besoin de régénérer la voix pour une vérification. Sur un serveur Linux avec MuseTalk 1.5, tous ses poids et une installation PyTorch CUDA réellement opérationnels :

```bash
python3 offline_presenter.py doctor \
  --musetalk-dir "$HOME/MuseTalk" \
  --musetalk-python "$HOME/musetalk-venv/bin/python"

python3 offline_presenter.py presenter \
  --source "$HOME/ugc-private/presenter_clip.mp4" \
  --existing-narration "$HOME/ugc-private/narration_fr.wav" \
  --voice-license-ref "REFERENCE_DE_LICENCE_VOCALE" \
  --image-rights-ref "REFERENCE_AUTORISATION_DU_CLIP" \
  --confirm-voice-rights --confirm-image-rights \
  --musetalk-dir "$HOME/MuseTalk" \
  --musetalk-python "$HOME/musetalk-venv/bin/python" \
  --output "$HOME/ugc-private/presenter_result.mp4"
```

Le WAV doit être un **vrai WAV Piper avec son manifeste `.voice.json` existant** et une référence de licence identique ; les valeurs ci-dessus sont des exemples de chemins et références à renseigner avec les ressources privées autorisées, pas des assets publiés ou fabriqués.

Sorties : `presenter_result.mp4` et `presenter_result.presenter.json` (provenance + contrôles techniques). Le fichier n'est **jamais** publié automatiquement.

## Validation réelle et limites

GitHub Actions valide sur CPU le maintien de mouvements entre deux images décodées d'un clip **réellement encodé avec FFmpeg**, sa conversion en 25 i/s et les rejets d'entrées incorrectes, en complément des contrôles Piper, HTTP et Docker. **Aucun runner GPU ou accès au serveur personnel n'est disponible dans cette validation.** Une exécution de MuseTalk sur une carte NVIDIA, le rendu visuel d'une influenceuse complète, la cohérence bouche/phonèmes, les droits commerciaux et les gestes naturels nécessitent encore une vérification manuelle d'un véritable clip autorisé.

Une installation CPU Docker via `install_studio.sh` seule ne fournit pas CUDA : pour une génération réelle, le studio doit être lancé sur un hôte GPU équipé des dépendances et des deux paramètres `--musetalk-dir` et `--musetalk-python`.
