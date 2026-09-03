import os
import json
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OUTPUT = os.path.join(ROOT, "output")
VIDEO = os.path.join(OUTPUT, "factverse.mp4")
METADATA = os.path.join(OUTPUT, "metadata.json")

VOICE = os.path.join(OUTPUT, "voice.wav")
MUSIC = os.path.join(OUTPUT, "music.wav")
FINAL = os.path.join(OUTPUT, "factverse_final.mp4")


def run(cmd):
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


print("====================================")
print("FACTVERSE AUDIO ENGINE")
print("====================================")


# ------------------------------------
# Load metadata
# ------------------------------------

with open(METADATA, "r", encoding="utf-8") as f:
    data = json.load(f)


hook = data["hook"]
fact = data["fact"]
twist = data["twist"]

script = f"{hook}. {fact}. {twist}."


print("Voice script:")
print(script)


# ------------------------------------
# Generate voice
# ------------------------------------

print("Generating voice...")


run([
    "espeak-ng",
    "-v", "en-us",
    "-s", "155",
    "-p", "45",
    "-a", "145",
    "-w", VOICE,
    script
])


# ------------------------------------
# Generate cinematic instrumental
# ------------------------------------

print("Generating instrumental music...")


music_filter = (
    "sine=frequency=196:duration=15,"
    "volume=0.06"
)

run([
    "ffmpeg",
    "-y",
    "-f", "lavfi",
    "-i", music_filter,
    "-ar", "44100",
    "-ac", "2",
    MUSIC
])


# ------------------------------------
# Mix voice + music with video
# ------------------------------------

print("Mixing voice + instrumental...")


run([
    "ffmpeg",
    "-y",

    "-i", VIDEO,
    "-i", VOICE,
    "-i", MUSIC,

    "-filter_complex",
    "[1:a]volume=1.0[voice];"
    "[2:a]volume=0.35[music];"
    "[voice][music]amix=inputs=2:"
    "duration=first:"
    "dropout_transition=2[audio]",

    "-map", "0:v:0",
    "-map", "[audio]",

    "-c:v", "copy",
    "-c:a", "aac",
    "-b:a", "128k",

    "-shortest",
    "-movflags", "+faststart",

    FINAL
])


# ------------------------------------
# Replace original video
# ------------------------------------

os.replace(FINAL, VIDEO)


print("====================================")
print("FACTVERSE AUDIO COMPLETE")
print("====================================")
print("Voice:", VOICE)
print("Music:", MUSIC)
print("Final video:", VIDEO)
print("====================================")
