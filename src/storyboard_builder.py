import json
import os
from pathlib import Path

import requests

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
KEY = os.environ.get("GEMINI_API_KEY", "").strip()
OUT = Path("output") / "storyboard.json"


def main():
    if not KEY:
        raise SystemExit("GEMINI_API_KEY is required")

    metadata_path = Path("output") / "metadata.json"
    data = json.loads(metadata_path.read_text(encoding="utf-8"))

    prompt = f'''Create a production-ready visual storyboard for a short science documentary.
There is NO hard 15-second limit. Target 18-22 seconds so the explanation is clear and natural.
Use exactly 4 shots unless the story genuinely needs 5. Each shot must be 3-5 seconds.
Shots MUST be contiguous: shot 1 starts at 0, and each next shot starts exactly where the previous ends.
The final end time must be between 18 and 22 seconds.

Most important rule: every shot MUST be semantically aligned with its narration.
The visual must literally show the subject, action, object, process, or comparison being described.
Never use generic filler such as "here is what is happening" or "the surprising part".
Do not repeat the same generic visual across shots.

For every shot return:
- start: number in seconds
- end: number in seconds
- narration: natural spoken English for that exact shot
- caption: maximum 8 words, a concise key phrase from the narration
- visual_prompt: exact visual subject/action, premium photorealistic documentary style, vertical 9:16, cinematic but scientifically believable, smooth controlled camera movement

Narration should explain the visual, not merely repeat the original fact. Keep wording concise enough to fit its shot duration.
Visual prompts must not contain written text, subtitles, logos, watermarks, UI, or infographic labels.
If a scientific concept is abstract, visualize it with a realistic physical analogy or elegant cinematic scientific visualization.

HOOK: {data.get('hook','')}
FACT: {data.get('fact','')}
TWIST: {data.get('twist','')}

Return ONLY valid JSON:
{{"shots":[{{"start":0,"end":4,"narration":"...","caption":"...","visual_prompt":"..."}}]}}'''

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.35,
            "responseMimeType": "application/json",
        },
    }

    response = requests.post(
        API.format(model=MODEL),
        params={"key": KEY},
        json=body,
        timeout=90,
    )
    response.raise_for_status()

    text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    board = json.loads(text)
    shots = board.get("shots", [])

    if not 4 <= len(shots) <= 5:
        raise SystemExit("Storyboard must contain 4 or 5 shots")

    previous_end = 0.0
    for i, shot in enumerate(shots):
        try:
            start = float(shot["start"])
            end = float(shot["end"])
        except (KeyError, TypeError, ValueError):
            raise SystemExit(f"Shot {i + 1} has invalid start/end")

        duration = end - start
        if i == 0 and abs(start) > 0.01:
            raise SystemExit("Storyboard must start at 0 seconds")
        if abs(start - previous_end) > 0.01:
            raise SystemExit(f"Shot {i + 1} is not contiguous with the previous shot")
        if duration < 3.0 or duration > 5.0:
            raise SystemExit(f"Shot {i + 1} duration must be 3-5 seconds")

        for key in ("narration", "caption", "visual_prompt"):
            if not str(shot.get(key, "")).strip():
                raise SystemExit(f"Shot {i + 1} missing {key}")

        if len(str(shot["caption"]).split()) > 8:
            raise SystemExit(f"Shot {i + 1} caption exceeds 8 words")

        previous_end = end

    if previous_end < 18.0 or previous_end > 22.0:
        raise SystemExit("Storyboard duration must be 18-22 seconds")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(board, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Storyboard created: {OUT}")
    print(f"Shots: {len(shots)} | Duration: {previous_end:.2f}s")


if __name__ == "__main__":
    main()
