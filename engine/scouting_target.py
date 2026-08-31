"""Resolve the active scouting target for scheduled FOSI runs."""
import json
from pathlib import Path

CONFIG = Path("config/active-scout.json")


def load_target():
    if not CONFIG.exists():
        return None
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    if not data.get("active") or not data.get("team"):
        return None
    return data


def main():
    target = load_target()
    print(json.dumps(target or {"active": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
