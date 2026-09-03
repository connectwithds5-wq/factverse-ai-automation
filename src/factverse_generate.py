import json
import os
import random
import re
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types


# ==========================================================
# FACTVERSE 2.0
# TRENDING TOPIC + VERIFIED FACT + VIRAL SEO
# ==========================================================

ROOT = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

OUTPUT = os.path.join(ROOT, "output")

VIDEO = os.path.join(
    OUTPUT,
    "factverse.mp4"
)

METADATA = os.path.join(
    OUTPUT,
    "metadata.json"
)

FRAMES = os.path.join(
    OUTPUT,
    "factverse_frames"
)


WIDTH = 1080
HEIGHT = 1920
FPS = 30
DURATION = 15


os.makedirs(
    OUTPUT,
    exist_ok=True
)

os.makedirs(
    FRAMES,
    exist_ok=True
)


# ==========================================================
# GEMINI
# ==========================================================

api_key = os.environ.get(
    "GEMINI_API_KEY"
)

if not api_key:

    raise RuntimeError(
        "GEMINI_API_KEY GitHub Secret is missing."
    )


client = genai.Client(
    api_key=api_key
)


model = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.7-flash"
)


# ==========================================================
# GOOGLE TRENDS INDIA
# ==========================================================

def get_trending_topics():

    url = (
        "https://trends.google.com/"
        "trending/rss?geo=IN"
    )

    print("")
    print("======================================")
    print("FETCHING INDIA TRENDING TOPICS")
    print("======================================")


    try:

        request = urllib.request.Request(

            url,

            headers={
                "User-Agent":
                "Mozilla/5.0"
            }

        )

        with urllib.request.urlopen(
            request,
            timeout=20
        ) as response:

            xml_data = response.read()


        root = ET.fromstring(
            xml_data
        )


        topics = []


        for item in root.findall(
            ".//item"
        ):

            title_node = item.find(
                "title"
            )

            traffic_node = item.find(
                "{https://trends.google.com/trending/rss}approx_traffic"
            )


            if title_node is None:
                continue


            title = (
                title_node.text or ""
            ).strip()


            traffic = ""

            if traffic_node is not None:

                traffic = (
                    traffic_node.text or ""
                ).strip()


            if title:

                topics.append({

                    "topic": title,

                    "traffic": traffic

                })


        # Remove duplicates

        unique = []

        seen = set()


        for item in topics:

            key = item["topic"].lower()

            if key not in seen:

                seen.add(key)

                unique.append(item)


        print(
            "Trending topics found:",
            len(unique)
        )


        for item in unique[:15]:

            print(
                "-",
                item["topic"],
                item["traffic"]
            )


        return unique[:30]


    except Exception as error:

        print(
            "Google Trends unavailable:",
            error
        )

        print(
            "Using FACTVERSE evergreen fallback."
        )


        return [

            {
                "topic": "AI technology",
                "traffic": ""
            },

            {
                "topic": "space discovery",
                "traffic": ""
            },

            {
                "topic": "human brain",
                "traffic": ""
            },

            {
                "topic": "ocean mystery",
                "traffic": ""
            },

            {
                "topic": "animal intelligence",
                "traffic": ""
            },

            {
                "topic": "strange science",
                "traffic": ""
            }

        ]


trends = get_trending_topics()


trend_text = "\n".join(

    f"- {item['topic']} "
    f"(search activity: {item['traffic'] or 'unknown'})"

    for item in trends

)


# ==========================================================
# FACTVERSE CONTENT PROMPT
# ==========================================================

prompt = f"""
You are the senior viral content strategist for FACTVERSE.

FACTVERSE creates short-form videos about:

- mind-blowing facts
- science
- technology
- AI
- space
- psychology
- history mysteries
- animals
- strange natural phenomena
- unexplained mysteries

CURRENT INDIA TRENDING SEARCHES:

{trend_text}


YOUR JOB:

Find ONE topic that has BOTH:

1. Current search interest or trend potential
2. A genuinely fascinating FACTVERSE angle

Do NOT simply make a news recap.

Turn the trend into a curiosity-driven factual story.

Example:

Trend:
AI

Bad:
"AI is becoming popular."

Good:
"Your AI chatbot may remember more than you think."

Trend:
Space

Bad:
"NASA discovered something."

Good:
"Scientists found a place in space where time behaves strangely."


IMPORTANT FACT RULES:

- Never invent facts.
- Never invent statistics.
- Never make unsupported claims.
- Do not use rumors as facts.
- If something is a theory, clearly label it as a theory.
- Verify factual claims using current Google Search information.
- Prefer reliable sources such as NASA, NOAA, scientific institutions, universities, museums, Britannica, government sources and major reputable publications.
- Avoid medical advice.
- Avoid politics.
- Avoid dangerous instructions.
- Avoid graphic content.
- Avoid fake celebrity claims.
- Avoid copyright-sensitive quotes.


VIDEO:

Exactly 15 seconds.

Structure:

0-2 seconds:
EXTREME curiosity hook.

2-6 seconds:
Introduce the fascinating fact.

6-11 seconds:
Explain the fact simply.

11-14 seconds:
Surprising twist.

14-15 seconds:
Short loop-friendly ending.


WRITING STYLE:

- Natural spoken English.
- Very easy to understand.
- Short sentences.
- No boring introduction.
- No "Hello guys".
- No "Today we are going to".
- No filler.
- Make viewers want to stay until the final second.


SEO:

Create:

- Highly clickable YouTube Shorts title.
- Natural search keywords.
- Strong description.
- Relevant hashtags only.
- Do NOT keyword stuff.
- Include the actual topic naturally.
- Do NOT use misleading clickbait.


RETURN ONLY VALID JSON.

Required structure:

{{
  "trend_topic": "exact trending topic or relevant trend",
  "topic": "FACTVERSE video topic",
  "category": "science/technology/space/etc",
  "hook": "maximum 10 words",
  "fact": "maximum 45 words",
  "twist": "maximum 15 words",
  "title": "SEO optimized YouTube Shorts title",
  "description": "SEO optimized natural description",
  "keywords": [
    "keyword 1",
    "keyword 2",
    "keyword 3",
    "keyword 4",
    "keyword 5",
    "keyword 6",
    "keyword 7",
    "keyword 8"
  ],
  "hashtags": [
    "#facts",
    "#didyouknow",
    "#shorts",
    "#factverse"
  ],
  "source_urls": [
    "source URL used to verify the fact"
  ]
}}
"""


# ==========================================================
# GEMINI SEARCH-GROUNDED GENERATION
# ==========================================================

print("")
print("======================================")
print("GENERATING VERIFIED FACTVERSE CONTENT")
print("======================================")


grounding_tool = types.Tool(
    google_search=types.GoogleSearch()
)


response = client.models.generate_content(

    model=model,

    contents=prompt,

    config=types.GenerateContentConfig(

        tools=[
            grounding_tool
        ],

        response_mime_type="application/json",

        max_output_tokens=1800

    )

)


text = response.text.strip()


# ==========================================================
# CLEAN JSON
# ==========================================================

if text.startswith(
    "```json"
):

    text = text[7:]


if text.startswith(
    "```"
):

    text = text[3:]


if text.endswith(
    "```"
):

    text = text[:-3]


try:

    data = json.loads(
        text.strip()
    )

except Exception as error:

    print(
        "Gemini returned:",
        text
    )

    raise RuntimeError(
        f"Invalid JSON from Gemini: {error}"
    )


# ==========================================================
# VALIDATE
# ==========================================================

required = [

    "trend_topic",
    "topic",
    "category",
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


# ==========================================================
# SAFETY / QUALITY CHECKS
# ==========================================================

if len(data["hook"].split()) > 12:

    raise RuntimeError(
        "Hook is too long."
    )


if len(data["fact"].split()) > 60:

    raise RuntimeError(
        "Fact is too long."
    )


if len(data["twist"].split()) > 20:

    raise RuntimeError(
        "Twist is too long."
    )


data["channel"] = "FACTVERSE"

data["duration"] = DURATION

data["generated_at"] = time.strftime(
    "%Y-%m-%d %H:%M:%S UTC",
    time.gmtime()
)


# ==========================================================
# SAVE METADATA
# ==========================================================

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


print("")
print("======================================")
print("FACTVERSE CONTENT READY")
print("======================================")
print(
    "Trend:",
    data["trend_topic"]
)
print(
    "Topic:",
    data["topic"]
)
print(
    "Category:",
    data["category"]
)
print(
    "Title:",
    data["title"]
)
print("======================================")


# ==========================================================
# FONTS
# ==========================================================

FONT_BOLD = (
    "/usr/share/fonts/truetype/"
    "dejavu/DejaVuSans-Bold.ttf"
)

FONT_REGULAR = (
    "/usr/share/fonts/truetype/"
    "dejavu/DejaVuSans.ttf"
)


font_hook = ImageFont.truetype(
    FONT_BOLD,
    76
)

font_fact = ImageFont.truetype(
    FONT_BOLD,
    58
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


# ==========================================================
# TEXT WRAPPER
# ==========================================================

def wrap_text(
    text,
    font,
    max_width
):

    dummy = Image.new(
        "RGB",
        (WIDTH, HEIGHT)
    )

    draw = ImageDraw.Draw(
        dummy
    )

    words = text.split()

    lines = []

    current = ""


    for word in words:

        test = (

            current
            + " "
            + word

            if current

            else word

        )


        box = draw.textbbox(

            (0, 0),

            test,

            font=font

        )


        if (
            box[2] - box[0]
            <= max_width
        ):

            current = test

        else:

            if current:

                lines.append(
                    current
                )

            current = word


    if current:

        lines.append(
            current
        )


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


# ==========================================================
# STAR FIELD
# ==========================================================

random.seed(
    sum(
        ord(c)
        for c in data["topic"]
    )
)


stars = []


for _ in range(140):

    stars.append(

        (

            random.randint(
                20,
                WIDTH - 20
            ),

            random.randint(
                20,
                HEIGHT - 20
            ),

            random.randint(
                1,
                4
            )

        )

    )


# ==========================================================
# CENTER TEXT
# ==========================================================

def draw_centered(

    draw,
    lines,
    font,
    center_y,
    spacing

):

    total = (
        len(lines)
        * spacing
    )


    y = (
        center_y
        - total // 2
    )


    for line in lines:

        box = draw.textbbox(

            (0, 0),

            line,

            font=font

        )


        width = (
            box[2] - box[0]
        )


        x = (
            WIDTH - width
        ) // 2


        # Shadow

        draw.text(

            (
                x + 5,
                y + 6
            ),

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


# ==========================================================
# FRAME GENERATION
# ==========================================================

def create_frame(
    frame_number
):

    img = Image.new(

        "RGB",

        (
            WIDTH,
            HEIGHT
        ),

        (8, 10, 25)

    )


    draw = ImageDraw.Draw(
        img
    )


    # ------------------------------------------------------
    # Animated stars
    # ------------------------------------------------------

    for x, y, r in stars:

        yy = int(

            (
                y
                + frame_number * 0.45
            )
            % HEIGHT

        )


        brightness = (
            100
            + (
                frame_number
                % 50
            )
        )


        draw.ellipse(

            (

                x - r,
                yy - r,
                x + r,
                yy + r

            ),

            fill=(

                brightness,
                brightness,
                min(
                    190,
                    brightness + 30
                )

            )

        )


    # ------------------------------------------------------
    # Moving accent circles
    # ------------------------------------------------------

    pulse = (
        frame_number
        % 90
    )


    radius = (
        180
        + pulse
    )


    cx = WIDTH // 2

    cy = 880


    draw.ellipse(

        (

            cx - radius,
            cy - radius,

            cx + radius,
            cy + radius

        ),

        outline=(

            45,
            55,
            90

        ),

        width=3

    )


    # ------------------------------------------------------
    # BRAND
    # ------------------------------------------------------

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

            (
                WIDTH
                - brand_width
            ) // 2,

            120

        ),

        brand,

        font=font_brand,

        fill=(245, 200, 80)

    )


    # ------------------------------------------------------
    # TREND LABEL
    # ------------------------------------------------------

    label = "TRENDING FACT"


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

            (
                WIDTH
                - label_width
            ) // 2,

            450

        ),

        label,

        font=font_small,

        fill=(180, 185, 205)

    )


    # ------------------------------------------------------
    # TIMELINE
    # ------------------------------------------------------

    if frame_number < FPS * 2:

        draw_centered(

            draw,

            hook_lines,

            font_hook,

            850,

            105

        )


    elif frame_number < FPS * 11:

        draw_centered(

            draw,

            fact_lines,

            font_fact,

            900,

            86

        )


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


        width = (
            box[2] - box[0]
        )


        draw.text(

            (

                (
                    WIDTH - width
                ) // 2,

                1200

            ),

            follow,

            font=font_small,

            fill=(180, 185, 205)

        )


    # ------------------------------------------------------
    # PROGRESS BAR
    # ------------------------------------------------------

    progress = int(

        WIDTH
        * (
            frame_number + 1
        )
        / (
            FPS * DURATION
        )

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


# ==========================================================
# GENERATE FRAMES
# ==========================================================

print("")
print(
    "Generating FACTVERSE frames..."
)


total_frames = (
    FPS * DURATION
)


for i in range(
    total_frames
):

    frame = create_frame(
        i
    )


    frame.save(

        os.path.join(

            FRAMES,

            f"frame_{i:05d}.png"

        )

    )


# ==========================================================
# FFMPEG
# ==========================================================

print(
    "Encoding final video..."
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


# ==========================================================
# CLEAN OLD FRAMES
# ==========================================================

try:

    for filename in os.listdir(
        FRAMES
    ):

        os.remove(
            os.path.join(
                FRAMES,
                filename
            )
        )

    os.rmdir(
        FRAMES
    )

except Exception:

    pass


print("")
print("======================================")
print("FACTVERSE VIDEO GENERATED 🚀")
print("======================================")
print(
    "Trend:",
    data["trend_topic"]
)
print(
    "Topic:",
    data["topic"]
)
print(
    "Title:",
    data["title"]
)
print(
    "Video:",
    VIDEO
)
print(
    "Metadata:",
    METADATA
)
print("======================================")
