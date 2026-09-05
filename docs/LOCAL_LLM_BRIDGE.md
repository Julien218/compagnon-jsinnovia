# Pont IA locale JS-Innov.IA — Ollama → AI Core

## Objectif

Utiliser `qwen3.5:4b` et `llama3.2:3b` installés sur le PC Windows depuis le Cockpit cloud, **sans exposer Ollama sur Internet**.

Architecture :

```text
Cockpit / AI Core (Railway)
        │
        │ file sécurisée Supabase
        ▼
jsinnovia-agent
        ▲
        │ HTTPS sortant uniquement
        │
Worker Windows JS-Innov.IA
        │
        ▼
Ollama 127.0.0.1:11434
```

Aucun NAT, port-forwarding, tunnel entrant ou ouverture du port `11434` n'est nécessaire.

## Modèles autorisés

Le worker refuse tout modèle autre que :

- `qwen3.5:4b` — modèle local principal ;
- `llama3.2:3b` — fallback local.

Le mode de raisonnement visible est désactivé (`think=false`).

## Jumelage

Railway possède une variable secrète dédiée `LOCAL_LLM_BRIDGE_KEY`. Ne jamais la committer ni la coller dans un chat, une capture d'écran ou une variable frontend.

Sur le PC Windows, enregistrer **la même valeur** dans la variable utilisateur `LOCAL_LLM_BRIDGE_KEY`, puis rouvrir PowerShell. La variable `JSINNOVIA_AGENT_URL` est optionnelle et vaut par défaut :

`https://jsinnovia-agent-production.up.railway.app`

Ollama doit rester :

`http://127.0.0.1:11434`

## Démarrage

Depuis la racine de `compagnon-jsinnovia` :

```powershell
.\scripts\start_local_ai_bridge.ps1
```

Pour voir les logs directement :

```powershell
.\scripts\start_local_ai_bridge.ps1 -Foreground
```

Le script vérifie d'abord `/api/tags`, refuse de démarrer si aucun modèle autorisé n'est présent, arrête un ancien worker du même type puis lance le bridge en arrière-plan.

## Sécurité

- Ollama n'écoute pas publiquement ;
- le PC initie toutes les connexions vers Railway ;
- chaque job est loué temporairement à un worker identifié ;
- le worker n'exécute aucune commande shell reçue du cloud ;
- les payloads autorisent uniquement des messages de chat et quelques options bornées ;
- les jobs et workers sont stockés dans des tables Supabase avec RLS activée et sans accès anon/authenticated ;
- les endpoints worker utilisent une clé distincte de la clé publique du site et de la clé OpenAI.

## FinOps

Le worker retourne :

- `prompt_eval_count` ;
- `eval_count` ;
- durées Ollama ;
- modèle réellement utilisé.

AI Cost Control enregistre l'appel avec `provider=ollama` et un coût API de `0`. Le coût technique local (électricité, GPU, amortissement) reste distinct et ne doit être ajouté à la refacturation qu'après définition explicite de la politique FinOps locale.
