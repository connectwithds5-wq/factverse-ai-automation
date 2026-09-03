import json
import os
import random
import subprocess
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT = os.path.join(ROOT, "output")
VIDEO = os.path.join(OUTPUT, "factverse.mp4")
METADATA = os.path.join(OUTPUT, "metadata.json")
FRAMES = os.path.join(OUTPUT, "factverse_frames")

WIDTH = 1080
HEIGHT = 1920
FPS = 30
DURATION = 15

os.makedirs(OUTPUT, exist_ok=True)
os.makedirs(FRAMES, exist_ok=True)

api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY GitHub Secret is missing.")

client = genai.Client(api_key=api_key)

model = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.6-flash"
)

categories = [
    "mind blowing facts",
    "mystery and unexplained facts",
    "space facts",
    "science facts",
    "psychology facts",
    "history mysteries",
    "animal facts",
    "strange world facts"
]

category = random.choice(categories)

prompt = f"""
You are the content creator for FACTVERSE.

Create ONE highly engaging YouTube Short.

Category:
{category}

The video must be:
- 15 seconds
- English
- Fascinating
- Accurate
- Suitable for general audiences
- Designed for maximum viewer retention

IMPORTANT:
Never invent facts.
Never invent statistics.
Never present rumors as facts.
If something is unexplained, clearly say it is unexplained or a theory.
Avoid medical advice, politics, dangerous instructions and graphic content.

The opening must create curiosity immediately.

Return ONLY valid JSON:

{{
  "hook": "Powerful hook, maximum 10 words",
  "fact": "Interesting factual explanation, maximum 45 words",
  "twist": "Surprising ending, maximum 15 words",
  "title": "SEO optimized YouTube Shorts title",
  "description": "SEO optimized description with natural keywords",
  "keywords": [
    "facts",
    "did you know",
    "amazing facts",
    "interesting facts",
    "mystery facts",
    "shorts"
  ],
  "hashtags": [
    "#facts",
    "#didyouknow",
    "#amazingfacts",
    "#mystery",
    "#shorts",
    "#factverse"
  ]
}}
"""

response = client.models.generate_content(
    model=model,
    contents=prompt,
    config=types.GenerateContentConfig(
        response_mime_type="application/json"
    )
)

text = response.text.strip()

if text.startswith("```json"):
    text = text[7:]

if text.startswith("```"):
    text = text[3:]

if text.endswith("```"):
    text = text[:-3]

data = json.loads(text.strip())

required = [
    "hook",
    "fact",
    "twist",
    "title",
    "description",
    "keywords",
    "hashtags"
]

for field in required:
    if field not in data:
        raise RuntimeError(
            f"Missing metadata field: {field}"
        )

data["channel"] = "FACTVERSE"
data["category"] = category

with open(
    METADATA,
    "w",
    encoding="utf-8"
) as file:

    json.dump(
        data,
        file,
        ensure_ascii=False,
        indent=2
    )


FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

font_hook = ImageFont.truetype(
    FONT_BOLD,
    76
)

font_fact = ImageFont.truetype(
    FONT_BOLD,
    60
)

font_twist = ImageFont.truetype(
    FONT_BOLD,
    64
)

font_brand = ImageFont.truetype(
    FONT_BOLD,
    36
)

font_small = ImageFont.truetype(
    FONT_REGULAR,
    30
)


def wrap_text(text, font, max_width):

    dummy = Image.new(
        "RGB",
        (WIDTH, HEIGHT)
    )

    draw = ImageDraw.Draw(dummy)

    words = text.split()

    lines = []
    current = ""

    for word in words:

        test = (
            current + " " + word
            if current
            else word
        )

        box = draw.textbbox(
            (0, 0),
            test,
            font=font
        )

        if box[2] - box[0] <= max_width:

            current = test

        else:

            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return lines


hook_lines = wrap_text(
    data["hook"],
    font_hook,
    850
)

fact_lines = wrap_text(
    data["fact"],
    font_fact,
    850
)

twist_lines = wrap_text(
    data["twist"],
    font_twist,
    850
)


random.seed(42)

stars = []

for i in range(100):

    stars.append(
        (
            random.randint(20, WIDTH - 20),
            random.randint(20, HEIGHT - 20),
            random.randint(1, 4)
        )
    )


def draw_centered(
    draw,
    lines,
    font,
    center_y,
    spacing
):

    total = len(lines) * spacing

    y = center_y - total // 2

    for line in lines:

        box = draw.textbbox(
            (0, 0),
            line,
            font=font
        )

        width = box[2] - box[0]

        x = (WIDTH - width) // 2

        # shadow
        draw.text(
            (x + 5, y + 6),
            line,
            font=font,
            fill=(0, 0, 0)
        )

        draw.text(
            (x, y),
            line,
            font=font,
            fill=(245, 245, 250)
        )

        y += spacing


def create_frame(frame_number):

    img = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (8, 10, 25)
    )

    draw = ImageDraw.Draw(img)

    # animated stars
    for x, y, r in stars:

        yy = int(
            (y + frame_number * 0.4)
            % HEIGHT
        )

        draw.ellipse(
            (
                x - r,
                yy - r,
                x + r,
                yy + r
            ),
            fill=(120, 125, 155)
        )

    # Brand
    brand = "FACTVERSE"

    box = draw.textbbox(
        (0, 0),
        brand,
        font=font_brand
    )

    brand_width = box[2] - box[0]

    draw.text(
        (
            (WIDTH - brand_width) // 2,
            120
        ),
        brand,
        font=font_brand,
        fill=(245, 200, 80)
    )

    # DID YOU KNOW
    label = "DID YOU KNOW?"

    box = draw.textbbox(
        (0, 0),
        label,
        font=font_small
    )

    label_width = box[2] - box[0]

    draw.text(
        (
            (WIDTH - label_width) // 2,
            450
        ),
        label,
        font=font_small,
        fill=(180, 185, 205)
    )

    # 0-4 seconds
    if frame_number < FPS * 4:

        draw_centered(
            draw,
            hook_lines,
            font_hook,
            850,
            105
        )

    # 4-11 seconds
    elif frame_number < FPS * 11:

        draw_centered(
            draw,
            fact_lines,
            font_fact,
            900,
            88
        )

    # 11-15 seconds
    else:

        draw_centered(
            draw,
            twist_lines,
            font_twist,
            850,
            90
        )

        follow = "FOLLOW FOR MORE"

        box = draw.textbbox(
            (0, 0),
            follow,
            font=font_small
        )

        width = box[2] - box[0]

        draw.text(
            (
                (WIDTH - width) // 2,
                1200
            ),
            follow,
            font=font_small,
            fill=(180, 185, 205)
        )

    # progress bar

    progress = int(
        WIDTH *
        (frame_number + 1) /
        (FPS * DURATION)
    )

    draw.rectangle(
        (
            0,
            HEIGHT - 15,
            progress,
            HEIGHT
        ),
        fill=(245, 200, 80)
    )

    return img


print("Generating FACTVERSE video...")

total_frames = FPS * DURATION

for i in range(total_frames):

    frame = create_frame(i)

    frame.save(
        os.path.join(
            FRAMES,
            f"frame_{i:05d}.png"
        )
    )


subprocess.run(
    [
        "ffmpeg",
        "-y",
        "-framerate",
        str(FPS),
        "-i",
        os.path.join(
            FRAMES,
            "frame_%05d.png"
        ),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-movflags",
        "+faststart",
        VIDEO
    ],
    check=True
)


print("====================================")
print("FACTVERSE VIDEO GENERATED")
print("====================================")
print("Category:", category)
print("Title:", data["title"])
print("Video:", VIDEO)
print("Metadata:", METADATA)
print("====================================")
