import unittest
from enrich_normalized import player_stats, nested_id, spatial_type

class EnrichNormalizedTests(unittest.TestCase):
    def test_nested_player_match_identity(self):
        item={"player":{"id":123},"match":{"eventId":456},"stats":{"minutes":90,"goals":1,"passes":42}}
        self.assertEqual(nested_id(item,("playerId","player_id")), "123")
        self.assertEqual(nested_id(item,("matchId","match_id","eventId","event_id")), "456")
        self.assertEqual(player_stats(item)["minutes"], 90.0)
        self.assertEqual(player_stats(item)["passes"], 42.0)

    def test_spatial_classification(self):
        self.assertEqual(spatial_type({"x":40,"y":50}, "heatmaps/123.json"), "heatmap")
        self.assertEqual(spatial_type({"x":40,"y":50}, "passing/map.json"), "pass")

if __name__ == "__main__": unittest.main()
