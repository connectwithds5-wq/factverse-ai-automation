import json
import os
import subprocess
import time
from pathlib import Path

import requests


API_URL = "https://gateway.pixazo.ai/ltx-video/v1/text-to-video"
STATUS_URL = "https://gateway.pixazo.ai/v2/requests/status/{request_id}"
API_KEY = os.environ.get("PIXAZO_API_KEY", "").strip()

OUTPUT = Path("output")
CLIPS = OUTPUT / "pixazo_clips"
PLAN_FILE = OUTPUT / "documentary_plan.json"
FINAL = OUTPUT / "factverse_pixazo_documentary.mp4"
REQUESTS_FILE = OUTPUT / "pixazo_requests.json"

NEGATIVE = "blurry, low quality, distorted, worst quality, jpeg artifacts, text, subtitles, watermark, logo, UI, split screen"


def run(cmd):
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def esc_drawtext(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
    )


def request_clip(prompt: str, num_frames: int, seed: int):
    # IMPORTANT: prompt is passed exactly as supplied by the fixed test plan.
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

    response = requests.post(API_URL, json=payload, headers=headers, timeout=60)
    if response.status_code >= 400:
        raise RuntimeError(f"Pixazo submit failed ({response.status_code}): {response.text[:1000]}")

    data = response.json()
    request_id = data.get("request_id")
    if not request_id:
        raise RuntimeError(f"Pixazo response missing request_id: {data}")

    print(f"Pixazo request queued: {request_id}")
    status_url = data.get("polling_url") or STATUS_URL.format(request_id=request_id)

    deadline = time.time() + 12 * 60
    while time.time() < deadline:
        status_response = requests.get(status_url, headers=headers, timeout=60)
        if status_response.status_code >= 400:
            raise RuntimeError(
                f"Pixazo status failed ({status_response.status_code}): {status_response.text[:1000]}"
            )

        status = status_response.json()
        state = str(status.get("status", "")).upper()
        print(f"  status={state}")

        if state == "COMPLETED":
            media = (status.get("output") or {}).get("media_url") or []
            if not media:
                raise RuntimeError(f"Pixazo completed without media_url: {status}")
            return request_id, media[0]

        if state in {"FAILED", "ERROR"}:
            raise RuntimeError(f"Pixazo generation failed: {status}")

        time.sleep(5)

    raise TimeoutError(f"Pixazo request timed out after 12 minutes: {request_id}")


def download(url: str, path: Path):
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)


def main():
    if not API_KEY:
        raise SystemExit("PIXAZO_API_KEY is required")
    if not PLAN_FILE.exists():
        raise SystemExit(f"Missing fixed prompt plan: {PLAN_FILE}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    CLIPS.mkdir(parents=True, exist_ok=True)

    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    shots = plan.get("shots", [])
    if not shots:
        raise SystemExit("documentary_plan.json contains no shots")

    records = []
    processed = []

    for index, shot in enumerate(shots, start=1):
        start = float(shot["start"])
        end = float(shot["end"])
        duration = end - start
        # Free LTX uses frames rather than a duration parameter.
        frames = max(25, round(duration * 24) + 1)
        prompt = str(shot["visual_query"]).strip()
        if not prompt:
            raise SystemExit(f"Shot {index} has an empty visual prompt")

        print(f"\n=== Shot {index}: {start:.1f}s-{end:.1f}s ===")
        print(f"EXACT PROMPT: {prompt}")

        request_id, media_url = request_clip(prompt, frames, 4200 + index)
        raw_clip = CLIPS / f"shot_{index:02d}_raw.mp4"
        download(media_url, raw_clip)

        duration_path = CLIPS / f"shot_{index:02d}.mp4"
        caption = esc_drawtext(str(shot.get("caption", "")).strip())
        vf = (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            "setsar=1,"
            "drawbox=x=0:y=0:w=iw:h=140:color=black@0.22:t=fill,"
            "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            "text='FACTVERSE  •  DOCUMENTARY TEST':fontcolor=white:fontsize=42:"
            "x=54:y=48:shadowcolor=black@0.7:shadowx=2:shadowy=2,"
            f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"text='{caption}':fontcolor=white:fontsize=54:line_spacing=8:"
            "x=(w-text_w)/2:y=h-250:box=1:boxcolor=black@0.45:boxborderw=24:"
            "shadowcolor=black@0.8:shadowx=2:shadowy=2"
        )

        run([
            "ffmpeg", "-y", "-i", str(raw_clip),
            "-vf", vf,
            "-t", f"{duration:.3f}",
            "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-r", "30",
            str(duration_path),
        ])

        processed.append(duration_path)
        records.append({
            "shot": index,
            "start": start,
            "end": end,
            "duration": duration,
            "prompt": prompt,
            "request_id": request_id,
            "media_url": media_url,
            "frames_requested": frames,
            "model": "ltx-video (Pixazo LTX 2.5 Free)",
        })

    REQUESTS_FILE.write_text(json.dumps(records, indent=2), encoding="utf-8")

    concat_file = CLIPS / "concat.txt"
    concat_file.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in processed) + "\n",
        encoding="utf-8",
    )

    run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-an", "-t", "15",
        "-movflags", "+faststart",
        str(FINAL),
    ])

    if not FINAL.exists() or FINAL.stat().st_size == 0:
        raise SystemExit("Pixazo documentary video was not created")

    print(f"Created: {FINAL}")


if __name__ == "__main__":
    main()
