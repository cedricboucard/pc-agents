# pc_agents — Les composants du PC se parlent

## Installation
```bash
pip install -r requirements.txt
ollama pull llama3.2:3b      # ou qwen2.5:3b, mistral:7b...
ollama serve                 # si pas déjà lancé
```

## Lancement
```bash
python main.py --demo        # tester sans stresser la machine
python main.py               # télémétrie réelle
python main.py --no-llm      # sans Ollama (répliques de secours)
python main.py --model qwen2.5:3b --turns 3 --no-typewriter
```

## Dialoguer avec les composants
Pendant que la surveillance tourne, tape directement dans le terminal :
```
Toi ▸ salut vous trois, ça va ?        # les trois répondent
Toi ▸ @gpu tu peux gérer un jeu en 4K ?  # le GPU répond, un collègue réagit
Toi ▸ /status                           # métriques actuelles
Toi ▸ /quit                             # quitter (ou Ctrl+C)
```
Les agents partagent une mémoire des dernières répliques (`HISTORY_SIZE` dans `config.py`)
et connaissent les métriques en temps réel : demande-leur comment ils vont pendant un `stress`.
Avec `--no-chat`, la saisie est désactivée.

## Modules
| Fichier | Rôle |
|---|---|
| `config.py` | Seuils, cooldowns, modèle LLM, rendu |
| `telemetry.py` | psutil / pynvml + mode démo |
| `personalities.py` | System prompts, couleurs, répliques de secours |
| `triggers.py` | Machine à états + anti-spam (EMA, hystérésis, cooldowns) |
| `llm.py` | Client Ollama + dialogue multi-agents |
| `renderer.py` | Rendu ANSI thread-safe |
| `main.py` | Orchestration (télémétrie / worker LLM) |

## Notes
- Température CPU : disponible sous Linux/macOS via psutil ; `None` sous Windows (les seuils de température sont alors ignorés pour le CPU).
- GPU : NVIDIA uniquement (pynvml). Sans GPU compatible, l'agent GPU est désactivé automatiquement.
- Pour ajouter un agent (ex. SSD, VENTILO) : créer un `Agent` dans `personalities.py`, un collecteur dans `telemetry.py` et des seuils dans `config.py`.
