import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
VOICE_DIR = ROOT / "voices"
VOICE_NAME = "en_US-lessac-medium"
VOICE_MODEL = VOICE_DIR / f"{VOICE_NAME}.onnx"

VIDEO = OUTPUT / "factverse.mp4"
METADATA = OUTPUT / "metadata.json"
STORYBOARD = OUTPUT / "storyboard.json"
VOICE = OUTPUT / "voice.wav"
VOICE_CLEAN = OUTPUT / "voice_clean.wav"
MUSIC = OUTPUT / "music.wav"
MIXED = OUTPUT / "factverse_mixed.mp4"


def run(command):
    print("+", " ".join(map(str, command)))
    subprocess.run([str(x) for x in command], check=True)


def probe_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def atempo_filter(speed):
    return f"atempo={max(0.5, min(1.15, speed)):.6f}"


def validate_storyboard(shots):
    if not 4 <= len(shots) <= 5:
        raise RuntimeError("Storyboard must contain 4 or 5 shots")
    previous_end = 0.0
    for index, shot in enumerate(shots, 1):
        start, end = float(shot["start"]), float(shot["end"])
        duration = end - start
        if index == 1 and abs(start) > 0.01:
            raise RuntimeError("Storyboard must start at 0 seconds")
        if abs(start - previous_end) > 0.01:
            raise RuntimeError(f"Storyboard shot {index} is not contiguous")
        if not 3.0 <= duration <= 5.0:
            raise RuntimeError(f"Storyboard shot {index} duration must be 3-5 seconds")
        if not str(shot.get("narration", "")).strip():
            raise RuntimeError(f"Storyboard shot {index} has no narration")
        previous_end = end
    if not 18.0 <= previous_end <= 22.0:
        raise RuntimeError(f"Storyboard duration {previous_end:.2f}s is outside 18-22s")
    return previous_end


def generate_shot_voice(shots):
    shot_audio_dir = OUTPUT / "storyboard_audio"
    shot_audio_dir.mkdir(parents=True, exist_ok=True)
    normalized_parts = []

    for index, shot in enumerate(shots, 1):
        duration = float(shot["end"]) - float(shot["start"])
        narration = str(shot["narration"]).strip()
        raw = shot_audio_dir / f"shot_{index:02d}_voice_raw.wav"
        fitted = shot_audio_dir / f"shot_{index:02d}_voice_fitted.wav"
        padded = shot_audio_dir / f"shot_{index:02d}_voice.wav"

        run([
            sys.executable, "-m", "piper",
            "--model", VOICE_MODEL,
            "--output_file", raw,
            "--length_scale", "1.06",
            "--noise_scale", "0.55",
            "--noise_w_scale", "0.65",
            "--", narration,
        ])

        raw_duration = probe_duration(raw)
        if raw_duration > duration + 0.08:
            speed = raw_duration / duration
            if speed > 1.15:
                raise RuntimeError(
                    f"Shot {index} narration is too long for natural delivery: "
                    f"{raw_duration:.2f}s for {duration:.2f}s"
                )
            run(["ffmpeg", "-y", "-i", raw, "-af", atempo_filter(speed),
                 "-ar", "48000", "-ac", "2", fitted])
            source = fitted
        else:
            source = raw

        run([
            "ffmpeg", "-y", "-i", source,
            "-af", f"apad=pad_dur={duration:.3f},atrim=duration={duration:.3f}",
            "-ar", "48000", "-ac", "2", padded,
        ])
        normalized_parts.append(padded)

    concat_file = shot_audio_dir / "audio_concat.txt"
    concat_file.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in normalized_parts),
        encoding="utf-8",
    )
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
         "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", VOICE])


def generate_music(duration):
    # Procedural cinematic bed: layered consonant tones + slow pulse + filtered
    # texture. This avoids the old single-tone "sine wave" sound while remaining
    # deterministic and requiring no copyrighted music asset.
    duration = float(duration)
    filter_complex = (
        f"[0:a]volume=0.055,lowpass=f=900,"
        f"afade=t=in:st=0:d=2,afade=t=out:st={max(0.1, duration-3):.3f}:d=3[drone];"
        f"[1:a]volume=0.030,lowpass=f=1800,"
        f"tremolo=f=0.18:d=0.65[pad];"
        f"[2:a]volume=0.018,highpass=f=900,lowpass=f=5000,"
        f"tremolo=f=0.11:d=0.35[air];"
        f"[3:a]volume=0.022,lowpass=f=2400,"
        f"afade=t=in:st=0:d=1,afade=t=out:st={max(0.1, duration-2):.3f}:d=2[pulse];"
        "[drone][pad][air][pulse]amix=inputs=4:duration=longest:dropout_transition=2,"
        "loudnorm=I=-30:TP=-8:LRA=12"
    )
    run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-t", f"{duration:.3f}", "-i", "sine=frequency=110:sample_rate=48000",
        "-f", "lavfi", "-t", f"{duration:.3f}", "-i", "sine=frequency=165:sample_rate=48000",
        "-f", "lavfi", "-t", f"{duration:.3f}", "-i", "sine=frequency=247:sample_rate=48000",
        "-f", "lavfi", "-t", f"{duration:.3f}", "-i", "sine=frequency=82.5:sample_rate=48000",
        "-filter_complex", filter_complex, "-ar", "48000", "-ac", "2", MUSIC,
    ])


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    VOICE_DIR.mkdir(parents=True, exist_ok=True)

    if not VIDEO.exists() or not METADATA.exists():
        raise RuntimeError("output/factverse.mp4 and output/metadata.json are required")

    if not VOICE_MODEL.exists():
        run([sys.executable, "-m", "piper.download_voices", "--data-dir", VOICE_DIR, VOICE_NAME])
    if not VOICE_MODEL.exists():
        raise RuntimeError(f"Piper voice model missing: {VOICE_MODEL}")

    board = json.loads(STORYBOARD.read_text(encoding="utf-8")) if STORYBOARD.exists() else {}
    shots = board.get("shots", [])
    total_duration = validate_storyboard(shots) if shots else None

    if shots:
        print(f"Generating storyboard-aligned narration for {len(shots)} shots")
        generate_shot_voice(shots)
    else:
        metadata = json.loads(METADATA.read_text(encoding="utf-8"))
        script = f"{metadata['hook']} ... {metadata['fact']} ... {metadata['twist']}"
        run([sys.executable, "-m", "piper", "--model", VOICE_MODEL,
             "--output_file", VOICE, "--length_scale", "1.06", "--", script])
        total_duration = probe_duration(VOICE)

    run([
        "ffmpeg", "-y", "-i", VOICE,
        "-af", "highpass=f=70,lowpass=f=12000,"
               "acompressor=threshold=-20dB:ratio=2.2:attack=5:release=90,"
               "loudnorm=I=-16:TP=-1.5:LRA=10",
        "-ar", "48000", "-ac", "2", VOICE_CLEAN,
    ])
    VOICE_CLEAN.replace(VOICE)

    generate_music(total_duration)

    # Voice stays dominant. Music is ducked automatically while speech is present.
    # A tiny music lift during pauses gives the edit a cinematic pulse.
    run([
        "ffmpeg", "-y", "-i", VIDEO, "-i", VOICE, "-i", MUSIC,
        "-filter_complex",
        "[1:a]aresample=48000,volume=1.0[voice];"
        "[2:a]aresample=48000,volume=0.70[bed];"
        "[voice][bed]sidechaincompress=threshold=0.035:ratio=8:attack=8:release=220:makeup=1:mix=1[musicduck];"
        "[voice][musicduck]amix=inputs=2:duration=first:dropout_transition=2,"
        "loudnorm=I=-14:TP=-1.5:LRA=9[audio]",
        "-map", "0:v:0", "-map", "[audio]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-shortest", "-movflags", "+faststart", MIXED,
    ])
    MIXED.replace(VIDEO)

    final_duration = probe_duration(VIDEO)
    audio_probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=codec_name,sample_rate,channels", "-of", "json", str(VIDEO)],
        check=True, capture_output=True, text=True,
    )
    audio_streams = json.loads(audio_probe.stdout).get("streams", [])
    if not audio_streams:
        raise RuntimeError("Final video has no audio stream")
    if not 18.0 <= final_duration <= 22.0:
        raise RuntimeError(f"Final video duration {final_duration:.2f}s is outside 18-22s")

    print("======================================")
    print("FACTVERSE AUDIO COMPLETE")
    print("======================================")
    print(f"Duration: {final_duration:.2f}s")
    print("Voice: Piper neural narration")
    print("Music: procedural cinematic bed")
    print("Mix: voice-priority sidechain ducking")
    print("Audio stream: VERIFIED")
    print("Final video:", VIDEO)


if __name__ == "__main__":
    main()
