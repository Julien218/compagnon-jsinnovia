# Compagnon JS-Innov.IA — Elyna 3D & Assets Premium

**Phénix Companion officiel** de la marque **JS-Innov.IA**  
Créé par **Julien Pagin** — www.jsinnovia.com

Ce dépôt est la **source de vérité technique** du Compagnon JS-Innov.IA / Elyna : identité, règles visuelles, références, pipeline 3D, manifests runtime et contrat des assets.

## Référence canonique

La référence visuelle officielle reste :

- `00_phenix_companion_officiel_reference.png`
- Google Drive file ID : `1y96GHd7_du62CNAIS9fZCUZsra7xKAto`

Les médias binaires sont actuellement conservés dans Google Drive. GitHub stocke les spécifications et fichiers techniques ; les vidéos lourdes doivent rester sur Drive ou être publiées via Releases/LFS.

L’index machine-readable des références se trouve dans `config/source-assets.json`.

## Structure

```text
config/
  elyna-3d.manifest.json
  avatar_states.json
  source-assets.json
  comfyui_presets.json

docs/
  CHARACTER_SHEET.md
  TURNAROUND_SPEC.md
  3D_PIPELINE.md
  LOCAL_EXECUTION_WINDOWS.md

assets/
  reference/
    README.md
  turnaround/
    README.md
    GENERATED_ASSETS.json

workflows/
  comfyui/
    elyna_hunyuan3d_shape.json

scripts/
  setup_hunyuan3d_checkpoint.ps1

PRODUCTION_STATUS.md
README.md
RELEASE_NOTES_v1.0.md
STRUCTURE.md
```

## ADN visuel

- Phénix Companion 3D premium
- visage mature, élégant et rassurant
- casque noir/or + microphone + marquage JS
- armure ivoire / bleu nuit / or
- emblème S sur la poitrine
- ailes iridescentes cyan → bleu électrique → violet → magenta → or
- jamais cartoon, kawaii, jouet, enfantin ou robot générique

Voir `docs/CHARACTER_SHEET.md`.

## Pipeline 3D

```text
Référence canonique
  ↓
Turnaround front / left / back / right
  ↓
Hunyuan3D 2.1 / ComfyUI
  ↓
GLB brut
  ↓
Blender : cleanup + retopo + UV + matériaux + rig
  ↓
Expressions / lipsync / animations
  ↓
VRM optimisé
  ↓
Three.js / React Three Fiber / Cockpit JS-Innov.IA
```

Le dépôt fournit maintenant un workflow ComfyUI exécutable :

`workflows/comfyui/elyna_hunyuan3d_shape.json`

Deux profils sont définis dans `config/comfyui_presets.json` :

- **diagnostic basse VRAM** : latent `1024`, batch `1`, steps `12`, CFG `5`, octree `128` ;
- **candidat production** : latent `2048`, batch `1`, steps `12`, CFG `5`, octree `128`.

Le preset 1024 sert à vérifier le pipeline et la géométrie avant toute montée en résolution. Le preset 2048 n’est pas considéré « validé » tant qu’un run réel n’a pas terminé sans erreur et que le GLB n’a pas passé la revue visuelle.

La documentation officielle Hunyuan3D 2.1 annonce environ **10 Go de VRAM pour la génération de forme seule**. ComfyUI peut utiliser l’offload mémoire, mais cela ne garantit pas qu’une configuration donnée sera stable sur une carte plus petite. Voir `docs/LOCAL_EXECUTION_WINDOWS.md`.

## Checkpoint

Le workflow attend :

`hunyuan_3d_v2.1.safetensors`

Le script :

`scripts/setup_hunyuan3d_checkpoint.ps1`

installe le checkpoint dans `ComfyUI/models/checkpoints/` et vérifie son SHA256 avant utilisation.

## Turnaround canonique attendu

```text
assets/turnaround/elyna_front.png
assets/turnaround/elyna_left.png
assets/turnaround/elyna_back.png
assets/turnaround/elyna_right.png
```

Ces fichiers ne doivent être ajoutés qu’après validation visuelle. Une vue miroir qui déplace le microphone ou les asymétries n’est pas acceptable.

Le registre actuel est `assets/turnaround/GENERATED_ASSETS.json`. Il indique que les vues ont été générées mais que les binaires doivent encore être uploadés et validés.

## Runtime cible

Le manifeste `config/elyna-3d.manifest.json` définit notamment :

- format runtime VRM
- `@pixiv/three-vrm`
- poids cible <= 15 MiB
- fallback 2D obligatoire
- états idle, listening, thinking, speaking, greeting, presenting, success et error
- expressions minimales `blink` et `aa`

## Assets existants sur Drive

Le kit source comprend notamment :

- full-body idle / wave / welcome / holograms
- bust idle / speaking / thinking
- animations idle, greeting, welcome, holograms et promise
- vidéos cinématiques et publicitaires
- `avatar_config.json`
- Character Sheet et guide d'intégration

Les vidéos sont des références d’animation ; elles ne doivent pas redéfinir la géométrie canonique du personnage.

## État de production

Voir `PRODUCTION_STATUS.md` pour distinguer clairement :

- ce qui est terminé ;
- ce qui est prêt à exécuter ;
- ce qui nécessite encore un run 3D réel ;
- ce qui bloque l’activation web de la 3D.

---

**JS-Innov.IA® — L’intelligence qui élève vos idées**  
© Julien Pagin / JS-Innov.IA
