"""Isolated Wan 2.2 cinematic test.

This file intentionally does not modify the production Pixazo renderer.
It uses the same Wan 2.2 Gradio Space tested in toon_kids_automation.
"""
import os
import shutil
from pathlib import Path
from gradio_client import Client, handle_file

SPACE = os.getenv("HF_WAN_SPACE", "zerogpu-aoti/wan2-2-fp8da-aoti-faster")
HF_TOKEN = os.getenv("HF_TOKEN") or None
OUT = Path(os.getenv("WAN22_TEST_OUTPUT", "output/wan22_cinematic_test.mp4"))
DURATION = float(os.getenv("WAN22_TEST_DURATION", "5"))


def extract_video(result):
    if isinstance(result, dict):
        for key in ("video", "output", "file", "path"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return value
    if isinstance(result, (list, tuple)):
        for item in result:
            try:
                return extract_video(item)
            except RuntimeError:
                pass
    if isinstance(result, str) and result:
        return result
    raise RuntimeError(f"No video path returned by Wan 2.2: {result!r}")


def main():
    image = os.getenv("WAN22_TEST_IMAGE")
    if not image or not Path(image).is_file():
        raise RuntimeError("Set WAN22_TEST_IMAGE to a valid local image path")

    prompt = os.getenv("WAN22_TEST_PROMPT", """
Premium cinematic documentary-style image-to-video shot. Preserve the exact subject identity,
shape, colors and environment from the reference image. Create believable natural motion with
clear physical movement, cinematic depth, realistic lighting, subtle camera movement and strong
foreground/midground/background separation. Slow controlled camera push-in, polished film look,
photorealistic detail, stable anatomy, no morphing. Vertical 9:16 composition. No text, captions,
logos or watermarks.
""").strip()
    negative = "text, letters, subtitles, logo, watermark, UI, blurry, low quality, flicker, jitter, camera shake, morphing, deformed anatomy, duplicate subject, unstable colors"

    client = Client(SPACE, token=HF_TOKEN) if HF_TOKEN else Client(SPACE)
    result = client.predict(
        handle_file(image), prompt, 6, negative, DURATION, 1.0, 1.0, 22026, False,
        api_name="/generate_video"
    )
    source = Path(extract_video(result))
    if not source.is_file():
        raise FileNotFoundError(source)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, OUT)
    print(f"WAN22_TEST_OUTPUT={OUT}")


if __name__ == "__main__":
    main()
