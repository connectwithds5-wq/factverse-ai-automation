import json
import os
import subprocess
import tempfile
from pathlib import Path

OUTPUT = Path("output")
CLIPS = OUTPUT / "pixazo_clips"
STORYBOARD = OUTPUT / "storyboard.json"
FINAL = OUTPUT / "factverse.mp4"


def probe(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def run(cmd):
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main():
    board = json.loads(STORYBOARD.read_text(encoding="utf-8"))
    shots = board["shots"]
    if not 4 <= len(shots) <= 5:
        raise SystemExit("Storyboard must contain 4 or 5 shots")

    durations = [float(s["end"]) - float(s["start"]) for s in shots]
    expected = sum(durations)

    for index, target in enumerate(durations, 1):
        path = CLIPS / f"shot_{index:02d}.mp4"
        if not path.exists() or path.stat().st_size == 0:
            raise SystemExit(f"Missing Pixazo clip: {path}")
        actual = probe(path)
        print(f"Shot {index}: Pixazo={actual:.3f}s target={target:.3f}s")

        if actual < target - 0.03:
            pad = target - actual
            print(f"Shot {index}: padding final frame for {pad:.3f}s to preserve storyboard timing")
            fd, tmp_name = tempfile.mkstemp(suffix=".mp4", dir=str(CLIPS))
            os.close(fd)
            tmp = Path(tmp_name)
            try:
                run([
                    "ffmpeg", "-y", "-i", str(path),
                    "-vf", f"tpad=stop_mode=clone:stop_duration={pad:.3f},trim=duration={target:.3f},setpts=PTS-STARTPTS",
                    "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-r", "30", str(tmp),
                ])
                os.replace(tmp, path)
            finally:
                if tmp.exists():
                    tmp.unlink()
        elif actual > target + 0.03:
            run([
                "ffmpeg", "-y", "-i", str(path),
                "-t", f"{target:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-pix_fmt", "yuv420p", "-r", "30", str(path.with_suffix(".trim.mp4")),
            ])
            os.replace(path.with_suffix(".trim.mp4"), path)

        final_actual = probe(path)
        if final_actual < target - 0.05:
            raise SystemExit(f"Shot {index} remains too short: {final_actual:.3f}s < {target:.3f}s")

    concat = CLIPS / "normalized_concat.txt"
    concat.write_text("\n".join(f"file '{(CLIPS / f'shot_{i:02d}.mp4').resolve()}'" for i in range(1, len(shots) + 1)) + "\n", encoding="utf-8")
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", "-r", "30", "-an",
        "-movflags", "+faststart", str(FINAL),
    ])

    actual_final = probe(FINAL)
    print(f"Normalized Pixazo video: {actual_final:.3f}s; storyboard target: {expected:.3f}s")
    if actual_final < expected - 0.08 or actual_final > expected + 0.20:
        raise SystemExit(f"Final Pixazo duration mismatch: {actual_final:.3f}s vs {expected:.3f}s")


if __name__ == "__main__":
    main()
