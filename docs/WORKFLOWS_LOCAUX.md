# Workflows IA locaux — état vérifié

Dernière vérification réelle : 25 août 2026 (Europe/Brussels).

## État du moteur local

- ComfyUI répond sur `http://127.0.0.1:8188`.
- Version ComfyUI mesurée : `0.27.0`.
- Python mesuré : `3.13.12`.
- GPU mesuré : `NVIDIA RTX A3000 Laptop GPU` (CUDA).
- VRAM totale annoncée par ComfyUI : `6 441 926 656` octets.
- FFmpeg mesuré : `8.1.2-full_build-www.gyan.dev`.

Preuves Cockpit :

- recherche locale des workflows : `890d4963-16a7-4323-9fb4-e1d98f5bb428` ;
- santé ComfyUI : `8699cb73-ecd1-412a-abc8-a882d86485c9` ;
- version FFmpeg : `0044edc7-bb2e-4685-a89a-abf5b29cc3eb`.

## Workflows présents

Le dossier `workflows/comfyui` contient actuellement :

- `avatar_hunyuan3d_shape_api.json` ;
- `elyna_hunyuan3d_shape.json` ;
- `elyna_hunyuan3d_shape_api.json`.

La configuration `config/comfyui_presets.json` référence le checkpoint
`hunyuan_3d_v2.1.safetensors` et le workflow
`workflows/comfyui/elyna_hunyuan3d_shape.json`.

La présence du nom d’un checkpoint dans cette configuration ne prouve pas que le fichier modèle est installé. Il faut vérifier le modèle et les nœuds ComfyUI avant toute génération.

## MiniMax H3

Aucun fichier de workflow MiniMax H3 n’a été trouvé dans les racines locales autorisées (`Documents`, `Downloads`, `Videos`) lors de la dernière recherche. Cette absence est un résultat de diagnostic, pas une preuve que MiniMax H3 est indisponible via une API distante.

## Procédure de contrôle

1. Ouvrir le Cockpit Windows ; NOVA locale démarre automatiquement ComfyUI lorsqu’une installation compatible est détectée.
2. Vérifier que ComfyUI répond sur le port `8188`.
3. Lancer d’abord le preset `diagnostic_low_vram`.
4. Conserver le `tool_run` ou l’identifiant de file ComfyUI et le chemin exact du fichier de sortie.
5. Ne passer au preset `production_shape` qu’après validation du diagnostic.
6. Analyser tout média exporté avec FFprobe avant de le présenter comme livrable.

## Travail encore nécessaire

- vérifier la présence réelle du checkpoint Hunyuan3D et de tous les nœuds requis ;
- effectuer une génération de diagnostic et conserver le fichier produit ;
- valider la retopologie, le rigging, les expressions, le skinning et l’export VRM ;
- ajouter ou importer un workflow MiniMax H3 si ce moteur doit être utilisé ;
- tester de bout en bout la création, l’édition, la génération, l’export et l’automatisation.

Tant que ces sorties ne sont pas produites et analysées, l’avatar et la campagne vidéo restent en cours. Aucun résultat ne doit être simulé.
