import json
import os
import re
import subprocess
import textwrap
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
VISUALS = OUTPUT / "documentary_visuals"
VIDEO = OUTPUT / "factverse_documentary_test.mp4"
METADATA = OUTPUT / "metadata.json"
PLAN = OUTPUT / "documentary_plan.json"

W, H, FPS = 1080, 1920, 30
DURATION = 15

OUTPUT.mkdir(exist_ok=True)
VISUALS.mkdir(exist_ok=True)

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def run(cmd):
    print("RUN:", " ".join(map(str, cmd)))
    subprocess.run(cmd, check=True)


def clean_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < 0:
        return None
    try:
        return json.loads(text[a:b + 1])
    except Exception:
        return None


def make_plan(data):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required")
    client = genai.Client(api_key=key)
    prompt = f"""
You are a documentary film editor for a premium factual YouTube Short.
Fact: {data['fact']}
Hook: {data['hook']}
Twist: {data['twist']}

Create a 15-second visual plan using 4 cinematic documentary shots.
Prefer real-world photographic subjects that can be found on Wikimedia Commons.
Do not invent people, locations, statistics, or events.
For each shot return: start, end, visual_query, caption.
Queries should be 2-6 concrete English words and suitable for Wikimedia image search.
Return ONLY JSON: {{"shots":[{{"start":0,"end":4,"visual_query":"...","caption":"..."}}]}}
"""
    for model in [os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"), "gemini-2.5-flash-lite"]:
        try:
            r = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.4),
            )
            plan = clean_json(r.text)
            if plan and isinstance(plan.get("shots"), list) and len(plan["shots"]) >= 3:
                plan["shots"] = plan["shots"][:4]
                return plan
        except Exception as e:
            print("Plan model failed:", model, str(e)[:250])
    return {"shots": [
        {"start": 0, "end": 4, "visual_query": data["hook"], "caption": data["hook"]},
        {"start": 4, "end": 8, "visual_query": data["fact"], "caption": "THE FACT"},
        {"start": 8, "end": 12, "visual_query": data["fact"], "caption": "LOOK CLOSER"},
        {"start": 12, "end": 15, "visual_query": data["twist"], "caption": data["twist"]},
    ]}


def wikimedia_image(query, out):
    api = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query", "generator": "search", "gsrsearch": query,
        "gsrnamespace": 6, "gsrlimit": 8,
        "prop": "imageinfo", "iiprop": "url|mime|size",
        "iiurlwidth": 1400, "format": "json",
    }
    r = requests.get(api, params=params, timeout=20, headers={"User-Agent": "FACTVERSE-documentary-test/1.0"})
    r.raise_for_status()
    pages = r.json().get("query", {}).get("pages", {})
    candidates = []
    for p in pages.values():
        info = (p.get("imageinfo") or [{}])[0]
        url = info.get("thumburl") or info.get("url")
        mime = info.get("mime", "")
        if url and mime.startswith("image/"):
            candidates.append(url)
    for url in candidates:
        try:
            rr = requests.get(url, timeout=25, headers={"User-Agent": "FACTVERSE-documentary-test/1.0"})
            rr.raise_for_status()
            tmp = out.with_suffix(".download")
            tmp.write_bytes(rr.content)
            img = Image.open(tmp).convert("RGB")
            img.thumbnail((1800, 2400))
            img.save(out, quality=92)
            tmp.unlink(missing_ok=True)
            return True
        except Exception:
            continue
    return False


def fallback_visual(index, caption):
    img = Image.new("RGB", (W, H), (10, 12, 20))
    d = ImageDraw.Draw(img)
    # Subtle documentary grid / light field, intentionally not a flat text card.
    for x in range(0, W, 90):
        d.line((x, 0, x, H), fill=(35, 38, 50), width=1)
    for y in range(0, H, 90):
        d.line((0, y, W, y), fill=(35, 38, 50), width=1)
    d.ellipse((W//2-420, H//2-420, W//2+420, H//2+420), outline=(70, 75, 95), width=5)
    font = ImageFont.truetype(FONT_BOLD, 58)
    lines = textwrap(caption, 720, font, d)
    y = H//2 - len(lines)*38
    for line in lines:
        box = d.textbbox((0, 0), line, font=font)
        d.text(((W-(box[2]-box[0]))/2, y), line, font=font, fill=(235,235,240))
        y += 76
    img.save(OUTPUT / f"visual_{index:02d}.jpg", quality=92)
    return OUTPUT / f"visual_{index:02d}.jpg"


def textwrap(text, width, font, draw):
    words = str(text).split()
    lines, cur = [], ""
    for word in words:
        test = f"{cur} {word}".strip()
        if draw.textbbox((0, 0), test, font=font)[2] <= width:
            cur = test
        else:
            if cur: lines.append(cur)
            cur = word
    if cur: lines.append(cur)
    return lines


def cinematic_frame(src, t, caption, shot_no):
    img = Image.open(src).convert("RGB")
    scale = max(W / img.width, H / img.height)
    img = img.resize((int(img.width*scale), int(img.height*scale)), Image.Resampling.LANCZOS)
    max_x, max_y = img.width-W, img.height-H
    # Slow Ken Burns push + lateral drift.
    p = min(max(t, 0), 1)
    x = int(max_x * (0.10 + 0.75*p)) if max_x else 0
    y = int(max_y * (0.20 + 0.45*p)) if max_y else 0
    img = img.crop((x, y, x+W, y+H))
    overlay = Image.new("RGBA", (W, H), (0,0,0,0))
    od = ImageDraw.Draw(overlay)
    od.rectangle((0, 0, W, 170), fill=(0,0,0,120))
    od.rectangle((0, H-390, W, H), fill=(0,0,0,145))
    font = ImageFont.truetype(FONT_BOLD, 54)
    small = ImageFont.truetype(FONT_REG, 28)
    od.text((55, 55), f"FACTVERSE  /  DOCUMENTARY TEST", font=small, fill=(230,230,235,220))
    od.text((55, H-320), caption, font=font, fill=(250,250,250,255), stroke_width=2, stroke_fill=(0,0,0,180))
    od.text((55, H-85), f"SHOT {shot_no:02d}   •   {int(p*100):02d}%", font=small, fill=(220,220,225,220))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def build_video(plan):
    frames_dir = OUTPUT / "documentary_frames"
    frames_dir.mkdir(exist_ok=True)
    # Download at least one real visual per planned shot.
    assets = []
    for i, shot in enumerate(plan["shots"], 1):
        path = VISUALS / f"shot_{i:02d}.jpg"
        ok = wikimedia_image(shot.get("visual_query", ""), path)
        if not ok:
            path = fallback_visual(i, shot.get("caption", "FACTVERSE"))
        assets.append(path)

    # Normalize timing to the full 15 seconds.
    shots = plan["shots"]
    for i, shot in enumerate(shots):
        start = float(shot.get("start", 0))
        end = float(shot.get("end", DURATION))
        if i == 0: start = 0
        if i == len(shots)-1: end = DURATION
        shots[i]["start"], shots[i]["end"] = start, end

    n = 0
    for shot_idx, (shot, asset) in enumerate(zip(shots, assets), 1):
        duration = max(0.5, shot["end"] - shot["start"])
        count = int(round(duration * FPS))
        for j in range(count):
            frame = cinematic_frame(asset, j/max(1,count-1), shot.get("caption", ""), shot_idx)
            frame.save(frames_dir / f"frame_{n:05d}.jpg", quality=90)
            n += 1

    run(["ffmpeg", "-y", "-framerate", str(FPS), "-i", str(frames_dir / "frame_%05d.jpg"),
         "-t", str(DURATION), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(VIDEO)])
    return VIDEO


def main():
    data = json.loads(METADATA.read_text(encoding="utf-8"))
    plan = make_plan(data)
    PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    video = build_video(plan)
    print("DOCUMENTARY TEST VIDEO:", video)


if __name__ == "__main__":
    main()
