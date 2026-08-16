# Pipeline 3D — Elyna / Compagnon JS-Innov.IA

## Objectif

Produire un avatar 3D premium, léger, riggable et exploitable sur le site JS-Innov.IA et dans le Cockpit, sans perdre l'identité visuelle du Compagnon.

## Pipeline de production

### 1. Références

- Source maître : `00_phenix_companion_officiel_reference.png`
- Références secondaires : full-body idle, wave, bust idle/speaking/thinking
- Character Sheet : identité, palette et interdictions
- Les vidéos servent de références de mouvement, pas de référence géométrique principale.

### 2. Turnaround

Créer quatre vues cohérentes : front, left, back, right. Voir `TURNAROUND_SPEC.md`.

### 3. Reconstruction locale

Moteur : Hunyuan3D 2.1 dans ComfyUI.

Checkpoint : `hunyuan_3d_v2.1.safetensors`.

Configuration de départ validée :

- latent resolution : 2048
- batch : 1
- steps : 12
- cfg : 5
- octree : 128

Sortie : GLB brut.

### 4. Blender

Étapes attendues :

1. Nettoyage du mesh et correction de silhouette.
2. Retopologie adaptée à l'animation temps réel.
3. Séparation logique : tête, casque/micro, torse, bras/mains, jambes, ailes, queue/plumes.
4. UV unwrap propre.
5. Matériaux PBR conformes à la palette JS-Innov.IA.
6. Optimisation du nombre de polygones.
7. Rig humanoïde/custom avec contrôles spécifiques aux ailes et à la queue.
8. Skinning et correction des déformations.

### 5. Expressions et états

Expressions minimales runtime :

- `blink`
- `aa` pour lipsync minimal

États comportementaux :

- idle
- listening
- thinking
- speaking
- greeting
- presenting
- success
- error

Les images et vidéos du kit existant servent de références pour reproduire ces états sur le rig 3D.

### 6. Export runtime

Format cible : VRM.

Contraintes :

- taille cible <= 15 MiB
- fallback 2D obligatoire
- activation uniquement après validation du modèle
- runtime web : `@pixiv/three-vrm`

### 7. Intégration

Web/Cockpit : Three.js ou React Three Fiber + three-vrm.

Le contrôleur d'état doit être indépendant du modèle afin de permettre :

- changement idle/listening/thinking/speaking ;
- lipsync synchronisé avec TTS ;
- animations contextuelles ;
- fallback PNG/vidéo si WebGL/VRM indisponible.

## Definition of Done

Le modèle n'est considéré livrable que si :

- la silhouette respecte la référence canonique à 360° ;
- le casque, le micro et l'emblème S sont corrects ;
- les ailes gardent leur gradient iridescent ;
- aucune apparence enfantine/cartoon n'est introduite ;
- le rig passe les tests idle, blink, speaking et greeting ;
- le VRM reste sous la limite de poids ;
- le fallback 2D fonctionne ;
- le modèle est testé desktop et mobile.
