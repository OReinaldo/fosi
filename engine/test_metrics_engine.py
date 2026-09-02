import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import metrics_engine


class MetricsEngineTests(unittest.TestCase):
    def test_team_score_and_result(self):
        cfg = {"team_id": "3117", "team": "Pogoń Szczecin", "provider_ids": {"fotmob": "8023", "sofascore": "3117"}}
        match = {"home_team": {"id": "3117", "name": "Pogoń Szczecin"}, "away_team": {"id": "9", "name": "Opponent"}, "score": {"home": 2, "away": 1}}
        self.assertEqual(metrics_engine.team_score(match, cfg), (2.0, 1.0))
        self.assertEqual(metrics_engine.result_for(match, cfg), "W")

    def test_missing_score_is_not_zero(self):
        cfg = {"team_id": "3117", "team": "Pogoń Szczecin", "provider_ids": {"fotmob": "8023", "sofascore": "3117"}}
        match = {"home_team": {"id": "3117", "name": "Pogoń Szczecin"}, "away_team": {"id": "9", "name": "Opponent"}, "score": {"home": None, "away": None}}
        self.assertEqual(metrics_engine.team_score(match, cfg), (None, None))
        self.assertIsNone(metrics_engine.result_for(match, cfg))

    def test_shot_xg_and_opponent_attribution(self):
        cfg = {"team_id": "3117", "team": "Pogoń Szczecin", "provider_ids": {"fotmob": "8023", "sofascore": "3117"}}
        own = {"id": 1, "teamId": "3117", "expectedGoals": 0.25}
        opp = {"id": 2, "teamId": "9", "expectedGoals": 0.10}
        self.assertTrue(metrics_engine.belongs_to_team(own, cfg))
        self.assertFalse(metrics_engine.belongs_to_team(opp, cfg))
        self.assertTrue(metrics_engine.has_explicit_other_team(opp, cfg))
        self.assertEqual(metrics_engine.xg(own), 0.25)


if __name__ == "__main__":
    unittest.main()
