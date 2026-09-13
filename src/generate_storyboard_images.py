import base64
import json
import os
import shutil
from pathlib import Path

from google import genai

STORYBOARD = Path("output/storyboard.json")
OUT = Path("output/wan22_images")
AVATAR = Path("output/avatar_reference.jpg")
MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")


def load_api_keys():
    keys = []
    for name in (
        "GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3",
        "GEMINI_API_KEY_4", "GEMINI_API_KEY_5",
    ):
        value = os.getenv(name, "").strip()
        if value and value not in keys:
            keys.append(value)
    return keys


def is_key_related_error(exc):
    text = str(exc).lower()
    return any(marker in text for marker in (
        "429", "quota", "rate limit", "resource_exhausted", "too many requests",
        "401", "403", "unauthorized", "forbidden",
    ))


def generate_with_fallback(keys, key_index, prompt):
    errors = []
    total = len(keys)
    for offset in range(total):
        idx = (key_index + offset) % total
        try:
            print(f"Trying Gemini image key {idx + 1}/{total}")
            client = genai.Client(api_key=keys[idx])
            interaction = client.interactions.create(
                model=MODEL,
                input=prompt,
                response_format={"type": "image", "mime_type": "image/jpeg", "aspect_ratio": "9:16", "image_size": "1K"},
            )
            image = getattr(interaction, "output_image", None)
            data = getattr(image, "data", None) if image else None
            if not data:
                raise RuntimeError("Gemini image generation returned no image")
            return base64.b64decode(data), idx
        except Exception as exc:
            errors.append(f"key {idx + 1}: {exc}")
            if not is_key_related_error(exc):
                raise
            print(f"Gemini key {idx + 1} unavailable; rotating to next key")
    raise RuntimeError("All configured Gemini API keys failed:\n" + "\n".join(errors))


def main():
    if not STORYBOARD.exists():
        raise SystemExit("output/storyboard.json is required")
    board = json.loads(STORYBOARD.read_text(encoding="utf-8"))
    shots = board.get("shots", [])
    if not 4 <= len(shots) <= 5:
        raise SystemExit("Storyboard must contain 4 or 5 shots")

    OUT.mkdir(parents=True, exist_ok=True)

    # Avatar-first mode: when the private avatar reference is available, use
    # the same source frame for every shot. This preserves identity and avoids
    # making the whole production dependent on Gemini image-generation quota.
    if AVATAR.exists() and AVATAR.stat().st_size > 0:
        print(f"Avatar reference detected: {AVATAR}")
        for index in range(1, len(shots) + 1):
            target = OUT / f"shot_{index:02d}.jpg"
            shutil.copy2(AVATAR, target)
            print(f"Shot {index}: using avatar reference -> {target}")
        print("Avatar-first mode complete; Gemini image generation skipped.")
        return

    keys = load_api_keys()
    if not keys:
        raise SystemExit("No Gemini image keys available and no avatar reference was downloaded")

    key_index = 0
    for index, shot in enumerate(shots, 1):
        target = OUT / f"shot_{index:02d}.jpg"
        if target.exists() and target.stat().st_size > 0:
            print(f"Shot {index}: reusing {target}")
            continue
        visual = str(shot["visual_prompt"]).strip()
        prompt = (
            "Create a single premium photorealistic vertical 9:16 documentary keyframe for a video shot. "
            "This image will be animated by Wan 2.2 image-to-video. Show exactly the subject, environment, "
            "physical action and visual relationship described below. Make the first frame compositionally "
            "strong and animation-friendly: clear foreground, midground and background, stable geometry, "
            "natural lighting, realistic materials, physically believable scale. No text, subtitles, captions, "
            "logos, UI, infographic labels or watermark-like graphics. Do not add unrelated people or objects.\n\n"
            f"SHOT VISUAL: {visual}"
        )
        print(f"\nGenerating cinematic keyframe {index} with {MODEL}")
        data, key_index = generate_with_fallback(keys, key_index, prompt)
        target.write_bytes(data)
        print(f"Shot {index}: saved {target}")


if __name__ == "__main__":
    main()
