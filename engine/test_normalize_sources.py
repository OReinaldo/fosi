import unittest
from normalize_sources import normalize_match, normalize_players, normalize_event_like


class NormalizeSourcesTests(unittest.TestCase):
    def sample(self):
        return {
            "general": {
                "matchId": "1",
                "matchName": "Pogoń Szczecin-vs-Legia Warszawa_Fri, Jul 24, 2026, 18:30 UTC",
                "leagueName": "Ekstraklasa",
                "matchTimeUTCDate": "2026-07-24T18:30:00.000Z",
            },
            "header": {"teams": [
                {"name": "Pogoń Szczecin", "id": 8023, "score": 0},
                {"name": "Legia Warszawa", "id": 8673, "score": 1},
            ]},
            "lineup": {"players": [
                {"id": 10, "name": "Example", "teamId": 8023, "role": "Forward",
                 "stats": [{"stats": {"Goals": {"key": "goals", "stat": {"value": 1}},
                                           "Minutes played": {"key": "minutes_played", "stat": {"value": 90}}}}]},
                {"id": 11, "name": "Opponent", "teamId": 8673, "role": "Forward"},
            ]},
        }

    def test_match_extracts_header_teams_and_score(self):
        m = normalize_match(self.sample(), "x.json", "fotmob")
        self.assertEqual(m["home_team"]["id"], 8023)
        self.assertEqual(m["away_team"]["name"], "Legia Warszawa")
        self.assertEqual(m["score"], {"home": 0, "away": 1})
        self.assertEqual(m["date"], "2026-07-24T18:30:00.000Z")

    def test_players_are_limited_to_selected_provider_team(self):
        rows = normalize_players(self.sample(), "matches/1.json", "fotmob", 8023)
        self.assertEqual([r["provider_id"] for r in rows], ["10"])
        self.assertEqual(rows[0]["stats"]["goals"], 1)
        self.assertEqual(rows[0]["stats"]["minutes"], 90)

    def test_heatmaps_are_spatial_evidence(self):
        payload = {"matchId": "1", "heatmaps": [{"playerId": 10, "heatmap": [{"x": 25, "y": 40}]}]}
        rows = normalize_event_like(payload, "heatmaps/1.json", "fotmob")
        self.assertEqual(len(rows["spatial_actions"]), 1)
        self.assertEqual(rows["spatial_actions"][0]["playerId"], 10)
        self.assertEqual(rows["spatial_actions"][0]["match_id"], "1")


if __name__ == "__main__":
    unittest.main()
