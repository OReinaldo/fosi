import unittest
from scouting_intelligence import build_player_intelligence, build_match_intelligence, build_threat_weakness_center


class ScoutingIntelligenceTests(unittest.TestCase):
    def test_player_rank_requires_minutes_and_preserves_evidence(self):
        rows = build_player_intelligence([
            {"player_id": "1", "name": "A", "position": "FWD", "stats": {"minutes": 540, "goals": 3, "assists": 1}, "per90": {"goals": 0.5, "assists": 0.17}},
            {"player_id": "2", "name": "B", "stats": {"minutes": 90, "goals": 4}, "per90": {"goals": 4}},
        ])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "A")
        self.assertIn("goals", rows[0]["evidence"])
        self.assertIn("production", rows[0]["family_scores"])

    def test_match_intelligence_is_conservative(self):
        rows = build_match_intelligence([
            {"provider_id": "m1", "date": "2026-08-01", "score": {"home": 2, "away": 1}}
        ], [{"match_id": "m1", "result": "W", "goals_for": 2, "goals_against": 1, "xg": 1.1, "xga": 0.7, "shots_for": 8, "shots_against": 5}])
        self.assertEqual(rows[0]["result"], "W")
        self.assertIn("balance_xg_positive", rows[0]["patterns"])
        self.assertEqual(rows[0]["status"], "pattern")

    def test_threat_weakness_never_creates_tactical_fact(self):
        out = build_threat_weakness_center(
            {"xg": 10, "xga": 6, "shots_for": 80, "shots_against": 50},
            [{"name": "A", "minutes": 900, "leading_statistical_family": "production", "family_scores": {"production": 8}, "confidence": 80}],
            [],
        )
        self.assertTrue(out["threats"])
        self.assertFalse(any("debe" in x["title"].lower() for x in out["threats"] + out["weaknesses"]))


if __name__ == "__main__":
    unittest.main()
