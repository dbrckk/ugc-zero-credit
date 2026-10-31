# V19 — mise en scène produit dynamique (sans API payante)

## Fonctionnement

Le moteur narrated_short.py produit un véritable MP4 vertical H.264/AAC avec 1 à 6 photographies autorisées et une narration Piper FR/EN du projet. La V19 remplace la photographie aplatie par une composition à deux plans : fond flouté sombre et carte-photo distincte avec bordure ivoire.

Chaque carte apparaît progressivement, entre alternativement depuis le bord droit ou gauche puis se stabilise. Elle conserve ensuite un léger mouvement indépendant du fond. Les scènes se succèdent par transition FFmpeg smoothright ou smoothleft. Les titres animés V18, la barre de progression, les repères de scène et les mentions légales restent présents.

Ce moteur ne synthétise aucune influenceuse, ne génère aucun mouvement humain, ne garantit aucun lip-sync et n'invente pas d'allégations produit. Pour une vraie publicité avec influenceuse, importer une vidéo parlée autorisée dans le parcours montage, ou valider séparément le pont GPU MuseTalk (non démontré de bout en bout).

## Déploiement privé

Sur un serveur Debian/Ubuntu Linux qui héberge déjà le studio :

    cd ugc-zero-credit
    git pull --ff-only origin main
    bash install_studio.sh

Ou, si le serveur n'a pas encore le dépôt :

    curl -fsSLo /tmp/ugc-bootstrap.sh https://raw.githubusercontent.com/dbrckk/ugc-zero-credit/main/bootstrap.sh && bash /tmp/ugc-bootstrap.sh

Le service n'écoute que sur la boucle locale de l'hôte ; l'accès Android passe par un tunnel SSH. Le studio ne nécessite pas de jeton ni de crédit d'une API vidéo.

## Validation reproductible

Le workflow GitHub v14-narrated-validation.yml, déclenché sur la branche V19, télécharge les deux vraies voix Piper, exécute les tests HTTP et les exports FFmpeg, puis reconstruit le conteneur complet. Le test test_05_product_photo_really_enters_from_right compare les pixels décodés à 0,10 s et 0,85 s pour vérifier que la carte est effectivement entrée dans le champ.

L'artefact ugc-v19-real-parallax-frames contient les images PNG de début et d'arrivée de la carte, en aperçu et en Full-HD. Il reste nécessaire de contrôler visuellement les vraies photographies du produit et de vérifier leurs droits avant toute commercialisation.

Les paramètres de mouvement sont fixés par le moteur pour rester légers sur CPU : apparition 0,28–0,48 s et entrée 0,32–0,72 s.

## Limites

Un vrai plan filmé reste préférable à un diaporama pour un contenu de type influenceuse. Le rendu ne produit pas de vidéos photoréalistes à partir d'une photo de visage. Les licences des voix Piper Siwis et Lessac, les photos et les allégations commerciales doivent être vérifiées par l'opérateur avant publication.
