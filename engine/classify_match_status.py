"""Classify normalized fixtures as finished or scheduled without inventing results.

A provider fixture can contain a placeholder 0-0 score before kickoff. That value must
never enter FOSI result/form/goal metrics as an observed result. We therefore use the
provider score only when the fixture is in the past; future fixtures have score=None.
This is deliberately conservative: a past fixture without a real score remains
unresolved rather than being converted into a draw.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

CFG = Path("config/selected-scout.json")
ROOT = Path("data/scouting")


def parse_dt(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def valid_score(score):
    if not isinstance(score, dict):
        return False
    for key in ("home", "away"):
        value = score.get(key)
        if isinstance(value, bool):
            return False
        try:
            if value is None or float(value) < 0:
                return False
        except (TypeError, ValueError):
            return False
    return True


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    root = ROOT / cfg["country"].lower().replace(" ", "-") / cfg["competition"].lower().replace(" ", "-") / cfg["team_id"]
    path = root / "normalized" / "fosi.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    finished = scheduled = unresolved = 0

    for match in data.get("matches", []):
        if not isinstance(match, dict):
            continue
        dt = parse_dt(match.get("date"))
        score = match.get("score")
        if dt is not None and dt > now:
            match["status"] = "scheduled"
            match["played"] = False
            match["score"] = None
            match["result_for_home"] = None
            scheduled += 1
        elif valid_score(score):
            match["status"] = "finished"
            match["played"] = True
            finished += 1
        else:
            match["status"] = "unresolved"
            match["played"] = False
            unresolved += 1

    data.setdefault("status_model", {})
    data["status_model"] = {
        "classified_at": now.isoformat(),
        "finished": finished,
        "scheduled": scheduled,
        "unresolved": unresolved,
        "rule": "future fixtures with placeholder scores are excluded from result and metric calculations"
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(data["status_model"], ensure_ascii=False))


if __name__ == "__main__":
    main()
