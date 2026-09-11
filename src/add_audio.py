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

# Ryan High is a clearer, more natural documentary-style male voice than the
# previous medium model. Keep a medium fallback so the pipeline remains robust.
VOICE_CANDIDATES = ["en_US-ryan-high", "en_US-lessac-medium"]
VOICE_NAME = None
VOICE_MODEL = None


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
    speed = max(0.5, min(1.08, speed))
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

# Prefer a high-quality male documentary voice, but automatically fall back to
# the already-used Lessac medium model if the high model cannot be downloaded.
for candidate in VOICE_CANDIDATES:
    candidate_model = os.path.join(VOICE_DIR, candidate + ".onnx")
    if os.path.exists(candidate_model):
        VOICE_NAME, VOICE_MODEL = candidate, candidate_model
        break

if VOICE_MODEL is None:
    for candidate in VOICE_CANDIDATES:
        try:
            print(f"Trying Piper voice: {candidate}")
            run([
                sys.executable,
                "-m",
                "piper.download_voices",
                "--data-dir",
                VOICE_DIR,
                candidate,
            ])
            candidate_model = os.path.join(VOICE_DIR, candidate + ".onnx")
            if os.path.exists(candidate_model):
                VOICE_NAME, VOICE_MODEL = candidate, candidate_model
                break
        except subprocess.CalledProcessError as exc:
            print(f"Voice download failed for {candidate}: {exc}")

if VOICE_MODEL is None:
    raise RuntimeError("No usable Piper voice model could be installed")

print(f"Piper voice model ready: {VOICE_NAME}")

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
            # Deliberately slower for clear documentary narration.
            "--length_scale", "1.14",
            "--noise_scale", "0.48",
            "--noise_w_scale", "0.55",
            "--sentence_silence", "0.08",
            "--",
            narration,
        ])

        raw_duration = probe_duration(raw)
        print(f"Shot {index}: raw narration {raw_duration:.3f}s; target {duration:.3f}s")

        # Never squeeze speech hard enough to sound rushed. If the storyboard
        # sentence is too long, fail instead of creating unintelligible audio.
        if raw_duration > duration + 0.08:
            speed = raw_duration / duration
            if speed > 1.08:
                raise RuntimeError(
                    f"Storyboard shot {index} narration is too verbose for natural speech: "
                    f"{raw_duration:.2f}s audio for {duration:.2f}s shot. "
                    "Regenerate the storyboard with fewer words."
                )
            print(f"Shot {index}: tiny timing fit with atempo={speed:.3f}x")
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
        "--length_scale", "1.14",
        "--noise_scale", "0.48",
        "--noise_w_scale", "0.55",
        "--sentence_silence", "0.08",
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
        "acompressor=threshold=-20dB:ratio=2.2:attack=8:release=100,"
        "loudnorm=I=-16:TP=-1.5:LRA=9"
    ),
    "-ar", "44100", "-ac", "2", VOICE_CLEAN,
])
os.replace(VOICE_CLEAN, VOICE)

print(f"Creating soft cinematic background bed ({total_duration:.2f}s)...")
# A layered synthetic pad is intentionally used instead of a raw single sine:
# it sounds like a quiet documentary bed while requiring no copyrighted asset.
run([
    "ffmpeg", "-y",
    "-f", "lavfi",
    "-i", (
        f"sine=frequency=196:duration={total_duration:.3f}:sample_rate=44100," 
        "volume=0.32[a];"
        f"sine=frequency=261.63:duration={total_duration:.3f}:sample_rate=44100," 
        "volume=0.20[b];"
        f"sine=frequency=329.63:duration={total_duration:.3f}:sample_rate=44100," 
        "volume=0.12[c];"
        "[a][b][c]amix=inputs=3:normalize=0,"
        "lowpass=f=1800,highpass=f=90,"
        "afade=t=in:st=0:d=2,"
        f"afade=t=out:st={max(0.1, total_duration - 3):.3f}:d=3"
    ),
    "-ar", "44100", "-ac", "2", MUSIC,
])

print("Mixing voice + cinematic bed...")
run([
    "ffmpeg", "-y",
    "-i", VIDEO,
    "-i", VOICE,
    "-i", MUSIC,
    "-filter_complex",
    (
        "[1:a]volume=1.0,aresample=44100[voice];"
        "[2:a]volume=0.10,aresample=44100[music];"
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
print(f"Voice: {VOICE_NAME}")
print("Natural neural voice: READY")
print("Storyboard timing: ALIGNED")
print("Cinematic background bed: READY")
print("Final video:", VIDEO)
print("======================================")
