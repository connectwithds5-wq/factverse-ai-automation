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
# Keep these as broad content lanes so the strategy engine can
# select the best-performing niche without changing the renderer.

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
    # New story-first Shorts lanes
    "cinematic animal survival stories",
    "horror and mystery micro stories",
    "cinematic historical stories",
    "geography and country mysteries",
    "what if geography and science scenarios",
    "AI micro drama and twist stories",
    "cars and luxury cinematic stories",
    "weird facts and curiosity stories",
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
Create a fact or original micro-story that makes viewers stop scrolling,
watch until the end, and want to comment/share.

VIDEO:
- Exactly 15 seconds
- English
- General audience
- Highly fascinating
- Natural spoken English
- Short sentences
- Strong curiosity gap
- Strong ending or twist
- No boring introduction
- Prefer story-first visual concepts over listicles

FACT QUALITY / STORY QUALITY:
- Facts must be accurate and defensible.
- Never invent real-world facts and present them as true.
- For fictional micro-stories, clearly make the narrative fictional in the
  metadata/context rather than fabricating real events.
- Build the opening around a visual contradiction, mystery, danger, surprise,
  or unanswered question.
"""
