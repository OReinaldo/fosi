import unittest
from enrich_normalized import player_stats, nested_id, spatial_type

class EnrichNormalizedTests(unittest.TestCase):
    def test_nested_player_match_identity(self):
        item={"player":{"id":123},"match":{"eventId":456},"stats":{"minutes":90,"goals":1,"passes":42}}
        self.assertEqual(nested_id(item,("playerId","player_id")), "123")
        self.assertEqual(nested_id(item,("matchId","match_id","eventId","event_id")), "456")
        self.assertEqual(player_stats(item)["minutes"], 90.0)
        self.assertEqual(player_stats(item)["passes"], 42.0)

    def test_structured_fotmob_stat_blocks(self):
        item={"id":289211,"name":{"fullName":"Valentin Cojocaru"},"stats":[{"title":"Top stats","stats":{
            "Minutes played":{"key":"minutes_played","stat":{"value":90,"type":"integer"}},
            "Accurate passes":{"key":"accurate_passes","stat":{"value":21,"total":37,"type":"fractionWithPercentage"}},
            "Chances created":{"key":"chances_created","stat":{"value":2,"type":"integer"}}
        }},{"title":"Defense","stats":{
            "Recoveries":{"key":"recoveries","stat":{"value":11,"type":"integer"}},
            "Tackles":{"key":"matchstats.headers.tackles","stat":{"value":1,"type":"integer"}}
        }}]}
        stats=player_stats(item)
        self.assertEqual(stats["minutes"],90.0)
        self.assertEqual(stats["accurate_passes"],21.0)
        self.assertEqual(stats["accurate_passes_total"],37.0)
        self.assertEqual(stats["key_passes"],2.0)
        self.assertEqual(stats["recoveries"],11.0)
        self.assertEqual(stats["tackles"],1.0)

    def test_spatial_classification(self):
        self.assertEqual(spatial_type({"x":40,"y":50}, "heatmaps/123.json"), "heatmap")
        self.assertEqual(spatial_type({"x":40,"y":50}, "passing/map.json"), "pass")

if __name__ == "__main__": unittest.main()
