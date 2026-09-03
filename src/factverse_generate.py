import json
import os
import random
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET

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


# ==========================================================
# VERIFIED FALLBACK FACTS
# If Gemini quota/API fails, workflow continues automatically.
# ==========================================================

FALLBACK_FACTS = [
    {
        "trend_topic": "space",
        "topic": "A day on Venus is longer than its year",
        "category": "space",
        "hook": "Did you know a day on Venus lasts longer than its year?",
        "fact": "Venus takes about 243 Earth days to rotate once, but only about 225 Earth days to orbit the Sun.",
        "twist": "So on Venus, one day is longer than one year.",
        "source_urls": [
            "https://science.nasa.gov/venus/venus-facts/"
        ]
    },

    {
        "trend_topic": "ocean",
        "topic": "Much of Earth's ocean remains unexplored",
        "category": "science",
        "hook": "We still know surprisingly little about Earth's deep ocean.",
        "fact": "The deep ocean is difficult to study because it is dark, cold and under enormous pressure.",
        "twist": "Earth still has huge underwater mysteries.",
        "source_urls": [
            "https://oceanservice.noaa.gov/facts/exploration.html"
        ]
    },

    {
        "trend_topic": "animal",
        "topic": "Octopuses have three hearts",
        "category": "animal facts",
        "hook": "An octopus has three hearts. Here's why that's strange.",
        "fact": "Two hearts pump blood toward the gills, while a third pumps blood around the rest of the body.",
        "twist": "Their circulation is seriously unusual.",
        "source_urls": [
            "https://oceanservice.noaa.gov/facts/octopus.html"
        ]
    },

    {
        "trend_topic": "mars",
        "topic": "Mars has the largest volcano in the solar system",
        "category": "space",
        "hook": "Mars has a volcano far bigger than Earth's tallest mountains.",
        "fact": "Olympus Mons on Mars is the largest known volcano in the solar system, rising roughly 22 kilometers above the surrounding plains.",
        "twist": "Mars has a truly gigantic volcano.",
        "source_urls": [
            "https://science.nasa.gov/mars/facts/"
        ]
    },

    {
        "trend_topic": "brain",
        "topic": "The human brain uses a lot of energy",
        "category": "science",
        "hook": "Your brain is small, but it has a huge energy bill.",
        "fact": "The adult human brain is only a small fraction of body mass, yet it uses roughly 20 percent of the body's resting energy.",
        "twist": "Small organ. Huge energy demand.",
        "source_urls": [
            "https://www.ncbi.nlm.nih.gov/books/NBK279388/"
        ]
    }
]


# ==========================================================
# GOOGLE TRENDS
# ==========================================================

def get_google_trends():

    url = "https://trends.google.com/trending/rss?geo=IN"

    try:

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=15
        ) as response:

            root = ET.fromstring(
                response.read()
            )

        trends = []
        seen = set()

        for item in root.findall(".//item"):

            title = item.find("title")

            if title is None:
                continue

            if not title.text:
                continue

            topic = title.text.strip()

            key = topic.lower()

            if key in seen:
                continue

            seen.add(key)

            trends.append(topic)

        return trends[:20]

    except Exception as error:

        print(
            "Google Trends unavailable:",
            repr(error)
        )

        return []


# ==========================================================
# FALLBACK
# ==========================================================

def get_fallback(trends):

    trend_text = " ".join(
        trends
    ).lower()

    ranked = []

    for item in FALLBACK_FACTS:

        score = 0

        for word in item[
            "trend_topic"
        ].lower().split():

            if word in trend_text:

                score += 1

        ranked.append(
            (
                score,
                item
            )
        )

    ranked.sort(
        key=lambda x: x[0],
        reverse=True
    )

    return dict(
        ranked[0][1]
    )


# ==========================================================
# CLEAN GEMINI JSON
# ==========================================================

def clean_json(text):

    text = text.strip()

    if text.startswith(
        "```json"
    ):

        text = text[7:]

    elif text.startswith(
        "```"
    ):

        text = text[3:]

    if text.endswith(
        "```"
    ):

        text = text[:-3]

    return json.loads(
        text.strip()
    )


# ==========================================================
# GEMINI CONTENT
# ==========================================================

def generate_content(trends):

    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    use_gemini = os.environ.get(
        "USE_GEMINI",
        "true"
    ).lower() == "true"

    if not api_key:

        print(
            "Gemini API key missing."
        )

        print(
            "Using verified fallback."
        )

        return get_fallback(
            trends
        )

    if not use_gemini:

        print(
            "Gemini disabled."
        )

        return get_fallback(
            trends
        )

    model = os.environ.get(
        "GEMINI_MODEL",
        "gemini-2.5-flash-lite"
    )

    trend_text = "\n".join(
        f"- {x}"
        for x in trends
    )

    if not trend_text:

        trend_text = (
            "- No live trend data"
        )


    prompt = f"""
You are the viral short-form fact editor
for a YouTube channel called FACTVERSE.

Current India trending searches:

{trend_text}

Create ONE highly engaging 15-second
YouTube Short.

Choose a topic that can attract curiosity,
but NEVER invent facts.

FACT RULES:

- Every factual claim must be accurate.
- Never invent statistics.
- Never present rumors as facts.
- Avoid fake mysteries.
- Prefer NASA, NOAA, universities,
  museums, government and scientific sources.
- No politics.
- No medical advice.
- No dangerous instructions.
- No graphic content.

RETENTION STRUCTURE:

0-2 seconds:
POWERFUL curiosity hook.

2-6 seconds:
Reveal the fact.

6-11 seconds:
Simple explanation.

11-14 seconds:
Surprising twist.

14-15 seconds:
Loop-friendly ending.

VOICE STYLE:

Natural spoken English.
Short sentences.
Easy pronunciation.
No greeting.
No filler.
No robotic wording.

SEO:

Create:
- Clickable truthful title
- Natural description
- 8-12 keywords
- 4-7 hashtags

Return ONLY valid JSON:

{{
  "trend_topic": "...",
  "topic": "...",
  "category": "...",
  "hook": "...",
  "fact": "...",
  "twist": "...",
  "title": "...",
  "description": "...",
  "keywords": [],
  "hashtags": [],
  "source_urls": []
}}
"""


    try:

        client = genai.Client(
            api_key=api_key
        )

        # ONE Gemini request only
        response = client.models.generate_content(

            model=model,

            contents=prompt,

            config=types.GenerateContentConfig(

                response_mime_type="application/json",

                max_output_tokens=1400
            )
        )

        data = clean_json(
            response.text
        )

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

                raise ValueError(
                    f"Missing field: {field}"
                )

        print(
            "Gemini generation SUCCESS"
        )

        return data


    except Exception as error:

        print(
            "Gemini unavailable:"
        )

        print(
            repr(error)
        )

        print(
            "Using verified fallback."
        )

        return get_fallback(
            trends
        )


# ==========================================================
# METADATA
# ==========================================================

def save_metadata(
    data,
    trends
):

    data["channel"] = "FACTVERSE"

    data["duration"] = DURATION

    data["generated_at"] = (
        time.strftime(
            "%Y-%m-%d %H:%M:%S UTC",
            time.gmtime()
        )
    )

    data[
        "live_trends_checked"
    ] = trends[:20]

    if not data.get(
        "title"
    ):

        data["title"] = (
            f"{data['topic']} 🤯 "
            f"| Did You Know? #Shorts"
        )

    if not data.get(
        "description"
    ):

        data["description"] = (
            f"Discover the truth about "
            f"{data['topic']} in this quick "
            f"FACTVERSE Short. Amazing facts, "
            f"science, mysteries and discoveries."
        )

    if not data.get(
        "keywords"
    ):

        data["keywords"] = [
            "facts",
            "did you know",
            "amazing facts",
            "interesting facts",
            "science facts",
            "mystery facts",
            "shorts",
            "factverse"
        ]

    if not data.get(
        "hashtags"
    ):

        data["hashtags"] = [
            "#facts",
            "#didyouknow",
            "#amazingfacts",
            "#science",
            "#shorts",
            "#factverse"
        ]

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


# ==========================================================
# FONT
# ==========================================================

FONT_BOLD = (
    "/usr/share/fonts/truetype/"
    "dejavu/DejaVuSans-Bold.ttf"
)

FONT_REGULAR = (
    "/usr/share/fonts/truetype/"
    "dejavu/DejaVuSans.ttf"
)


def get_font(
    path,
    size
):

    return ImageFont.truetype(
        path,
        size
    )


# ==========================================================
# TEXT WRAPPING
# ==========================================================

def wrap_text(
    draw,
    text,
    font,
    max_width
):

    words = text.split()

    lines = []

    current = ""

    for word in words:

        test = (
            f"{current} {word}"
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
            box[2]
            - box[0]
        )

        x = (
            WIDTH
            - width
        ) // 2

        draw.text(
            (
                x + 5,
                y + 6
            ),
            line,
            font=font,
            fill=(0, 0, 0)
        )

        draw.text(
            (
                x,
                y
            ),
            line,
            font=font,
            fill=(245, 245, 250)
        )

        y += spacing


# ==========================================================
# RENDER VIDEO
# ==========================================================

def render_video(data):

    font_hook = get_font(
        FONT_BOLD,
        72
    )

    font_fact = get_font(
        FONT_BOLD,
        55
    )

    font_twist = get_font(
        FONT_BOLD,
        62
    )

    font_brand = get_font(
        FONT_BOLD,
        36
    )

    font_small = get_font(
        FONT_REGULAR,
        30
    )


    dummy = Image.new(
        "RGB",
        (
            WIDTH,
            HEIGHT
        )
    )

    draw = ImageDraw.Draw(
        dummy
    )


    hook_lines = wrap_text(
        draw,
        data["hook"],
        font_hook,
        850
    )

    fact_lines = wrap_text(
        draw,
        data["fact"],
        font_fact,
        850
    )

    twist_lines = wrap_text(
        draw,
        data["twist"],
        font_twist,
        850
    )


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


    total_frames = (
        FPS * DURATION
    )


    print(
        "Rendering FACTVERSE video..."
    )


    for frame_number in range(
        total_frames
    ):

        image = Image.new(
            "RGB",
            (
                WIDTH,
                HEIGHT
            ),
            (8, 10, 25)
        )

        draw = ImageDraw.Draw(
            image
        )


        # Animated stars

        for x, y, radius in stars:

            yy = int(
                (
                    y
                    + frame_number
                    * 0.45
                )
                % HEIGHT
            )

            draw.ellipse(
                (
                    x - radius,
                    yy - radius,
                    x + radius,
                    yy + radius
                ),
                fill=(
                    120,
                    125,
                    155
                )
            )


        # BRAND

        brand = "FACTVERSE"

        box = draw.textbbox(
            (0, 0),
            brand,
            font=font_brand
        )

        brand_width = (
            box[2]
            - box[0]
        )

        draw.text(
            (
                (
                    WIDTH
                    - brand_width
                ) // 2,
                110
            ),
            brand,
            font=font_brand,
            fill=(
                245,
                200,
                80
            )
        )


        # LABEL

        label = "DID YOU KNOW?"

        box = draw.textbbox(
            (0, 0),
            label,
            font=font_small
        )

        label_width = (
            box[2]
            - box[0]
        )

        draw.text(
            (
                (
                    WIDTH
                    - label_width
                ) // 2,
                440
            ),
            label,
            font=font_small,
            fill=(
                180,
                185,
                205
            )
        )


        # HOOK

        if (
            frame_number
            < FPS * 4
        ):

            draw_centered(
                draw,
                hook_lines,
                font_hook,
                850,
                100
            )


        # FACT

        elif (
            frame_number
            < FPS * 11
        ):

            draw_centered(
                draw,
                fact_lines,
                font_fact,
                900,
                84
            )


        # TWIST

        else:

            draw_centered(
                draw,
                twist_lines,
                font_twist,
                850,
                88
            )

            follow = (
                "FOLLOW FOR MORE"
            )

            box = draw.textbbox(
                (0, 0),
                follow,
                font=font_small
            )

            follow_width = (
                box[2]
                - box[0]
            )

            draw.text(
                (
                    (
                        WIDTH
                        - follow_width
                    ) // 2,
                    1210
                ),
                follow,
                font=font_small,
                fill=(
                    180,
                    185,
                    205
                )
            )


        # PROGRESS BAR

        progress = int(
            WIDTH
            * (
                frame_number + 1
            )
            / total_frames
        )

        draw.rectangle(
            (
                0,
                HEIGHT - 15,
                progress,
                HEIGHT
            ),
            fill=(
                245,
                200,
                80
            )
        )


        image.save(
            os.path.join(
                FRAMES,
                f"frame_{frame_number:05d}.png"
            )
        )


    # ======================================================
    # FFMPEG
    # ======================================================

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
# MAIN
# ==========================================================

if __name__ == "__main__":

    print(
        "======================================"
    )

    print(
        "FACTVERSE 3.0"
    )

    print(
        "LOW QUOTA + FALLBACK MODE"
    )

    print(
        "======================================"
    )


    trends = get_google_trends()

    print(
        "Trending topics found:",
        len(trends)
    )


    data = generate_content(
        trends
    )


    save_metadata(
        data,
        trends
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
        "Sources:",
        data.get(
            "source_urls",
            []
        )
    )


    render_video(
        data
    )


    print(
        "======================================"
    )

    print(
        "FACTVERSE VIDEO GENERATED"
    )

    print(
        "Video:",
        VIDEO
    )

    print(
        "Metadata:",
        METADATA
    )

    print(
     
