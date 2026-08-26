# Avatar Factory — validation locale

## Objectif
Obtenir un **candidat 3D GLB riggé et animé (idle)** automatiquement à partir d'une image déposée dans le Cockpit, puis le valider humainement avant publication.

## 1. Démarrer ComfyUI
ComfyUI doit répondre sur :

`http://127.0.0.1:8188`

Les checkpoints attendus sont :

`ComfyUI/models/checkpoints/hunyuan_3d_v2.1.safetensors`

`ComfyUI/models/checkpoints/hunyuan3d-dit-v2-mv_fp16.safetensors`

Le premier sert au parcours de compatibilité à une image. Le second est
obligatoire pour le parcours recommandé à quatre vues : `reference_path`
(face), `left_reference_path`, `back_reference_path` et
`right_reference_path`. Le moteur multivue utilise une graine stable par
défaut (`2182026`) afin qu'un même jeu de quatre images soit reproductible.

## 2. Vérifier Blender
`blender.exe` doit être disponible dans le `PATH`, ou définir :

```powershell
$env:BLENDER_EXE='C:\Program Files\Blender Foundation\Blender\blender.exe'
```

## 3. Préflight
Depuis la racine du dépôt :

```powershell
.\scripts\preflight_avatar_factory.ps1
```

Le préflight vérifie Python, GPU, Blender, checkpoint + SHA256, API/nœuds ComfyUI, disque et contrat du dépôt. **L'absence d'image de référence n'est plus bloquante** : elle peut être envoyée ensuite depuis le Cockpit.

Pour tester volontairement une image locale précise pendant le préflight :

```powershell
.\scripts\preflight_avatar_factory.ps1 -ReferencePath 'C:\chemin\reference.png'
```

## 4. FinOps central
Pour synchroniser automatiquement les coûts locaux vers le Cockpit :

```powershell
$env:COCKPIT_URL='https://cockpit.jsinnovia.com'
$env:FINOPS_INGEST_KEY='<secret configuré côté Cockpit/Railway>'
```

Le secret ne doit jamais être commité.

## 5. Démarrer Avatar Factory

```powershell
.\scripts\start_avatar_factory.ps1
```

Services locaux :

- orchestrateur Avatar Factory : `http://127.0.0.1:8791`
- réception sécurisée des images de référence : `http://127.0.0.1:8792`

Le service 8792 n'accepte que PNG/JPEG/WebP, contrôle la signature réelle du fichier, limite les images à 12 Mo et les stocke dans le workspace local avec un nom unique.

## 6. Lancer depuis le Cockpit
Ouvre **Avatar Factory**. Les deux indicateurs **Agent 8791** et **Upload 8792** doivent être connectés.

Renseigne le client, la société/ASBL, le projet et le personnage, puis
**dépose directement les quatre images dans le Cockpit** : face, arrière,
gauche et droite. Aucun chemin Windows ni copie manuelle vers ComfyUI n'est
nécessaire. Les quatre images doivent représenter exactement le même
personnage, avec la même tenue, une posture et un cadrage cohérents.

Pour le pilote avec une RTX A3000 6 Go, conserve le preset `diagnostic 1024` pour le premier run.

Quand l'aperçu indique que la référence est prête, clique **Lancer la production**.

Le pipeline exécute :

`upload Cockpit → reference QA → Hunyuan3D mono ou multivue/ComfyUI → GLB brut → nettoyage prudent des fragments → Blender rig/idle → runtime QA → validation humaine`

Le nettoyage ne supprime des îlots détachés que si une pièce principale
représente au moins 80 % du maillage. Le rapport QA conserve le nombre de
composants et de sommets retirés. Aucun candidat n'est publié automatiquement.

## 7. Validation
Le candidat final apparaît dans :

`runtime/avatar-factory/jobs/<job_id>/avatar-candidate.glb`

Le Cockpit affiche le statut, le rapport QA, les événements et les coûts. Tu peux **Valider** ou **Refuser** le candidat. Un refus conserve l'historique et les coûts du run pour comparaison.

## Fallback local
Le pipeline conserve la possibilité de fournir un `reference_path` local pour le diagnostic ou le développement, mais le parcours utilisateur normal passe désormais par l'upload depuis le Cockpit.

## Limite volontaire de cette version
Le produit de validation est un **GLB animé candidat**. L'export VRM final, les visèmes/lipsync et la bibliothèque complète d'animations sont activés après validation visuelle du personnage et du rig de base afin de ne pas construire la couche comportementale sur un mesh non validé.
