import json
import os
import sys
import urllib.error
import urllib.request

MODEL = "wan-video/wan-2.2-s2v"
URL = f"https://api.replicate.com/v1/models/{MODEL}"


def main():
    token = os.getenv("REPLICATE_API_TOKEN", "").strip()
    print("========================================")
    print("FACTVERSE REPLICATE WAN 2.2 S2V PREFLIGHT")
    print("========================================")
    print("NO generation will be requested.")

    if not token:
        raise SystemExit("REPLICATE_API_TOKEN is missing")

    req = urllib.request.Request(
        URL,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status != 200:
                raise SystemExit(f"Replicate model lookup failed: HTTP {response.status}")
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Replicate model lookup failed: HTTP {exc.code}: {exc.reason}")
    except Exception as exc:
        raise SystemExit(f"Replicate model lookup failed: {type(exc).__name__}: {exc}")

    latest = data.get("latest_version") or {}
    version_id = latest.get("id")
    schema = latest.get("openapi_schema") or {}
    inputs = ((schema.get("components") or {}).get("schemas") or {}).get("Input", {}).get("properties", {})

    print(f"Model: {data.get('owner')}/{data.get('name')}")
    print(f"Latest version: {version_id or 'not exposed'}")
    print(f"Official/visibility: {data.get('visibility', 'unknown')}")
    print("Input fields:", ", ".join(sorted(inputs)) if inputs else "schema not exposed")

    if not version_id:
        raise SystemExit("PREFLIGHT FAILED: Replicate returned no latest model version")
    required = {"image", "audio"}
    if inputs and not required.issubset(inputs):
        raise SystemExit(f"PREFLIGHT FAILED: expected image+audio inputs, got {sorted(inputs)}")

    print("\nREPLICATE S2V PREFLIGHT PASSED")
    print("The model endpoint is reachable and exposes the expected S2V model.")
    print("No prediction/generation was submitted.")


if __name__ == "__main__":
    main()
