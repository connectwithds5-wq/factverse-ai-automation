import json
import os
import shutil
import subprocess
from pathlib import Path

from gradio_client import Client, handle_file

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
AVATAR = OUTPUT / "avatar_reference.jpg"
STORYBOARD = OUTPUT / "storyboard.json"
CHOICE = OUTPUT / "free_avatar_choice.json"
VOICE_DIR = ROOT / "voices"
VOICE_MODEL = VOICE_DIR / "en_US-lessac-medium.onnx"
AUDIO = OUTPUT / "free_avatar_voice.wav"
VIDEO = OUTPUT / "free_avatar_test.mp4"
TOKEN = os.getenv("HF_TOKEN_2") or os.getenv("HF_TOKEN") or None


def run(cmd):
    print("RUN:", " ".join(map(str, cmd)), flush=True)
    subprocess.run(cmd, check=True)


def duration(path):
    return float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], text=True).strip())


def extract_video(result):
    if isinstance(result, dict):
        for key in ("video", "output_video", "output", "file", "path"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, dict):
                nested = extract_video(value)
                if nested:
                    return nested
    if isinstance(result, (list, tuple)):
        for item in result:
            try:
                return extract_video(item)
            except RuntimeError:
                pass
    if isinstance(result, str) and result:
        return result
    raise RuntimeError(f"No video path returned: {result!r}")


def build_audio(narration, target):
    VOICE_DIR.mkdir(exist_ok=True)
    if not VOICE_MODEL.exists():
        run([os.sys.executable, "-m", "piper.download_voices", "--data-dir", str(VOICE_DIR), "en_US-lessac-medium"])
    raw = OUTPUT / "free_avatar_voice_raw.wav"
    run([
        os.sys.executable, "-m", "piper", "--model", str(VOICE_MODEL),
        "--output_file", str(raw), "--length_scale", "1.05",
        "--noise_scale", "0.55", "--noise_w_scale", "0.65", "--", narration,
    ])
    raw_dur = duration(raw)
    if raw_dur > target * 1.15:
        raise RuntimeError(f"Narration too long: {raw_dur:.2f}s for {target:.2f}s shot")
    speed = min(1.15, max(0.5, raw_dur / target)) if raw_dur > target + 0.05 else 1.0
    if speed != 1.0:
        run(["ffmpeg", "-y", "-i", str(raw), "-af", f"atempo={speed:.6f}", "-ar", "44100", "-ac", "2", str(AUDIO)])
    else:
        shutil.copy2(raw, AUDIO)


def main():
    if not AVATAR.exists() or AVATAR.stat().st_size == 0:
        raise SystemExit("Missing avatar_reference.jpg")
    if not STORYBOARD.exists() or not CHOICE.exists():
        raise SystemExit("Missing storyboard or preflight choice")

    board = json.loads(STORYBOARD.read_text(encoding="utf-8"))
    shots = board.get("shots", [])
    if not shots:
        raise SystemExit("Storyboard has no shots")
    shot = shots[0]
    target = float(shot["end"]) - float(shot["start"])
    narration = str(shot.get("narration", "")).strip()
    if not narration:
        raise SystemExit("Shot 1 has no narration")
    if not 3 <= target <= 5:
        raise SystemExit(f"Expected 3-5 sec test shot, got {target:.2f}s")

    choice = json.loads(CHOICE.read_text(encoding="utf-8"))
    space = choice["space"]
    api_name = choice["api_name"]
    name = choice["name"]
    print(f"SELECTED FREE MODEL: {name}", flush=True)
    print(f"SPACE: {space}", flush=True)
    print(f"ENDPOINT: {api_name}", flush=True)
    print("THIS STEP PERFORMS EXACTLY ONE VIDEO GENERATION. NO RETRIES.", flush=True)

    build_audio(narration, target)
    client = Client(space, token=TOKEN) if TOKEN else Client(space)

    if name.startswith("LongCat"):
        result = client.predict(
            handle_file(str(AVATAR)),
            handle_file(str(AUDIO)),
            "A person is speaking naturally and expressively to camera, with realistic facial motion and subtle emotion.",
            "480p",
            42,
            api_name=api_name,
        )
    elif name == "EchoMimic":
        # Shared ZeroGPU Space exposes the documented generate_video signature.
        result = client.predict(
            handle_file(str(AVATAR)),
            handle_file(str(AUDIO)),
            512,
            512,
            120,
            420,
            0.1,
            0.5,
            12,
            3,
            2.5,
            30,
            16000,
            24,
            "cuda",
            api_name=api_name,
        )
    else:
        raise SystemExit(f"Selected model has no safe explicit wrapper: {name}")

    source = Path(extract_video(result))
    if not source.exists() or source.stat().st_size == 0:
        raise RuntimeError(f"Model returned missing/empty video: {source}")
    shutil.copy2(source, VIDEO)
    print(f"ONE-SHOT SUCCESS: {VIDEO} ({duration(VIDEO):.2f}s)", flush=True)


if __name__ == "__main__":
    main()
