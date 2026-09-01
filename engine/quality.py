"""FOSI coverage scoring. Only evidence-backed source states count."""
def score(layers):
    weights={"team":10,"matches":20,"players":15,"stats":20,"events":15,"spatial":10,"video":10}; earned=0
    for name,weight in weights.items():
        state=layers.get(name)
        if state in {"available","ready"}: earned+=weight
        elif state=="partial": earned+=weight*0.5
    return round(100*earned/sum(weights.values()))
