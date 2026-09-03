import os
import json
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OUTPUT = os.path.join(ROOT, "output")

VIDEO = os.path.join(
    OUTPUT,
    "factverse.mp4"
)

METADATA = os.path.join(
    OUTPUT,
    "metadata.json"
)

VOICE = os.path.join(
    OUTPUT,
    "voice.wav"
)

MUSIC = os.path.join(
    OUTPUT,
    "music.wav"
)

FINAL = os.path.join(
    OUTPUT,
    "factverse_final.mp4"
)


def run(command):
    print("RUNNING:")
    print(" ".join(command))
    subprocess.run(command, check=True)


print("======================================")
print("     FACTVERSE AUDIO ENGINE V2")
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


# Natural pauses for better narration
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
# PIPER VOICE
# ==========================================================

VOICE_NAME = "en_US-lessac-medium"


print("Installing/downloading Piper voice:")
print(VOICE_NAME)


# Piper automatically downloads the voice model
# when the model name is supplied.

run([
    sys.executable,
    "-m",
    "piper",
    "--model",
    VOICE_NAME,
    "--output_file",
    VOICE
])


# ==========================================================
# NORMALIZE VOICE
# ==========================================================

VOICE_CLEAN = os.path.join(
    OUTPUT,
    "voice_clean.wav"
)


print("Cleaning voice audio...")


run([
    "ffmpeg",
    "-y",

    "-i",
    VOICE,

    "-af",
    (
        "highpass=f=80,"
        "lowpass=f=12000,"
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
# INSTRUMENTAL MUSIC
# ==========================================================

print("Creating background instrumental...")


run([
    "ffmpeg",
    "-y",

    "-f",
    "lavfi",

    "-i",
    (
        "sine=frequency=196:"
        "duration=15:"
        "sample_rate=44100"
    ),

    "-af",
    (
        "volume=0.035,"
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

print("Mixing voice and music...")


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
        "volume=0.22,"
        "aresample=44100"
        "[music];"

        "[voice][music]"
        "amix=inputs=2:"
        "duration=first:"
        "dropout_transition=2,"
        "loudnorm=I=-16:TP=-1.5:LRA=11"
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
# REPLACE ORIGINAL VIDEO
# ==========================================================

os.replace(
    FINAL,
    VIDEO
)


print("")
print("======================================")
print("     FACTVERSE AUDIO COMPLETE")
print("======================================")

print("Voice:")
print(VOICE)

print("Music:")
print(MUSIC)

print("Final:")
print(VIDEO)

print("======================================")
