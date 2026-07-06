# OW Counter-Pick Engine

A personal, fully-editable counter-pick recommender. The Python engine is small and stable; the **data files are the product** — you tune them, the engine just reads them.

## Run it

```bash
python3 engine.py
```

Prints a ranked recommendation for the demo scenario at the bottom of `engine.py`. Edit that `state` dict to match a real game.

## How scoring works

For each candidate hero `h`, given the enemy team `E` and your locked teammates `T`:

```
Score(h) =  alpha * Counter(h, E)      how well you beat their team (tank>support>dps weighted)
         -  delta * Countered(h, E)    how hard they counter you back  <- the term most tools forget
         +  beta  * Synergy(h, T)      fit with your locked teammates + comp coherence
         +  gamma * Comfort(h)         your personal preference nudge
```

An enemy you flag in `carry_targets` gets a `carry_multiplier`, so the engine leans toward shutting *them* down specifically.

## The files (edit these)

| File | What it holds | How often it changes |
|---|---|---|
| `data/heroes.json` | Registry: role, **subrole**, mechanical tags, archetypes | Per roster/patch |
| `data/subroles.json` | The 10 official sub-roles, their passives, implied tags | Rarely |
| `data/matchup_rules.json` | Tag/sub-role rules that **auto-generate** the base matrix | When you refine logic |
| `data/matchup_overrides.json` | Famous specific matchups, override the rules | Per patch |
| `data/synergies.json` | Pairwise combos + archetype coherence bonus | Rarely |
| `data/preferences.json` | **Yours**: comfort weights + hard excludes | Whenever |
| `data/config.json` | Weights, role priority, carry multiplier | Tuning |

## The matchup matrix: rules + overrides

You don't hand-write ~2500 cells. `matchup_rules.json` holds a few dozen rules over **tags and sub-roles**, e.g. "dive_threat + high_mobility beats low_mobility + backline → +2". The engine applies every matching rule to every hero pair and sums them. Then `matchup_overrides.json` stamps the famous specific counters on top. Editing a rule re-tunes hundreds of pairs at once; editing an override fixes one exactly.

The new sub-role system gives these rules a real mechanical basis instead of vibes — e.g. crit-reliant Sharpshooters are penalised into Bruiser tanks (crit-damage reduction), CC/boop value drops into Stalwart tanks (knockback resistance), divers lose value into Recon DPS (wallhacks on low-HP escapees). Those are encoded as sub-role rules already.

## Before you trust the numbers — read this

This scaffold was built against the **Season 1–2 2026 sub-role data**. Two parts are snapshots, not ground truth:

1. **`_needs_review` heroes** in the registry (Domina, Hazard, Anran, Vendetta, Emre, Sierra, Jetpack Cat, Mizuki, Wuyang, Freja) — recent additions whose tags I couldn't verify. Sierra's role *and* subrole are unconfirmed. Fill these in from the in-game Advanced Info Panel.
2. **Matchup values** — both the rule magnitudes and the overrides drift every balance patch. Treat them as a sensible first draft and re-tune after big changes. The *engine* is patch-proof; the *numbers* are not.

## Common edits

- **Add a hero**: one entry in `heroes.json` (role, subrole, tags). Rules pick it up automatically; add overrides only for its famous matchups.
- **Change role priority**: `config.json` → `role_weights`.
- **"I won't play X"**: add to `preferences.json` → `exclude`.
- **"My duo always plays Lucio"**: it already feeds synergy via `my_team`; bump the relevant pair in `synergies.json`.
- **Whole-comp suggestions instead of one slot**: loop `recommend()` over open slots, or set `my_role_lock: null` to score all roles.

## Inspect the generated matrix

```python
from engine import load_all, build_matrix
data = load_all(); M = build_matrix(data)
print(M["genji"]["zenyatta"])   # how hard Genji counters Zen
```

## Sensible next steps (deferred by design)

- **Map context** — biggest missing input; counters swing by geometry. Add a map archetype to `state` and a small modifier layer.
- **Counter-anticipation** — one-ply lookahead: "if I pick this, what's their best swap, am I still ahead?"
- **Faster input** — fast manual entry (portraits/hotkeys). Note: automated screen-reading of the scoreboard sits in risky ToS/anti-cheat territory — resolve that before relying on it.
