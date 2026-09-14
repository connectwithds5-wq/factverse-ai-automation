import json
import os
from pathlib import Path

import requests
from gradio_client import Client

OUTPUT = Path("output")
CHOICE = OUTPUT / "free_avatar_choice.json"
TOKEN = os.getenv("HF_TOKEN_2") or os.getenv("HF_TOKEN") or None

# Free-tier-safe order. Candidates are checked for Space health before any
# generation. We deliberately exclude models that can reserve more GPU time
# than the current free-tier budget can reasonably support.
CANDIDATES = [
    {
        "name": "LTX23Sync",
        "space": "linoyts/LTX-2-3-sync",
        "priority": 1,
        "max_gpu_seconds": 100,
    },
    {
        "name": "EchoMimicV3",
        "space": "artificialguybr/EchoMimicV3-Demo",
        "priority": 2,
        "max_gpu_seconds": 120,
    },
]


def endpoint_is_avatar(endpoint):
    text = json.dumps(endpoint, ensure_ascii=False).lower()
    has_image = any(x in text for x in ("image", "reference image", "portrait", "source_image", "character reference"))
    has_audio = any(x in text for x in ("audio", "driving audio", "input audio", "driven_audio"))
    has_video = any(x in text for x in ("video", "output_video", "output video"))
    return has_image and has_audio and has_video


def space_state(space):
    """Zero-cost HF Space health check; never requests a GPU lease."""
    headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    r = requests.get(f"https://huggingface.co/api/spaces/{space}", headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()
    return str(data.get("runtime", {}).get("stage") or data.get("runtime", {}).get("stageName") or "UNKNOWN").upper()


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    print("==============================================")
    print("FACTVERSE FREE AVATAR ROUTER — ZERO-COST PREFLIGHT")
    print("==============================================")
    print("NO VIDEO GENERATION WILL BE REQUESTED.")

    for candidate in CANDIDATES:
        space = candidate["space"]
        print(f"\n[{candidate['priority']}] Checking {candidate['name']} -> {space}", flush=True)
        try:
            state = space_state(space)
            print(f"  HF SPACE STATE: {state}", flush=True)
            if state != "RUNNING":
                print("  SKIP: Space is not currently RUNNING", flush=True)
                continue

            client = Client(space, token=TOKEN) if TOKEN else Client(space)
            info = client.view_api(return_format="dict")
            endpoints = info.get("named_endpoints", {}) if isinstance(info, dict) else {}
            matches = []
            for api_name, details in endpoints.items():
                if endpoint_is_avatar(details):
                    matches.append(api_name)
                    print(f"  VERIFIED endpoint: {api_name}", flush=True)
                    print(f"  PARAMS: {details.get('parameters', [])}", flush=True)
            if matches:
                choice = {
                    **candidate,
                    "api_name": matches[0],
                    "space_state": state,
                    "reason": "verified RUNNING free image+audio->video endpoint",
                }
                CHOICE.write_text(json.dumps(choice, indent=2), encoding="utf-8")
                print(f"\nSELECTED: {choice['name']} ({choice['space']}) {choice['api_name']}", flush=True)
                print(f"GPU REQUEST CEILING: {choice['max_gpu_seconds']}s", flush=True)
                print("Fallback is preflight-based: only ONE model will be generated.", flush=True)
                return
            print("  SKIP: no compatible named endpoint", flush=True)
        except Exception as exc:
            print(f"  SKIP: {type(exc).__name__}: {exc}", flush=True)

    raise SystemExit("NO_FREE_AVATAR_CANDIDATE: all zero-cost candidates failed preflight")


if __name__ == "__main__":
    main()
