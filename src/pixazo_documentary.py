import concurrent.futures
import json
import os
import subprocess
import time
from pathlib import Path

import requests

API_URL = os.environ.get("PIXAZO_API_URL", "https://gateway.pixazo.ai/ltx-video/v1/text-to-video")
STATUS_URL = "https://gateway.pixazo.ai/v2/requests/status/{request_id}"
API_KEY = os.environ.get("PIXAZO_API_KEY", "").strip()

OUTPUT = Path("output")
CLIPS = OUTPUT / "pixazo_clips"
FINAL = OUTPUT / "factverse.mp4"
REQUESTS_FILE = OUTPUT / "pixazo_requests.json"
MANIFEST_FILE = OUTPUT / "pixazo_manifest.json"
STORYBOARD = OUTPUT / "storyboard.json"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
NEGATIVE = (
    "blurry, low quality, distorted, worst quality, jpeg artifacts, text, subtitles, "
    "watermark, logo, UI, split screen, duplicate person, deformed hands, distorted face, "
    "unreadable symbols, floating objects, unrealistic anatomy"
)

# Pixazo LTX Free is a shared asynchronous service. Keep generation sequential so a
# slow queued job does not leave several orphaned server-side jobs running after one
# client-side timeout. The GitHub job has a 120-minute budget.
POLL_SECONDS = 8
SHOT_TIMEOUT_SECONDS = 30 * 60
SUBMIT_RETRIES = 4
MAX_WORKERS = 1


def run(cmd):
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def wrap_caption(text, width=24):
    words = str(text).replace("\n", " ").split()
    lines, line = [], ""
    for word in words:
        candidate = word if not line else line + " " + word
        if len(candidate) > width and line:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return "\n".join(lines[:3])


def request_clip(prompt, num_frames, seed, shot_index):
    payload = {
        "prompt": prompt,
        "negative": NEGATIVE,
        "seed": seed,
        "aspect": "9:16",
        "width": 576,
        "height": 1024,
        "num_frames": num_frames,
        "frame_rate": 24,
        "steps": 8,
        "cfg": 3.0,
    }
    headers = {
        "Content-Type": "application/json",
        "Ocp-Apim-Subscription-Key": API_KEY,
    }

    response = None
    for attempt in range(1, SUBMIT_RETRIES + 1):
        try:
            response = requests.post(API_URL, json=payload, headers=headers, timeout=60)
            if response.status_code != 429:
                break
            wait = min(30, 5 * attempt)
            print(f"Shot {shot_index}: Pixazo rate limited on submit; retrying in {wait}s")
            time.sleep(wait)
        except requests.RequestException as exc:
            if attempt == SUBMIT_RETRIES:
                raise RuntimeError(f"Shot {shot_index}: Pixazo submit request failed: {exc}") from exc
            wait = min(30, 5 * attempt)
            print(f"Shot {shot_index}: submit network error; retrying in {wait}s: {exc}")
            time.sleep(wait)

    if response is None or response.status_code >= 400:
        detail = response.text[:1000] if response is not None else "no response"
        code = response.status_code if response is not None else "unknown"
        raise RuntimeError(f"Shot {shot_index}: Pixazo submit failed ({code}): {detail}")

    data = response.json()
    request_id = data.get("request_id")
    if not request_id:
        raise RuntimeError(f"Shot {shot_index}: Pixazo response missing request_id: {data}")

    print(f"Shot {shot_index}: Pixazo request queued: {request_id}")
    status_url = data.get("polling_url") or STATUS_URL.format(request_id=request_id)
    deadline = time.time() + SHOT_TIMEOUT_SECONDS

    while time.time() < deadline:
        try:
            status_response = requests.get(status_url, headers=headers, timeout=60)
        except requests.RequestException as exc:
            print(f"Shot {shot_index}: status network error; retrying: {exc}")
            time.sleep(POLL_SECONDS)
            continue

        if status_response.status_code == 429:
            print(f"Shot {shot_index}: status rate limited; retrying in {POLL_SECONDS}s")
            time.sleep(POLL_SECONDS)
            continue
        if status_response.status_code >= 400:
            raise RuntimeError(
                f"Shot {shot_index}: Pixazo status failed ({status_response.status_code}): "
                f"{status_response.text[:1000]}"
            )

        status = status_response.json()
        state = str(status.get("status", "")).upper()
        print(f"Shot {shot_index}: status={state}")
        if state == "COMPLETED":
            media = (status.get("output") or {}).get("media_url") or []
            if not media:
                raise RuntimeError(f"Shot {shot_index}: completed without media_url: {status}")
            return request_id, media[0]
        if state in {"FAILED", "ERROR"}:
            raise RuntimeError(f"Shot {shot_index}: Pixazo generation failed: {status}")
        time.sleep(POLL_SECONDS)

    raise TimeoutError(
        f"Shot {shot_index}: Pixazo request timed out after {SHOT_TIMEOUT_SECONDS // 60} minutes: {request_id}"
    )


def download(url, path):
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)


def load_storyboard():
    if not STORYBOARD.exists():
        raise SystemExit("output/storyboard.json is required before Pixazo rendering")

    board = json.loads(STORYBOARD.read_text(encoding="utf-8"))
    shots = board.get("shots", [])
    if not 4 <= len(shots) <= 5:
        raise SystemExit("Storyboard must contain 4 or 5 shots")

    previous_end = 0.0
    for index, shot in enumerate(shots, start=1):
        try:
            start = float(shot["start"])
            end = float(shot["end"])
        except (KeyError, TypeError, ValueError):
            raise SystemExit(f"Storyboard shot {index} has invalid timing")
        duration = end - start
        if index == 1 and abs(start) > 0.01:
            raise SystemExit("Storyboard must start at 0 seconds")
        if abs(start - previous_end) > 0.01:
            raise SystemExit(f"Storyboard shot {index} is not contiguous")
        if duration < 3.0 or duration > 5.0:
            raise SystemExit(f"Storyboard shot {index} duration must be 3-5 seconds")
        for key in ("narration", "caption", "visual_prompt"):
            if not str(shot.get(key, "")).strip():
                raise SystemExit(f"Storyboard shot {index} missing {key}")
        previous_end = end

    if previous_end < 18.0 or previous_end > 22.0:
        raise SystemExit("Storyboard duration must be 18-22 seconds")
    return shots, previous_end


def prepare_shot(index, shot):
    start = float(shot["start"])
    end = float(shot["end"])
    duration = end - start
    narration = str(shot["narration"]).strip()
    caption = str(shot["caption"]).strip()
    visual_prompt = str(shot["visual_prompt"]).strip()
    prompt = (
        f"{visual_prompt}. This shot is exactly {duration:.1f} seconds long. "
        "Show one coherent continuous action from beginning to end. "
        "Keep the main subject clearly visible and centered in the vertical safe area. "
        "Premium cinematic science documentary, photorealistic, physically believable, "
        "natural motion, realistic camera optics, subtle depth of field, controlled camera movement."
    )
    frames = max(25, round(duration * 24) + 1)
    return {
        "shot": index,
        "start": start,
        "end": end,
        "duration": duration,
        "narration": narration,
        "caption": caption,
        "prompt": prompt,
        "frames_requested": frames,
        "seed": 9100 + index,
    }


def process_shot(spec, cached_record=None):
    index = spec["shot"]
    duration = spec["duration"]
    processed_clip = CLIPS / f"shot_{index:02d}.mp4"
    raw = CLIPS / f"shot_{index:02d}_raw.mp4"

    if processed_clip.exists() and processed_clip.stat().st_size > 0:
        print(f"Shot {index}: reusing cached processed clip")
        return {
            **spec,
            "request_id": (cached_record or {}).get("request_id", "cached"),
            "media_url": (cached_record or {}).get("media_url", "cached"),
            "model": "ltx-video (Pixazo LTX Free)",
            "cached": True,
        }

    print(f"\n=== Pixazo documentary shot {index} ({duration:.1f}s) ===")
    print("NARRATION:", spec["narration"])
    print("CAPTION:", spec["caption"])
    print("PROMPT:", spec["prompt"])

    request_id, media_url = request_clip(spec["prompt"], spec["frames_requested"], spec["seed"], index)
    download(media_url, raw)

    caption_file = CLIPS / f"caption_{index:02d}.txt"
    caption_file.write_text(wrap_caption(spec["caption"]), encoding="utf-8")

    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,setsar=1,"
        "drawbox=x=0:y=0:w=iw:h=130:color=black@0.18:t=fill,"
        f"drawtext=fontfile={FONT}:text='FACTVERSE':fontcolor=white:fontsize=38:"
        "x=54:y=42:shadowcolor=black@0.75:shadowx=2:shadowy=2,"
        f"drawtext=fontfile={FONT}:textfile='{caption_file.resolve()}':"
        "fontcolor=white:fontsize=58:line_spacing=10:"
        "x=(w-text_w)/2:y=1310:box=1:boxcolor=black@0.46:boxborderw=22:"
        "shadowcolor=black@0.85:shadowx=2:shadowy=2"
    )

    run([
        "ffmpeg", "-y", "-i", str(raw), "-vf", vf,
        "-t", f"{duration:.3f}", "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-r", "30", str(processed_clip),
    ])

    return {
        **spec,
        "request_id": request_id,
        "media_url": media_url,
        "model": "ltx-video (Pixazo LTX Free)",
        "cached": False,
    }


def main():
    if not API_KEY:
        raise SystemExit("PIXAZO_API_KEY is required")

    metadata_path = OUTPUT / "metadata.json"
    if not metadata_path.exists():
        raise SystemExit("output/metadata.json is required before Pixazo rendering")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    CLIPS.mkdir(parents=True, exist_ok=True)
    shots, total_duration = load_storyboard()
    specs = [prepare_shot(index, shot) for index, shot in enumerate(shots, start=1)]

    manifest = {}
    if MANIFEST_FILE.exists():
        try:
            manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            manifest = {}

    records = [None] * len(specs)
    pending = []

    for spec in specs:
        cached = manifest.get(str(spec["shot"]))
        if (CLIPS / f"shot_{spec['shot']:02d}.mp4").exists():
            records[spec["shot"] - 1] = process_shot(spec, cached)
        else:
            pending.append(spec)

    if pending:
        print("Starting Pixazo shots sequentially to avoid free-tier queue contention")
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_map = {executor.submit(process_shot, spec): spec for spec in pending}
            for future in concurrent.futures.as_completed(future_map):
                spec = future_map[future]
                try:
                    record = future.result()
                except Exception as exc:
                    for other in future_map:
                        if other is not future:
                            other.cancel()
                    raise RuntimeError(f"Pixazo shot {spec['shot']} failed: {exc}") from exc
                records[spec["shot"] - 1] = record
                manifest[str(spec["shot"])] = record
                MANIFEST_FILE.write_text(
                    json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                print(f"Shot {spec['shot']}: completed and checkpointed")

    if any(record is None for record in records):
        raise SystemExit("Pixazo rendering ended without all storyboard shots")

    REQUESTS_FILE.write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    processed = [CLIPS / f"shot_{i:02d}.mp4" for i in range(1, len(specs) + 1)]
    concat_file = CLIPS / "concat.txt"
    concat_file.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in processed) + "\n", encoding="utf-8"
    )

    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-pix_fmt", "yuv420p", "-r", "30", "-an",
        "-movflags", "+faststart", str(FINAL),
    ])

    if not FINAL.exists() or FINAL.stat().st_size == 0:
        raise SystemExit("Pixazo documentary video was not created")

    print(f"Created: {FINAL} ({total_duration:.2f}s storyboard target)")


if __name__ == "__main__":
    main()
