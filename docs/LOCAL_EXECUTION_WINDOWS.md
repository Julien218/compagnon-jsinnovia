# Exécution locale Elyna — Windows / ComfyUI

## Pré-requis

- ComfyUI fonctionnel
- NVIDIA GPU avec pilotes compatibles CUDA
- Espace disque suffisant pour le checkpoint et les sorties GLB
- Référence canonique : `00_phenix_companion_officiel_reference.png`

Le démarrage détecte automatiquement l'installation ComfyUI Desktop et Blender 5.x. Pour une installation personnalisée, définir `COMFYUI_ROOT` et `BLENDER_EXE` avant de lancer `scripts/start_avatar_factory.ps1`.

## Checkpoint Hunyuan3D 2.1

Le workflow ComfyUI utilise :

`hunyuan_3d_v2.1.safetensors`

Source Comfy-Org :

`https://huggingface.co/Comfy-Org/hunyuan3D_2.1_repackaged/resolve/main/hunyuan_3d_v2.1.safetensors`

SHA256 attendu :

`5f21e98a6cb99b13b5e224abaee33929570fff7af2b6a0060001559a04ba9d72`

Le script `scripts/setup_hunyuan3d_checkpoint.ps1` télécharge le checkpoint dans `ComfyUI/models/checkpoints/` et vérifie son SHA256 avant de le considérer valide.

## Mémoire GPU

Le dépôt officiel Hunyuan3D 2.1 annonce environ 10 Go de VRAM pour la génération de forme seule et davantage pour la génération de textures PBR. ComfyUI dispose toutefois de mécanismes d'offload mémoire ; pour une carte plus petite, commencer exclusivement par le preset diagnostic 1024 et ne monter en résolution que si l'exécution est stable.

## Préparer la référence

Copier :

`00_phenix_companion_officiel_reference.png`

vers :

`ComfyUI/input/00_phenix_companion_officiel_reference.png`

Ne pas utiliser une image humanoïde ou un autre phénix à la place de cette référence.

## Importer le workflow

Importer dans ComfyUI :

`workflows/comfyui/elyna_hunyuan3d_shape.json`

Le workflow utilise uniquement les nœuds Hunyuan3D/core attendus :

- `ImageOnlyCheckpointLoader`
- `CLIPVisionEncode`
- `Hunyuan3Dv2Conditioning`
- `ModelSamplingAuraFlow`
- `EmptyLatentHunyuan3Dv2`
- `KSampler`
- `VAEDecodeHunyuan3D`
- `VoxelToMesh`
- `SaveGLB`

## Premier passage — diagnostic

Valeurs de départ :

- Resolution : 1024
- Batch : 1
- Steps : 12
- CFG : 5
- Sampler : euler
- Scheduler : normal
- Octree : 128
- Threshold : 0.7

Objectif : vérifier silhouette, tête, proportions, ailes et queue. Ce GLB n'est pas encore un produit final.

## Deuxième passage — candidat production

Si le diagnostic est stable et fidèle :

- passer Resolution à 2048 ;
- conserver Batch 1, Steps 12, CFG 5 et Octree 128 ;
- générer un nouveau GLB ;
- comparer les deux versions avant de poursuivre.

## Critères de rejet immédiat

Rejeter le mesh si :

- casque ou microphone disparaissent ;
- emblème central change ;
- ailes perdent leur palette iridescente ;
- tête ou yeux deviennent enfantins/kawaii ;
- ailes, bras, jambes ou queue fusionnent de manière inutilisable ;
- la silhouette ne correspond plus à la référence canonique.

## Après le GLB

Le GLB doit encore passer par Blender pour :

1. nettoyage ;
2. retopologie ;
3. séparation des pièces ;
4. UV/PBR ;
5. rig et skinning ;
6. contrôles ailes/queue ;
7. expressions `blink` et `aa` ;
8. export VRM.

Le fichier final ne doit être copié vers le site qu'après validation complète.
