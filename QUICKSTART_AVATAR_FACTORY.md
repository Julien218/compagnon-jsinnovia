# Avatar Factory — validation locale

## Objectif
Obtenir un **candidat 3D GLB riggé et animé (idle)** automatiquement à partir d'une image de référence, puis le valider humainement dans le Cockpit avant publication.

## 1. Préparer la référence
Pour le pilote Vaincriez, copie l'image approuvée ici :

`characters/vaincriez-canary/reference.png`

Le fichier doit être une vraie image PNG/JPG/WebP et faire plus de 10 KB.

## 2. Démarrer ComfyUI
ComfyUI doit répondre sur :

`http://127.0.0.1:8188`

Le checkpoint attendu est :

`ComfyUI/models/checkpoints/hunyuan_3d_v2.1.safetensors`

## 3. Vérifier Blender
`blender.exe` doit être disponible dans le `PATH`, ou définir :

```powershell
$env:BLENDER_EXE='C:\Program Files\Blender Foundation\Blender\blender.exe'
```

## 4. Préflight
Depuis la racine du dépôt :

```powershell
.\scripts\preflight_avatar_factory.ps1
```

Le préflight vérifie Python, GPU, Blender, checkpoint + SHA256, API/nœuds ComfyUI, référence, disque et contrat du dépôt.

## 5. FinOps central
Pour synchroniser automatiquement les coûts locaux vers le Cockpit :

```powershell
$env:COCKPIT_URL='https://cockpit.jsinnovia.com'
$env:FINOPS_INGEST_KEY='<secret configuré côté Cockpit/Railway>'
```

Le secret ne doit jamais être commité.

## 6. Démarrer l'agent

```powershell
.\scripts\start_avatar_factory.ps1
```

API locale : `http://127.0.0.1:8791`

## 7. Lancer depuis le Cockpit
Ouvre **Avatar Factory**, vérifie :

- client : `olivier` pour le pilote si applicable ;
- entité/société/ASBL correcte ;
- projet ;
- personnage : `vaincriez-canary` ;
- référence : `characters/vaincriez-canary/reference.png` ;
- preset : `diagnostic` pour la RTX A3000 6 Go.

Clique **Lancer la production**.

Le pipeline exécute :

`reference QA → Hunyuan3D/ComfyUI → GLB brut → Blender rig/idle → runtime QA → validation humaine`

## 8. Validation
Le candidat final apparaît dans le dossier :

`runtime/avatar-factory/jobs/<job_id>/avatar-candidate.glb`

Le Cockpit affiche le statut, le rapport QA, les événements et les coûts. Tu peux **Valider** ou **Refuser** le candidat.

## Limite volontaire de cette version
Le produit de validation est un **GLB animé**. L'export VRM final, les visèmes/lipsync et la bibliothèque complète d'animations doivent être activés après validation visuelle du personnage et du rig de base. Cela évite de construire toute la couche comportementale sur un mesh non validé.
