import json
import os
from pathlib import Path

from gradio_client import Client

OUTPUT = Path("output")
CHOICE = OUTPUT / "free_avatar_choice.json"
TOKEN = os.getenv("HF_TOKEN_2") or os.getenv("HF_TOKEN") or None

# Priority is deliberately conservative: only public ZeroGPU Spaces with verified
# image+audio -> video implementations are candidates. No generation is done here.
CANDIDATES = [
    {
        "name": "LongCat-Video-Avatar-1.5",
        "space": "victor/LongCat-Video-Avatar-1.5",
        "priority": 1,
    },
    {
        "name": "EchoMimic",
        "space": "fffiloni/EchoMimic",
        "priority": 2,
    },
]


def endpoint_is_avatar(endpoint):
    text = json.dumps(endpoint, ensure_ascii=False).lower()
    has_image = any(x in text for x in ("image", "reference image", "portrait", "ref_img"))
    has_audio = any(x in text for x in ("audio", "driving audio", "input audio"))
    has_video = any(x in text for x in ("video", "output_video", "output video"))
    return has_image and has_audio and has_video


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
                    "reason": "verified image+audio->video endpoint",
                }
                CHOICE.write_text(json.dumps(choice, indent=2), encoding="utf-8")
                print(f"\nSELECTED: {choice['name']} ({choice['space']}) {choice['api_name']}", flush=True)
                print("Fallback is preflight-based: only ONE model will be generated.", flush=True)
                return
            print("  SKIP: no compatible named endpoint", flush=True)
        except Exception as exc:
            print(f"  SKIP: {type(exc).__name__}: {exc}", flush=True)

    raise SystemExit("NO_FREE_AVATAR_CANDIDATE: all zero-cost candidates failed preflight")


if __name__ == "__main__":
    main()
