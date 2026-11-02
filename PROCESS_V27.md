# V27 — garantir que le MP4 provient du bon rendu Kaggle

## Problème réel corrigé

Jusqu'à V26, l'automatisation lançait un notebook privé Kaggle, puis consultait son statut et téléchargeait le MP4 via l'identifiant sans numéro de version (format `utilisateur/notebook`). Cette syntaxe demande à Kaggle le **dernier run**, qui peut changer entre la soumission et la récupération si un autre lancement a lieu. Cela pouvait produire un faux succès en réutilisant le MP4 d'une ancienne version.

## Correction

L'API CLI officielle `kaggle==2.2.5` retourne une réponse du type `Kernel version 42 successfully pushed`. Le contrôleur `kaggle_automate.py` :

1. Lit ce numéro après la soumission réelle sur Kaggle.
2. Refuse un résultat vide, ambigu, sans numéro ou indiquant seulement une sauvegarde sans exécution.
3. Suit uniquement `kaggle kernels status utilisateur/notebook/42`.
4. Récupère uniquement `kaggle kernels output utilisateur/notebook/42`.
5. Vérifie ensuite le manifeste GPU, l'empreinte du MP4 et son décodage FFmpeg intégral comme en V26.

L'interface GitHub Actions n'affiche plus un lien non versionné pouvant mener à une autre exécution. Le lien exact est affiché par le script dans le journal privé du workflow.

## Vérification

Les tests du contrôleur valident les réponses ambiguës et assurent qu'un run 42 utilise la version 42 pour le suivi **et** les téléchargements, sans exposer le jeton. Le workflow de validation V14 exécute en plus des tests réels Piper FR/EN, FFmpeg 1080 × 1920, et la reconstruction Docker.

Documentation CLI Kaggle : https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md

## Limitation restante

Un résultat correctement associé à un numéro de version ne prouve toujours pas que **MuseTalk fonctionne sur un GPU Kaggle**. Seuls un vrai MP4 rendu sur Kaggle, ses rapports vérifiés et l'inspection visuelle des lèvres permettent de valider cette étape. Aucune authentification Kaggle ni nouveau rendu GPU n'ont été réalisés dans cette mise à jour.
