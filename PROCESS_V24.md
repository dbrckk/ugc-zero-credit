# V24 / P0 — GPU MuseTalk NVIDIA : déploiement reproductible

## État réel

Les contrôles CPU V23 sont validés. Aucun serveur personnel avec GPU CUDA n'est actuellement connecté pour cette tâche et aucun vrai rendu GPU n'a été produit. La V24 prépare une installation exécutable sur un **hôte NVIDIA existant**. Elle ne touche pas au Docker CPU, à ses volumes de projets ou à son port.

## Pré-requis sur le serveur

- Debian/Ubuntu Linux x86_64 avec GPU NVIDIA et pilotes opérationnels (nvidia-smi -L), 4 Gio de VRAM au minimum, idéalement 8 Gio ou plus.
- 20 Gio de disque disponibles ; Internet pendant l'installation seulement ; sudo pour installer les dépendances système.
- Le bootstrap ne provisionne pas de serveur et ne modifie pas les pilotes NVIDIA.
- Les sources officielles du modèle peuvent appliquer leurs propres règles et limites de téléchargement.

## Installer sur un GPU NVIDIA existant

Depuis le clone du dépôt dbrckk/ugc-zero-credit :

~~~bash
git checkout main
git pull --ff-only origin main
bash gpu_host.sh --install
bash gpu_host.sh --doctor
bash gpu_host.sh --enable-service
~~~

Le script crée deux environnements distincts : Python 3.10 avec PyTorch CUDA 11.8 et MuseTalk 1.5 officiel figé au commit 0a89dec45a0192b824e3cf4daf96c239440c5ed8, et Python 3.11 avec Piper CPU FR/EN. Les poids officiels sont récupérés via gpu_fetch_weights.py sans miroir Hugging Face non vérifié. Google Drive héberge un modèle FaceParsing ; si le téléchargement est limité, le script échoue sans annoncer de succès. L'exécution normale ne télécharge pas de modèles.

Le diagnostic charge les **vrais modules MuseTalk** et vérifie CUDA, les poids locaux et la VRAM libre ; aucune simulation GPU.

Le service systemd utilisateur écoute uniquement sur 127.0.0.1:8788. En l'absence de systemd utilisateur, la commande alternative est :

~~~bash
bash gpu_host.sh --run
~~~

Si les services utilisateur s'arrêtent après déconnexion, leur persistance peut nécessiter l'action administrateur sudo loginctl enable-linger suivie du nom d'utilisateur. Le service CPU Docker d'origine écoute toujours séparément sur 127.0.0.1:8787 et conserve ses projets. Aucune migration de données n'est réalisée automatiquement.

## Android

Depuis Termux sur Android, ouvrir un tunnel SSH :

~~~bash
pkg install openssh
ssh -L 8788:127.0.0.1:8788 UTILISATEUR@SERVEUR
~~~

Naviguer vers http://127.0.0.1:8788. Le jeton privé du studio GPU est consultable sur le serveur :

~~~bash
cat ~/.ugc-gpu-studio-token
~~~

Ne jamais publier ce jeton dans une issue ou dans des logs. Le service GPU ne l'imprime plus dans journald.

## Produire et vérifier une vraie vidéo MuseTalk

Utiliser un vrai clip vertical autorisé, un WAV Piper local accompagné de son manifeste de provenance .voice.json, et une référence écrite des droits du clip.

~~~bash
bash gpu_acceptance.sh \
  "$HOME/ugc-private/presenter_clip.mp4" \
  "$HOME/ugc-private/narration_fr.wav" \
  "REFERENCE_VERIFIABLE_AUTORISATION_CLIP"
~~~

Le script vérifie le diagnostic NVIDIA, la licence vocale inscrite dans le manifeste, puis lance MuseTalk pour de vrai. Il vérifie l'intégrité du MP4 et du rapport de rendu.

Les fichiers sont créés dans le répertoire privé ~/ugc-gpu-reviews, jamais publiés automatiquement. Les critères techniques (son présent, durée et décodage) ne prouvent pas à eux seuls la qualité de la synchronisation labiale : inspecter les lèvres, la voix, les gestes, la ressemblance et le produit.

## Limitations

- Les dépendances MuseTalk officielles Python 3.10, MMLab et CUDA peuvent ne pas s'installer sur toutes les distributions NVIDIA. Le script échoue explicitement au lieu d'annoncer un déploiement fictif.
- FaceParsing est hébergé sur Google Drive par le projet officiel et peut être temporairement inaccessible.
- Les conditions de licence MuseTalk, des modèles tiers, des voix et des médias doivent être vérifiées pour toute utilisation commerciale.
- Sans matériel NVIDIA accessible, la V24 peut être préparée et validée en CI CPU mais **le P0 ne peut être déclaré finalisé**. La preuve attendue est un vrai MP4 généré sur GPU et revu visuellement.

## Contrôles

GitHub Actions lance les vérifications syntaxiques des scripts, le contrôle du refus sur un hôte CPU et les tests existants avec vrais médias Piper/FFmpeg/Docker. Aucun poids GPU n'est téléchargé ou exécuté sur les runners CPU.
