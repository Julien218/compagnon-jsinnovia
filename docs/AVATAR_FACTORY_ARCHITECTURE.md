# Avatar Factory — architecture de production

## Objectif
Transformer le pipeline Elyna existant en moteur multi-personnages pilotable par le Cockpit JS-Innov.IA, tout en conservant les calculs lourds sur la station Windows locale.

## Pipeline
`Cockpit -> Avatar Factory API -> Local Agent -> Director -> Turnaround QA -> ComfyUI/Hunyuan3D -> 3D QA -> Blender automation -> Rig -> Animations/Lipsync -> Export GLB/VRM -> Runtime QA -> Validation humaine -> Publication`

## Principes
- multi-client et multi-personnage ;
- isolation stricte client / entité / projet / job ;
- traitements GPU/CPU lourds exécutés localement par défaut ;
- cloud uniquement selon politique de routage ;
- checkpoints humains après turnaround et avant publication ;
- aucun GLB brut considéré comme produit final ;
- journalisation de chaque tentative, durée, consommation et artefact ;
- FinOps obligatoire sur chaque job.

## Agents
1. Director Agent — analyse référence, ADN et contraintes.
2. Turnaround Agent — prépare front/left/back/right et contrôle la cohérence.
3. 3D Generator Agent — pilote ComfyUI/Hunyuan3D.
4. 3D QA Agent — valide géométrie et conformité.
5. Blender Agent — cleanup, optimisation, UV/matériaux et préparation runtime.
6. Rig Agent — squelette, skinning, yeux/bouche/appendices.
7. Animation Agent — idle, greeting, listening, thinking, speaking, presenting, success/error.
8. Export Agent — GLB/VRM et variantes web.
9. Runtime QA Agent — poids, rig, animations, compatibilité et performance.
10. Publisher Agent — publication uniquement après validation.

## Routage compute
Chaque étape déclare `local`, `cloud` ou `hybrid`. Le routeur compare capacité VRAM/RAM, temps estimé, coût estimé et qualité requise. La station locale reste le choix par défaut lorsqu'elle satisfait le SLA.

## Cockpit
Le module Avatar Factory doit exposer : nouveau projet, référence, ADN, statut pipeline, logs, previews, validations, versions, artefacts, temps machine, coût de production, prix/marge et bouton de publication.

## FinOps
Chaque étape émet des événements normalisés vers le moteur FinOps commun. Voir `config/finops-policy.schema.json`.
