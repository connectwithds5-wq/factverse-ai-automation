import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "output" / "metadata.json"
HISTORY = ROOT / "data" / "published_history.json"


def main():
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    try:
        history = json.loads(HISTORY.read_text(encoding="utf-8"))
    except Exception:
        history = {"videos": []}

    videos = history.get("videos", []) if isinstance(history, dict) else []
    if not isinstance(videos, list):
        videos = []

    entry = {
        "published_at": datetime.now(timezone.utc).isoformat(),
        "title": str(metadata.get("title", "")).strip(),
        "hook": str(metadata.get("hook", "")).strip(),
        "fact": str(metadata.get("fact", "")).strip(),
        "category": str(metadata.get("category", "")).strip(),
    }

    # Avoid adding the same publication twice if a retry reaches this step.
    key = (entry["title"].lower(), entry["fact"].lower())
    videos = [v for v in videos if (str(v.get("title", "")).lower(), str(v.get("fact", "")).lower()) != key]
    videos.append(entry)
    history = {"videos": videos[-100:]}
    HISTORY.write_text(json.dumps(history, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Recorded published FACTVERSE video:", entry["title"])


if __name__ == "__main__":
    main()
