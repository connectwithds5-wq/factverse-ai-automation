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
TIMING_FILE = OUTPUT / "documentary_timing.json"
FINAL = OUTPUT / "factverse_pixazo_documentary.mp4"
REQUESTS_FILE = OUTPUT / "pixazo_requests.json"

NEGATIVE = "blurry, low quality, distorted, worst quality, jpeg artifacts, text, subtitles, watermark, logo, UI, split screen, duplicate person, deformed hands, distorted face"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def run(cmd):
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def wrap_caption(text: str, width: int = 24) -> str:
    words = str(text).replace("\\n", " ").split()
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
    return "\\n".join(lines[:3])


def request_clip(prompt: str, num_frames: int, seed: int):
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
    headers = {"Content-Type": "application/json", "Ocp-Apim-Subscription-Key": API_KEY}
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
            raise RuntimeError(f"Pixazo status failed ({status_response.status_code}): {status_response.text[:1000]}")
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
    if not PLAN_FILE.exists() or not TIMING_FILE.exists():
        raise SystemExit("Missing documentary plan or narration timing map")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    CLIPS.mkdir(parents=True, exist_ok=True)
    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    timing = json.loads(TIMING_FILE.read_text(encoding="utf-8"))
    shots = plan.get("shots", [])
    segments = timing.get("segments", [])
    if not shots or len(shots) != len(segments):
        raise SystemExit("Plan/timing segment count mismatch")

    records, processed = [], []
    for index, (shot, seg) in enumerate(zip(shots, segments), start=1):
        start = float(seg["start"])
        end = float(seg["end"])
        shot_duration = end - start
        prompt = str(shot.get("visual_prompt") or shot.get("visual_query") or "").strip()
        caption_text = str(shot.get("caption") or "").strip()
        if not prompt:
            raise SystemExit(f"Shot {index} has no visual prompt")

        print(f"\\n=== Shot {index}: {start:.2f}s-{end:.2f}s ({shot_duration:.2f}s) ===")
        print(f"VISUAL PROMPT: {prompt}")
        print(f"CAPTION: {caption_text}")

        frames = max(25, round(shot_duration * 24) + 1)
        request_id, media_url = request_clip(prompt, frames, 4200 + index)
        raw_clip = CLIPS / f"shot_{index:02d}_raw.mp4"
        download(media_url, raw_clip)

        processed_clip = CLIPS / f"shot_{index:02d}.mp4"
        caption_file = CLIPS / f"caption_{index:02d}.txt"
        caption_file.write_text(wrap_caption(caption_text), encoding="utf-8")

        # Important text sits in the middle/lower safe area, well above Shorts/Reels UI.
        vf = (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,setsar=1,"
            "drawbox=x=0:y=0:w=iw:h=130:color=black@0.18:t=fill,"
            f"drawtext=fontfile={FONT}:text='FACTVERSE':fontcolor=white:fontsize=38:"
            "x=54:y=42:shadowcolor=black@0.75:shadowx=2:shadowy=2,"
            f"drawtext=fontfile={FONT}:textfile='{caption_file.resolve()}':"
            "fontcolor=white:fontsize=58:line_spacing=10:"
            "x=(w-text_w)/2:y=1180:box=1:boxcolor=black@0.46:boxborderw=22:"
            "shadowcolor=black@0.85:shadowx=2:shadowy=2"
        )
        run([
            "ffmpeg", "-y", "-i", str(raw_clip), "-vf", vf,
            "-t", f"{shot_duration:.3f}", "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-r", "30", str(processed_clip),
        ])
        processed.append(processed_clip)
        records.append({
            "shot": index,
            "start": start,
            "end": end,
            "duration": shot_duration,
            "prompt": prompt,
            "source_visual_query": shot.get("visual_query", ""),
            "caption": caption_text,
            "request_id": request_id,
            "media_url": media_url,
            "frames_requested": frames,
            "model": "ltx-video (Pixazo LTX Free)",
        })

    REQUESTS_FILE.write_text(json.dumps(records, indent=2), encoding="utf-8")
    concat_file = CLIPS / "concat.txt"
    concat_file.write_text("\\n".join(f"file '{p.resolve()}'" for p in processed) + "\\n", encoding="utf-8")

    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-pix_fmt", "yuv420p", "-r", "30", "-an", "-t", "14.7",
        "-movflags", "+faststart", str(FINAL),
    ])
    held = OUTPUT / "factverse_pixazo_documentary_15s.mp4"
    run([
        "ffmpeg", "-y", "-i", str(FINAL),
        "-vf", "tpad=stop_mode=clone:stop_duration=0.3",
        "-t", "15", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart", str(held),
    ])
    os.replace(held, FINAL)

    if not FINAL.exists() or FINAL.stat().st_size == 0:
        raise SystemExit("Pixazo documentary video was not created")
    print(f"Created: {FINAL}")


if __name__ == "__main__":
    main()
