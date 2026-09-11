import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT = os.path.join(ROOT, "output")
VOICE_DIR = os.path.join(ROOT, "voices")
METADATA = os.path.join(OUTPUT, "metadata.json")
VOICE = os.path.join(OUTPUT, "voice.wav")
MUSIC = os.path.join(OUTPUT, "music.wav")
TIMING = os.path.join(OUTPUT, "documentary_timing.json")
VOICE_NAME = "en_US-lessac-medium"
VOICE_MODEL = os.path.join(VOICE_DIR, VOICE_NAME + ".onnx")


def run(command):
    print("RUNNING:", " ".join(command))
    subprocess.run(command, check=True)


def duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


os.makedirs(OUTPUT, exist_ok=True)
os.makedirs(VOICE_DIR, exist_ok=True)

with open(METADATA, "r", encoding="utf-8") as f:
    data = json.load(f)

segments = [
    ("hook", data["hook"] + "..."),
    ("fact", data["fact"] + "."),
    ("surprise", "Here's the surprising part..."),
    ("twist", data["twist"]),
]

if not os.path.exists(VOICE_MODEL):
    run([sys.executable, "-m", "piper.download_voices", "--data-dir", VOICE_DIR, VOICE_NAME])

segment_files = []
for index, (name, text) in enumerate(segments, start=1):
    raw = os.path.join(OUTPUT, f"voice_segment_{index:02d}.wav")
    clean = os.path.join(OUTPUT, f"voice_segment_{index:02d}_clean.wav")
    print(f"VOICE SEGMENT {index}: {name}: {text}")
    run([
        sys.executable, "-m", "piper", "--model", VOICE_MODEL,
        "--output_file", raw, "--length_scale", "0.95",
        "--noise_scale", "0.55", "--noise_w_scale", "0.65", "--", text
    ])
    run([
        "ffmpeg", "-y", "-i", raw,
        "-af", "highpass=f=70,lowpass=f=12000,acompressor=threshold=-18dB:ratio=2.5:attack=5:release=80,loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ar", "44100", "-ac", "2", clean
    ])
    segment_files.append(clean)

# Build one continuous narration while retaining exact segment boundaries.
concat_file = os.path.join(OUTPUT, "voice_segments.txt")
with open(concat_file, "w", encoding="utf-8") as f:
    for path in segment_files:
        f.write(f"file '{os.path.abspath(path)}'\n")

run([
    "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
    "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2", VOICE
])

# Calculate exact boundaries from the generated speech, then scale the whole narration
# to fit the 15-second visual timeline without changing pitch.
raw_total = duration(VOICE)
target_speech = 14.7
atempo = raw_total / target_speech

stretched = os.path.join(OUTPUT, "voice_stretched.wav")
run([
    "ffmpeg", "-y", "-i", VOICE,
    "-af", f"atempo={atempo:.8f}",
    "-ar", "44100", "-ac", "2", stretched
])
os.replace(stretched, VOICE)

raw_durations = [duration(p) for p in segment_files]
scale = target_speech / sum(raw_durations)
timing = []
current = 0.0
for (name, _), seg_dur in zip(segments, raw_durations):
    seg = seg_dur * scale
    timing.append({"name": name, "start": round(current, 3), "end": round(current + seg, 3)})
    current += seg

# Keep a tiny breathing room at the end; the video remains exactly 15 seconds.
TIMING_DATA = {"duration": 15.0, "speech_end": round(target_speech, 3), "segments": timing}
with open(TIMING, "w", encoding="utf-8") as f:
    json.dump(TIMING_DATA, f, indent=2)

# Background bed is exactly 15 seconds.
run([
    "ffmpeg", "-y", "-f", "lavfi",
    "-i", "sine=frequency=196:duration=15:sample_rate=44100",
    "-af", "volume=0.025,afade=t=in:st=0:d=2,afade=t=out:st=12:d=3",
    "-ar", "44100", "-ac", "2", MUSIC
])

print("ISOLATED DOCUMENTARY AUDIO READY")
print(f"Narration: {duration(VOICE):.3f}s / target 14.7s")
print(f"Timing map: {TIMING}")
