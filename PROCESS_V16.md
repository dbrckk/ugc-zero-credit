# V16 — composition éditoriale des Shorts 9:16

## Résultat
- Titres produits de 2–48 caractères répartis sur 1 à 4 lignes, avec police adaptative, sans promesse inventée.
- Photographie intégralement contenue au centre sur fond flouté sombre ; cadre discret, bandeaux pour la lisibilité et repère de scène 01 / 06.
- Zoom et déplacement léger alternés par scène (FFmpeg), sans image générée artificiellement.
- Rapport de rendu : taille de titre, nombre de lignes et composition utilisée.
- Les mentions publicitaires V15, la provenance des voix FR/EN, les droits et la revue humaine sont préservés.

## Utilisation
Dans le studio Android : choisir la voix française/anglaise, joindre les images autorisées et saisir le titre, puis créer l'aperçu et le Short 1080 × 1920. Pas de service payant.

Sur le serveur Debian/Ubuntu déjà installé : `cd ugc-zero-credit && git pull --ff-only origin main && bash install_studio.sh`. Le port HTTP demeure privé derrière le tunnel SSH.

## Validation
La CI V16 exécute les vrais tests Piper + FFmpeg (aperçu et export Full-HD), vérifie les titres longs et le décodage audio/vidéo, puis joint deux captures de frames dans `ugc-v16-real-visual-frames`. Ces captures doivent être examinées humainement : elles ne garantissent pas la qualité de toutes les photos.

Aucun visage ou lip-sync n'est synthétisé et les droits commerciaux doivent rester vérifiés indépendamment.
