# Processus V7 : sous-titres précis sans crédits externes

## Problème résolu

La V6 refusait de produire des sous-titres sans JSON mot-à-mot. Cela bloquait
l'utilisation des fichiers SRT ordinaires exportés par des éditeurs, même
quand leurs temps étaient fiables. La V7 distingue deux niveaux de preuve :

- `words` : horodatages acoustiques par **mot** ; surlignage mot par mot.
- `segments` : horodatages par **phrase SRT** ; affichage stable sans faux
  mouvements de surlignage mot-à-mot.

Les deux modes sont mutuellement exclusifs. Aucun service distant n'est contacté.

## Workflow

1. Acquérir une vidéo d'influenceuse IA disposant déjà de sa voix synchronisée.
2. Déclarer explicitement les droits, le produit et ses allégations dans le JSON.
3. Obtenir un SRT fiable avec les temps du clip ou de la source entière.
4. Corriger manuellement les noms de marque et les éventuels faux mots.
5. `python3 ugc.py captions-import projet.json voix.srt --clip 0 --output projet_subtitles.json --replace-existing`
6. `python3 ugc.py check projet_subtitles.json` puis `python3 ugc.py plan projet_subtitles.json`.
7. `python3 ugc.py render projet_subtitles.json --output rendu.mp4`
8. Lire la vidéo, son audio, le SRT et le rapport avant toute publication.

Pour un second clip, importer dans une **nouvelle copie** en utilisant le JSON
généré à l'étape 5 comme nouvelle entrée et `--clip 1`.

## Limites et sécurité

L'intervalle SRT décrit la présence *potentielle* de parole : il peut englober
des micro-silences. Le rapport porte `speech_timing_precision: phrase` et
`speech_intervals_are_conservative: true`. Ces champs ne prouvent ni la
synchronisation phonème/lèvres ni la fidélité de la transcription.

L'import refuse les chevauchements, les chemins de sortie hors du projet,
les sorties préexistantes, le remplacement implicite, les légendes mal formées
et les temps hors de la portion parlée. L'empreinte SHA-256 du fichier SRT
est enregistrée pour tracer la version relue.

Les vérifications de droits, de publication et d'identité produit restent
indispensables. Le système n'effectue aucun upload, aucune publication et
aucune génération d'influenceuse IA. Ressources consommées : CPU/disk locaux.
