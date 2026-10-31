# UGC Zero Credit

**Studio UGC TikTok, Reels et YouTube Shorts — V8.** Assemble et contrôle localement des vidéos d'influenceuses IA **déjà existantes**, en conservant leur voix native. Aucune API de génération payante, aucun jeton d'inférence consommé.

## Nouveau : studio web accessible depuis Android

La V8 ajoute une interface pour créer des projets, transférer des vidéos parlées, des photos de produit, une musique facultative et des sous-titres SRT, gérer le storyboard, effectuer des vérifications, prévisualiser et exporter une publicité verticale 9:16.

Démarrer sur un serveur Linux disposant de Python 3.10+ et de FFmpeg/FFprobe :

```bash
sudo apt install -y python3 ffmpeg
python3 studio_web.py --host 127.0.0.1 --port 8787 --data "$HOME/ugc-studio-data"
```

La console affiche un jeton de connexion privé. Depuis un téléphone Android avec Termux et SSH :

```bash
pkg install openssh
ssh -L 8787:127.0.0.1:8787 utilisateur@serveur
```

Ouvrir `http://127.0.0.1:8787` sur Android, renseigner le jeton, importer les médias, configurer l'ordre des clips, les droits, les inserts et les sous-titres puis cliquer sur **Exporter 1080 × 1920**.

**Sécurité :** accès loopback seulement, tunnel SSH nécessaire si le serveur est distant. **Ne pas exposer ce serveur directement à Internet.** Le rendu consomme CPU, espace disque et électricité, mais aucun crédit IA distant. Voir [PROCESS_V8.md](PROCESS_V8.md) pour toutes les instructions et limites.

## Moteur de montage et contrôle local

- Conserve ensemble l'image et l'audio natifs de chaque clip de présentatrice ; les inserts de produit ne coupent pas sa voix.
- Exporte du H.264/AAC vertical **1080 × 1920 à 30 FPS** ; prévisualisation basse résolution disponible.
- Anime localement les images produit (zooms, panoramiques, fondus) et atténue la musique sous la parole.
- Gère les sous-titres mot par mot **uniquement avec des horodatages fiables**, ou par phrases via un import SRT contrôlé (V7).
- Vérifie les déclarations de droits, les horodatages, le format, la présence audio, la synchronisation temporelle source→export, les images noires/figées, les crêtes sonores et, optionnellement, les mouvements de bouche.
- Prépare rapports, sous-titres SRT/ASS, captures et dossier de revue Android ; protège les fichiers originaux des écrasements.
- Refuse de qualifier comme publiable une simple démonstration synthétique.

**Limites :** ce logiciel **ne génère pas** une nouvelle influenceuse photoréaliste, ne synthétise pas une nouvelle voix, ne garantit pas le lip-sync phonétique, ne vérifie pas automatiquement la marque sur le flacon, ni les droits commerciaux, et ne publie pas sur TikTok. Il travaille avec des rushs d'influenceuse et des médias déjà autorisés.

## Essai sans service tiers

```bash
python3 make_synthetic_demo.py
python3 ugc.py doctor
python3 ugc.py check examples/synthetic_demo.json
python3 ugc.py render examples/synthetic_demo.json --output demo_1080x1920.mp4
python3 ugc.py audit demo_1080x1920.mp4 --full-decode
```

L'exemple produit une vidéo de démonstration **non publiable** ; il ne comporte pas de vraie influenceuse.

## Vérifications fonctionnelles

```bash
python3 functional_checks_v3.py
python3 functional_checks_v4.py
python3 functional_checks_v5.py
python3 functional_checks_v6.py
python3 functional_checks_v7.py
python3 functional_checks_v8.py
```

Test navigateur V8 facultatif (Playwright, Chromium installé séparément) : `python3 browser_smoke_v8.py`. Dans notre environnement de contrôle géré, Chromium interdit les navigations réseau : le test injecte les pages et fait passer les appels HTTP au vrai serveur via une passerelle Python ; les contrôles JavaScript et les API sont exercés, mais pas la lecture média réseau native de Chromium. Le test HTTP V8 couvre séparément les URL de lecture signées et les réponses `Range`.

Documentation détaillée : [PROCESS_V6.md](PROCESS_V6.md), [PROCESS_V7.md](PROCESS_V7.md), [PROCESS_V8.md](PROCESS_V8.md).

## Gratuit par défaut

Aucune clé, aucun SaaS de rendu, aucun téléchargement automatique de modèle. OpenCV/NumPy et faster-whisper sont facultatifs ; une installation de dépendances ou un modèle vocal peut nécessiter de la bande passante et du matériel adéquat. Le pipeline n'utilise pas les générateurs Higgsfield, Picsart, ElevenLabs ou d'autres API payantes.

Projet indépendant de [monteur-video](https://github.com/dbrckk/monteur-video). Aucun exemple comportant une influenceuse réelle ou des médias de produit sans droits n'est publié dans ce dépôt.
