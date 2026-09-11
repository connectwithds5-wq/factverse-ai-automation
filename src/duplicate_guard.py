import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "output" / "metadata.json"
HISTORY = ROOT / "data" / "published_history.json"
MAX_REGENERATIONS = 5


def norm(text):
    text = str(text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_history():
    if not HISTORY.exists():
        return []
    try:
        data = json.loads(HISTORY.read_text(encoding="utf-8"))
        videos = data.get("videos", []) if isinstance(data, dict) else []
        return videos if isinstance(videos, list) else []
    except Exception as exc:
        print(f"DUPLICATE GUARD: history unavailable; continuing safely ({exc})")
        return []


def load_metadata():
    return json.loads(METADATA.read_text(encoding="utf-8"))


def is_duplicate(current, history):
    current_title = norm(current.get("title"))
    current_hook = norm(current.get("hook"))
    current_fact = norm(current.get("fact"))
    current_category = norm(current.get("category"))

    for old in history[-50:]:
        old_title = norm(old.get("title"))
        old_hook = norm(old.get("hook"))
        old_fact = norm(old.get("fact"))
        old_category = norm(old.get("category"))

        if current_title and current_title == old_title:
            return True, f"same title: {old.get('title', '')}"
        if current_hook and current_hook == old_hook:
            return True, "same hook"
        if current_fact and current_fact == old_fact:
            return True, "same fact"

        # Catch near-identical regenerated metadata by comparing the first
        # 12 normalized words of the factual explanation.
        if current_fact and old_fact:
            a = " ".join(current_fact.split()[:12])
            b = " ".join(old_fact.split()[:12])
            if len(a) >= 45 and a == b:
                return True, "same factual opening"

        # If the category and core hook are both unchanged, treat it as a
        # duplicate even if punctuation/title wording changed.
        if current_category and current_category == old_category:
            a = set(current_hook.split())
            b = set(old_hook.split())
            if len(a) >= 4 and len(b) >= 4:
                overlap = len(a & b) / max(1, len(a | b))
                if overlap >= 0.75:
                    return True, "same category and near-identical hook"

    return False, ""


def main():
    if not METADATA.exists():
        raise SystemExit("DUPLICATE GUARD: output/metadata.json not found")

    history = load_history()
    for attempt in range(MAX_REGENERATIONS + 1):
        current = load_metadata()
        duplicate, reason = is_duplicate(current, history)
        if not duplicate:
            print(f"DUPLICATE GUARD: PASS (attempt {attempt + 1})")
            print("Title:", current.get("title", ""))
            return

        if attempt >= MAX_REGENERATIONS:
            raise SystemExit(
                "DUPLICATE GUARD: could not generate a sufficiently fresh topic "
                f"after {MAX_REGENERATIONS} regenerations ({reason})"
            )

        print(
            f"DUPLICATE GUARD: duplicate detected ({reason}); "
            f"regenerating {attempt + 1}/{MAX_REGENERATIONS}..."
        )
        subprocess.run(
            [sys.executable, str(ROOT / "src" / "generate_with_strategy.py")],
            cwd=ROOT,
            check=True,
        )


if __name__ == "__main__":
    main()
