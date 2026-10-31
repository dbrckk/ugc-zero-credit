# UGC Zero Credit

**Studio UGC TikTok, Reels et YouTube Shorts — V18.** Assemble et contrôle localement des vidéos d'influenceuses IA **déjà existantes**, en conservant leur voix native. Aucune API de génération payante, aucun jeton d'inférence consommé.

## Studio Android, rendu V10 et génération vocale locale V11

Le studio web V8 permet de créer des projets, importer des vidéos parlées, images de produit, musiques et sous-titres SRT, gérer le storyboard, prévisualiser et exporter des vidéos 9:16. La **V9** sécurise les rendus sur les petits serveurs CPU :

- Une seule vidéo est encodée à la fois, avec au plus une deuxième en attente.
- Les demandes supplémentaires sont refusées (HTTP 429), ainsi que les rendus doublons sur un même projet (HTTP 409).
- La configuration d'un projet ne peut pas être modifiée pendant l'export.
- Un snapshot de configuration est revérifié juste avant son admission, afin de refuser un projet modifié pendant la vérification.
- Tests de concurrence avec de vrais rendus FFmpeg, sans API IA payante. Voir [PROCESS_V9.md](PROCESS_V9.md).

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

## V15 — lisibilité des mentions sur les Shorts

La V15 réduit la taille de la mention obligatoire sur les aperçus 360 × 640 pour éviter son débordement horizontal ; le rendu 1080 × 1920 utilise aussi une taille plus sûre. Le rapport d'export indique `safe_disclosure_v15`. Les tests FFmpeg V14 sont réexécutés sur la branche avant fusion.

## V16 — composition éditoriale des Shorts

Titres de 1–4 lignes adaptés aux écrans mobiles, fond flouté sobre, cadre discret autour du produit, repère de séquence et variations légères de zoom/panoramique. La photo n'est pas recadrée et les déclarations publicitaires restent affichées. Les tests construisent de vrais MP4 et sauvegardent des captures PNG de contrôle ; voir [PROCESS_V16.md](PROCESS_V16.md).

## V18 — animation du titre et progression réelle

Le Short produit (FR/EN) dispose désormais d'un **titre animé à l'apparition** (glissement et fondu de 500 ms) et d'un **indicateur de progression temporel de 20 segments**, encodés image par image par FFmpeg. Ils ne sont pas un effet simulé dans l'interface : ils figurent dans le MP4 9:16, en aperçu comme en Full-HD. Une vérification fonctionnelle lit les pixels de deux instants du vrai MP4 et vérifie la progression. Les mentions IA, les photos d'origine, le contrôle des droits et le son restent inchangés.

## V14 — transformer une narration FR/EN et des photos en vrai Short 9:16

Depuis Android, générer un WAV Piper (FR ou EN), importer 1–6 photos autorisées, puis utiliser **Short narré — photos + voix FR / EN**. Le serveur encode réellement un MP4 H.264/AAC avec photos contenues sur fond flou, zooms progressifs, fondus, titre et mention « PUBLICITÉ · CONTENU GÉNÉRÉ AVEC IA ». L'aperçu et l'export 1080 × 1920 sont accessibles dans la bibliothèque de rendus, sans API payante. Les sorties sont décodées intégralement avant publication dans l'interface. Ce mode **n'invente ni visage, ni lip-sync, ni sous-titres horodatés** et nécessite une revue humaine.

Voir [PROCESS_V14.md](PROCESS_V14.md). Ce mode est distinct des anciens montages de vidéos de présentatrice : les anciens projets et exports restent compatibles.

## V13 — installation autonome sur serveur privé (une commande)

Le [guide V13](PROCESS_V13.md) fournit une installation reproductible et entièrement locale : Docker, FFmpeg, Piper CPU, voix **française et anglaise**, stockage privé persistant, jeton et démarrage automatique.

```bash
curl -fsSLo /tmp/ugc-bootstrap.sh https://raw.githubusercontent.com/dbrckk/ugc-zero-credit/main/bootstrap.sh && bash /tmp/ugc-bootstrap.sh
```

Si le serveur utilise déjà Docker, aucune installation système manuelle n'est nécessaire. Sinon le script tente l'installation avec apt sur Debian/Ubuntu, sous sudo si nécessaire. Pour Android, conserver le tunnel SSH : **le studio ne devient jamais un service HTTP public**.

**Prudence commerciale :** les licences des données ayant servi à entraîner les voix sont différentes, notamment le corpus Blizzard 2013 de Lessac (et l'historique de Siwis). Elles doivent être vérifiées avant des publicités monétisées.

## V12 — choix de la voix française ou anglaise (Piper CPU)

Le studio peut désormais générer un WAV **en français ou en anglais** avec Piper ONNX local. L'écran Android comporte un sélecteur Français / English ; seules les langues réellement installées sont activées. Le serveur vérifie que chaque modèle correspond à sa langue avant son démarrage et refuse toute demande dans une langue absente. Aucune traduction automatique, aucun téléchargement de poids pendant la génération et aucune API payante.

Activer les deux voix au démarrage avec `--voice-model-fr`, `--voice-license-ref-fr`, `--voice-model-en` et `--voice-license-ref-en`. L'ancienne configuration V11 (une seule voix) reste reconnue. Voir [PROCESS_V12.md](PROCESS_V12.md).

La commande `offline_presenter.py voice` fonctionne aussi sans interface. `offline_presenter.py presenter` fournit un pont vers **MuseTalk 1.5 CUDA** pour animer localement un portrait autorisé, sous réserve de poids et d'un GPU. La voie GPU n'est pas validée sur notre CI CPU ; elle refuse l'exécution si MuseTalk ou CUDA manque. **Ce logiciel ne crée pas l'apparence d'une nouvelle influenceuse photoréaliste.** Voir [PROCESS_V11.md](PROCESS_V11.md).

## Moteur de montage et contrôle local

- Conserve ensemble l'image et l'audio natifs de chaque clip de présentatrice ; les inserts de produit ne coupent pas sa voix.
- Exporte du H.264/AAC vertical **1080 × 1920 à 30 FPS** ; prévisualisation basse résolution disponible.
- Anime localement les images produit (zooms, panoramiques, fondus) et atténue la musique sous la parole.
- **V10 :** carte produit avec bordure et ombre, en incrustation à gauche ou à droite pour ne pas masquer tout le plan de la présentatrice. Le visage reste à vérifier manuellement.
- Gère les sous-titres mot par mot **uniquement avec des horodatages fiables**, ou par phrases via un import SRT contrôlé (V7).
- Vérifie les déclarations de droits, les horodatages, le format, la présence audio, la synchronisation temporelle source→export, les images noires/figées, les crêtes sonores et, optionnellement, les mouvements de bouche.
- Prépare rapports, sous-titres SRT/ASS, captures et dossier de revue Android ; protège les fichiers originaux des écrasements.
- Refuse de qualifier comme publiable une simple démonstration synthétique.

**Limites :** ce logiciel **ne génère pas** une nouvelle influenceuse photoréaliste, ne garantit pas une voix humaine indiscernable, ne garantit pas le lip-sync phonétique, ne vérifie pas automatiquement la marque sur le flacon, ni les droits commerciaux, et ne publie pas sur TikTok. Il travaille avec des rushs d'influenceuse et des médias déjà autorisés.

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
python3 functional_checks_v9.py
python3 functional_checks_v10.py
python3 functional_checks_v11.py
python3 functional_checks_v11_web.py   # modèle Piper requis
python3 functional_checks_v12.py        # deux modèles locaux FR/EN requis
python3 functional_checks_v14.py        # voix Piper + FFmpeg réels
```

Test navigateur V8 facultatif (Playwright, Chromium installé séparément) : `python3 browser_smoke_v8.py`. Dans notre environnement de contrôle géré, Chromium interdit les navigations réseau : le test injecte les pages et fait passer les appels HTTP au vrai serveur via une passerelle Python ; les contrôles JavaScript et les API sont exercés, mais pas la lecture média réseau native de Chromium. Le test HTTP V8 couvre séparément les URL de lecture signées et les réponses `Range`.

Documentation détaillée : [PROCESS_V6.md](PROCESS_V6.md), [PROCESS_V7.md](PROCESS_V7.md), [PROCESS_V8.md](PROCESS_V8.md) [PROCESS_V9.md](PROCESS_V9.md), [PROCESS_V10.md](PROCESS_V10.md), [PROCESS_V11.md](PROCESS_V11.md) [PROCESS_V12.md](PROCESS_V12.md) et [PROCESS_V13.md](PROCESS_V13.md).

## Gratuit par défaut

Aucune clé, aucun SaaS de rendu, aucun téléchargement automatique de modèle. OpenCV/NumPy et faster-whisper sont facultatifs ; une installation de dépendances ou un modèle vocal peut nécessiter de la bande passante et du matériel adéquat. Le pipeline n'utilise pas les générateurs Higgsfield, Picsart, ElevenLabs ou d'autres API payantes.

Projet indépendant de [monteur-video](https://github.com/dbrckk/monteur-video). Aucun exemple comportant une influenceuse réelle ou des médias de produit sans droits n'est publié dans ce dépôt.
