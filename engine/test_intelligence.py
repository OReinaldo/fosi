import unittest

import intelligence


class IntelligenceTests(unittest.TestCase):
    def test_xg_balance_and_coverage(self):
        metrics = {"xg": 14.0, "xga": 10.0, "matches_sample": 6}
        meta = {"xg": {"coverage": 1.0}, "xga": {"coverage": 1.0}}
        rows = intelligence.build_insights(metrics, meta, {})
        self.assertTrue(any(x["title"] == "Balance positivo de ocasiones" for x in rows))
        self.assertTrue(all(35 <= x["confidence"] <= 95 for x in rows))

    def test_shot_quality_pattern(self):
        metrics = {"xg_per_match": 1.0, "shots_for": 30, "matches_sample": 5}
        meta = {"xg": {"coverage": 1.0}, "shots_for": {"coverage": 1.0}}
        rows = intelligence.build_insights(metrics, meta, {})
        self.assertTrue(any(x["title"] == "Perfil de ocasiones de alta calidad" for x in rows))

    def test_player_contributor_requires_minutes(self):
        metrics = {"matches_sample": 6}
        bundle = {"player_metrics": [
            {"name": "Jugador corto", "stats": {"minutes": 90, "goals": 5}},
            {"name": "Jugador estable", "stats": {"minutes": 270, "goals": 2, "assists": 1}},
        ]}
        rows = intelligence.build_insights(metrics, {}, bundle)
        player_rows = [x for x in rows if x["kind"] == "player"]
        self.assertEqual(len(player_rows), 1)
        self.assertIn("Jugador estable", player_rows[0]["evidence"])

    def test_missing_data_does_not_create_xg_pattern(self):
        metrics = {"matches_sample": 6, "xg": None, "xga": None}
        rows = intelligence.build_insights(metrics, {}, {})
        self.assertFalse(any("ocasiones" in x["title"] for x in rows))


if __name__ == "__main__":
    unittest.main()
