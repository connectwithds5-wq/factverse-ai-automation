import json
import os
import subprocess
from pathlib import Path

import requests

OUTPUT = Path("output")
AVATAR = OUTPUT / "avatar_reference.jpg"
STORYBOARD = OUTPUT / "storyboard.json"
IMAGE_DIR = OUTPUT / "wan22_images"


def fail(message):
    raise SystemExit(f"PREFLIGHT FAILED: {message}")


def set_env(name, value):
    env_path = os.environ.get("GITHUB_ENV")
    if env_path:
        with open(env_path, "a", encoding="utf-8") as env:
            env.write(f"{name}={value}\n")


def check_binary(name):
    result = subprocess.run(["bash", "-lc", f"command -v {name}"], capture_output=True, text=True)
    if result.returncode != 0:
        fail(f"required binary not found: {name}")
    print(f"OK: {name} -> {result.stdout.strip()}")


def check_avatar():
    if not AVATAR.exists() or AVATAR.stat().st_size < 1000:
        fail(f"avatar reference missing or empty: {AVATAR}")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height", "-of", "json", str(AVATAR)],
        capture_output=True, text=True,
    )
    if probe.returncode != 0:
        fail(f"avatar is not a readable image: {probe.stderr[:300]}")
    data = json.loads(probe.stdout or "{}")
    streams = data.get("streams", [])
    if not streams:
        fail("avatar contains no video/image stream")
    stream = streams[0]
    print(f"OK: avatar {stream.get('codec_name')} {stream.get('width')}x{stream.get('height')}")


def check_gemini_model():
    key = os.getenv("GEMINI_API_KEY", "").strip()
    configured = os.getenv("GEMINI_MODEL", "").strip()
    if not key:
        fail("GEMINI_API_KEY is missing")

    try:
        response = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": key, "pageSize": 1000},
            timeout=30,
        )
        if response.status_code in {401, 403, 429}:
            print(f"WARNING: Gemini model-list returned HTTP {response.status_code}; disabling Gemini storyboard generation to avoid wasted requests.")
            set_env("GEMINI_STORYBOARD_ENABLED", "0")
            return
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        print(f"WARNING: Gemini model-list preflight could not complete: {exc}")
        print("WARNING: disabling Gemini storyboard generation; deterministic fallback will be used.")
        set_env("GEMINI_STORYBOARD_ENABLED", "0")
        return

    available = {}
    for model in payload.get("models", []):
        name = str(model.get("name", "")).removeprefix("models/")
        methods = model.get("supportedGenerationMethods", [])
        if name and "generateContent" in methods:
            available[name] = model

    if configured and configured in available:
        print(f"OK: Gemini storyboard model available: {configured}")
        set_env("GEMINI_STORYBOARD_ENABLED", "1")
        return

    print(f"WARNING: configured Gemini storyboard model is unavailable: {configured or '<empty>'}")
    candidates = [name for name in available if "flash" in name.lower() and "image" not in name.lower()]
    if candidates:
        print("Available text-generation candidates:", ", ".join(sorted(candidates)[:20]))
    print("WARNING: storyboard generation will use the deterministic fallback; no Gemini generation request will be attempted.")
    set_env("GEMINI_STORYBOARD_ENABLED", "0")


def check_storyboard_and_images():
    if not STORYBOARD.exists():
        print("INFO: storyboard not created yet; skipping storyboard/image checks in this stage.")
        return

    board = json.loads(STORYBOARD.read_text(encoding="utf-8"))
    shots = board.get("shots", [])
    if not 4 <= len(shots) <= 5:
        fail("storyboard must contain 4 or 5 shots")
    previous = 0.0
    for index, shot in enumerate(shots, 1):
        start = float(shot["start"])
        end = float(shot["end"])
        duration = end - start
        if abs(start - previous) > 0.01 or duration < 3 or duration > 5:
            fail(f"invalid storyboard timing at shot {index}: {start}->{end}")
        if not str(shot.get("visual_prompt", "")).strip():
            fail(f"shot {index} has no visual_prompt")
        previous = end
    if previous < 18 or previous > 22:
        fail(f"storyboard duration is {previous:.2f}s; expected 18-22s")
    print(f"OK: storyboard {len(shots)} shots / {previous:.2f}s")

    missing = [str(IMAGE_DIR / f"shot_{i:02d}.jpg") for i in range(1, len(shots) + 1) if not (IMAGE_DIR / f"shot_{i:02d}.jpg").exists()]
    if missing:
        fail("missing Wan reference images: " + ", ".join(missing))
    print(f"OK: {len(shots)} Wan reference images present")


def check_wan_space():
    space = os.getenv("HF_WAN_SPACE", "").strip()
    token = os.getenv("HF_TOKEN", "").strip() or None
    if not space:
        fail("HF_WAN_SPACE is missing")

    print(f"Checking Wan Space configuration only (no video generation): {space}")
    try:
        from gradio_client import Client
        client = Client(space, token=token, verbose=False)
        api = client.view_api(return_format="dict")
    except Exception as exc:
        fail(f"Wan Space/API preflight failed before generation: {exc}")

    text = json.dumps(api, ensure_ascii=False)
    if "/generate_video" not in text:
        fail("Wan Space does not expose the expected /generate_video endpoint")
    print("OK: Wan Space reachable and /generate_video endpoint is exposed")


def main():
    print("=== FACTVERSE WAN 2.2 ZERO-COST PREFLIGHT ===")
    check_binary("ffmpeg")
    check_binary("ffprobe")
    check_avatar()
    check_gemini_model()
    check_storyboard_and_images()
    check_wan_space()
    print("=== PREFLIGHT PASSED: safe to proceed to Wan generation ===")


if __name__ == "__main__":
    main()
