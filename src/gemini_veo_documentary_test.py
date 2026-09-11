import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
CLIPS = OUT / "gemini_veo_clips"
FINAL = OUT / "factverse_gemini_veo.mp4"
VOICE = OUT / "gemini_veo_voice.wav"
MUSIC = OUT / "gemini_veo_music.wav"
MODEL = os.getenv("VEO_MODEL", "veo-3.1-generate-preview")
TEXT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
TARGET = 15.0
SPEECH_TARGET = 14.7
OUT.mkdir(parents=True, exist_ok=True)
CLIPS.mkdir(parents=True, exist_ok=True)

key = os.getenv("GEMINI_API_KEY")
if not key:
    raise RuntimeError("GEMINI_API_KEY GitHub Secret is missing.")
client = genai.Client(api_key=key)


def run(command):
    print("RUNNING:", " ".join(map(str, command)))
    subprocess.run(command, check=True)


def duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def parse_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < 0:
        return None
    try:
        return json.loads(text[a:b + 1])
    except Exception:
        return None


def make_plan():
    prompt = """
Create ONE factual, highly engaging 15-second FACTVERSE YouTube Short in English.
Use a surprising but well-established science, history, space, animal, psychology,
or technology fact. Never invent facts or statistics.
Return ONLY JSON in this exact shape:
{
  "hook": "max 10 words",
  "fact": "max 42 spoken words",
  "twist": "max 12 words",
  "title": "clickable Shorts title",
  "description": "natural SEO description",
  "keywords": ["facts", "did you know", "shorts"],
  "hashtags": ["#facts", "#shorts", "#factverse"],
  "shots": [
    {"duration": 4, "narration": "exact spoken words for this beat", "visual_prompt": "specific cinematic visual matching those words"},
    {"duration": 4, "narration": "exact spoken words for this beat", "visual_prompt": "specific cinematic visual matching those words"},
    {"duration": 4, "narration": "exact spoken words for this beat", "visual_prompt": "specific cinematic visual matching those words"},
    {"duration": 3, "narration": "exact spoken words for this beat", "visual_prompt": "specific cinematic visual matching those words"}
  ]
}
Shot durations must total exactly 15 seconds. Every visual prompt must be premium
photorealistic documentary footage, vertical 9:16, deliberate camera movement,
realistic lighting, and semantically match the narration. Prefer objects,
environments, scientific visualizations, macro, aerial or natural phenomena over
generic talking heads. No text, captions, logos, watermarks, UI or split screens.
"""
    r = client.models.generate_content(
        model=TEXT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json", temperature=0.7
        ),
    )
    d = parse_json(r.text)
    shots = d.get("shots", []) if d else []
    if not d or len(shots) != 4 or sum(int(x.get("duration", 0)) for x in shots) != 15:
        raise RuntimeError("Invalid Gemini documentary plan.")
    return d


def generate_voice(data):
    voice_dir = ROOT / "voices"
    voice_dir.mkdir(parents=True, exist_ok=True)
    model_name = "en_US-lessac-medium"
    model_path = voice_dir / f"{model_name}.onnx"
    if not model_path.exists():
        run([sys.executable, "-m", "piper.download_voices", "--data-dir", str(voice_dir), model_name])

    segments = []
    raw_durations = []
    for i, shot in enumerate(data["shots"], 1):
        text = str(shot["narration"]).strip()
        raw = OUT / f"gemini_voice_{i:02d}_raw.wav"
        clean = OUT / f"gemini_voice_{i:02d}.wav"
        run([
            sys.executable, "-m", "piper", "--model", str(model_path),
            "--output_file", str(raw), "--length_scale", "0.95",
            "--noise_scale", "0.55", "--noise_w_scale", "0.65", "--", text
        ])
        run([
            "ffmpeg", "-y", "-i", str(raw),
            "-af", "highpass=f=70,lowpass=f=10000,acompressor=threshold=-18dB:ratio=2.5:attack=5:release=80,loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar", "44100", "-ac", "2", str(clean)
        ])
        segments.append(clean)
        raw_durations.append(duration(clean))

    concat = OUT / "gemini_voice_segments.txt"
    concat.write_text("\n".join(f"file '{p.resolve()}'" for p in segments) + "\n", encoding="utf-8")
    raw_total = sum(raw_durations)
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
        "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2", str(VOICE)
    ])
    raw_total = duration(VOICE)
    atempo = raw_total / SPEECH_TARGET
    stretched = OUT / "gemini_veo_voice_stretched.wav"
    run(["ffmpeg", "-y", "-i", str(VOICE), "-af", f"atempo={atempo:.8f}",
         "-ar", "44100", "-ac", "2", str(stretched)])
    stretched.replace(VOICE)

    scale = SPEECH_TARGET / raw_total
    timing = []
    current = 0.0
    for i, (shot, raw_dur) in enumerate(zip(data["shots"], raw_durations), 1):
        seg = raw_dur * scale
        timing.append({
            "shot": i,
            "start": round(current, 3),
            "end": round(current + seg, 3),
            "narration": shot["narration"],
        })
        current += seg
    return timing


def make_music():
    # Very low-volume cinematic pulse; narration remains dominant.
    run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "sine=frequency=110:duration=15:sample_rate=44100",
        "-af", "volume=0.018,afade=t=in:st=0:d=1.5,afade=t=out:st=12:d=3",
        "-ar", "44100", "-ac", "2", str(MUSIC)
    ])


def veo(index, shot):
    prompt = f"""
Premium factual documentary footage for a YouTube Short.
Vertical 9:16, photorealistic, cinematic, physically plausible motion, realistic
lighting, high detail, intentional slow camera movement.
SUBJECT: {shot['visual_prompt']}
This is shot {index + 1} of 4. Keep the main subject clearly visible throughout.
Use one continuous visual idea; no abrupt internal cuts.
STRICTLY NO text, subtitles, captions, logos, watermarks, UI, fake labels,
readable signs, split screens, duplicated subjects, distorted anatomy, faces,
hands or AI artifacts. Generate visuals only; no spoken narration.
"""
    # Veo supports 4-second minimum in this workflow. The final 4-second clip is
    # trimmed to 3 seconds, preserving the requested 4+4+4+3 timeline.
    requested = int(shot["duration"])
    generation_duration = 4 if requested == 3 else requested
    op = client.models.generate_videos(
        model=MODEL,
        prompt=prompt,
        config=types.GenerateVideosConfig(
            aspect_ratio="9:16",
            resolution="720p",
            duration_seconds=generation_duration,
            number_of_videos=1,
        ),
    )
    started = time.time()
    while not op.done:
        if time.time() - started > 900:
            raise TimeoutError(f"Veo shot {index + 1} timed out")
        time.sleep(10)
        op = client.operations.get(op)
    if not op.response or not op.response.generated_videos:
        raise RuntimeError(f"No video returned for shot {index + 1}")
    path = CLIPS / f"shot_{index + 1:02d}.mp4"
    client.files.download(file=op.response.generated_videos[0].video, destination=str(path))
    return path, prompt


def caption(src, text, index, duration_seconds):
    dst = OUT / f"gemini_caption_{index:02d}.mp4"
    words, lines, cur = text.split(), [], ""
    for word in words:
        test = (cur + " " + word).strip()
        if len(test) <= 25:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    # Use an actual newline for drawtext line breaks.
    cap = "\\n".join(lines[:3]).replace(":", "\\:").replace("'", "\\\\'")
    vf = (
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        f"text='{cap}':fontcolor=white:fontsize=58:line_spacing=10:"
        "borderw=4:bordercolor=black:box=1:boxcolor=black@0.58:boxborderw=22:"
        "x=(w-text_w)/2:y=1160"
    )
    run([
        "ffmpeg", "-y", "-i", str(src), "-t", str(duration_seconds),
        "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "19", "-pix_fmt", "yuv420p", str(dst)
    ])
    return dst


def main():
    data = make_plan()
    (OUT / "metadata.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "gemini_veo_plan.json").write_text(
        json.dumps({"model": MODEL, "text_model": TEXT_MODEL, "shots": data["shots"]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    timing = generate_voice(data)
    make_music()
    (OUT / "gemini_veo_timing.json").write_text(
        json.dumps({"duration": TARGET, "speech_end": SPEECH_TARGET, "shots": timing}, indent=2),
        encoding="utf-8",
    )

    processed = []
    requests = []
    for i, shot in enumerate(data["shots"]):
        src, prompt = veo(i, shot)
        processed.append(caption(src, shot["narration"], i + 1, int(shot["duration"])))
        requests.append({
            "shot": i + 1,
            "duration": shot["duration"],
            "narration": shot["narration"],
            "visual_prompt": shot["visual_prompt"],
            "veo_prompt": prompt,
        })

    (OUT / "gemini_veo_requests.json").write_text(json.dumps(requests, ensure_ascii=False, indent=2), encoding="utf-8")
    concat = OUT / "gemini_veo_concat.txt"
    concat.write_text("\n".join(f"file '{p.resolve()}'" for p in processed) + "\n", encoding="utf-8")
    visuals = OUT / "gemini_veo_visuals.mp4"
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
        "-t", str(TARGET), "-an", "-r", "30", "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", str(visuals)
    ])

    run([
        "ffmpeg", "-y", "-i", str(visuals), "-i", str(VOICE), "-i", str(MUSIC),
        "-filter_complex", "[1:a]apad,atrim=0:15,volume=1.0[voice];[2:a]volume=0.65[music];[voice][music]amix=inputs=2:duration=longest:dropout_transition=0[a]",
        "-map", "0:v:0", "-map", "[a]", "-t", "15", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(FINAL)
    ])

    final_duration = duration(FINAL)
    if abs(final_duration - TARGET) > 0.15:
        raise RuntimeError(f"Final duration is {final_duration:.3f}s, expected 15s")
    print("FINAL:", FINAL)
    print("TITLE:", data["title"])
    print("DURATION:", final_duration)


if __name__ == "__main__":
    main()
