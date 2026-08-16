# Compagnon JS-Innov.IA — Elyna 3D & Assets Premium

**Phénix Companion officiel** de la marque **JS-Innov.IA**  
Créé par **Julien Pagin** — www.jsinnovia.com

Ce dépôt devient la **source de vérité technique** du Compagnon JS-Innov.IA / Elyna : identité, règles visuelles, pipeline 3D, manifests runtime et contrat des assets.

## Référence canonique

La référence visuelle officielle reste :

- `00_phenix_companion_officiel_reference.png`
- Google Drive file ID : `1y96GHd7_du62CNAIS9fZCUZsra7xKAto`

Les médias binaires sont actuellement conservés dans Google Drive. GitHub stocke les spécifications et fichiers techniques ; les vidéos lourdes doivent rester sur Drive ou être publiées via Releases/LFS.

## Structure

```text
config/
  elyna-3d.manifest.json

docs/
  CHARACTER_SHEET.md
  TURNAROUND_SPEC.md
  3D_PIPELINE.md

assets/
  reference/
    README.md
  turnaround/
    README.md

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

Configuration locale de départ validée sur RTX A3000 6 Go :

- Hunyuan3D 2.1
- latent `2048`
- batch `1`
- steps `12`
- CFG `5`
- octree `128`

Voir `docs/3D_PIPELINE.md` et `docs/TURNAROUND_SPEC.md`.

## Turnaround canonique attendu

```text
assets/turnaround/elyna_front.png
assets/turnaround/elyna_left.png
assets/turnaround/elyna_back.png
assets/turnaround/elyna_right.png
```

Ces fichiers ne doivent être ajoutés qu'après validation visuelle. Une vue miroir qui déplace le microphone ou les asymétries n'est pas acceptable.

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

Les vidéos sont des références d'animation ; elles ne doivent pas redéfinir la géométrie canonique du personnage.

---

**JS-Innov.IA® — L’intelligence qui élève vos idées**  
© Julien Pagin / JS-Innov.IA
