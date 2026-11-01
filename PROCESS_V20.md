# V20 — coupes calées sur les pauses audibles (CPU, sans crédits)

## Amélioration livrée

Le moteur des Shorts narrés examine le WAV Piper FR/EN avec **FFmpeg silencedetect**.
Lorsque la bande sonore contient une pause exploitable proche du changement de photo prévu, le passage à la scène suivante se centre sur cette pause au lieu de couper à un instant strictement uniforme.

- Audio inchangé : aucune accélération, coupure ou régénération de voix.
- Transition croisée de 300 ms : calcul des durées de chaque scène et des offsets à partir du même calendrier.
- Entrées animées, arrière-plan indépendant, titres, progression et avertissement commercial V19 conservés.
- Limites de déplacement et de durée pour éviter les passages trop rapides ou trop tardifs.
- Repli automatique sur des coupes régulières si aucune pause acceptable n'est détectée.
- Analyse locale par FFmpeg : aucun modèle à télécharger, aucun service tiers ni jeton d'inférence.

## Vérification

Le fichier \`*.report.json\` ajoute :

- \`scene_cut_method\` : méthode de calcul.
- \`scene_cut_times\` : instants de passage entre photos, en secondes.
- \`scene_durations\` : durées des plans, chevauchement de transition inclus.
- \`narration_pauses_detected\` : nombre de pauses mesurées.
- \`scene_cuts_near_pauses\` : nombre de coupes rapprochées de pauses.

Le workflow \`.github/workflows/v14-narrated-validation.yml\` exécute des tests avec un vrai WAV synthétique de pauses, un vrai WAV Piper anglais, deux photos et des MP4 H.264/AAC en aperçu et Full HD. Les anciens contrôles et la construction Docker sont conservés.

## Limites

L'absence de pause n'autorise pas à supposer la fin d'une phrase. Cette synchronisation est **temporelle et acoustique**, non sémantique. Ce changement ne transcrit pas la parole et ne produit pas de lip-sync. Le parcours avec une influenceuse parlante nécessite toujours un rush vidéo parlant autorisé ou un moteur de synchronisation labiale local indépendant, validé sur GPU. La revue humaine et les droits commerciaux restent requis.

Mise à jour du serveur existant :

\`\`\`bash
cd ugc-zero-credit
git pull --ff-only origin main
bash install_studio.sh
\`\`\`
