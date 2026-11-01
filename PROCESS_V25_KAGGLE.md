# V25 — Plan Kaggle T4 x2 pour valider MuseTalk

## Décision du 1er novembre 2026

Utiliser le GPU gratuit Kaggle **T4 x2**, deux cartes de 16 Go chacune (mémoire non cumulable) pour une première validation MuseTalk. Le GPU P100 est retiré depuis le 15 septembre 2026. Les quotas sont variables, souvent autour de 30 heures GPU par semaine ; l'accès et la durée des sessions ne sont pas garantis. Ce n'est pas un serveur permanent et nous n'y exposons pas de service HTTP.

Sources :
- https://www.kaggle.com/product-announcements/735239
- https://www.kaggle.com/docs/notebooks
- https://www.kaggle.com/docs/efficient-gpu-usage

## Plan d'action et critères

| Phase | Travail | Critère de réussite |
| --- | --- | --- |
| P0.1 | Activer GPU T4 x2 et Internet sur un Notebook Kaggle privé | CUDA disponible et minimum 4 Go de VRAM libre |
| P0.2 | Ajouter un dataset privé avec vraie vidéo, script, langue et droits | Contrôles de format, consentement et langue effectués avant téléchargement |
| P0.3 | Installer PyTorch CUDA et MuseTalk 1.5 épinglé dans /kaggle/temp | Imports des vrais composants GPU et poids valides |
| P0.4 | Générer la voix Piper FR/EN localement, lancer MuseTalk | MP4 et WAV réels avec manifestes de provenance |
| P0.5 | Contrôler bouche, gestuelle, voix, expression et produit | Revue humaine d'un vrai MP4 terminé |
| P0.6 | Répéter en anglais, puis préparer le transfert au studio Android | Deux vraies publicités bilingues cohérentes |

## Les quatre fichiers à ajouter

Dans un **dataset Kaggle privé**, placer exactement :
- presenter.mp4 : clip vertical autorisé de 5–10 secondes recommandé (MOV/MKV également acceptés), 120 Mo maximum, largeur et hauteur >= 256 pixels, durée 0,8–60 secondes.
- script.txt : le texte prononcé, 2–350 caractères, vrai argumentaire produit avec bénéfices vérifiés.
- language.txt : fr ou en, sur une ligne.
- portrait_rights.txt : référence de droits écrite et vérifiable, attestant du consentement ou de la création autorisée (une ligne de 8–500 caractères).

Ne jamais y mettre d'identifiants, de jetons GitHub, de contenus confidentiels ou de médias sans droit d'utilisation. Le calcul est exécuté sur l'infrastructure externe Kaggle, pas sur ton propre serveur.

## Depuis Android

1. Ouvrir https://www.kaggle.com/code et créer un Notebook privé.
2. Paramètres du Notebook : choisir Accelerator > GPU T4 x2 et Internet ON pour l'installation initiale. L'accès peut nécessiter une vérification du compte.
3. Via Add Input/Add Data, joindre le dataset privé de quatre fichiers. Ne pas rendre public le Notebook ni ses sorties.
4. Importer le notebook du dépôt : https://github.com/dbrckk/ugc-zero-credit/blob/main/kaggle/ugc_musetalk_gpu.ipynb (en téléchargeant le fichier, puis File > Import Notebook).
5. Lancer Run All : contrôle des données et de CUDA, installation isolée des dépendances/poids, génération Piper, inférence MuseTalk et contrôles réels de la sortie.
6. Télécharger les résultats depuis /kaggle/working/ugc-v25-results puis arrêter le GPU.

## Optimisation et limites

Les composants lourds sont stockés dans /kaggle/temp, non pérenne ; seuls WAV, MP4 et rapports sont conservés dans /kaggle/working. La première installation peut prendre une partie importante de la session, et une future optimisation pourra réutiliser des poids via un dataset Kaggle privé si les licences le permettent.

Le notebook ne contourne pas les quotas Kaggle, n'utilise aucune API de synthèse payante, et ne publie rien automatiquement. Les dépendances MMLab de MuseTalk peuvent nécessiter des adaptations spécifiques sur Kaggle ; en cas d'échec, aucun rendu fictif n'est annoncé.

La CI GitHub CPU valide le notebook, la source MP4 réellement encodée, les contrôles de droits et le refus de faux CUDA ; elle ne prouve pas un rendu GPU Kaggle. **P0 ne sera terminé qu'après production et inspection d'une vraie vidéo MuseTalk.**
