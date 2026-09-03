import json
import os
import random
import subprocess
import re
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types

# ============================================================
# FACTVERSE 4.0
# AI FACT CONTENT + VERTICAL SHORT VIDEO
# ============================================================

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

# ============================================================
# GEMINI
# ============================================================

api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError(
        "GEMINI_API_KEY GitHub Secret is missing."
    )

client = genai.Client(api_key=api_key)

# Use a stable model.
# Can be overridden from GitHub Variables with GEMINI_MODEL.
MODEL_CANDIDATES = [
    os.environ.get("GEMINI_MODEL", "gemini-3.6-flash"),
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]

# remove duplicates while preserving order
MODEL_CANDIDATES = list(dict.fromkeys(MODEL_CANDIDATES))

# ============================================================
# TRENDING / HIGH RETENTION CATEGORIES
# ============================================================

categories = [
    "mind blowing science facts",
    "mystery and unexplained facts",
    "space and universe facts",
    "psychology and human behavior",
    "strange animal facts",
    "history mysteries",
    "technology and AI facts",
    "ocean and deep sea mysteries",
    "weird but true facts",
    "human body facts",
]

category = random.choice(categories)

# ============================================================
# PROMPT
# ============================================================

prompt = f"""
You are the senior content creator for FACTVERSE.

Create ONE highly engaging YouTube Short for the category:

{category}

GOAL:
Create a fact that makes viewers stop scrolling, watch until the
end, and want to comment/share.

VIDEO:
- Exactly 15 seconds
- English
- General audience
- Highly fascinating
- Natural spoken English
- Short sentences
- Strong curiosity gap
- Strong ending
- No boring introduction

FACT QUALITY:
- NEVER invent facts.
- NEVER invent statistics.
- NEVER make unsupported claims.
- Prefer well-established scientific, historical or factual information.
- If something is debated, say it is a theory or debated.
- No medical advice.
- No politics.
- No dangerous instructions.
- No graphic content.

RETENTION STRUCTURE:

HOOK:
Maximum 10 words.
Must immediately create curiosity.

FACT:
Maximum 45 words.
Explain the fact clearly and naturally.

TWIST:
Maximum 15 words.
The final line should create surprise and encourage viewers to
keep watching or comment.

SEO:
Create a clickable YouTube Shorts title.
Description should naturally include relevant search keywords.
Do not keyword stuff.

RETURN ONLY VALID JSON.
NO markdown.
NO code fences.

JSON FORMAT:

{{
  "hook": "Short curiosity hook",
  "fact": "Clear factual explanation",
  "twist": "Surprising ending",
  "title": "SEO optimized YouTube Shorts title",
  "description": "SEO optimized description",
  "keywords": [
    "facts",
    "did you know",
    "amazing facts",
    "interesting facts",
    "mind blowing facts",
    "science facts",
    "shorts"
  ],
  "hashtags": [
    "#facts",
    "#didyouknow",
    "#amazingfacts",
    "#interestingfacts",
    "#shorts",
    "#factverse"
  ]
}}
"""

# ============================================================
# SAFE JSON PARSER
# ============================================================

def clean_json(text):

    if not text:
        return None

    text = text.strip()

    # Remove markdown fences
    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    # Find JSON object if extra text exists
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1:
        return None

    text = text[start:end + 1]

    try:
        return json.loads(text)
    except Exception:
        return None


# ============================================================
# VERIFIED FALLBACK CONTENT
# ============================================================

FALLBACK_FACTS = [
    {
        "hook": "Your brain can create memories that never happened.",
        "fact": "Memory is reconstructive. When you remember an event, your brain rebuilds parts of it, which means details can sometimes change without you realizing it.",
        "twist": "So a vivid memory isn't always a perfect recording.",
        "title": "Your Brain Can Create Fake Memories 🤯",
        "description": "Did you know your brain can create memories that never happened? Learn this fascinating psychology fact about human memory in this short.",
        "keywords": [
            "facts",
            "did you know",
            "psychology facts",
            "brain facts",
            "human brain",
            "memory facts",
            "interesting facts",
            "shorts"
        ],
        "hashtags": [
            "#facts",
            "#didyouknow",
            "#psychology",
            "#brainfacts",
            "#interestingfacts",
            "#shorts",
            "#factverse"
        ]
    },
    {
        "hook": "There is a planet where it may rain glass sideways.",
        "fact": "On the exoplanet HD 189733 b, scientists have found evidence of extreme winds and silicate particles. Under those conditions, researchers think glass-like particles could be blown sideways.",
        "twist": "Imagine weather made of glass moving at extreme speed.",
        "title": "A Planet Where It May Rain Glass 😳",
        "description": "A fascinating space fact about HD 189733 b and its extreme atmosphere. Could glass-like particles really blow sideways on another planet?",
        "keywords": [
            "space facts",
            "planet facts",
            "amazing facts",
            "science facts",
            "universe",
            "astronomy",
            "did you know",
            "shorts"
        ],
        "hashtags": [
            "#space",
            "#spacefacts",
            "#science",
            "#universe",
            "#astronomy",
            "#didyouknow",
            "#shorts",
            "#factverse"
        ]
    },
    {
        "hook": "Octopuses have three hearts.",
        "fact": "An octopus has three hearts. Two pump blood toward its gills, while the third pumps blood through the rest of its body.",
        "twist": "And swimming temporarily changes how one of those hearts works.",
        "title": "Octopuses Have THREE Hearts 🐙",
        "description": "Did you know octopuses have three hearts? Discover one of the strangest and most amazing animal facts in this quick FACTVERSE Short.",
        "keywords": [
            "animal facts",
            "octopus facts",
            "amazing facts",
            "did you know",
            "ocean facts",
            "interesting facts",
            "shorts"
        ],
        "hashtags": [
            "#animalfacts",
            "#octopus",
            "#ocean",
            "#didyouknow",
            "#amazingfacts",
            "#shorts",
            "#factverse"
        ]
    },
    {
        "hook": "Space is completely silent.",
        "fact": "Sound needs a medium such as air, water, or another material to travel. Most of outer space is an extremely thin vacuum, so ordinary sound waves cannot travel through it.",
        "twist": "So explosions in space wouldn't sound like movies.",
        "title": "Why Space Is Completely Silent 🚀",
        "description": "Why is space silent? Discover the science behind sound, vacuum, and outer space in this fascinating FACTVERSE Short.",
        "keywords": [
            "space facts",
            "science facts",
            "sound in space",
            "universe facts",
            "astronomy",
            "did you know",
            "shorts"
        ],
        "hashtags": [
            "#spacefacts",
            "#sciencefacts",
            "#space",
            "#astronomy",
            "#universe",
            "#didyouknow",
            "#shorts",
            "#factverse"
        ]
    }
]


def verified_fallback():

    # Choose a random verified fallback.
    item = random.choice(FALLBACK_FACTS)

    return dict(item)


# ============================================================
# GENERATE AI CONTENT
# ============================================================

data = None
used_model = None

print("====================================")
print("FACTVERSE 4.0")
print("CATEGORY:", category)
print("====================================")

for model in MODEL_CANDIDATES:

    try:

        print("Trying Gemini model:", model)

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.8,
            )
        )

        parsed = clean_json(response.text)

        if parsed and all(
            key in parsed
            for key in [
                "hook",
                "fact",
                "twist",
                "title",
                "description",
                "keywords",
                "hashtags"
            ]
        ):

            data = parsed
            used_model = model

            print("Gemini generation successful.")
            print("MODEL:", model)

            break

        print(
            "Gemini returned invalid/incomplete JSON:",
            model
        )

    except Exception as error:

        print(
            "Gemini model failed:",
            model
        )

        print(
            "Reason:",
            str(error)[:500]
        )

        continue


# ============================================================
# FINAL FALLBACK
# ============================================================

if data is None:

    print("====================================")
    print("USING VERIFIED FALLBACK")
    print("====================================")

    data = verified_fallback()
    used_model = "verified-fallback"


# ============================================================
# GUARANTEE REQUIRED FIELDS
# ============================================================

fallback = verified_fallback()

for field in [
    "hook",
    "fact",
    "twist",
    "title",
    "description",
    "keywords",
    "hashtags"
]:

    if field not in data:
        data[field] = fallback[field]


# Make sure strings are strings
data["hook"] = str(data["hook"]).strip()
data["fact"] = str(data["fact"]).strip()
data["twist"] = str(data["twist"]).strip()
data["title"] = str(data["title"]).strip()
data["description"] = str(data["description"]).strip()

# Guarantee lists
if not isinstance(data["keywords"], list):
    data["keywords"] = fallback["keywords"]

if not isinstance(data["hashtags"], list):
    data["hashtags"] = fallback["hashtags"]


# ============================================================
# METADATA
# ============================================================

data["channel"] = "FACTVERSE"
data["category"] = category
data["model"] = used_model
data["duration"] = DURATION
data["language"] = "English"

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


# ============================================================
# FONTS
# ============================================================

FONT_BOLD = (
    "/usr/share/fonts/truetype/dejavu/"
    "DejaVuSans-Bold.ttf"
)

FONT_REGULAR = (
    "/usr/share/fonts/truetype/dejavu/"
    "DejaVuSans.ttf"
)

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


# ============================================================
# TEXT WRAPPING
# ============================================================

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


# ============================================================
# STAR FIELD
# ============================================================

random.seed()

stars = []

for i in range(120):

    stars.append(
        (
            random.randint(20, WIDTH - 20),
            random.randint(20, HEIGHT - 20),
            random.randint(1, 4)
        )
    )


# ============================================================
# CENTERED TEXT
# ============================================================

def draw_centered(
    draw,
    lines,
    font,
    center_y,
    spacing
):

    total_height = (
        len(lines) * spacing
    )

    y = center_y - total_height // 2

    for line in lines:

        box = draw.textbbox(
            (0, 0),
            line,
            font=font
        )

        width = box[2] - box[0]

        x = (
            WIDTH - width
        ) // 2

        # Shadow
        draw.text(
            (x + 5, y + 6),
            line,
            font=font,
            fill=(0, 0, 0)
        )

        # Main text
        draw.text(
            (x, y),
            line,
            font=font,
            fill=(245, 245, 250)
        )

        y += spacing


# ============================================================
# FRAME GENERATOR
# ============================================================

def create_frame(frame_number):

    img = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (8, 10, 25)
    )

    draw = ImageDraw.Draw(img)

    # Animated stars
    for x, y, r in stars:

        yy = int(
            (
                y +
                frame_number * 0.4
            ) % HEIGHT
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

    # ========================================================
    # BRAND
    # ========================================================

    brand = "FACTVERSE"

    box = draw.textbbox(
        (0, 0),
        brand,
        font=font_brand
    )

    brand_width = (
        box[2] - box[0]
    )

    draw.text(
        (
            (WIDTH - brand_width) // 2,
            120
        ),
        brand,
        font=font_brand,
        fill=(245, 200, 80)
    )

    # ========================================================
    # LABEL
    # ========================================================

    label = "DID YOU KNOW?"

    box = draw.textbbox(
        (0, 0),
        label,
        font=font_small
    )

    label_width = (
        box[2] - box[0]
    )

    draw.text(
        (
            (WIDTH - label_width) // 2,
            450
        ),
        label,
        font=font_small,
        fill=(180, 185, 205)
    )

    # ========================================================
    # HOOK
    # ========================================================

    if frame_number < FPS * 4:

        draw_centered(
            draw,
            hook_lines,
            font_hook,
            850,
            105
        )

    # ========================================================
    # FACT
    # ========================================================

    elif frame_number < FPS * 11:

        draw_centered(
            draw,
            fact_lines,
            font_fact,
            900,
            88
        )

    # ========================================================
    # TWIST
    # ========================================================

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

        follow_width = (
            box[2] - box[0]
        )

        draw.text(
            (
                (WIDTH - follow_width) // 2,
                1200
            ),
            follow,
            font=font_small,
            fill=(180, 185, 205)
        )

    # ========================================================
    # PROGRESS BAR
    # ========================================================

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


# ============================================================
# CLEAN OLD FRAMES
# ============================================================

for filename in os.listdir(FRAMES):

    if filename.endswith(".png"):

        try:
            os.remove(
                os.path.join(
                    FRAMES,
                    filename
                )
            )

        except Exception:
            pass


# ============================================================
# GENERATE FRAMES
# ============================================================

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


# ============================================================
# FFMPEG
# ============================================================

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
        "-preset",
        "medium",
        "-crf",
        "20",
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


# ============================================================
# FINAL CHECK
# ============================================================

if not os.path.exists(VIDEO):
    raise RuntimeError(
        "FACTVERSE video was not generated."
    )

if not os.path.exists(METADATA):
    raise RuntimeError(
        "FACTVERSE metadata was not generated."
    )


print("====================================")
print("FACTVERSE VIDEO GENERATED")
print("====================================")
print("Category:", category)
print("Model:", used_model)
print("Title:", data["title"])
print("Video:", VIDEO)
print("Metadata:", METADATA)
print("====================================")
