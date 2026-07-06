# Build prompt — Overwatch counter-pick engine

> Paste this whole file into Codex. If a prior scaffold already exists in the repo, treat this as the authoritative spec: reconcile against it, prefer this spec where they conflict, but preserve any hero `tags` or matchup values already filled in.

## Goal

Build a small, fully data-driven Overwatch counter-pick recommender. Given an enemy team comp, my locked teammates, and an open slot, it ranks which hero I should play. The engine must be patch-proof; all volatile game knowledge lives in editable JSON, never in code.

## Hard constraints

- Python 3.10+, **standard library only** (no pip installs). `json`, `pathlib` only.
- All game data in `./data/*.json`. The engine reads data; it never hardcodes heroes or matchup numbers.
- `python engine.py` must run with zero arguments and print a ranked recommendation for a demo scenario.
- Code must be readable and commented — I will hand-edit it.
- Use stable string slugs as hero IDs everywhere (e.g. `soldier76`, `junker_queen`), never display names.

## File layout

```
data/
  heroes.json            # registry: role, subrole, tags, archetypes
  subroles.json          # the 10 official sub-roles, passives, implied tags
  matchup_rules.json     # tag/subrole rules that AUTO-GENERATE the base matrix
  matchup_overrides.json # famous specific matchups, override the rules
  synergies.json         # pairwise combos + archetype coherence
  preferences.json       # my comfort weights + hard excludes
  config.json            # weights, role priority, carry multiplier
engine.py
README.md
```

## Scoring (implement exactly)

For each candidate hero `h`, enemy team `E`, my locked teammates `T`:

```
Score(h) =  alpha * Counter(h, E)
         -  delta * Countered(h, E)     # being-countered-back penalty — DO NOT OMIT
         +  beta  * Synergy(h, T)
         +  gamma * Comfort(h)

Counter(h, E)   = sum over e in E:  M[h][e] * role_weight(e.role) * carry_mult(e)
Countered(h, E) = sum over e in E:  M[e][h] * role_weight(e.role) * carry_mult(e)
```

- `M[a][b]` is the directional matchup value (−3..+3, positive = a beats b).
- `role_weight` applies a tank > support > dps priority to each enemy.
- `carry_mult` is applied to any enemy listed in `carry_targets` (else 1.0), so the engine leans toward shutting down whoever is popping off.

## Engine behaviour

1. **Load** all JSON, stripping any key beginning with `_` (those are comments).
2. **Merge** each hero's sub-role-implied tags into its own tag set → effective tags used by rules.
3. **Build matrix** `M`: for every ordered hero pair, sum the `value` of every rule whose `attacker` conditions match A and `defender` conditions match B; clamp to `config.matrix_clamp`. Then apply `matchup_overrides.json` on top (overrides replace the generated value for that exact pair). A rule condition matches if the hero satisfies ALL of the listed `role` / `subrole` / `archetype` / `tags` constraints; an absent/empty condition matches anything.
4. **Synergy**: pairwise bonuses (symmetric) against locked teammates, plus a coherence bonus if the candidate's archetype matches the dominant archetype among locked teammates.
5. **Recommend**: candidate pool = all heroes filtered by `my_role_lock` (if set), minus `preferences.exclude`, minus heroes already in `my_team`. Score each, sort descending, return top N as dicts exposing the component breakdown (counter / countered / synergy / comfort), and print a readable table in the demo.

## Game data to build against (verified, current as of the 2026 sub-role relaunch)

Overwatch's Season 1 relaunch replaced the old single role-passive with **sub-roles**, each carrying a gameplay passive. Use this taxonomy as the canonical mid-level classification — it is an in-game property of each hero. Encode the passive's mechanical effect as matchup rules where relevant (noted below).

**Sub-roles + passives:**
- Tank — **Stalwart**: reduces knockbacks/slows. **Initiator**: airborne/movement grants heal-over-time. **Bruiser**: reduces critical damage taken; +move speed below 50% HP.
- DPS — **Flanker**: health packs restore extra HP. **Recon**: detect enemies below half HP through walls after damaging them. **Sharpshooter**: critical hits reduce movement-ability cooldowns. **Specialist**: eliminating an enemy briefly boosts reload speed.
- Support — **Tactician**: retains excess ultimate charge after ulting. **Medic**: healing allies also self-heals (25%). **Survivor**: using a movement ability triggers passive HP regen.

**Hero → sub-role assignments:**
- Stalwart: Reinhardt, Sigma, Ramattra, Junker Queen, Domina, Hazard
- Initiator: D.Va, Winston, Doomfist, Wrecking Ball
- Bruiser: Mauga, Orisa, Roadhog, Zarya
- Flanker: Genji, Tracer, Reaper, Venture, Anran, Vendetta
- Recon: Echo, Pharah, Sombra, Freja
- Sharpshooter: Widowmaker, Hanzo, Ashe, Cassidy, Sojourn
- Specialist: Soldier: 76, Mei, Bastion, Junkrat, Symmetra, Torbjorn, Emre
- Tactician: Ana, Baptiste, Lucio, Zenyatta, Jetpack Cat
- Medic: Kiriko, Mercy, Moira, Lifeweaver
- Survivor: Brigitte, Illari, Juno, Mizuki, Wuyang
- Sierra: newest hero — role and subrole UNCONFIRMED (released after these lists). Include with `subrole: null`.

**Encode at least these sub-role-passive rules** (the mechanical basis for counters):
- crit-reliant Sharpshooter into a Bruiser tank → negative (crit-damage reduction)
- CC/knockback-heavy attacker into a Stalwart tank → negative (knockback/slow resistance)
- diver into a Recon DPS → slightly negative (wallhacks on low-HP escapees)
- anti-heal attacker into a self-sustaining Medic / big sustain tank → positive

Plus the archetypal rules: hitscan/long-range punishes floaty backline; dive eats immobile backline; anti-dive (e.g. Brigitte) shuts down divers; brawl beats poke in tight geometry; poke kites brawl on open sightlines; barrier-piercers negate shields; anti-tank DPS melt tanks.

## Correctness + honesty requirements

- For recent heroes whose kit/tags can't be verified — **Domina, Hazard, Anran, Vendetta, Emre, Sierra, Jetpack Cat, Mizuki, Wuyang, Freja** — set role/subrole as given above but leave `tags`/`archetypes` minimal and add a `"_needs_review"` note. Do NOT invent detailed kits for them.
- Matchup values (rules and overrides) are a reasonable **first draft only**; they drift every balance patch. Add a clear note in `README.md` that the engine is patch-proof but the numbers are a snapshot to re-tune. Do not present them as authoritative.
- Keep the being-countered-back (`delta`) term — it's the whole point of "net advantage, not raw counter value."

## Acceptance criteria

- `python engine.py` prints a ranked table for a demo where the enemy runs a dive comp (e.g. Winston / Genji / Sombra / Lucio / Kiriko), my tank+supports are locked, I fill DPS, and Genji is flagged as a carry. Top picks should be sensible anti-dive answers (Mei / Reaper / Cassidy range).
- Adding a new hero requires editing only `heroes.json` (rules pick it up automatically; overrides optional).
- Changing role priority, comfort, or excludes requires editing only JSON, never `engine.py`.
- `README.md` documents the scoring formula, every data file, the edit workflow, and the staleness caveats.

## Stretch goals (phase 2 — build only if asked, but leave clean seams)

- **Map-context modifier**: add a map archetype to the input state and a small modifier layer (high-ground/long-sightline favours poke/hitscan; chokes/close-quarters favour brawl).
- **Whole-comp mode**: fill all open slots, not just one.
- **Counter-anticipation**: one-ply lookahead — "if I pick X, what's their best swap, am I still ahead?"
- **Faster input** (manual portrait/hotkey entry). Note in code comments: automated scoreboard screen-reading sits in risky ToS/anti-cheat territory — do not implement without explicit sign-off.
