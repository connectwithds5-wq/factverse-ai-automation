import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT = os.path.join(ROOT, "output")
VOICE_DIR = os.path.join(ROOT, "voices")

VIDEO = os.path.join(OUTPUT, "factverse.mp4")
METADATA = os.path.join(OUTPUT, "metadata.json")
STORYBOARD = os.path.join(OUTPUT, "storyboard.json")
VOICE = os.path.join(OUTPUT, "voice.wav")
MUSIC = os.path.join(OUTPUT, "music.wav")
FINAL = os.path.join(OUTPUT, "factverse_final.mp4")

VOICE_NAME = "en_US-lessac-medium"
VOICE_MODEL = os.path.join(VOICE_DIR, VOICE_NAME + ".onnx")


def run(command):
    print("RUNNING:")
    print(" ".join(command))
    subprocess.run(command, check=True)


def probe_duration(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def atempo_filter(speed):
    speed = max(0.5, min(1.15, speed))
    return f"atempo={speed:.6f}"


os.makedirs(OUTPUT, exist_ok=True)
os.makedirs(VOICE_DIR, exist_ok=True)

print("======================================")
print("FACTVERSE AUDIO ENGINE")
print("======================================")

with open(METADATA, "r", encoding="utf-8") as f:
    metadata = json.load(f)

if os.path.exists(STORYBOARD):
    with open(STORYBOARD, "r", encoding="utf-8") as f:
        board = json.load(f)
    shots = board.get("shots", [])
    if not 4 <= len(shots) <= 5:
        raise RuntimeError("Storyboard must contain 4 or 5 shots")
else:
    shots = []

if os.path.exists(VOICE_MODEL):
    print("Piper voice model already exists. Skipping download.")
else:
    print("Downloading Piper voice model...")
    run([
        sys.executable,
        "-m",
        "piper.download_voices",
        "--data-dir",
        VOICE_DIR,
        VOICE_NAME,
    ])

if not os.path.exists(VOICE_MODEL):
    raise RuntimeError(f"Piper voice model was not downloaded: {VOICE_MODEL}")

print("Piper voice model ready.")

if shots:
    print("Using storyboard-aligned narration.")
    shot_audio_dir = os.path.join(OUTPUT, "storyboard_audio")
    os.makedirs(shot_audio_dir, exist_ok=True)
    normalized_parts = []
    previous_end = 0.0

    for index, shot in enumerate(shots, start=1):
        start = float(shot["start"])
        end = float(shot["end"])
        duration = end - start
        narration = str(shot.get("narration", "")).strip()
        if not narration:
            raise RuntimeError(f"Storyboard shot {index} has no narration")
        if index == 1 and abs(start) > 0.01:
            raise RuntimeError("Storyboard must start at 0 seconds")
        if abs(start - previous_end) > 0.01:
            raise RuntimeError(f"Storyboard shot {index} is not contiguous")
        if duration < 3.0 or duration > 5.0:
            raise RuntimeError(f"Storyboard shot {index} duration must be 3-5 seconds")

        raw = os.path.join(shot_audio_dir, f"shot_{index:02d}_voice_raw.wav")
        fitted = os.path.join(shot_audio_dir, f"shot_{index:02d}_voice_fitted.wav")
        padded = os.path.join(shot_audio_dir, f"shot_{index:02d}_voice.wav")

        print(f"\nGenerating voice for shot {index} ({duration:.2f}s)")
        print("NARRATION:", narration)
        run([
            sys.executable,
            "-m",
            "piper",
            "--model", VOICE_MODEL,
            "--output_file", raw,
            # Slightly slower than Piper's default so words remain clear.
            "--length_scale", "1.08",
            "--noise_scale", "0.55",
            "--noise_w_scale", "0.65",
            "--",
            narration,
        ])

        raw_duration = probe_duration(raw)
        print(f"Shot {index}: raw narration {raw_duration:.3f}s; target {duration:.3f}s")

        # Never aggressively speed up speech. A small fit (up to 1.15x) is
        # acceptable; anything beyond that means the storyboard narration is
        # too verbose and should be regenerated shorter instead.
        if raw_duration > duration + 0.08:
            speed = raw_duration / duration
            if speed > 1.15:
                raise RuntimeError(
                    f"Storyboard shot {index} narration is too verbose for natural speech: "
                    f"{raw_duration:.2f}s audio for {duration:.2f}s shot. "
                    "Regenerate the storyboard with shorter narration."
                )
            print(f"Shot {index}: small timing fit with atempo={speed:.3f}x")
            run([
                "ffmpeg", "-y", "-i", raw,
                "-af", atempo_filter(speed),
                "-ar", "44100", "-ac", "2", fitted,
            ])
            source_audio = fitted
        else:
            source_audio = raw

        run([
            "ffmpeg", "-y", "-i", source_audio,
            "-af", f"apad=pad_dur={duration:.3f},atrim=duration={duration:.3f}",
            "-ar", "44100", "-ac", "2", padded,
        ])
        normalized_parts.append(padded)
        previous_end = end

    concat_file = os.path.join(shot_audio_dir, "audio_concat.txt")
    with open(concat_file, "w", encoding="utf-8") as f:
        for part in normalized_parts:
            f.write(f"file '{os.path.abspath(part)}'\n")

    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_file,
        "-ar", "44100", "-ac", "2",
        "-c:a", "pcm_s16le", VOICE,
    ])

    total_duration = previous_end
    if total_duration < 18.0 or total_duration > 22.0:
        raise RuntimeError("Storyboard duration must be 18-22 seconds")
else:
    hook = metadata["hook"]
    fact = metadata["fact"]
    twist = metadata["twist"]
    script = f"{hook}... {fact}. Here's the surprising part... {twist}"
    print("Using legacy metadata narration.")
    print("VOICE SCRIPT:", script)
    run([
        sys.executable,
        "-m",
        "piper",
        "--model", VOICE_MODEL,
        "--output_file", VOICE,
        "--length_scale", "1.08",
        "--noise_scale", "0.55",
        "--noise_w_scale", "0.65",
        "--",
        script,
    ])
    total_duration = probe_duration(VOICE)

VOICE_CLEAN = os.path.join(OUTPUT, "voice_clean.wav")
print("Cleaning voice...")
run([
    "ffmpeg", "-y", "-i", VOICE,
    "-af", (
        "highpass=f=70,"
        "lowpass=f=12000,"
        "acompressor=threshold=-18dB:ratio=2.5:attack=5:release=80,"
        "loudnorm=I=-16:TP=-1.5:LRA=11"
    ),
    "-ar", "44100", "-ac", "2", VOICE_CLEAN,
])
os.replace(VOICE_CLEAN, VOICE)

print(f"Creating soft background instrumental ({total_duration:.2f}s)...")
run([
    "ffmpeg", "-y",
    "-f", "lavfi",
    "-i", f"sine=frequency=196:duration={total_duration:.3f}:sample_rate=44100",
    "-af", (
        "volume=0.025,"
        f"afade=t=in:st=0:d=2,"
        f"afade=t=out:st={max(0.1, total_duration - 3):.3f}:d=3"
    ),
    "-ar", "44100", "-ac", "2", MUSIC,
])

print("Mixing voice + instrumental...")
run([
    "ffmpeg", "-y",
    "-i", VIDEO,
    "-i", VOICE,
    "-i", MUSIC,
    "-filter_complex",
    (
        "[1:a]volume=1.0,aresample=44100[voice];"
        "[2:a]volume=0.18,aresample=44100[music];"
        "[voice][music]amix=inputs=2:duration=first:dropout_transition=2[audio]"
    ),
    "-map", "0:v:0",
    "-map", "[audio]",
    "-c:v", "copy",
    "-c:a", "aac",
    "-b:a", "160k",
    "-ar", "44100",
    "-shortest",
    "-movflags", "+faststart",
    FINAL,
])

os.replace(FINAL, VIDEO)

print("")
print("======================================")
print("FACTVERSE AUDIO COMPLETE")
print("======================================")
print("Natural neural voice: READY")
print("Storyboard timing: ALIGNED")
print("Instrumental music: READY")
print("Final video:", VIDEO)
print("======================================")
