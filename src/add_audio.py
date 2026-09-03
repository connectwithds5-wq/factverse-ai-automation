import os
import json
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OUTPUT = os.path.join(ROOT, "output")
VOICE_DIR = os.path.join(ROOT, "voices")

VIDEO = os.path.join(OUTPUT, "factverse.mp4")
METADATA = os.path.join(OUTPUT, "metadata.json")

VOICE = os.path.join(OUTPUT, "voice.wav")
MUSIC = os.path.join(OUTPUT, "music.wav")
FINAL = os.path.join(OUTPUT, "factverse_final.mp4")

VOICE_NAME = "en_US-lessac-medium"
VOICE_MODEL = os.path.join(
    VOICE_DIR,
    VOICE_NAME + ".onnx"
)


def run(command):
    print("RUNNING:")
    print(" ".join(command))
    subprocess.run(command, check=True)


os.makedirs(OUTPUT, exist_ok=True)
os.makedirs(VOICE_DIR, exist_ok=True)

print("======================================")
print("FACTVERSE AUDIO ENGINE")
print("======================================")


# ==========================================================
# LOAD METADATA
# ==========================================================

with open(
    METADATA,
    "r",
    encoding="utf-8"
) as f:
    data = json.load(f)


hook = data["hook"]
fact = data["fact"]
twist = data["twist"]

script = (
    f"{hook}... "
    f"{fact}. "
    f"Here's the surprising part... "
    f"{twist}"
)

print("")
print("VOICE SCRIPT:")
print(script)
print("")


# ==========================================================
# DOWNLOAD PIPER VOICE MODEL
# ==========================================================

print("Downloading Piper voice model...")
print(VOICE_NAME)

run([
    sys.executable,
    "-m",
    "piper.download_voices",
    "--data-dir",
    VOICE_DIR,
    VOICE_NAME
])


if not os.path.exists(VOICE_MODEL):
    raise RuntimeError(
        f"Piper voice model was not downloaded: {VOICE_MODEL}"
    )


print("Piper voice model ready.")


# ==========================================================
# GENERATE NATURAL VOICE
# ==========================================================

print("Generating neural voice...")


run([
    sys.executable,
    "-m",
    "piper",

    "--model",
    VOICE_MODEL,

    "--output_file",
    VOICE,

    "--length_scale",
    "0.95",

    "--noise_scale",
    "0.55",

    "--noise_w_scale",
    "0.65",

    "--",
    script
])


# ==========================================================
# CLEAN / NORMALIZE VOICE
# ==========================================================

VOICE_CLEAN = os.path.join(
    OUTPUT,
    "voice_clean.wav"
)

print("Cleaning voice...")


run([
    "ffmpeg",
    "-y",

    "-i",
    VOICE,

    "-af",
    (
        "highpass=f=70,"
        "lowpass=f=12000,"
        "acompressor="
        "threshold=-18dB:"
        "ratio=2.5:"
        "attack=5:"
        "release=80,"
        "loudnorm=I=-16:TP=-1.5:LRA=11"
    ),

    "-ar",
    "44100",
    "-ac",
    "2",

    VOICE_CLEAN
])


os.replace(
    VOICE_CLEAN,
    VOICE
)


# ==========================================================
# CREATE SOFT BACKGROUND MUSIC
# ==========================================================

print("Creating background instrumental...")


run([
    "ffmpeg",
    "-y",

    "-f",
    "lavfi",

    "-i",
    "sine=frequency=196:duration=15:sample_rate=44100",

    "-af",
    (
        "volume=0.025,"
        "afade=t=in:st=0:d=2,"
        "afade=t=out:st=12:d=3"
    ),

    "-ar",
    "44100",
    "-ac",
    "2",

    MUSIC
])


# ==========================================================
# MIX VOICE + MUSIC
# ==========================================================

print("Mixing voice + instrumental...")


run([
    "ffmpeg",
    "-y",

    "-i",
    VIDEO,
    "-i",
    VOICE,
    "-i",
    MUSIC,

    "-filter_complex",

    (
        "[1:a]"
        "volume=1.0,"
        "aresample=44100"
        "[voice];"

        "[2:a]"
        "volume=0.18,"
        "aresample=44100"
        "[music];"

        "[voice][music]"
        "amix=inputs=2:"
        "duration=first:"
        "dropout_transition=2"
        "[audio]"
    ),

    "-map",
    "0:v:0",
    "-map",
    "[audio]",

    "-c:v",
    "copy",

    "-c:a",
    "aac",
    "-b:a",
    "160k",
    "-ar",
    "44100",

    "-shortest",

    "-movflags",
    "+faststart",

    FINAL
])


# ==========================================================
# REPLACE VIDEO
# ==========================================================

os.replace(
    FINAL,
    VIDEO
)


print("")
print("======================================")
print("FACTVERSE AUDIO COMPLETE")
print("======================================")
print("Natural neural voice: READY")
print("Instrumental music: READY")
print("Final video:", VIDEO)
print("======================================")
