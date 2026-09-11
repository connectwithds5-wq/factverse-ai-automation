import base64
import json
import os
from pathlib import Path

from google import genai

STORYBOARD = Path("output/storyboard.json")
OUT = Path("output/wan22_images")
MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")


def main():
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise SystemExit("GEMINI_API_KEY is required")
    if not STORYBOARD.exists():
        raise SystemExit("output/storyboard.json is required")

    board = json.loads(STORYBOARD.read_text(encoding="utf-8"))
    shots = board.get("shots", [])
    if not 4 <= len(shots) <= 5:
        raise SystemExit("Storyboard must contain 4 or 5 shots")

    OUT.mkdir(parents=True, exist_ok=True)
    client = genai.Client(api_key=key)

    for index, shot in enumerate(shots, 1):
        target = OUT / f"shot_{index:02d}.png"
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
        interaction = client.interactions.create(
            model=MODEL,
            input=prompt,
            response_format={
                "type": "image",
                "mime_type": "image/png",
                "aspect_ratio": "9:16",
                "image_size": "1K",
            },
        )
        image = getattr(interaction, "output_image", None)
        data = getattr(image, "data", None) if image else None
        if not data:
            raise RuntimeError(f"Gemini image generation returned no image for shot {index}")
        target.write_bytes(base64.b64decode(data))
        print(f"Shot {index}: saved {target}")


if __name__ == "__main__":
    main()
