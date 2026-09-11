import json
import os
import time
from pathlib import Path

import requests

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
KEY = os.environ.get("GEMINI_API_KEY", "").strip()
OUT = Path("output") / "storyboard.json"


def fallback_storyboard(data, reason=""):
    """Build a deterministic aligned storyboard so Pixazo can continue if Gemini fails."""
    hook = str(data.get("hook", "")).strip()
    fact = str(data.get("fact", "")).strip()
    twist = str(data.get("twist", "")).strip()

    # Keep the fallback concise enough for an ~18 second voice track while
    # preserving the original story. The visual prompts are deliberately
    # specific instead of using generic filler language.
    shots = [
        {
            "start": 0,
            "end": 4.5,
            "narration": hook,
            "caption": "The surprising fact",
            "visual_prompt": (
                f"Open on a premium cinematic documentary visualization of this exact idea: {hook}. "
                "Show the real subject clearly in the first second, then make the key comparison or phenomenon "
                "visually obvious. Photorealistic, scientifically believable, dramatic natural lighting, slow "
                "controlled camera movement, vertical 9:16, no text, subtitles, logos or watermark."
            ),
        },
        {
            "start": 4.5,
            "end": 9.0,
            "narration": fact,
            "caption": "How it happens",
            "visual_prompt": (
                f"Create a concrete cinematic visual explanation of this exact scientific fact: {fact}. "
                "Show the actual physical objects, environment, scale difference, motion or process described, "
                "rather than an unrelated person or generic science imagery. Premium photorealistic documentary "
                "style, clear subject, smooth camera movement, vertical 9:16, no written text, subtitles, logos or watermark."
            ),
        },
        {
            "start": 9.0,
            "end": 13.5,
            "narration": f"The key is what this means in reality: {fact}",
            "caption": "The key mechanism",
            "visual_prompt": (
                f"Visually demonstrate the mechanism behind this statement: {fact}. "
                "Use a close, easy-to-understand physical demonstration or cinematic scientific visualization "
                "that directly corresponds to the words being spoken. Keep the main subject centered and readable, "
                "premium photorealistic documentary cinematography, vertical 9:16, controlled motion, no text, subtitles, logos or watermark."
            ),
        },
        {
            "start": 13.5,
            "end": 18.0,
            "narration": twist,
            "caption": "And that changes everything",
            "visual_prompt": (
                f"Create the final memorable documentary reveal for this exact conclusion: {twist}. "
                "Show the consequence or result literally and clearly, with a strong visual payoff rather than "
                "a generic abstract image. Premium photorealistic cinematic science documentary, subtle atmospheric "
                "motion, slow forward camera push, vertical 9:16, no text, subtitles, logos or watermark."
            ),
        },
    ]
    board = {"shots": shots, "source": "deterministic_fallback"}
    if reason:
        board["fallback_reason"] = reason[:500]
    return board


def validate_board(board):
    shots = board.get("shots", [])
    if not 4 <= len(shots) <= 5:
        raise ValueError("Storyboard must contain 4 or 5 shots")

    previous_end = 0.0
    for i, shot in enumerate(shots):
        try:
            start = float(shot["start"])
            end = float(shot["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Shot {i + 1} has invalid start/end") from exc

        duration = end - start
        if i == 0 and abs(start) > 0.01:
            raise ValueError("Storyboard must start at 0 seconds")
        if abs(start - previous_end) > 0.01:
            raise ValueError(f"Shot {i + 1} is not contiguous with the previous shot")
        if duration < 3.0 or duration > 5.0:
            raise ValueError(f"Shot {i + 1} duration must be 3-5 seconds")

        for key in ("narration", "caption", "visual_prompt"):
            if not str(shot.get(key, "")).strip():
                raise ValueError(f"Shot {i + 1} missing {key}")

        if len(str(shot["caption"]).split()) > 8:
            raise ValueError(f"Shot {i + 1} caption exceeds 8 words")

        previous_end = end

    if previous_end < 18.0 or previous_end > 22.0:
        raise ValueError("Storyboard duration must be 18-22 seconds")
    return previous_end


def request_gemini(prompt):
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.35,
            "responseMimeType": "application/json",
        },
    }

    last_error = None
    for attempt in range(1, 4):
        try:
            response = requests.post(
                API.format(model=MODEL),
                params={"key": KEY},
                json=body,
                timeout=90,
            )
            if response.status_code >= 400:
                detail = response.text[:800].replace("\n", " ")
                # Retry quota/transient/server failures; a persistent 4xx will
                # fall through to the deterministic storyboard quickly.
                if response.status_code in {408, 429, 500, 502, 503, 504} and attempt < 3:
                    wait = 2 ** (attempt - 1)
                    print(f"Gemini storyboard HTTP {response.status_code}; retrying in {wait}s ({attempt}/3)...")
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"Gemini storyboard HTTP {response.status_code}: {detail}")

            payload = response.json()
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except (requests.RequestException, ValueError, KeyError, TypeError, RuntimeError) as exc:
            last_error = exc
            if attempt < 3 and isinstance(exc, requests.RequestException):
                wait = 2 ** (attempt - 1)
                print(f"Gemini storyboard request error; retrying in {wait}s ({attempt}/3): {exc}")
                time.sleep(wait)
                continue
            break

    raise RuntimeError(str(last_error) if last_error else "Unknown Gemini storyboard error")


def main():
    if not KEY:
        raise SystemExit("GEMINI_API_KEY is required")

    metadata_path = Path("output") / "metadata.json"
    if not metadata_path.exists():
        raise SystemExit("output/metadata.json is required before storyboard generation")
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

    board = None
    try:
        board = request_gemini(prompt)
        duration = validate_board(board)
        board["source"] = "gemini"
        print(f"Gemini storyboard validated: {len(board['shots'])} shots, {duration:.2f}s")
    except Exception as exc:
        print(f"WARNING: Gemini storyboard unavailable or invalid: {exc}")
        print("Using deterministic aligned fallback storyboard; continuing to Pixazo.")
        board = fallback_storyboard(data, str(exc))
        duration = validate_board(board)
        print(f"Fallback storyboard validated: {len(board['shots'])} shots, {duration:.2f}s")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(board, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Storyboard created: {OUT}")


if __name__ == "__main__":
    main()
