# Elyna 3D — Quickstart Windows

Ce raccourci lance la phase **génération de forme** du Compagnon phénix Elyna avec Hunyuan3D 2.1 / ComfyUI.

## Commande recommandée

Depuis la racine du dépôt `compagnon-jsinnovia` :

```powershell
.\scripts\bootstrap_elyna_3d.ps1 -Preset diagnostic
```

Le bootstrap réalise automatiquement, dans cet ordre :

1. vérification de l’installation ComfyUI ;
2. installation ou vérification SHA256 de `hunyuan_3d_v2.1.safetensors` ;
3. détection de l’API ComfyUI sur `127.0.0.1:8188` ;
4. démarrage du launcher NVIDIA portable si ComfyUI n’est pas déjà lancé ;
5. attente de disponibilité de l’API ;
6. vérification des nœuds Hunyuan3D requis ;
7. utilisation de la référence canonique `00_phenix_companion_officiel_reference.png` ou du fichier local historique `elyna-reference.png` ;
8. soumission du workflow diagnostic 1024 ;
9. attente de la fin du prompt ;
10. recherche et affichage du ou des nouveaux fichiers `.glb`.

## Si le diagnostic 1024 réussit

Examiner visuellement le GLB. Continuer uniquement si :

- la silhouette reste celle du phénix officiel ;
- le casque et le microphone sont présents ;
- l’emblème central est préservé ;
- la tête, les bras, les jambes, les ailes et la queue sont séparables/nettoyables ;
- aucun changement de personnage ou style enfantin n’a été introduit.

Ensuite seulement :

```powershell
.\scripts\bootstrap_elyna_3d.ps1 -Preset production
```

Le mode production passe la résolution de forme à 2048. Il peut échouer sur une carte à VRAM limitée ; la réussite du diagnostic 1024 ne garantit pas la réussite du 2048.

## Important

Le `.glb` produit à cette étape est **un candidat de reconstruction brut**. Il n’est pas encore le produit final.

Il reste ensuite :

1. Blender : nettoyage et correction de silhouette ;
2. retopologie ;
3. séparation logique casque/micro, armure, ailes, queue et membres ;
4. UV et matériaux PBR ;
5. rig + skinning ;
6. contrôles ailes/queue ;
7. expressions `blink` et `aa` ;
8. animations d’états ;
9. export VRM ;
10. validation du VRM et smoke tests web desktop/mobile.

Ne jamais renommer un GLB brut en `.vrm` pour contourner les validations du site.
