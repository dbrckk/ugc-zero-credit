# V22 — fiabilité MuseTalk : état réel du GPU et contrôle audio/vidéo

## Problèmes corrigés

La V21 proposait une intégration Android avec une configuration GPU facultative, mais un chemin MuseTalk renseigné n'assurait pas que CUDA, les modèles ou l'interface de commande étaient réellement disponibles. Elle acceptait aussi un MP4 avec des pistes audio/vidéo présentes mais potentiellement décalées, muettes ou mal synchronisées en durée.

## Fonctionnement

1. **Diagnostic privé** `GET /api/presenter/readiness` : authentification obligatoire, vérification des fichiers et modèles, compatibilité des options de l'interface officielle `scripts.inference`, puis appel du vrai Python PyTorch CUDA. Le serveur ne publie aucun chemin privé. Le résultat est mis en cache 120 secondes ; une seule vérification active est autorisée pour éviter de multiplier les processus GPU.
2. **Android** : état MuseTalk/CUDA confirmé affiché dans le panneau ; le bouton de génération est désactivé tant que le diagnostic n'est pas positif. Un bouton permet de vérifier les modèles et le GPU. Le diagnostic se déclenche également après l'ouverture d'un projet configuré.
3. **Encodage** : sortie MuseTalk vérifiée avec ffprobe et décodage FFmpeg complet. Résolution vidéo minimale, différence de durée des pistes audio/vidéo de 450 ms maximum, cohérence des durées source→pistes et présence d'une voix audible via `volumedetect` (maximum supérieur ou égal à -55 dB). Un MP4 muet, corrompu ou trop décalé n'est pas enregistré comme rendu réussi.
4. **Sécurité** : refus des chemins de sortie symboliques, y compris les liens pendants. Les rapports indiquent l'écart audio/vidéo, les durées des pistes et le niveau de crête.
5. **Flux Android** : une vidéo terminée apparaît dans la bibliothèque du projet, un lien de téléchargement est disponible, et la sélection des médias du monteur est actualisée sans rechargement.

Le système n'achète aucun crédit IA, ne télécharge pas de modèle à l'exécution et ne publie pas automatiquement sur les réseaux sociaux.

## Vérification reproductible

Le workflow V14 élargi à V22 exécute les vrais tests Piper/FFmpeg et Docker du projet, vérifie l'API privée CPU (absence de GPU → refus contrôlé) et crée de vrais MP4 H.264/AAC avec tonalité audible et piste muette pour confirmer les barrières du nouveau contrôle audio. `node --check` valide l'interface JavaScript.

**Limites** : la disponibilité GPU n'est pas la validation d'un rendu MuseTalk réel. Les tests GitHub Actions ne possèdent pas de GPU CUDA. Aucun score de synchronisation lèvres/phonèmes n'est revendiqué. Il faut encore vérifier un vrai rendu sur serveur GPU autorisé, ainsi que les licences des voix, modèles et portraits.

La mise à jour normale du studio CPU reste :

```bash
cd ugc-zero-credit
git pull --ff-only origin main
bash install_studio.sh
```

Pour configurer MuseTalk sur un GPU existant, voir [PROCESS_V21.md](PROCESS_V21.md). Aucun accès SSH à un serveur personnel n'a été utilisé.
