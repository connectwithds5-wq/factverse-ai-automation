"""Run the existing FACTVERSE generator with the latest AI strategy."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "src" / "factverse_generate.py"
STRATEGY = ROOT / "data" / "strategy.json"


def load_strategy():
    if not STRATEGY.exists():
        print("FACTVERSE STRATEGY: no strategy.json; using normal generator")
        return {}
    try:
        value = json.loads(STRATEGY.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception as exc:
        print(f"FACTVERSE STRATEGY: invalid strategy.json; using normal generator ({exc})")
        return {}


def main():
    strategy = load_strategy()
    next_video = strategy.get("next_video") if isinstance(strategy.get("next_video"), dict) else {}

    recommended_duration = next_video.get("duration_seconds")
    if recommended_duration is not None:
        print(
            f"FACTVERSE STRATEGY: AI recommended duration={recommended_duration}s; "
            "renderer remains fixed at 15s"
        )

    category = str(next_video.get("category") or "").strip()

    source = GENERATOR.read_text(encoding="utf-8")

    # The existing generator is deliberately kept intact. We adapt its
    # category and prompt at runtime so the proven rendering/fallback code
    # continues to be used.
    target = "category = random.choice(categories)"
    if category:
        if target not in source:
            raise RuntimeError("FACTVERSE strategy hook not found: category selector")
        source = source.replace(target, f"category = {category!r}", 1)

    strategy_context = {
        "category": category,
        "hook_style": next_video.get("hook_style", ""),
        "concept": next_video.get("concept", ""),
        "opening_direction": next_video.get("opening_direction", ""),
        "twist_direction": next_video.get("twist_direction", ""),
        "experiment": strategy.get("experiment", ""),
    }
    context_json = json.dumps(strategy_context, ensure_ascii=False, indent=2)

    prompt_marker = "Create ONE highly engaging YouTube Short for the category:\n\n{category}"
    if category:
        if prompt_marker not in source:
            raise RuntimeError("FACTVERSE strategy hook not found: prompt category block")
        prompt_replacement = (
            "Create ONE highly engaging YouTube Short for the category:\n\n{category}\n\n"
            "AI GROWTH STRATEGY (use this as the creative decision input):\n\n"
            "{strategy_context_text}\n\n"
            "Use the strategy to guide the hook, concept, opening and twist. "
            "Create a fresh fact, not a duplicate of a previous video."
        )
        source = source.replace(prompt_marker, prompt_replacement, 1)

    metadata_marker = 'data["category"] = category\ndata["model"] = used_model'
    if category:
        if metadata_marker not in source:
            raise RuntimeError("FACTVERSE strategy hook not found: metadata block")
        metadata_replacement = (
            'data["category"] = category\n'
            'data["strategy_used"] = strategy_context\n'
            'data["model"] = used_model'
        )
        source = source.replace(metadata_marker, metadata_replacement, 1)

    globals_for_generator = {
        "__name__": "__main__",
        "strategy_context": strategy_context,
        "strategy_context_text": context_json,
    }

    print("====================================")
    print("FACTVERSE AI STRATEGY ENABLED")
    print("Category:", category or "generator default")
    print("Concept:", next_video.get("concept", "") or "none")
    print("====================================")

    exec(compile(source, str(GENERATOR), "exec"), globals_for_generator)


if __name__ == "__main__":
    main()
