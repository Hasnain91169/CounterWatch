import shutil
import tempfile
import unittest
from pathlib import Path

import server


ROOT = Path(__file__).parent


class AppApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_data = server.DATA
        temp_data = Path(self.tmp.name) / "data"
        shutil.copytree(ROOT / "data", temp_data)
        server.DATA = temp_data

    def tearDown(self):
        server.DATA = self.old_data
        self.tmp.cleanup()

    def test_demo_recommendations_stay_sensible(self):
        result = server.handle_recommend({
            "enemy": ["winston", "genji", "sombra", "lucio", "kiriko"],
            "my_team": {
                "tank": "reinhardt",
                "support1": "ana",
                "support2": "brigitte",
            },
            "my_slot": "dps2",
            "my_role_lock": "dps",
            "carry_targets": ["genji"],
            "top": 8,
        })

        slugs = [row["slug"] for row in result["recommendations"]]
        self.assertEqual(slugs[0], "mei")
        self.assertIn("reaper", slugs[:5])
        self.assertIn("cassidy", slugs[:5])
        self.assertIn("sombra", slugs[:5])
        self.assertIn("junkrat", slugs[:5])
        self.assertIn("contributions", result["recommendations"][0])

    def test_full_team_recommendation_fills_122_roles(self):
        result = server.handle_recommend_team({
            "enemy_team": {
                "tank": "winston",
                "dps1": "genji",
                "dps2": "sombra",
                "support1": "lucio",
                "support2": "kiriko",
            },
            "my_team": {},
            "carry_targets": ["genji"],
        })

        team = result["team_recommendation"]["team"]
        self.assertEqual(set(team), {"tank", "dps1", "dps2", "support1", "support2"})
        self.assertEqual(len(set(team.values())), 5)
        self.assertEqual(len(result["team_recommendation"]["slots"]), 5)

        heroes = server.load_all()["heroes"]
        self.assertEqual(heroes[team["tank"]]["role"], "tank")
        self.assertEqual(heroes[team["dps1"]]["role"], "dps")
        self.assertEqual(heroes[team["dps2"]]["role"], "dps")
        self.assertEqual(heroes[team["support1"]]["role"], "support")
        self.assertEqual(heroes[team["support2"]]["role"], "support")

    def test_full_team_keeps_locked_picks_and_rejects_wrong_slot_roles(self):
        result = server.handle_recommend_team({
            "enemy_team": {
                "tank": "genji",
                "dps1": "winston",
                "dps2": "sombra",
            },
            "my_team": {
                "tank": "reinhardt",
                "dps1": "ana",
            },
            "carry_targets": ["sombra"],
        })

        team = result["team_recommendation"]["team"]
        self.assertEqual(team["tank"], "reinhardt")
        self.assertNotEqual(team.get("dps1"), "ana")
        self.assertTrue(any("expected tank" in warning for warning in result["warnings"]))
        self.assertTrue(any("expected dps" in warning for warning in result["warnings"]))

    def test_invalid_duplicate_and_empty_inputs_warn_without_crashing(self):
        result = server.handle_recommend({
            "enemy": ["genji", "genji", "not_a_hero"],
            "my_team": {"support1": "ana", "support2": "ana"},
            "my_role_lock": "nonsense",
            "carry_targets": ["tracer", "genji"],
            "top": 3,
        })

        self.assertEqual(result["state"]["enemy"], ["genji"])
        self.assertEqual(result["state"]["carry_targets"], ["genji"])
        self.assertEqual(result["state"]["my_role_lock"], None)
        self.assertEqual(len(result["recommendations"]), 3)
        self.assertGreaterEqual(len(result["warnings"]), 4)

        empty = server.handle_recommend({"enemy": [], "my_team": {}, "top": 2})
        self.assertEqual(len(empty["recommendations"]), 2)
        self.assertTrue(any("Enemy team is empty" in warning for warning in empty["warnings"]))

    def test_recommendations_ignore_preferences_while_disabled(self):
        server.handle_preferences({
            "comfort": {"mei": -10.0},
            "exclude": ["mei"],
        })

        result = server.handle_recommend({
            "enemy": ["winston", "genji", "sombra", "lucio", "kiriko"],
            "my_team": {
                "tank": "reinhardt",
                "support1": "ana",
                "support2": "brigitte",
            },
            "my_role_lock": "dps",
            "carry_targets": ["genji"],
            "top": 3,
        })

        self.assertEqual(result["recommendations"][0]["slug"], "mei")
        self.assertEqual(result["recommendations"][0]["comfort"], 0.0)

    def test_safe_json_updates_persist_only_allowed_fields(self):
        prefs = server.handle_preferences({
            "comfort": {"mei": 2.5, "cassidy": 1.0},
            "exclude": ["widowmaker", "hanzo", "hanzo"],
        })["preferences"]

        self.assertEqual(prefs["comfort"]["mei"], 2.5)
        self.assertEqual(prefs["exclude"], ["widowmaker", "hanzo"])

        before = server.read_json(server.DATA / "config.json")
        config = server.handle_config({
            "weights": {"alpha": 1.2, "delta": 0.9},
            "role_weights": {"tank": 1.7},
            "carry_multiplier": 2.0,
        })["config"]

        self.assertEqual(config["weights"]["alpha"], 1.2)
        self.assertEqual(config["weights"]["delta"], 0.9)
        self.assertEqual(config["role_weights"]["tank"], 1.7)
        self.assertEqual(config["carry_multiplier"], 2.0)
        self.assertEqual(config["matrix_clamp"], before["matrix_clamp"])

        with self.assertRaises(server.ApiError):
            server.handle_config({"matrix_clamp": [-4, 4]})


if __name__ == "__main__":
    unittest.main()
