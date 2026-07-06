# CounterWatch

A personal, fully-editable Overwatch counter-pick recommender. Pick the enemy team
and it ranks the heroes that best counter them — weighing not just how well you beat
them, but how hard they counter you back, plus synergy with your locked teammates.

The Python engine is small and stable; the **data files are the product** — you tune
them, the engine just reads them.

## Launch it

The app runs a small local web server (Python standard library only) and opens in your
browser at `http://127.0.0.1:8765`.

- **Windows, easiest:** double-click **`OW Strategiser.exe`** inside `ow_counterpick/`
  (rebuildable — not committed; see below).
- **Windows, no build:** double-click **`Launch OW Strategiser.bat`** in this folder.
- **Any platform:** run the server directly:
  ```bash
  cd ow_counterpick
  python server.py       # then open http://127.0.0.1:8765
  ```

To print a one-off ranked recommendation for the demo scenario without the web UI:
```bash
cd ow_counterpick
python engine.py
```

## Project layout

```
CounterWatch/
├─ Launch OW Strategiser.bat     # double-click launcher (uses your installed Python)
└─ ow_counterpick/               # the app
   ├─ engine.py                  # scoring engine (loads data, builds matrix, ranks)
   ├─ server.py                  # local web server + JSON API
   ├─ owstrat_launcher.py        # entry point the .exe is built from
   ├─ web/                       # browser UI (hero grid, team builder) + hero icons
   └─ data/                      # the editable data — this is the product
```

## The data files (edit these)

| File | What it holds |
|---|---|
| `data/heroes.json` | Hero registry: role, sub-role, mechanical tags, archetypes |
| `data/subroles.json` | The official sub-roles, their passives, implied tags |
| `data/matchup_rules.json` | Tag/sub-role rules that **auto-generate** the base matchup matrix |
| `data/matchup_overrides.json` | Famous specific matchups that override the rules |
| `data/synergies.json` | Pairwise combos + archetype coherence bonus |
| `data/preferences.json` | Your comfort weights + hard excludes |
| `data/config.json` | Scoring weights, role priority, carry multiplier |

## How scoring works

For each candidate hero `h`, given the enemy team `E` and your locked teammates `T`:

```
Score(h) =  alpha * Counter(h, E)      how well you beat their team (tank>support>dps weighted)
         -  delta * Countered(h, E)    how hard they counter you back
         +  beta  * Synergy(h, T)      fit with your locked teammates + comp coherence
         +  gamma * Comfort(h)         your personal preference nudge
```

Flag an enemy in `carry_targets` and it gets a `carry_multiplier`, so the engine leans
toward shutting *them* down specifically.

You don't hand-write ~2500 matchup cells: `matchup_rules.json` holds a few dozen rules
over tags and sub-roles that generate the base matrix, then `matchup_overrides.json`
stamps the well-known specific counters on top. Editing a rule re-tunes hundreds of
pairs at once; editing an override fixes one exactly.

## A note on the numbers

The matchup values (rule magnitudes and overrides) and some recent heroes' tags are a
tunable draft, not ground truth — they drift every balance patch. The *engine* is
patch-proof; the *numbers* are not. Re-tune after big changes. A couple of recent heroes
are still marked `_needs_review` in `data/heroes.json`.

## Rebuilding the .exe

The launcher `.exe` is a build artifact (gitignored). To rebuild it:
```bash
cd ow_counterpick
python -m pip install pyinstaller
python -m PyInstaller --onefile --name "OW Strategiser" owstrat_launcher.py
```
Then copy `dist/OW Strategiser.exe` back into `ow_counterpick/` (it reads the neighbouring
`data/` and `web/` folders at runtime, so it must sit beside them).
