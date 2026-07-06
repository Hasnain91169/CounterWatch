"""
Overwatch counter-pick engine (personal tool).

Pipeline:
  1. Load editable JSON data from ./data
  2. Merge each hero's sub-role-implied tags into its own tags
  3. Build a base matchup matrix from tag/sub-role RULES, then apply specific OVERRIDES
  4. Score candidate heroes for a given game state and return them ranked

Scoring (per candidate h, given enemy team E and your locked teammates T):
  Score(h) =  alpha * Counter(h, E)
           -  delta * Countered(h, E)      # the term people forget
           +  beta  * Synergy(h, T)
           +  gamma * Comfort(h)

  Counter(h, E)   = sum over e in E:  M[h][e] * role_weight(e) * carry_mult(e)
  Countered(h, E) = sum over e in E:  M[e][h] * role_weight(e) * carry_mult(e)

Run `python engine.py` for a worked demo.
"""

import json
from pathlib import Path

DATA = Path(__file__).parent / "data"


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def _load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


def load_all():
    heroes    = _load("heroes.json")
    subroles  = _load("subroles.json")
    rules     = _load("matchup_rules.json")["rules"]
    overrides = _load("matchup_overrides.json")
    synergies = _load("synergies.json")
    prefs     = _load("preferences.json")
    config    = _load("config.json")

    # strip comment / metadata keys (anything starting with "_")
    heroes    = {k: v for k, v in heroes.items() if not k.startswith("_")}
    subroles  = {k: v for k, v in subroles.items() if not k.startswith("_")}
    overrides = {k: v for k, v in overrides.items() if not k.startswith("_")}

    # merge sub-role-implied tags into each hero's effective tag set
    for slug, h in heroes.items():
        tags = set(h.get("tags", []))
        sr = h.get("subrole")
        if sr and sr in subroles:
            tags.update(subroles[sr].get("implies", []))
        h["_tags"] = tags  # effective tags used by the engine

    return {
        "heroes": heroes, "subroles": subroles, "rules": rules,
        "overrides": overrides, "synergies": synergies,
        "prefs": prefs, "config": config,
    }


# --------------------------------------------------------------------------- #
# Matchup matrix
# --------------------------------------------------------------------------- #
def _condition_matches(cond, hero):
    """A rule condition matches a hero if all listed constraints hold."""
    if not cond:
        return True
    if "role" in cond and hero["role"] != cond["role"]:
        return False
    if "subrole" in cond and hero.get("subrole") != cond["subrole"]:
        return False
    if "archetype" in cond and cond["archetype"] not in hero.get("archetypes", []):
        return False
    if "tags" in cond and not set(cond["tags"]).issubset(hero["_tags"]):
        return False
    return True


def build_matrix(data):
    """Return M[attacker][defender] in [clamp_lo, clamp_hi]. Rules first, overrides on top."""
    heroes = data["heroes"]
    lo, hi = data["config"]["matrix_clamp"]
    M = {a: {} for a in heroes}

    # 1. rule-generated base
    for a, ah in heroes.items():
        for b, bh in heroes.items():
            if a == b:
                continue
            total = 0.0
            for rule in data["rules"]:
                if "attacker" not in rule:      # skip comment-only entries
                    continue
                if _condition_matches(rule["attacker"], ah) and \
                   _condition_matches(rule["defender"], bh):
                    total += rule["value"]
            if total:
                M[a][b] = max(lo, min(hi, total))

    # 2. specific overrides replace the generated value
    for a, row in data["overrides"].items():
        if a not in M:
            continue
        for b, v in row.items():
            if b in heroes:
                M[a][b] = max(lo, min(hi, v))

    return M


# --------------------------------------------------------------------------- #
# Synergy
# --------------------------------------------------------------------------- #
def _synergy_lookup(synergies):
    """Build a symmetric pair-bonus dict from the synergy list."""
    pair = {}
    for p in synergies["pairs"]:
        pair[(p["a"], p["b"])] = p["value"]
        pair[(p["b"], p["a"])] = p["value"]
    return pair


def _dominant_archetype(team_slugs, heroes):
    """Most common archetype among locked teammates (for the coherence bonus)."""
    counts = {}
    for slug in team_slugs:
        for arch in heroes.get(slug, {}).get("archetypes", []):
            counts[arch] = counts.get(arch, 0) + 1
    return max(counts, key=counts.get) if counts else None


def synergy_score(cand, team_slugs, data, pair_lookup):
    heroes = data["heroes"]
    score = sum(pair_lookup.get((cand, t), 0.0) for t in team_slugs)
    dom = _dominant_archetype(team_slugs, heroes)
    if dom and dom in heroes[cand].get("archetypes", []):
        score += data["synergies"]["archetype_coherence"].get(dom, 0.0)
    return score


def synergy_breakdown(cand, team_slugs, data, pair_lookup):
    """Return the synergy score plus the parts that explain it."""
    heroes = data["heroes"]
    pairs = []
    score = 0.0

    for teammate in team_slugs:
        value = pair_lookup.get((cand, teammate), 0.0)
        score += value
        if value and teammate in heroes:
            pairs.append({
                "teammate": teammate,
                "teammate_name": heroes[teammate]["name"],
                "value": round(value, 2),
            })

    dom = _dominant_archetype(team_slugs, heroes)
    coherence_value = 0.0
    if dom and dom in heroes[cand].get("archetypes", []):
        coherence_value = data["synergies"]["archetype_coherence"].get(dom, 0.0)
        score += coherence_value

    return score, {
        "pairs": pairs,
        "coherence": {
            "archetype": dom,
            "matched": bool(coherence_value),
            "value": round(coherence_value, 2),
        },
    }


# --------------------------------------------------------------------------- #
# Scoring + recommendation
# --------------------------------------------------------------------------- #
def _score_candidate_raw(cand, state, data, M, pair_lookup):
    cfg   = data["config"]
    w     = cfg["weights"]
    rw    = cfg["role_weights"]
    cm    = cfg["carry_multiplier"]
    heroes = data["heroes"]
    carry = set(state.get("carry_targets", []))

    counter = countered = 0.0
    contributions = []
    for e in state.get("enemy", []):
        if e not in heroes:
            continue
        weight = rw.get(heroes[e]["role"], 1.0) * (cm if e in carry else 1.0)
        matchup_for = M.get(cand, {}).get(e, 0.0)
        matchup_against = M.get(e, {}).get(cand, 0.0)
        counter_score = matchup_for * weight
        countered_score = matchup_against * weight
        counter += counter_score       # you beat them
        countered += countered_score   # they beat you
        contributions.append({
            "enemy": e,
            "enemy_name": heroes[e]["name"],
            "enemy_role": heroes[e]["role"],
            "is_carry": e in carry,
            "role_weight": rw.get(heroes[e]["role"], 1.0),
            "carry_multiplier": cm if e in carry else 1.0,
            "weight": round(weight, 2),
            "matchup_for": round(matchup_for, 2),
            "matchup_against": round(matchup_against, 2),
            "counter": round(counter_score, 2),
            "countered": round(countered_score, 2),
        })

    team = [t for t in state.get("my_team", {}).values() if t in heroes]
    synergy, synergy_parts = synergy_breakdown(cand, team, data, pair_lookup)
    comfort = data["prefs"]["comfort"].get(cand, 0.0)

    total = (w["alpha"] * counter
             - w["delta"] * countered
             + w["beta"]  * synergy
             + w["gamma"] * comfort)

    return {
        "total": total,
        "counter": counter,
        "countered": countered,
        "synergy": synergy,
        "comfort": comfort,
        "contributions": contributions,
        "synergy_breakdown": synergy_parts,
        "weighted_terms": {
            "counter": w["alpha"] * counter,
            "countered_penalty": -w["delta"] * countered,
            "synergy": w["beta"] * synergy,
            "comfort": w["gamma"] * comfort,
        },
    }


def score_candidate(cand, state, data, M, pair_lookup):
    heroes = data["heroes"]
    raw = _score_candidate_raw(cand, state, data, M, pair_lookup)

    return {
        "hero": heroes[cand]["name"], "slug": cand, "total": round(raw["total"], 2),
        "counter": round(raw["counter"], 2), "countered": round(raw["countered"], 2),
        "synergy": round(raw["synergy"], 2), "comfort": raw["comfort"],
        "subrole": heroes[cand].get("subrole"),
    }


def score_candidate_detailed(cand, state, data, M, pair_lookup):
    """Score a candidate and include frontend-friendly explanation fields."""
    heroes = data["heroes"]
    raw = _score_candidate_raw(cand, state, data, M, pair_lookup)
    return {
        "hero": heroes[cand]["name"],
        "slug": cand,
        "role": heroes[cand]["role"],
        "subrole": heroes[cand].get("subrole"),
        "archetypes": heroes[cand].get("archetypes", []),
        "total": round(raw["total"], 2),
        "counter": round(raw["counter"], 2),
        "countered": round(raw["countered"], 2),
        "synergy": round(raw["synergy"], 2),
        "comfort": raw["comfort"],
        "weighted_terms": {
            k: round(v, 2) for k, v in raw["weighted_terms"].items()
        },
        "contributions": raw["contributions"],
        "synergy_breakdown": raw["synergy_breakdown"],
    }


def recommend(state, data, M, top=8):
    """Rank candidate heroes for the open slot, honouring role lock and excludes."""
    heroes   = data["heroes"]
    excluded = set(data["prefs"]["exclude"])
    taken    = set(state.get("my_team", {}).values())
    role     = state.get("my_role_lock")
    pair_lookup = _synergy_lookup(data["synergies"])

    candidates = [
        s for s, h in heroes.items()
        if s not in excluded and s not in taken
        and (role is None or h["role"] == role)
    ]
    scored = [score_candidate(c, state, data, M, pair_lookup) for c in candidates]
    scored.sort(key=lambda x: x["total"], reverse=True)
    return scored[:top]


def recommend_detailed(state, data, M, top=8):
    """Rank candidate heroes and include component breakdowns for app UIs."""
    heroes   = data["heroes"]
    excluded = set(data["prefs"]["exclude"])
    taken    = set(state.get("my_team", {}).values())
    role     = state.get("my_role_lock")
    pair_lookup = _synergy_lookup(data["synergies"])

    candidates = [
        s for s, h in heroes.items()
        if s not in excluded and s not in taken
        and (role is None or h["role"] == role)
    ]
    scored = [score_candidate_detailed(c, state, data, M, pair_lookup) for c in candidates]
    scored.sort(key=lambda x: x["total"], reverse=True)
    return scored[:top]


# --------------------------------------------------------------------------- #
# Demo
# --------------------------------------------------------------------------- #
def _print_table(rows):
    hdr = f"{'#':>2}  {'HERO':<14}{'SUBROLE':<13}{'TOTAL':>7}{'CTR':>7}{'-CTRD':>7}{'SYN':>6}{'CMF':>6}"
    print(hdr)
    print("-" * len(hdr))
    for i, r in enumerate(rows, 1):
        print(f"{i:>2}  {r['hero']:<14}{str(r['subrole']):<13}"
              f"{r['total']:>7}{r['counter']:>7}{r['countered']:>7}"
              f"{r['synergy']:>6}{r['comfort']:>6}")


if __name__ == "__main__":
    data = load_all()
    M = build_matrix(data)

    # Example: enemy runs a dive comp, your tank+supports are locked, you fill DPS,
    # and their Genji is hard-carrying so you flag him.
    state = {
        "enemy": ["winston", "genji", "sombra", "lucio", "kiriko"],
        "my_team": {                 # locked teammates who won't switch
            "tank": "reinhardt",
            "support1": "ana",
            "support2": "brigitte",
        },
        "my_slot": "dps2",
        "my_role_lock": "dps",       # restrict candidates to DPS
        "carry_targets": ["genji"],  # their Genji is popping off
    }

    print("Enemy comp:", ", ".join(data["heroes"][e]["name"] for e in state["enemy"]))
    print("Locked teammates:", ", ".join(data["heroes"][t]["name"] for t in state["my_team"].values()))
    print(f"Filling: {state['my_slot']} (role-locked {state['my_role_lock']}) | "
          f"carry flagged: {', '.join(state['carry_targets'])}\n")

    _print_table(recommend(state, data, M, top=8))

    print("\nLegend: CTR=counter value | -CTRD=how hard you get countered back "
          "| SYN=synergy w/ locked team | CMF=your comfort")
