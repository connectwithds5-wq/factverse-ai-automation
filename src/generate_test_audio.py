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
VOICE_NAME = "en_US-lessac-medium"
VOICE_MODEL = os.path.join(VOICE_DIR, VOICE_NAME + ".onnx")


def run(command):
    print("RUNNING:", " ".join(command))
    subprocess.run(command, check=True)

os.makedirs(OUTPUT, exist_ok=True)
os.makedirs(VOICE_DIR, exist_ok=True)

with open(METADATA, "r", encoding="utf-8") as f:
    data = json.load(f)

script = f"{data['hook']}... {data['fact']}. Here's the surprising part... {data['twist']}"
print("DOCUMENTARY TEST VOICE:", script)

if not os.path.exists(VOICE_MODEL):
    run([sys.executable, "-m", "piper.download_voices", "--data-dir", VOICE_DIR, VOICE_NAME])

run([
    sys.executable, "-m", "piper", "--model", VOICE_MODEL,
    "--output_file", VOICE, "--length_scale", "0.95",
    "--noise_scale", "0.55", "--noise_w_scale", "0.65", "--", script
])

clean = os.path.join(OUTPUT, "voice_clean.wav")
run([
    "ffmpeg", "-y", "-i", VOICE,
    "-af", "highpass=f=70,lowpass=f=12000,acompressor=threshold=-18dB:ratio=2.5:attack=5:release=80,loudnorm=I=-16:TP=-1.5:LRA=11",
    "-ar", "44100", "-ac", "2", clean
])
os.replace(clean, VOICE)

run([
    "ffmpeg", "-y", "-f", "lavfi",
    "-i", "sine=frequency=196:duration=15:sample_rate=44100",
    "-af", "volume=0.025,afade=t=in:st=0:d=2,afade=t=out:st=12:d=3",
    "-ar", "44100", "-ac", "2", MUSIC
])

print("ISOLATED DOCUMENTARY AUDIO READY")
