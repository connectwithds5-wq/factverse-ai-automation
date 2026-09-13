import json
import os
import shutil
import subprocess
from pathlib import Path

from gradio_client import Client, handle_file

OUTPUT = Path("output")
IMAGE_DIR = OUTPUT / "wan22_images"
CLIPS = OUTPUT / "wan22_clips"
STORYBOARD = OUTPUT / "storyboard.json"
FINAL = OUTPUT / "factverse.mp4"
MANIFEST = OUTPUT / "wan22_manifest.json"

SPACE = os.getenv("HF_WAN_SPACE", "zerogpu-aoti/wan2-2-fp8da-aoti-faster")
HF_TOKEN = os.getenv("HF_TOKEN") or None

NEGATIVE = (
    "text, letters, subtitles, caption, logo, watermark, UI, blurry, low quality, flicker, jitter, "
    "camera shake, morphing, deformed anatomy, duplicate subject, unstable colors, warped geometry"
)


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
    raise RuntimeError(f"Wan 2.2 returned no video path: {result!r}")


def probe_video(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height", "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Generated clip is not readable: {path}: {result.stderr[:300]}")
    data = json.loads(result.stdout or "{}")
    if not data.get("streams"):
        raise RuntimeError(f"Generated clip has no video stream: {path}")
    return data["streams"][0]


def load_board():
    if not STORYBOARD.exists():
        raise SystemExit("output/storyboard.json is required")
    board = json.loads(STORYBOARD.read_text(encoding="utf-8"))
    shots = board.get("shots", [])
    if not 4 <= len(shots) <= 5:
        raise SystemExit("Storyboard must contain 4 or 5 shots")
    previous = 0.0
    for index, shot in enumerate(shots, 1):
        start = float(shot["start"])
        end = float(shot["end"])
        duration = end - start
        if index == 1 and abs(start) > 0.01:
            raise SystemExit("Storyboard must start at 0")
        if abs(start - previous) > 0.01:
            raise SystemExit(f"Shot {index} is not contiguous")
        if duration < 3 or duration > 5:
            raise SystemExit(f"Shot {index} duration must be 3-5 seconds")
        previous = end
    if previous < 18 or previous > 22:
        raise SystemExit("Storyboard duration must be 18-22 seconds")
    return shots


def generate_shot(client, index, shot, image_path):
    duration = float(shot["end"]) - float(shot["start"])
    prompt = (
        f"{shot['visual_prompt']}. "
        f"Animate this reference image for exactly about {duration:.1f} seconds. "
        "Preserve the exact subject identity, geometry, colors and environment from the reference. "
        "Create one coherent continuous physical action, realistic motion, cinematic depth and subtle "
        "controlled camera movement. Premium photorealistic science-documentary cinematography, natural "
        "lighting, believable physics, stable details. No scene change, no morphing, no text."
    )
    print(f"\n=== Wan 2.2 shot {index} ({duration:.1f}s) ===")
    print("PROMPT:", prompt)
    result = client.predict(
        handle_file(str(image_path)),
        prompt,
        6,
        NEGATIVE,
        duration,
        1.0,
        1.0,
        22026 + index,
        False,
        api_name="/generate_video",
    )
    return Path(extract_video(result))


def main():
    shots = load_board()
    OUTPUT.mkdir(exist_ok=True)
    IMAGE_DIR.mkdir(exist_ok=True)
    CLIPS.mkdir(exist_ok=True)

    missing = [str(IMAGE_DIR / f"shot_{i:02d}.jpg") for i in range(1, len(shots) + 1) if not (IMAGE_DIR / f"shot_{i:02d}.jpg").exists()]
    if missing:
        raise SystemExit("Missing Wan 2.2 reference images. Run src/generate_storyboard_images.py first: " + ", ".join(missing))

    client = Client(SPACE, token=HF_TOKEN) if HF_TOKEN else Client(SPACE)
    manifest = {}
    if MANIFEST.exists():
        try:
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    for index, shot in enumerate(shots, 1):
        clip = CLIPS / f"shot_{index:02d}.mp4"
        if clip.exists() and clip.stat().st_size > 0:
            try:
                stream = probe_video(clip)
                print(f"Shot {index}: reusing validated cached clip ({stream.get('width')}x{stream.get('height')}, {stream.get('codec_name')})")
                continue
            except Exception as exc:
                print(f"Shot {index}: cached clip is invalid; regenerating: {exc}")
                clip.unlink(missing_ok=True)

        image_path = IMAGE_DIR / f"shot_{index:02d}.jpg"
        source = generate_shot(client, index, shot, image_path)
        if not source.exists() or source.stat().st_size == 0:
            raise RuntimeError(f"Wan 2.2 returned a missing/empty video for shot {index}: {source}")
        stream = probe_video(source)
        print(f"Shot {index}: generated {stream.get('width')}x{stream.get('height')} {stream.get('codec_name')}")
        shutil.copy2(source, clip)
        probe_video(clip)
        manifest[str(index)] = {
            "model": "Wan 2.2 I2V A14B FP8 AOTI",
            "space": SPACE,
            "source_image": str(image_path),
            "duration": float(shot["end"]) - float(shot["start"]),
        }
        MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Shot {index}: saved and checkpointed")

    required = [CLIPS / f"shot_{i:02d}.mp4" for i in range(1, len(shots) + 1)]
    if not all(path.exists() and path.stat().st_size > 0 for path in required):
        raise SystemExit("Not all Wan 2.2 clips exist after generation; refusing to concatenate partial output")

    concat = CLIPS / "concat.txt"
    concat.write_text("\n".join(f"file '{path.resolve()}'" for path in required) + "\n", encoding="utf-8")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", "-r", "30",
        "-an", "-movflags", "+faststart", str(FINAL),
    ], check=True)
    probe_video(FINAL)
    print(f"Wan 2.2 documentary video created: {FINAL}")


if __name__ == "__main__":
    main()
