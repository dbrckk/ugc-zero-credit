# V9 — Fiabilité du studio mobile

La V9 protège le studio CPU contre l'accumulation illimitée de rendus.

- **Maximum deux exports actifs** au total : un en cours et un en attente. Les demandes supplémentaires reçoivent HTTP 429.
- **Un seul export par projet** à la fois : les demandes concurrentes reçoivent HTTP 409.
- **Configuration verrouillée pendant l'export** : le formulaire ne peut pas modifier le projet entre sa validation et son rendu. Une demande concurrente reçoit HTTP 409.
- Les exports terminés ou échoués libèrent automatiquement une place.
- Aucun service externe ni générateur IA n'est appelé.

## Vérification locale

```bash
python3 functional_checks_v9.py
python3 functional_checks_v8.py
```

La suite V9 teste la logique d'admission hors ligne. La suite V8 couvre le serveur HTTP et un rendu synthétique réel. Le studio reste privé, accessible par tunnel SSH, et non adapté à une exposition HTTP publique.

## Contrôle supplémentaire : configuration immuable pendant l'admission

Le serveur lit et vérifie un instantané du JSON avant d'ajouter le rendu à la file. Sous `jobs_lock`, il compare cet instantané au fichier actuel. Si un enregistrement concurrent a modifié le fichier, le rendu est rejeté avec **HTTP 409** et ne démarre pas avec un formulaire périmé.

Le test `functional_checks_v8.py` est étendu avec trois vrais rendus FFmpeg : il vérifie les refus 409/429, la cohérence des configurations et la récupération après achèvement. Les médias restent synthétiques et locaux. Les tests fonctionnels complets sont exécutés avant fusion sur la branche dédiée.
