import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUTPUT = Path("output")
STORYBOARD = OUTPUT / "storyboard.json"
META = OUTPUT / "metadata.json"
FRAMES = OUTPUT / "emergency_frames"
CLIPS = OUTPUT / "emergency_clips"
FINAL = OUTPUT / "factverse.mp4"

def get_font(size, bold=False):
    p = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    return ImageFont.truetype(p, size) if p.exists() else ImageFont.load_default()

def wrap(text, width):
    lines, cur = [], ""
    for word in str(text).split():
        trial = (cur + " " + word).strip()
        if len(trial) <= width:
            cur = trial
        else:
            if cur: lines.append(cur)
            cur = word
    if cur: lines.append(cur)
    return lines

def make_frame(i, shot, meta):
    w, h = 1280, 720
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            glow = int(20 * max(0, 1 - (((x-950)**2 + (y-170)**2)**0.5)/1100))
            b = 8 + int(9*(1-y/h))
            px[x,y] = (b+glow, b+glow, b+glow+5)
    img = img.filter(ImageFilter.GaussianBlur(0.2))
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle((55,55,w-55,h-55), outline=(170,170,180,110), width=2)
    d.rectangle((55,55,68,h-55), fill=(150,30,35,220))
    title = str(meta.get("title") or meta.get("topic") or "FACTVERSE")
    caption = str(shot.get("caption") or "")
    detail = str(meta.get("fact") or shot.get("visual_prompt") or "")
    d.text((100,95), "FACTVERSE", font=get_font(28, True), fill=(225,225,230,210))
    d.text((100,145), f"{i:02d}", font=get_font(26, True), fill=(190,50,55,255))
    y = 205
    for line in wrap(title, 38)[:3]:
        d.text((100,y), line, font=get_font(48, True), fill=(245,245,248,255)); y += 58
    y += 22
    for line in wrap(caption, 48)[:3]:
        d.text((100,y), line, font=get_font(30, True), fill=(215,215,220,255)); y += 40
    y = 530
    for line in wrap(detail, 78)[:2]:
        d.text((100,y), line, font=get_font(22), fill=(175,175,185,220)); y += 30
    path = FRAMES / f"frame_{i:02d}.png"
    img.save(path)
    return path

def main():
    board = json.loads(STORYBOARD.read_text(encoding="utf-8"))
    meta = json.loads(META.read_text(encoding="utf-8")) if META.exists() else {}
    shots = board.get("shots", [])
    if not 4 <= len(shots) <= 5: raise SystemExit("Storyboard must contain 4 or 5 shots")
    FRAMES.mkdir(parents=True, exist_ok=True); CLIPS.mkdir(parents=True, exist_ok=True)
    for i, shot in enumerate(shots, 1):
        duration = float(shot["end"]) - float(shot["start"])
        frame = make_frame(i, shot, meta)
        clip = CLIPS / f"shot_{i:02d}.mp4"
        vf = "scale=1536:864:force_original_aspect_ratio=increase,crop=1536:864,zoompan=z='min(zoom+0.0007,1.10)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:fps=30,scale=1280:720,format=yuv420p"
        subprocess.run(["ffmpeg","-y","-loop","1","-i",str(frame),"-t",f"{duration:.3f}","-vf",vf,"-an","-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p","-r","30",str(clip)], check=True)
    concat = CLIPS / "concat.txt"
    concat.write_text("\n".join(f"file '{(CLIPS/f'shot_{i:02d}.mp4').resolve()}'" for i in range(1,len(shots)+1))+"\n", encoding="utf-8")
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-c:v","libx264","-preset","veryfast","-crf","19","-pix_fmt","yuv420p","-r","30","-an","-movflags","+faststart",str(FINAL)], check=True)
    print("Zero-API emergency fallback video created:", FINAL)

if __name__ == "__main__":
    main()
