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


# ==========================================================
# FACTVERSE 3.0
# ==========================================================

ROOT = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

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
# Used automatically if Gemini quota/API fails
# ==========================================================

FALLBACK_FACTS = [

    {
        "trend_topic": "space",
        "topic": "A day on Venus is longer than its year",
        "category": "Space Facts",
        "hook": "Did you know a day on Venus lasts longer than its year?",
        "fact": (
            "Venus takes about 243 Earth days to rotate once, "
            "but only about 225 Earth days to orbit the Sun."
        ),
        "twist": (
            "So on Venus, one day is actually longer than one year."
        ),
        "source_urls": [
            "https://science.nasa.gov/venus/venus-facts/"
        ]
    },

    {
        "trend_topic": "ocean",
        "topic": "Earth's deep ocean remains difficult to explore",
        "category": "Ocean Facts",
        "hook": "We still know surprisingly little about the deep ocean.",
        "fact": (
            "The deep ocean is difficult to study because it is dark, "
            "cold and under enormous pressure."
        ),
        "twist": (
            "Some of Earth's biggest mysteries are underwater."
        ),
        "source_urls": [
            "https://oceanservice.noaa.gov/facts/exploration.html"
        ]
    },

    {
        "trend_topic": "animal",
        "topic": "Octopuses have three hearts",
        "category": "Animal Facts",
        "hook": "An octopus has three hearts. Here's why.",
        "fact": (
            "Two hearts pump blood toward the gills, "
            "while a third pumps blood around the body."
        ),
        "twist": (
            "Their circulatory system is seriously unusual."
        ),
        "source_urls": [
            "https://oceanservice.noaa.gov/facts/octopus.html"
        ]
    },

    {
        "trend_topic": "mars",
        "topic": "Mars has the largest volcano in the solar system",
        "category": "Space Facts",
        "hook": "Mars has a volcano bigger than Earth's tallest mountains.",
        "fact": (
            "Olympus Mons is the largest known volcano in the solar system, "
            "rising roughly 22 kilometers above the surrounding plains."
        ),
        "twist": (
            "Mars has a truly gigantic volcano."
        ),
        "source_urls": [
            "https://science.nasa.gov/mars/facts/"
        ]
    },

    {
        "trend_topic": "brain",
        "topic": "Your brain uses a surprising amount of energy",
        "category": "Science Facts",
        "hook": "Your brain is small, but its energy demand is huge.",
        "fact": (
            "The adult human brain is only a small fraction of body mass, "
            "yet it uses roughly 20 percent of the body's resting energy."
        ),
        "twist": (
            "Small organ. Huge energy demand."
        ),
        "source_urls": [
            "https://www.ncbi.nlm.nih.gov/books/NBK279388/"
        ]
    },

    {
        "trend_topic": "moon",
        "topic": "The Moon is slowly moving away from Earth",
        "category": "Space Facts",
        "hook": "The Moon is slowly drifting away from Earth.",
        "fact": (
            "The Moon is gradually moving away from Earth by about "
            "3.8 centimeters per year."
        ),
        "twist": (
            "Our Moon is slowly getting farther away."
        ),
        "source_urls": [
            "https://science.nasa.gov/moon/"
        ]
    }
]


# ==========================================================
# GOOGLE TRENDS INDIA
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

            xml_data = response.read()

        root = ET.fromstring(xml_data)

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

        print("Google Trends found:", len(trends))

        return trends[:20]

    except Exception as error:

        print(
            "Google Trends unavailable:",
            repr(error)
        )

        return []


# ==========================================================
# FALLBACK SELECTION
# ==========================================================

def get_fallback(trends):

    trend_text = " ".join(
        trends
    ).lower()

    scored = []

    for item in FALLBACK_FACTS:

        score = 0

        keywords = (
            item["trend_topic"]
            .lower()
            .split()
        )

        for word in keywords:

            if word in trend_text:
                score += 1

        scored.append(
            (
                score,
                item
            )
        )

    scored.sort(
        key=lambda x: x[0],
        reverse=True
    )

    # If no trend matches, choose randomly
    if scored[0][0] == 0:

        return dict(
            random.choice(FALLBACK_FACTS)
        )

    return dict(
        scored[0][1]
    )


# ==========================================================
# CLEAN GEMINI JSON
# ==========================================================

def clean_json(text):

    text = text.strip()

    if text.startswith("```json"):

        text = text[7:]

    elif text.startswith("```"):

        text = text[3:]

    if text.endswith("```"):

        text = text[:-3]

    return json.loads(
        text.strip()
    )


# ==========================================================
# GEMINI CONTENT GENERATION
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

        print("Gemini API key missing.")
        print("Using verified fallback.")

        return get_fallback(trends)

    if not use_gemini:

        print("Gemini disabled.")
        print("Using verified fallback.")

        return get_fallback(trends)

    model = os.environ.get(
        "GEMINI_MODEL",
        "gemini-2.5-flash-lite"
    )

    trend_text = "\n".join(
        f"- {trend}"
        for trend in trends
    )

    if not trend_text:

        trend_text = "- No live trend data available"

    prompt = f"""
You are the viral short-form fact editor
for a YouTube Shorts channel called FACTVERSE.

LIVE INDIA TRENDING SEARCHES:

{trend_text}

Create ONE highly engaging 15-second
YouTube Short.

Choose a topic connected to current interest
when possible, but factual accuracy is more
important than trend matching.

STRICT FACT RULES:

- Never invent facts.
- Never invent statistics.
- Never present rumors as facts.
- Never create fake mysteries.
- Prefer NASA, NOAA, universities, museums,
  government and scientific sources.
- Avoid politics.
- Avoid medical advice.
- Avoid dangerous instructions.
- Avoid graphic content.

RETENTION STRUCTURE:

0-2 seconds:
Create an extremely strong curiosity hook.

2-7 seconds:
Reveal the main fact.

7-11 seconds:
Explain it simply.

11-14 seconds:
Give a surprising twist.

14-15 seconds:
End naturally so the video can loop.

VOICE STYLE:

Natural spoken English.
Very clear pronunciation.
Short spoken sentences.
No greeting.
No filler.
No robotic wording.

SEO:

Create:
- Clickable truthful YouTube Shorts title
- SEO optimized natural description
- 8-12 keywords
- 5-7 hashtags

Return ONLY valid JSON.

JSON FORMAT:

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

        print("Generating verified FACTVERSE content...")

        # ONE Gemini request
        response = client.models.generate_content(

            model=model,

            contents=prompt,

            config=types.GenerateContentConfig(

                response_mime_type="application/json",

                max_output_tokens=1400
            )
        )

        if not response.text:

            raise RuntimeError(
                "Gemini returned empty response."
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
                    f"Missing Gemini field: {field}"
                )

        print("Gemini generation SUCCESS.")

        return data

    except Exception as error:

        print("Gemini unavailable:")
        print(repr(error))
        print("Using verified fallback.")

        return get_fallback(trends)


# ==========================================================
# METADATA
# ==========================================================

def save_metadata(data, trends):

    data["channel"] = "FACTVERSE"

    data["duration"] = DURATION

    data["generated_at"] = time.strftime(
        "%Y-%m-%d %H:%M:%S UTC",
        time.gmtime()
    )

    data["live_trends_checked"] = trends[:20]

    if not data.get("title"):

        data["title"] = (
            f"{data['topic']} | "
            f"Did You Know? #Shorts"
        )

    if not data.get("description"):

        data["description"] = (
            f"Discover the truth about "
            f"{data['topic']} in this quick "
            f"FACTVERSE Short. "
            f"Follow for amazing facts, "
            f"science, mysteries and discoveries."
        )

    if not data.get("keywords"):

        data["keywords"] = [
            "facts",
            "did you know",
            "amazing facts",
            "interesting facts",
            "science facts",
            "mystery facts",
            "space facts",
            "animal facts",
            "viral facts",
            "youtube shorts",
            "shorts",
            "factverse"
        ]

    if not data.get("hashtags"):

        data["hashtags"] = [
            "#facts",
            "#didyouknow",
            "#amazingfacts",
            "#science",
            "#mystery",
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

    print("Metadata saved.")


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


def get_font(path, size):

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

        width = (
            box[2] - box[0]
        )

        if width <= max_width:

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
# CENTERED TEXT
# ==========================================================

def draw_centered(
    draw,
    lines,
    font,
    center_y,
    spacing
):

    total_height = (
        len(lines)
        * spacing
    )

    y = (
        center_y
        - total_height // 2
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
# CREATE FRAME
# ==========================================================

def create_frame(
    frame_number,
    data,
    hook_lines,
    fact_lines,
    twist_lines,
    stars,
    fonts
):

    font_hook = fonts["hook"]
    font_fact = fonts["fact"]
    font_twist = fonts["twist"]
    font_brand = fonts["brand"]
    font_small = fonts["small"]

    img = Image.new(
        "RGB",
        (
            WIDTH,
            HEIGHT
        ),
        (8, 10, 25)
    )

    draw = ImageDraw.Draw(img)

    # Animated stars
    for x, y, radius in stars:

        yy = int(
            (
                y
                + frame_number * 0.4
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
            fill=(120, 125, 155)
        )

    # Brand
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

    # Label
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

    # HOOK
    if frame_number < FPS * 4:

        draw_centered(
            draw,
            hook_lines,
            font_hook,
            850,
            105
        )

    # FACT
    elif frame_number < FPS * 11:

        draw_centered(
            draw,
            fact_lines,
            font_fact,
            900,
            82
        )

    # TWIST
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

    # Progress bar
    progress = int(
        WIDTH
        * (
            (frame_number + 1)
            / (FPS * DURATION)
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
# RENDER VIDEO
# ==========================================================

def render_video(data):

    fonts = {

        "hook": get_font(
            FONT_BOLD,
            72
        ),

        "fact": get_font(
            FONT_BOLD,
            55
        ),

        "twist": get_font(
            FONT_BOLD,
            62
        ),

        "brand": get_font(
            FONT_BOLD,
            36
        ),

        "small": get_font(
            FONT_REGULAR,
            30
        )
    }

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
        fonts["hook"],
        850
    )

    fact_lines = wrap_text(
        draw,
        data["fact"],
        fonts["fact"],
        850
    )

    twist_lines = wrap_text(
        draw,
        data["twist"],
        fonts["twist"],
        850
    )

    random.seed(
        sum(
            ord(char)
            for char in data["topic"]
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

        frame = create_frame(
            frame_number,
            data,
            hook_lines,
            fact_lines,
            twist_lines,
            stars,
            fonts
        )

        frame.save(
            os.path.join(
                FRAMES,
                f"frame_{frame_number:05d}.png"
            )
        )

    print(
        "Encoding MP4..."
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

    print(
        "Video rendering SUCCESS."
    )


# ==========================================================
# MAIN
# ==========================================================

def main():

    print("")
    print("====================================")
    print("FACTVERSE 3.0")
    print("====================================")

    trends = get_google_trends()

    print("")
    print("LIVE TREND TOPICS:")
    print(trends[:10])

    data = generate_content(
        trends
    )

    print("")
    print("SELECTED TOPIC:")
    print(data["topic"])

    print("")
    print("TITLE:")
    print(data["title"])

    save_metadata(
        data,
        trends
    )

    render_video(
        data
    )

    print("")
    print("====================================")
    print("FACTVERSE VIDEO GENERATED")
    print("====================================")
    print("Video:", VIDEO)
    print("Metadata:", METADATA)
    print("Topic:", data["topic"])
    print("====================================")


if __name__ == "__main__":

    main()
