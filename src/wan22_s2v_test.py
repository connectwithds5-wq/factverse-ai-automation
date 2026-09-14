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
VOICE_DIR = ROOT / "voices"
VOICE_MODEL = VOICE_DIR / "en_US-lessac-medium.onnx"
SHOT_AUDIO = OUTPUT / "s2v_test_voice.wav"
SHOT_VIDEO = OUTPUT / "s2v_test.mp4"

SPACE = os.getenv("HF_S2V_SPACE", "mjinabq/Wan2.2-S2V")
RESOLUTION = os.getenv("HF_S2V_RESOLUTION", "480P")
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
        for key in ("video", "output", "file", "path", "output_video"):
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
                continue
    if isinstance(result, str) and result:
        return result
    raise RuntimeError(f"S2V returned no video path: {result!r}")


def main():
    if not AVATAR.exists() or AVATAR.stat().st_size == 0:
        raise SystemExit("Missing output/avatar_reference.jpg")
    if not STORYBOARD.exists():
        raise SystemExit("Missing output/storyboard.json")

    board = json.loads(STORYBOARD.read_text(encoding="utf-8"))
    shots = board.get("shots", [])
    if not shots:
        raise SystemExit("Storyboard has no shots")

    shot = shots[0]
    target = float(shot["end"]) - float(shot["start"])
    narration = str(shot.get("narration", "")).strip()
    if not narration:
        raise SystemExit("Shot 1 has no narration")
    if target < 3 or target > 5:
        raise SystemExit("S2V test expects a 3-5 second first shot")

    VOICE_DIR.mkdir(exist_ok=True)
    if not VOICE_MODEL.exists():
        run([os.sys.executable, "-m", "piper.download_voices", "--data-dir", str(VOICE_DIR), "en_US-lessac-medium"])
    if not VOICE_MODEL.exists():
        raise SystemExit("Piper voice model unavailable")

    print(f"S2V test narration: {narration}", flush=True)
    raw = OUTPUT / "s2v_test_voice_raw.wav"
    run([
        os.sys.executable, "-m", "piper", "--model", str(VOICE_MODEL),
        "--output_file", str(raw), "--length_scale", "1.05",
        "--noise_scale", "0.55", "--noise_w_scale", "0.65", "--", narration,
    ])
    raw_dur = duration(raw)
    if raw_dur > target * 1.15:
        raise SystemExit(f"Shot 1 narration is too long for natural S2V test: {raw_dur:.2f}s vs {target:.2f}s")
    speed = min(1.15, max(0.5, raw_dur / target)) if raw_dur > target + 0.05 else 1.0
    if speed != 1.0:
        run(["ffmpeg", "-y", "-i", str(raw), "-af", f"atempo={speed:.6f}", "-ar", "44100", "-ac", "2", str(SHOT_AUDIO)])
    else:
        shutil.copy2(raw, SHOT_AUDIO)

    print(f"Connecting to S2V Space: {SPACE}", flush=True)
    client = Client(SPACE, token=TOKEN) if TOKEN else Client(SPACE)
    print(f"Calling /predict at {SPACE} ({RESOLUTION}) — this is the ONLY compute generation in this test.", flush=True)
    result = client.predict(
        handle_file(str(AVATAR)),
        handle_file(str(SHOT_AUDIO)),
        RESOLUTION,
        api_name="/predict",
    )
    print("S2V endpoint returned; extracting video...", flush=True)
    source = Path(extract_video(result))
    if not source.exists() or source.stat().st_size == 0:
        raise RuntimeError(f"S2V returned missing/empty video: {source}")
    shutil.copy2(source, SHOT_VIDEO)
    print(f"S2V TEST SUCCESS: {SHOT_VIDEO} ({duration(SHOT_VIDEO):.2f}s)", flush=True)


if __name__ == "__main__":
    main()
