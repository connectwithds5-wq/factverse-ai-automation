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
STORYBOARD = OUTPUT / "storyboard.json"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
NEGATIVE = (
    "blurry, low quality, distorted, worst quality, jpeg artifacts, text, subtitles, "
    "watermark, logo, UI, split screen, duplicate person, deformed hands, distorted face, "
    "unreadable symbols, floating objects, unrealistic anatomy"
)


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


def request_clip(prompt, num_frames, seed):
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
        raise RuntimeError(
            f"Pixazo submit failed ({response.status_code}): {response.text[:1000]}"
        )
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
                f"Pixazo status failed ({status_response.status_code}): "
                f"{status_response.text[:1000]}"
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


def main():
    if not API_KEY:
        raise SystemExit("PIXAZO_API_KEY is required")

    metadata_path = OUTPUT / "metadata.json"
    if not metadata_path.exists():
        raise SystemExit("output/metadata.json is required before Pixazo rendering")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    CLIPS.mkdir(parents=True, exist_ok=True)
    shots, total_duration = load_storyboard()

    records = []
    processed = []

    for index, shot in enumerate(shots, start=1):
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

        print(f"\n=== Pixazo documentary shot {index} ({duration:.1f}s) ===")
        print("NARRATION:", narration)
        print("CAPTION:", caption)
        print("PROMPT:", prompt)

        frames = max(25, round(duration * 24) + 1)
        request_id, media_url = request_clip(prompt, frames, 9100 + index)

        raw = CLIPS / f"shot_{index:02d}_raw.mp4"
        download(media_url, raw)

        processed_clip = CLIPS / f"shot_{index:02d}.mp4"
        caption_file = CLIPS / f"caption_{index:02d}.txt"
        caption_file.write_text(wrap_caption(caption), encoding="utf-8")

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

        processed.append(processed_clip)
        records.append({
            "shot": index,
            "start": start,
            "end": end,
            "duration": duration,
            "narration": narration,
            "caption": caption,
            "prompt": prompt,
            "request_id": request_id,
            "media_url": media_url,
            "frames_requested": frames,
            "model": "ltx-video (Pixazo LTX Free)",
        })

    REQUESTS_FILE.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    concat_file = CLIPS / "concat.txt"
    concat_file.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in processed) + "\n",
        encoding="utf-8",
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
