# V8 : studio mobile privé, sans API et sans crédits

UGC Zero Credit V8 ajoute une interface web pour **assembler** des séquences vidéo d'influenceuses IA déjà créées et autorisées. Elle n'appelle jamais de générateur vidéo/voix payant ; elle ne crée pas elle-même de personne synthétique photoréaliste.

## Démarrage sur un serveur Linux

```bash
sudo apt update && sudo apt install -y python3 ffmpeg
# Cloner le dépôt une fois ; puis exécuter depuis sa racine :
python3 studio_web.py --host 127.0.0.1 --port 8787 --data "$HOME/ugc-studio-data"
```

Le terminal affiche un jeton aléatoire de 32 caractères ou davantage. Ne pas le publier. Pour un jeton stable après redémarrage :

```bash
export UGC_STUDIO_TOKEN="une-longue-cle-aleatoire-d-au-moins-24-caracteres"
python3 studio_web.py --data "$HOME/ugc-studio-data"
```

**Ne pas exécuter directement sur `0.0.0.0` en HTTP public.** Le serveur refuse expressément les interfaces autres que `127.0.0.1`, `localhost` et `::1`. Pour une exposition permanente, utiliser un tunnel privé chiffré, pas une ouverture de port. Aucun certificat, compte, service SaaS ou coût API n'est requis.

## Depuis un téléphone Android

Avec Termux (gratuit) sur le téléphone et un serveur distant accessible en SSH :

```bash
pkg install openssh
ssh -L 8787:127.0.0.1:8787 utilisateur@adresse-de-ton-serveur
```

**Prérequis :** le processus `studio_web.py` doit déjà tourner sur le serveur. Laisser la session SSH ouverte ; dans Chrome Android, ouvrir :

`http://127.0.0.1:8787`

Saisir le jeton imprimé sur le serveur dans l'interface (il est gardé dans la session du navigateur, quand le stockage de session est autorisé). Les vidéos sont lues via des URL de lecture temporaires et limitées à un fichier ; le jeton API n'apparaît pas dans ces URL.

## Parcours utilisateur

1. Créer un projet et importer les médias. Types acceptés : MP4/MOV/MKV/WebM, PNG/JPEG/WebP, WAV/MP3/M4A et SRT.
2. Saisir le produit et sélectionner une image de référence exacte. Déclarer les droits de chaque fichier et vérifier les affirmations. La mention « PUBLICITÉ · LIEN AFFILIÉ · INFLUENCEUSE IA » reste visible.
3. Ajouter les **vidéos parlées disposant déjà de leur voix native** ; renseigner le point de départ et la durée conservée, sans remplacer leur audio. Pour plusieurs séquences, les placer dans l'ordre narratif.
4. Ajouter des plans du produit. Leur audio est ignoré pour conserver la voix de l'influenceuse en continu.
5. Ajouter un fichier SRT par séquence parlée, avec la base temporelle `clip` (SRT commençant à zéro) ou `source` (temps dans le fichier original). Les phrases sont affichées à leurs temps réels ; **aucune précision mot à mot n'est inventée**.
6. Enregistrer et vérifier. Corriger toute erreur, puis lancer l'aperçu léger ou l'export Full HD 1080 × 1920, 30 FPS.
7. Visionner le MP4, relire les sous-titres et les rapports, vérifier manuellement le produit et le mouvement des lèvres, puis télécharger le résultat. La publication TikTok n'est pas automatique.

## Sécurité et confidentialité

- Bibliothèque standard Python : `ThreadingHTTPServer`, jeton `Authorization: Bearer`, protections d'origine, CSP, X-Frame-Options, no-store.
- Médias locaux uniquement ; pas d'URL externe, de clé cloud ni d'upload tiers. Chemins normalisés, fichiers confinés à leur projet et interdiction des écritures hors des dossiers désignés.
- 350 Mio maximum par média, 40 médias maximum par projet, 2 Gio maximum par projet et réserve de 256 Mio sur le volume ; SRT limité à 2 Mo.
- Les exports sont vérifiés avec FFprobe/FFmpeg et les mécanismes QA existants avant publication atomique dans le dossier projet.
- Le rendu d'une vidéo en Full HD peut être long sur CPU ; l'interface ne promet pas de durée de traitement. L'application n'effectue pas de rendu arrière-plan quand le processus Python est arrêté.
- Le mot de passe n'est pas une authentification multi-utilisateurs : ce studio est conçu pour **un seul opérateur** utilisant un tunnel SSH. Pour une exposition publique, il faut un frontal HTTPS/VPN, des contrôles de quota renforcés et une gestion des comptes.
- Les URL de consultation MP4 temporaires (1 h) sont en lecture seule et autorisent les requêtes `Range` pour naviguer dans une vidéo sur Android.

## Tests

```bash
python3 make_synthetic_demo.py
python3 functional_checks_v8.py
python3 browser_smoke_v8.py    # facultatif, nécessite Playwright + Chromium
```

Le test HTTP effectue des requêtes réelles au serveur en boucle locale, importe des médias synthétiques, valide le SRT, déclenche un rendu FFmpeg et vérifie la lecture partielle du MP4 (`Range: bytes=...`). Le test navigateur pilote l'interface en émulation mobile ; dans certains environnements de test, la politique de Chromium bloque toute navigation. Le test peut alors injecter l'interface dans une page isolée et transmettre ses requêtes au vrai serveur par Python : il vérifie les contrôles JavaScript et le serveur, **pas la connexion réseau native de Chromium ni sa lecture vidéo**.

Comme les V3–V7, les contrôles de timing audio ne prouvent **pas** une synchronisation phonétique exacte des lèvres. L'usage commercial exige aussi des droits, l'approbation des revendications et les déclarations publicitaires/IA sur la plateforme.
