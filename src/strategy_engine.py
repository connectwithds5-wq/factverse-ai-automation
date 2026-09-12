import json
import os
from datetime import datetime, timezone
from pathlib import Path
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
ANALYTICS = ROOT / "data" / "analytics_history.json"
STRATEGY = ROOT / "data" / "strategy.json"
MODEL_CANDIDATES = [os.environ.get("GEMINI_MODEL", "gemini-3.6-flash"), "gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
MODEL_CANDIDATES = list(dict.fromkeys(MODEL_CANDIDATES))


def load():
    if not ANALYTICS.exists(): return []
    try:
        x = json.loads(ANALYTICS.read_text(encoding="utf-8"))
        return x if isinstance(x, list) else []
    except Exception: return []


def fallback(data):
    return {
        "confidence": "LOW" if len(data) < 10 else "MEDIUM",
        "data_points": len(data),
        "overall_summary": "FACTVERSE is still collecting baseline data. Test distinct fact categories, story formats and hooks before making strong conclusions.",
        "winning_patterns": [],
        "weak_patterns": [],
        "next_video": {
            "category": "mind blowing science facts",
            "hook_style": "unexpected question",
            "concept": "A surprising, well-established science fact with a curiosity-gap opening and a strong final reveal.",
            "opening_direction": "Start with the surprising result, not the explanation.",
            "twist_direction": "End with the detail that changes how viewers see the fact.",
            "duration_seconds": 15,
            "posting_window": "18:00 - 22:00 IST",
            "reason": "Use broad-interest science while the channel establishes a performance baseline."
        },
        "experiment": "Test a non-generic science hook against the previous category and compare views and engagement.",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "model_used": "deterministic-fallback"
    }


def main():
    data = load()
    if not data:
        result = fallback(data)
    else:
        prompt = f'''You are the senior growth strategist for FACTVERSE, an English YouTube Shorts channel about facts, mysteries, science, space, psychology, animals, history, technology, cinematic animal survival, horror/mystery micro-stories, geography, country mysteries, what-if scenarios, historical storytelling, AI micro-drama and cinematic cars/luxury.\n\nAnalyze these YouTube observations. They may contain repeated observations of the same video, so reason from latest performance and trends rather than counting duplicates as separate videos.\n\nDATA:\n{json.dumps(data[-120:], ensure_ascii=False)}\n\nReturn ONLY valid JSON with this schema:\n{{\n "confidence":"LOW/MEDIUM/HIGH", "data_points":0, "overall_summary":"",\n "winning_patterns":[{{"pattern":"","evidence":"","action":""}}],\n "weak_patterns":[{{"pattern":"","evidence":"","action":""}}],\n "next_video":{{"category":"","hook_style":"","concept":"","opening_direction":"","twist_direction":"","duration_seconds":15,"posting_window":"","reason":""}},\n "experiment":""\n}}\n\nRules: never claim a winner from tiny samples; prioritize retention-friendly curiosity, factual accuracy, originality, strong visual storytelling and category diversity; do not invent performance metrics; next_video must be actionable for the generator. For fictional micro-stories, never present fiction as a real event. Prefer the new story-first niches when they have a stronger fit with observed performance, but keep the existing high-performing categories available.''' 
        result = None
        key = os.environ.get("GEMINI_API_KEY")
        if key:
            client = genai.Client(api_key=key)
            for model in MODEL_CANDIDATES:
                try:
                    r = client.models.generate_content(model=model, contents=prompt, config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.4))
                    text = (r.text or "").strip()
                    start, end = text.find("{"), text.rfind("}")
                    if start >= 0 and end > start:
                        result = json.loads(text[start:end + 1])
                        result["model_used"] = model
                        break
                except Exception as e:
                    print(f"Strategy model failed: {model}: {str(e)[:300]}")
        if not result:
            result = fallback(data)

    result["data_points"] = len(data)
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    STRATEGY.parent.mkdir(parents=True, exist_ok=True)
    STRATEGY.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Saved: {STRATEGY}")


if __name__ == "__main__":
    main()
