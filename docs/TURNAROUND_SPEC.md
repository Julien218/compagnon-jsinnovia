# Elyna — Turnaround canonique 3D

Ce document définit les règles de production des quatre vues maîtres utilisées pour la reconstruction 3D multi-vues.

## Source de vérité

La référence visuelle canonique est `00_phenix_companion_officiel_reference.png`, stockée actuellement dans Google Drive (file ID `1y96GHd7_du62CNAIS9fZCUZsra7xKAto`). Toute nouvelle vue doit rester cohérente avec cette référence et avec le Character Sheet JS-Innov.IA.

## Vues obligatoires

Les fichiers de production attendus sont :

- `elyna_front.png`
- `elyna_left.png`
- `elyna_back.png`
- `elyna_right.png`

## Règles absolues

1. Même personnage, même proportions, même hauteur et même cadrage sur les quatre vues.
2. Pose neutre ou A-pose légère, jambes stables, bras suffisamment dégagés du torse.
3. Même casque, même microphone, même crête, même emblème de poitrine, même armure et mêmes ailes.
4. Fond neutre uniforme ou transparence ; aucun texte, décor, hologramme ou accessoire flottant.
5. Conserver les asymétries réelles. Ne jamais fabriquer la vue opposée par simple miroir si cela déplace le microphone ou le marquage JS.
6. Les ailes doivent être dans une position de repos cohérente, non déployées comme dans les animations promotionnelles.
7. Aucun changement de style : pas de cartoon, kawaii, jouet, enfantin ou robot générique.

## Palette canonique

- Ivoire / armure claire : `#F5F1E8`
- Or métallique : `#D4AF37`
- Bleu nuit : `#0A1A2F`
- Cyan : `#00E5FF`
- Violet : `#9B5DE5`
- Magenta : `#F15BB5`

## Utilisation Hunyuan3D

Les quatre vues doivent alimenter `Hunyuan3Dv2ConditioningMultiView` dans ComfyUI :

- front → `elyna_front.png`
- left → `elyna_left.png`
- back → `elyna_back.png`
- right → `elyna_right.png`

Réglage de départ validé sur RTX A3000 6 Go :

- résolution latent : `2048`
- batch : `1`
- KSampler steps : `12`
- CFG : `5.0`
- octree : `128`

Si la mémoire GPU devient insuffisante : descendre à `1536` / octree `96`.

## Critères de validation avant rig

Le mesh n'est accepté que si :

- tête, bec, casque et crête sont propres et symétriquement cohérents ;
- microphone présent du bon côté ;
- épaules, bras, mains et jambes ne fusionnent pas ;
- ailes et queue sont séparables et lisibles ;
- silhouette reconnaissable immédiatement comme le Compagnon JS-Innov.IA ;
- aucune déformation majeure n'est visible à 360°.

Une fois validé : GLB → Blender → retopologie → UV/materials → rig → expressions → VRM.
