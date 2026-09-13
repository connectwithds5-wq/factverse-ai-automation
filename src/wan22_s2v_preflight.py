import os
import sys
from gradio_client import Client

CANDIDATES = [
    os.getenv("HF_S2V_SPACE", "mjinabq/Wan2.2-S2V"),
    "wavespeed/wan2.2-s2v",
    "Wan-AI/Wan2.2-S2V",
]


def flatten_api(info):
    if isinstance(info, dict):
        endpoints = info.get("named_endpoints") or info.get("named_endpoints_info") or {}
        if isinstance(endpoints, dict):
            return endpoints
    return {}


def main():
    token = os.getenv("HF_TOKEN_2") or os.getenv("HF_TOKEN") or None
    print("======================================")
    print("FACTVERSE WAN 2.2 S2V PRE-FLIGHT")
    print("======================================")
    print("No generation will be requested.")

    found = False
    for space in CANDIDATES:
        print(f"\n--- Inspecting {space} ---")
        try:
            client = Client(space, token=token) if token else Client(space)
            info = client.view_api(return_format="dict")
            endpoints = flatten_api(info)
            if not endpoints:
                print("No named endpoints returned.")
                continue
            for name, details in endpoints.items():
                print(f"ENDPOINT: {name}")
                print(f"  {details}")
                text = str(details).lower()
                if "audio" in text and ("image" in text or "ref" in text) and ("video" in text or "output" in text):
                    found = True
                    print("  -> Candidate audio+image video endpoint detected")
        except Exception as exc:
            print(f"UNAVAILABLE: {type(exc).__name__}: {exc}")

    if not found:
        raise SystemExit(
            "S2V PREFLIGHT FAILED: no reachable candidate exposed a verified audio+image video endpoint. "
            "No generation was attempted."
        )

    print("\nS2V PREFLIGHT PASSED: at least one candidate exposes an audio+image video endpoint.")
    print("Do not generate yet: the endpoint signature must be wired into the production script after inspection.")


if __name__ == "__main__":
    main()
