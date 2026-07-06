"""
Local browser app server for the OW counter-pick recommender.

Uses only the Python standard library. Run:
  python server.py
"""

import argparse
import json
import math
import mimetypes
import os
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from engine import _synergy_lookup, build_matrix, load_all, recommend_detailed, score_candidate_detailed


ROOT = Path(__file__).parent
DATA = ROOT / "data"
WEB = ROOT / "web"
HERO_ASSETS = WEB / "assets" / "heroes"

ROLES = ("tank", "dps", "support")
SCORE_WEIGHT_KEYS = ("alpha", "beta", "gamma", "delta")
ROLE_WEIGHT_KEYS = ("tank", "support", "dps")
ROLE_ORDER = {role: index for index, role in enumerate(ROLES)}
TEAM_SLOTS = (
    {"key": "tank", "label": "Tank", "role": "tank"},
    {"key": "dps1", "label": "DPS 1", "role": "dps"},
    {"key": "dps2", "label": "DPS 2", "role": "dps"},
    {"key": "support1", "label": "Support 1", "role": "support"},
    {"key": "support2", "label": "Support 2", "role": "support"},
)
TEAM_SLOT_ROLE = {slot["key"]: slot["role"] for slot in TEAM_SLOTS}
PREFERENCES_ENABLED = False


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def strip_meta(obj):
    if isinstance(obj, dict):
        return {k: v for k, v in obj.items() if not k.startswith("_")}
    return obj


def atomic_write_json(path, obj):
    path = Path(path)
    text = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    handle, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        # Validate the exact bytes we are about to promote.
        read_json(tmp_name)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def numeric(value, name, lo=0.0, hi=10.0):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ApiError(400, f"{name} must be a finite number.")
    if value < lo or value > hi:
        raise ApiError(400, f"{name} must be between {lo:g} and {hi:g}.")
    return round(float(value), 3)


def load_scoring_data():
    data = load_all()
    if not PREFERENCES_ENABLED:
        data["prefs"] = {"comfort": {}, "exclude": []}
    return data


def hero_catalog(data=None):
    data = data or load_all()
    raw_heroes = read_json(DATA / "heroes.json")
    raw_subroles = read_json(DATA / "subroles.json")
    heroes = {}

    for slug, hero in data["heroes"].items():
        raw = raw_heroes.get(slug, {})
        heroes[slug] = {
            "slug": slug,
            "name": hero["name"],
            "role": hero["role"],
            "subrole": hero.get("subrole"),
            "tags": raw.get("tags", []),
            "effective_tags": sorted(hero.get("_tags", [])),
            "archetypes": hero.get("archetypes", []),
            "needs_review": raw.get("_needs_review"),
            "icon": f"/assets/heroes/{slug}.png" if (HERO_ASSETS / f"{slug}.png").exists() else None,
        }

    return {
        "heroes": heroes,
        "hero_order": sorted(heroes, key=lambda s: (ROLE_ORDER.get(heroes[s]["role"], 99), heroes[s]["name"])),
        "team_slots": list(TEAM_SLOTS),
        "roles": list(ROLES),
        "subroles": strip_meta(raw_subroles),
        "tag_vocabulary": raw_heroes.get("_tag_vocabulary", []),
        "preferences": strip_meta(read_json(DATA / "preferences.json")),
        "preferences_enabled": PREFERENCES_ENABLED,
        "config": strip_meta(read_json(DATA / "config.json")),
    }


def unique_valid_slugs(values, heroes, field, warnings):
    cleaned = []
    seen = set()
    if values is None:
        return cleaned
    if not isinstance(values, list):
        raise ApiError(400, f"{field} must be a list.")
    for slug in values:
        if not slug:
            continue
        if not isinstance(slug, str):
            warnings.append(f"Ignored a non-string value in {field}.")
            continue
        if slug not in heroes:
            warnings.append(f"Ignored unknown hero '{slug}' in {field}.")
            continue
        if slug in seen:
            warnings.append(f"Ignored duplicate hero '{slug}' in {field}.")
            continue
        cleaned.append(slug)
        seen.add(slug)
    return cleaned


def clean_slotted_team(raw_team, heroes, field, warnings, enforce_roles=True):
    if raw_team is None:
        return {}
    if not isinstance(raw_team, dict):
        raise ApiError(400, f"{field} must be an object of slot -> hero slug.")

    cleaned = {}
    seen = set()
    for slot in TEAM_SLOT_ROLE:
        slug = raw_team.get(slot)
        if not slug:
            continue
        if not isinstance(slug, str):
            warnings.append(f"Ignored a non-string hero in {field}.{slot}.")
            continue
        if slug not in heroes:
            warnings.append(f"Ignored unknown hero '{slug}' in {field}.{slot}.")
            continue
        if slug in seen:
            warnings.append(f"Ignored duplicate hero '{slug}' in {field}.")
            continue
        if enforce_roles and heroes[slug]["role"] != TEAM_SLOT_ROLE[slot]:
            expected = TEAM_SLOT_ROLE[slot]
            actual = heroes[slug]["role"]
            warnings.append(f"Ignored {heroes[slug]['name']} in {field}.{slot}; expected {expected}, got {actual}.")
            continue
        cleaned[slot] = slug
        seen.add(slug)

    extra_slots = set(raw_team) - set(TEAM_SLOT_ROLE)
    for slot in sorted(extra_slots):
        if raw_team.get(slot):
            warnings.append(f"Ignored unknown slot '{slot}' in {field}.")

    return cleaned


def clean_role_lock(value, warnings):
    if value in (None, "", "all"):
        return None
    if value not in ROLES:
        warnings.append(f"Ignored unknown role lock '{value}'.")
        return None
    return value


def clean_state(payload, heroes):
    if not isinstance(payload, dict):
        raise ApiError(400, "Request body must be a JSON object.")

    warnings = []
    enemy_team = clean_slotted_team(payload.get("enemy_team"), heroes, "enemy_team", warnings)
    if enemy_team:
        enemy = [enemy_team[slot["key"]] for slot in TEAM_SLOTS if slot["key"] in enemy_team]
    else:
        enemy = unique_valid_slugs(payload.get("enemy", []), heroes, "enemy", warnings)
    if not enemy:
        warnings.append("Enemy team is empty, so recommendations use only team fit and base scoring.")

    my_team = clean_slotted_team(payload.get("my_team", {}), heroes, "my_team", warnings)

    carry_targets = unique_valid_slugs(
        payload.get("carry_targets", []),
        heroes,
        "carry_targets",
        warnings,
    )
    carry_targets = [slug for slug in carry_targets if slug in enemy]
    ignored_carry = set(payload.get("carry_targets", [])) - set(carry_targets)
    for slug in sorted(ignored_carry):
        if isinstance(slug, str) and slug in heroes and slug not in enemy:
            warnings.append(f"Ignored carry target '{slug}' because it is not on the enemy team.")

    top = payload.get("top", 8)
    if not isinstance(top, int) or isinstance(top, bool):
        raise ApiError(400, "top must be an integer.")
    top = max(1, min(20, top))

    return {
        "state": {
            "enemy": enemy,
            "enemy_team": enemy_team,
            "my_team": my_team,
            "my_slot": str(payload.get("my_slot", "open")),
            "my_role_lock": clean_role_lock(payload.get("my_role_lock"), warnings),
            "carry_targets": carry_targets,
        },
        "top": top,
        "warnings": warnings,
    }


def handle_recommend(payload):
    data = load_scoring_data()
    cleaned = clean_state(payload, data["heroes"])
    matrix = build_matrix(data)
    rows = recommend_detailed(cleaned["state"], data, matrix, top=cleaned["top"])
    return {
        "state": cleaned["state"],
        "recommendations": rows,
        "warnings": cleaned["warnings"],
    }


def score_for_slot(slug, slot_key, team, state, data, matrix, pair_lookup):
    teammates = {k: v for k, v in team.items() if k != slot_key and v}
    scoring_state = dict(state)
    scoring_state["my_team"] = teammates
    row = score_candidate_detailed(slug, scoring_state, data, matrix, pair_lookup)
    row["slot"] = slot_key
    row["slot_label"] = next(slot["label"] for slot in TEAM_SLOTS if slot["key"] == slot_key)
    return row


def candidates_for_role(role, team, data):
    heroes = data["heroes"]
    excluded = set(data["prefs"]["exclude"])
    taken = {slug for slug in team.values() if slug}
    return [
        slug for slug, hero in heroes.items()
        if hero["role"] == role and slug not in excluded and slug not in taken
    ]


def build_full_team(state, data, matrix):
    pair_lookup = _synergy_lookup(data["synergies"])
    locked_team = dict(state.get("my_team", {}))
    missing_slots = [
        slot for slot in TEAM_SLOTS
        if slot["key"] not in locked_team or not locked_team[slot["key"]]
    ]

    beams = [{"team": dict(locked_team), "score": 0.0}]
    warnings = []

    for slot in missing_slots:
        role = slot["role"]
        expanded = []
        for beam in beams:
            state_for_slot = dict(state)
            state_for_slot["my_team"] = dict(beam["team"])
            rows = []
            for slug in candidates_for_role(role, beam["team"], data):
                rows.append(score_candidate_detailed(slug, state_for_slot, data, matrix, pair_lookup))
            rows.sort(key=lambda row: row["total"], reverse=True)

            for row in rows[:10]:
                team = dict(beam["team"])
                team[slot["key"]] = row["slug"]
                expanded.append({
                    "team": team,
                    "score": beam["score"] + row["total"],
                })

        if not expanded:
            warnings.append(f"No available {role} candidates for {slot['label']}.")
            continue

        expanded.sort(key=lambda beam: beam["score"], reverse=True)
        beams = expanded[:40]

    best_team = beams[0]["team"] if beams else dict(locked_team)
    slots = []
    alternatives = {}

    for slot in TEAM_SLOTS:
        slot_key = slot["key"]
        slug = best_team.get(slot_key)
        if not slug:
            continue
        row = score_for_slot(slug, slot_key, best_team, state, data, matrix, pair_lookup)
        row["locked"] = slot_key in locked_team and locked_team[slot_key] == slug
        slots.append(row)

        alt_rows = []
        team_without_slot = {k: v for k, v in best_team.items() if k != slot_key}
        for alt_slug in candidates_for_role(slot["role"], team_without_slot, data):
            alt_rows.append(score_for_slot(alt_slug, slot_key, best_team, state, data, matrix, pair_lookup))
        alt_rows.sort(key=lambda alt: alt["total"], reverse=True)
        alternatives[slot_key] = alt_rows[:5]

    total = round(sum(row["total"] for row in slots), 2)
    return {
        "team": {slot["key"]: best_team.get(slot["key"]) for slot in TEAM_SLOTS if best_team.get(slot["key"])},
        "slots": slots,
        "alternatives": alternatives,
        "total": total,
        "warnings": warnings,
    }


def handle_recommend_team(payload):
    data = load_scoring_data()
    cleaned = clean_state(payload, data["heroes"])
    matrix = build_matrix(data)
    recommendation = build_full_team(cleaned["state"], data, matrix)
    return {
        "state": cleaned["state"],
        "team_recommendation": recommendation,
        "warnings": cleaned["warnings"] + recommendation["warnings"],
    }


def handle_preferences(payload):
    if not isinstance(payload, dict):
        raise ApiError(400, "Request body must be a JSON object.")
    extra = set(payload) - {"comfort", "exclude"}
    if extra:
        raise ApiError(400, f"Unsupported preference fields: {', '.join(sorted(extra))}.")

    data = load_all()
    raw = read_json(DATA / "preferences.json")

    if "comfort" in payload:
        if not isinstance(payload["comfort"], dict):
            raise ApiError(400, "comfort must be an object of hero slug -> number.")
        comfort = {}
        for slug, value in payload["comfort"].items():
            if slug not in data["heroes"]:
                raise ApiError(400, f"Unknown hero in comfort: {slug}.")
            comfort[slug] = numeric(value, f"comfort.{slug}", lo=-10.0, hi=10.0)
        raw["comfort"] = comfort

    if "exclude" in payload:
        if not isinstance(payload["exclude"], list):
            raise ApiError(400, "exclude must be a list of hero slugs.")
        exclude = []
        seen = set()
        for slug in payload["exclude"]:
            if slug not in data["heroes"]:
                raise ApiError(400, f"Unknown hero in exclude: {slug}.")
            if slug not in seen:
                exclude.append(slug)
                seen.add(slug)
        raw["exclude"] = exclude

    atomic_write_json(DATA / "preferences.json", raw)
    return {"preferences": strip_meta(read_json(DATA / "preferences.json"))}


def handle_config(payload):
    if not isinstance(payload, dict):
        raise ApiError(400, "Request body must be a JSON object.")
    extra = set(payload) - {"weights", "role_weights", "carry_multiplier"}
    if extra:
        raise ApiError(400, f"Unsupported config fields: {', '.join(sorted(extra))}.")

    raw = read_json(DATA / "config.json")

    if "weights" in payload:
        if not isinstance(payload["weights"], dict):
            raise ApiError(400, "weights must be an object.")
        extra_weights = set(payload["weights"]) - set(SCORE_WEIGHT_KEYS)
        if extra_weights:
            raise ApiError(400, f"Unsupported score weights: {', '.join(sorted(extra_weights))}.")
        merged = dict(raw.get("weights", {}))
        for key in SCORE_WEIGHT_KEYS:
            if key in payload["weights"]:
                merged[key] = numeric(payload["weights"][key], f"weights.{key}")
        raw["weights"] = merged

    if "role_weights" in payload:
        if not isinstance(payload["role_weights"], dict):
            raise ApiError(400, "role_weights must be an object.")
        extra_roles = set(payload["role_weights"]) - set(ROLE_WEIGHT_KEYS)
        if extra_roles:
            raise ApiError(400, f"Unsupported role weights: {', '.join(sorted(extra_roles))}.")
        merged = dict(raw.get("role_weights", {}))
        for key in ROLE_WEIGHT_KEYS:
            if key in payload["role_weights"]:
                merged[key] = numeric(payload["role_weights"][key], f"role_weights.{key}")
        raw["role_weights"] = merged

    if "carry_multiplier" in payload:
        raw["carry_multiplier"] = numeric(payload["carry_multiplier"], "carry_multiplier")

    atomic_write_json(DATA / "config.json", raw)
    return {"config": strip_meta(read_json(DATA / "config.json"))}


class Handler(BaseHTTPRequestHandler):
    server_version = "OWCounterpick/1.0"

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")

    def send_json(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_api_error(self, status, message):
        self.send_json(status, {"error": message})

    def read_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1024 * 1024:
            raise ApiError(413, "Request body is too large.")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ApiError(400, f"Invalid JSON: {exc.msg}.")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/catalog":
            try:
                self.send_json(200, hero_catalog())
            except Exception as exc:
                self.send_api_error(500, str(exc))
            return
        self.serve_static(parsed.path)

    def do_POST(self):
        try:
            path = urlparse(self.path).path
            if path == "/api/recommend":
                self.send_json(200, handle_recommend(self.read_body()))
            elif path == "/api/recommend-team":
                self.send_json(200, handle_recommend_team(self.read_body()))
            else:
                raise ApiError(404, "Unknown endpoint.")
        except ApiError as exc:
            self.send_api_error(exc.status, exc.message)
        except Exception as exc:
            self.send_api_error(500, str(exc))

    def do_PUT(self):
        try:
            path = urlparse(self.path).path
            body = self.read_body()
            if path == "/api/preferences":
                self.send_json(200, handle_preferences(body))
            elif path == "/api/config":
                self.send_json(200, handle_config(body))
            else:
                raise ApiError(404, "Unknown endpoint.")
        except ApiError as exc:
            self.send_api_error(exc.status, exc.message)
        except Exception as exc:
            self.send_api_error(500, str(exc))

    def serve_static(self, request_path):
        if request_path in ("", "/"):
            request_path = "/index.html"
        rel = unquote(request_path).lstrip("/")
        candidate = (WEB / rel).resolve()

        if not candidate.is_file() or not candidate.is_relative_to(WEB.resolve()):
            self.send_error(404)
            return

        ctype = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        body = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description="Run the local OW counter-pick app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()

    if not WEB.exists():
        raise SystemExit("Missing web/ directory. The app frontend has not been installed.")

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"OW Counter-Pick app running at http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
