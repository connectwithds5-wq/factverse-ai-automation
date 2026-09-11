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
    data = json.loads((Path("output") / "metadata.json").read_text(encoding="utf-8"))
    prompt = f'''Create a production-ready visual storyboard for a short science documentary.
The video has no hard 15-second limit; target 18-22 seconds if needed so the explanation is clear.
Every shot MUST be semantically aligned with its narration. Do not use generic filler visuals.
Use 4 or 5 shots. Total duration must be 18-22 seconds. Each shot must be 3-5 seconds.
For every shot return: start, end, narration, caption, visual_prompt.
Narration must be natural spoken English and directly explain what is visible.
Visual prompts must describe exactly the subject/action needed for that narration, photorealistic premium documentary style, vertical 9:16, smooth camera movement, no text, no subtitles, no watermark, no logo.
Captions must be short (max 8 words) and match the narration exactly.

HOOK: {data.get('hook','')}
FACT: {data.get('fact','')}
TWIST: {data.get('twist','')}

Return ONLY valid JSON: {{"shots":[{{"start":0,"end":4,"narration":"...","caption":"...","visual_prompt":"..."}}]}}'''
    body = {"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.4,"responseMimeType":"application/json"}}
    r = requests.post(API.format(model=MODEL), params={"key":KEY}, json=body, timeout=90)
    r.raise_for_status()
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    board = json.loads(text)
    shots = board.get("shots", [])
    if not 4 <= len(shots) <= 5:
        raise SystemExit("Storyboard must contain 4 or 5 shots")
    for i, shot in enumerate(shots):
        for key in ("narration", "caption", "visual_prompt"):
            if not str(shot.get(key, "")).strip():
                raise SystemExit(f"Shot {i+1} missing {key}")
        if float(shot["end"]) <= float(shot["start"]):
            raise SystemExit(f"Shot {i+1} has invalid timing")
    if float(shots[-1]["end"]) < 18 or float(shots[-1]["end"]) > 22:
        raise SystemExit("Storyboard duration must be 18-22 seconds")
    OUT.write_text(json.dumps(board, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Storyboard created: {OUT}")


if __name__ == "__main__":
    main()
