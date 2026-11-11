# pc_agents

**Les composants de ton PC prennent la parole.**
Le CPU, le GPU et la RAM sont surveillés en temps réel. Quand quelque chose se passe (pic de charge, surchauffe, retour au calme), ils se disputent dans ton terminal, chacun avec sa personnalité, grâce à un LLM local (Ollama). Tu peux aussi leur parler.

```
── PIC DE CHARGE · CPU · charge 95%, 78°C, 4.3 GHz ──
15:39:18 CPU │ Sérieusement, j'ai dépassé les 4 GHz et je sens ma température monter !
15:39:20 GPU │ Normal, je suis le vrai moteur ici : j'ai besoin de plus de watts !
15:39:22 RAM │ Fermez des onglets, par pitié... j'étouffe...
```
*(exemple de sortie ; les répliques sont générées à chaque fois par le modèle)*

## Fonctionnalités

- **Télémétrie temps réel** : charge, température et fréquence via `psutil` (CPU, RAM, swap) et `pynvml` (GPU NVIDIA).
- **Trois personnalités** définies par des system prompts : le CPU *gestionnaire stressé*, le GPU *impulsif, puissance brute*, la RAM *étouffée et claustrophobe*.
- **Déclenchement sans spam** : lissage, confirmation sur plusieurs mesures, hystérésis et cooldowns (voir plus bas).
- **Dialogues multi-agents** : chaque réplique est un appel LLM distinct avec le prompt de l'agent qui parle et une mémoire partagée de la conversation.
- **Chat interactif** : écris au trio, ou interpelle un composant avec `@cpu`, `@gpu`, `@ram`.
- **Rendu terminal** : couleurs ANSI par composant, effet machine à écrire, retour à la ligne adapté à la largeur de la fenêtre.
- **Mode secours** : sans Ollama, les agents répondent avec des répliques préécrites ; le programme ne plante jamais.
- **Mode démo** : un scénario simulé (calme → pic → surchauffe → repos) pour tout tester sans stresser la machine.

## Prérequis

- Python 3.9 ou plus
- [Ollama](https://ollama.com) avec un modèle installé (testé avec `llama3.2:3b`)
- Linux recommandé : la température CPU est lue via `psutil.sensors_temperatures()`, indisponible sous Windows
- Optionnel : GPU NVIDIA avec le pilote propriétaire (vérifie que `nvidia-smi` répond)

## Installation

```bash
git clone https://github.com/<ton-pseudo>/pc_agents.git
cd pc_agents

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Ollama (Linux) puis un modèle
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b
```

Sur Ubuntu, `python3-venv` peut manquer : `sudo apt install python3-venv`.
Si la température CPU n'apparaît pas : `sudo apt install lm-sensors && sudo sensors-detect`.

## Utilisation

```bash
python main.py                 # télémétrie réelle + Ollama + chat
python main.py --demo          # scénario simulé
python main.py --no-llm        # répliques de secours uniquement
python main.py --no-chat       # surveillance seule, sans saisie clavier
python main.py --model qwen2.5:7b --turns 3 --no-typewriter
```

| Option | Rôle |
|---|---|
| `--demo` | Utilise une télémétrie simulée |
| `--no-llm` | N'appelle pas Ollama |
| `--no-chat` | Désactive la saisie clavier |
| `--model` / `--url` | Modèle et adresse Ollama (défaut : `llama3.2:3b`, `http://localhost:11434`) |
| `--interval` | Secondes entre deux mesures (défaut : 1) |
| `--turns` | Répliques par échange (défaut : 4) |
| `--no-typewriter` | Affiche les répliques d'un coup |

Pour lancer le tout en un mot, ajoute un alias dans `~/.bashrc` :

```bash
alias pcparle="$HOME/pc_agents/.venv/bin/python $HOME/pc_agents/main.py"
```

### Parler aux composants

Pendant que la surveillance tourne, écris directement dans le terminal :

```
Toi ▸ salut vous trois, ça va ?          # les trois répondent
Toi ▸ @gpu tu peux gérer un jeu en 4K ?  # le GPU répond, un collègue réagit
Toi ▸ /status                            # métriques actuelles
Toi ▸ /help    /quit                     # aide, quitter (Ctrl+C marche aussi)
```

Les agents connaissent les métriques en temps réel et se souviennent des dernières répliques : lance `stress --cpu 8` dans un autre terminal, puis demande à `@cpu` comment il va.

## Comment ça marche

```
 télémétrie ──► EventEngine ──► file de jobs ──► DialogueGenerator ──► Renderer
 (psutil,       (seuils,           ▲              (Ollama, 1 appel       (ANSI)
  pynvml)        anti-spam)        │               par réplique)
                                clavier (chat)
```

Trois threads : la boucle de télémétrie ne bloque jamais, même quand le LLM est lent ; un worker génère les dialogues ; un thread lit le clavier.

### Anti-spam

| Mécanisme | Effet |
|---|---|
| Lissage exponentiel (EMA) de la charge | Un pic d'une seconde est ignoré |
| Confirmation sur N mesures consécutives | 3 pour un pic, 5 pour le retour au repos (8 pour la RAM) |
| Hystérésis | Seuil haut ≠ seuil bas, plus un seuil de refroidissement |
| Machine à états par composant | `calm → stressed → hot → calm` : pas de répétition d'un même événement |
| Cooldowns | Par événement (45 s, 60 s, 30 s) et global (20 s) ; la surchauffe contourne le global |
| Retour au repos conditionnel | Annoncé seulement si un pic ou une surchauffe l'avait été |
| File bornée | Au-delà de 3 événements en attente, les nouveaux sont ignorés |

### Seuils par défaut (`config.py`)

| | Pic de charge | Repos | Surchauffe | Refroidi |
|---|---|---|---|---|
| CPU | 85 % | 30 % | 85 °C | 70 °C |
| GPU | 90 % | 15 % | 82 °C | 65 °C |
| RAM | 88 % | 70 % | n/a | n/a |

### Personnalités

Les system prompts sont dans `personalities.py`. Chaque agent reçoit aussi des règles communes (une réplique, 25 mots max, pas de narration, aucun chiffre inventé) et son **état réel** qualifié (« au calme », « en surchauffe »…) pour éviter qu'il dramatise.

## Structure du projet

```
pc_agents/
├── main.py            # orchestration (threads, arguments, chat)
├── config.py          # seuils, cooldowns, paramètres LLM, rendu
├── telemetry.py       # collecteurs psutil / pynvml + mode démo
├── triggers.py        # détection d'événements et anti-spam
├── personalities.py   # system prompts, couleurs, répliques de secours
├── llm.py             # client Ollama + orchestration des dialogues
├── renderer.py        # affichage ANSI thread-safe
└── requirements.txt
```

## Ajouter un composant

1. **`telemetry.py`** : crée un collecteur avec `name` et `read() -> Sample`, puis ajoute-le à `RealTelemetry` et à `DemoTelemetry`.
2. **`config.py`** : ajoute ses seuils dans `THRESHOLDS`.
3. **`personalities.py`** : crée un `Agent` (prompt, couleur ANSI, répliques de secours) et ajoute-le à `AGENTS`.

## Limites connues

- Les GPU AMD et Intel ne sont pas pris en charge (NVIDIA uniquement) ; l'agent GPU est alors désactivé automatiquement.
- Sous Windows, la température CPU n'est pas disponible ; le code est conçu pour Linux et n'y a pas été testé.
- Avec un petit modèle (3 milliards de paramètres), les répliques peuvent être approximatives. Un modèle plus gros (`qwen2.5:7b`) suit mieux les personnalités, au prix de la vitesse.
- En mode `--demo`, la télémétrie est simulée et ne réagit pas à tes actions.
- Si un événement survient pendant que tu tapes, la ligne de saisie est effacée à l'écran (ton texte est conservé).

## Licence

MIT, voir le fichier `LICENSE`.
