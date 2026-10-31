# V10 : incrustations produit animées sans cacher toute la présentatrice

## Nouvelle fonction
- Chaque insert produit accepte `layout: "full"` (comportement V3–V9), `"pip_left"` ou `"pip_right"`.
- Les deux incrustations latérales sont proportionnelles au format 9:16, de l'aperçu à l'export 1080 × 1920, avec bordure blanche et contour sombre.
- Leur zone est placée entre les mentions publicitaires en haut et les sous-titres en bas. **Aucune détection de visage n'est impliquée dans le placement** : un visage situé derrière l'incrustation peut encore être caché ; vérification visuelle indispensable.
- Photos produit animées : effets Ken Burns existants, visibles dans la carte. Les vidéos produit ont un cadrage fixe et leur **audio est ignoré** pour conserver la voix native de la présentatrice.
- Nouveau sélecteur « Disposition » dans le studio Android. Les anciens projets sans champ `layout` fonctionnent toujours en plein écran.
- L'audit éditorial ne déclare pas un masquage **plein écran** pour les cartes PIP ; il précise `picture_in_picture_may_cover_speaker: true`.
- L'autoplan conserve les cartes produit hors du budget de coupes plein écran.

## Exemple de projet JSON
```json
{
  "file": "demo_media/produit.png",
  "start": 1.0,
  "duration": 1.4,
  "fade": 0.12,
  "rights": "owned",
  "layout": "pip_right",
  "motion": "push_in"
}
```

## Contrôles
```bash
python3 make_synthetic_demo.py
python3 functional_checks_v10.py
python3 functional_checks_v8.py
python3 functional_checks_v9.py
```

La suite V10 rend de vrais MP4 de démonstration pour une image et une vidéo en incrustation. Elle vérifie les coordonnées des cartes, le maintien d'une zone centrale à l'écran, l'apparition visible des produits, l'audio natif et le décodage intégral. Les médias sont synthétiques et **non publiables**. L'application ne fabrique toujours pas une influenceuse photoréaliste ni de lip-sync phonétique.
