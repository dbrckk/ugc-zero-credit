# V14 — Short narré FR / EN : photos produit + vraie vidéo 9:16

Le studio Android peut générer un MP4 avec **une narration française ou anglaise Piper**, 1 à 6 photos du produit, des transitions, un fond flouté et un titre. Le texte « PUBLICITÉ · CONTENU GÉNÉRÉ AVEC IA » reste visible. Le rendu est réellement encodé H.264/AAC par FFmpeg, 360 × 640 en aperçu ou 1080 × 1920 en version finale.

Il n'y a **aucun visage artificiel, aucun lip-sync fictif, aucune promesse de sous-titres mot par mot** : c'est un format de vidéo produit avec voix off. Le montage de vidéos parlées natives V10 reste disponible.

## Installation automatique

V13 installait déjà Docker, FFmpeg et les deux voix sur le serveur. V14 installe aussi la police DejaVu nécessaire au rendu des mentions.

Sur Debian/Ubuntu avec sudo, l'installation/mise à jour reste limitée à une commande :

```bash
curl -fsSLo /tmp/ugc-bootstrap.sh https://raw.githubusercontent.com/dbrckk/ugc-zero-credit/main/bootstrap.sh && bash /tmp/ugc-bootstrap.sh
```

Pour afficher le studio sur Android, passer par un tunnel SSH comme indiqué dans [PROCESS_V13.md](PROCESS_V13.md). Ne jamais exposer publiquement son port HTTP.

## Parcours Android

1. Ouvrir ou créer un projet dans le studio privé.
2. Générer une voix locale en français ou en anglais.
3. Importer 1–6 photos autorisées du produit.
4. Dans « Short narré — photos + voix FR / EN », choisir le WAV Piper, les photos et un titre exact, puis confirmer les droits et les allégations.
5. Générer **Aperçu rapide**, puis **Créer le Short 1080 × 1920**.
6. Visionner, écouter et vérifier le résultat et les mentions avant diffusion.

Les MP4 `narrated_preview.mp4` et `narrated.mp4` sont accessibles avec leurs rapports `*.report.json` depuis le projet.

## Sécurité et limites

- Les images et la voix proviennent du même projet privé. Le WAV doit être un vrai WAV Piper avec manifeste et empreinte SHA-256 inchangée.
- Durée de voix : 1–60 secondes ; images : 1–6, au moins une seconde par photo ; taille d'image maximum : 24 mégapixels.
- Aucune inférence réseau ni API payante n'est utilisée lors de la génération. Le système refuse les droits non confirmés, les allégations non vérifiées et les médias inconnus.
- Le moteur décode entièrement chaque MP4 avant de l'exposer au lecteur Android ; le fichier temporaire est atomiquement remplacé après validation.
- L'utilisation commerciale des voix Siwis/Lessac et des photos reste soumise aux licences et autorisations applicables. Un logiciel ne peut pas attester à lui seul ces droits.
- Le rendu Full-HD peut être exigeant en CPU/RAM ; il utilise le même travailleur borné que les exports du studio.
- Il n'existe pas de synchronisation temporelle mot à mot pour la voix-off. Les textes fournis ne sont pas représentés comme sous-titres synchronisés.

## Validation

```bash
UGC_TEST_PIPER_MODEL_EN="$HOME/ugc-voices/en_US-lessac-medium.onnx" python3 functional_checks_v14.py
```

La validation V14 exerce l'API HTTP authentifiée, l'import de PNG réels, la véritable génération vocale Piper, l'aperçu FFmpeg, l'export Full-HD et son décodage, les scènes visuellement distinctes, les liens de lecture signés et le refus des données non autorisées. Les tests historiques V9–V12 s'exécutent dans le même workflow de régression.
