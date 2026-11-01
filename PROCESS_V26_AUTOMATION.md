# V26 — automatisation Kaggle privée, depuis Android ou un terminal

## Ce qui est automatisé

Le programme kaggle_automate.py gère maintenant la création des datasets privés (si les médias sont disponibles localement), la génération du notebook Kaggle privé, la sélection du GPU T4 x2, la soumission à l'API officielle, le suivi des états et la récupération facultative des vidéos. Il refuse de déclarer une réussite sans vrai MP4 et rapport GPU vérifiés.

Le workflow GitHub propose aussi le déclenchement depuis Android sans terminal. Il **ne diffuse jamais les fichiers vidéo sur les artefacts publics GitHub** et ne relance pas automatiquement des tâches GPU en échec pour respecter le quota gratuit Kaggle.

## Option A — un clic GitHub Actions une fois configuré

La configuration initiale est obligatoire car Kaggle ne donne pas accès à un compte sans autorisation :

1. Ouvrir https://www.kaggle.com/settings/api et générer un jeton API personnel. Ne pas le transmettre dans le chat, dans un fichier du dépôt ou dans une issue.
2. Dans GitHub : dbrckk/ugc-zero-credit → Settings → Secrets and variables → Actions → New repository secret. Créer le secret nommé KAGGLE_API_TOKEN contenant ce jeton.
3. Ajouter dans un dataset Kaggle **privé** les quatre fichiers : presenter.mp4 (ou MOV/MKV), script.txt, language.txt (fr/en), portrait_rights.txt (référence de droits écrits et consentement).

Pour chaque nouveau rendu : ouvrir https://github.com/dbrckk/ugc-zero-credit/actions/workflows/kaggle-private-gpu.yml, cliquer Run workflow, donner son identifiant Kaggle et la référence du dataset privé (utilisateur/slug). Le workflow demande T4 x2, attend le verdict de Kaggle et affiche le lien vers le Notebook privé. Les sorties restent sur Kaggle ; le workflow ne les télécharge pas sur GitHub.

Le notebook doit pouvoir accéder au dataset privé. Si Kaggle refuse le GPU, le quota ou les téléchargements du modèle, le workflow échoue explicitement. Pas de génération payante ni de contournement des quotas.

## Option B — une seule commande locale avec téléchargement automatique

Il faut Python 3.11+, FFmpeg, ffprobe, Git et le CLI Kaggle officiel :

~~~bash
python -m pip install 'kaggle==2.2.5'
~~~

S'authentifier via la procédure officielle Kaggle (jeton dans ~/.kaggle/access_token avec permissions privées, ou connexion OAuth prise en charge par kaggle auth login). Depuis Android, Termux permet d'installer Python, Git et FFmpeg, puis d'exécuter la commande sur un clone à jour du dépôt.

Si les quatre fichiers autorisés sont déjà placés dans un dossier :

~~~bash
python kaggle_automate.py \
  --user UTILISATEUR_KAGGLE \
  --media-dir "$HOME/ugc-private" \
  --download-dir "$HOME/ugc-sorties"
~~~

Ou directement avec une vidéo, sans préparer les fichiers texte :

~~~bash
python kaggle_automate.py \
  --user UTILISATEUR_KAGGLE \
  --video "$HOME/Download/presenter.mp4" \
  --text "Voici notre produit et sa présentation." \
  --language fr \
  --rights "Consentement et droits du clip enregistrés" \
  --download-dir "$HOME/ugc-sorties"
~~~

Le script crée un dataset Kaggle **privé** en utilisant les données locales autorisées, construit le kernel et lance l'inférence. Il attend, télécharge les sorties et valide les SHA256 du MP4. Le dossier de téléchargement doit être inexistant pour ne jamais écraser une vidéo précédente.

## Garanties et limites

- Kaggle reçoit les vidéos et les voix nécessaires : ce ne sont pas des calculs sur un ordinateur personnel, les médias doivent être autorisés pour cet hébergement.
- Les datasets et notebooks créés par le contrôleur sont privés. Si l'on fournit un dataset Kaggle déjà existant, c'est à son propriétaire de s'assurer qu'il est privé.
- Les jetons ne sont jamais fournis en arguments de ligne de commande ni écrits dans le dépôt.
- Un état COMPLETE annoncé par Kaggle ne prouve pas une génération MuseTalk réussie : vérifier le vrai fichier vidéo et son manifeste, puis les lèvres et la qualité de la voix.
- Le workflow GitHub ne télécharge pas de vidéo dans un dépôt public. Le mode local peut récupérer les MP4 dans un dossier protégé.
- Kaggle est soumis à des quotas et n'est pas un serveur permanent ; le workflow est déclenché volontairement, pas chaque jour.
- Aucune exécution GPU réelle ne peut être revendiquée sans le compte Kaggle autorisé et des médias d'entrée consentis.
