"""FOSI data coverage and quality scoring."""

def score(layers):
    weights = {"team": 10, "matches": 20, "players": 15, "stats": 20, "events": 15, "spatial": 10, "video": 10}
    ready = {"ready", "source-loaded", "available"}
    total = sum(weights.values())
    earned = sum(weight for name, weight in weights.items() if layers.get(name) in ready)
    return round(100 * earned / total)
