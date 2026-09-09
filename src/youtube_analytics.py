import json
import os
from datetime import datetime, timezone
from pathlib import Path

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "analytics_history.json"

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def load_oauth():
    raw = os.environ.get("YOUTUBE_OAUTH_JSON", "")
    if not raw:
        raise RuntimeError("YOUTUBE_OAUTH_JSON is missing")
    data = json.loads(raw)
    missing = [k for k in ("client_id", "client_secret", "refresh_token") if not data.get(k)]
    if missing:
        raise RuntimeError("YOUTUBE_OAUTH_JSON missing: " + ", ".join(missing))
    return Credentials(
        token=None,
        refresh_token=data["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        scopes=SCOPES,
    )


def load_history():
    if not OUT.exists():
        return []
    try:
        value = json.loads(OUT.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except Exception:
        return []


def main():
    youtube = build("youtube", "v3", credentials=load_oauth())
    channel = youtube.channels().list(part="contentDetails,snippet,statistics", mine=True).execute()
    items = channel.get("items", [])
    if not items:
        raise RuntimeError("No YouTube channel found for OAuth account")

    ch = items[0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    stats = ch.get("statistics", {})

    videos = []
    page = None
    for _ in range(3):
        resp = youtube.playlistItems().list(
            part="contentDetails,snippet", playlistId=uploads, maxResults=50, pageToken=page
        ).execute()
        videos.extend(resp.get("items", []))
        page = resp.get("nextPageToken")
        if not page or len(videos) >= 150:
            break

    ids = [x["contentDetails"]["videoId"] for x in videos if x.get("contentDetails", {}).get("videoId")]
    records = []
    for start in range(0, len(ids), 50):
        batch = ids[start:start + 50]
        resp = youtube.videos().list(part="snippet,statistics,contentDetails", id=",".join(batch)).execute()
        for item in resp.get("items", []):
            st = item.get("statistics", {})
            sn = item.get("snippet", {})
            cd = item.get("contentDetails", {})
            records.append({
                "video_id": item["id"],
                "title": sn.get("title", ""),
                "published_at": sn.get("publishedAt", ""),
                "views": int(st.get("viewCount", 0)),
                "likes": int(st.get("likeCount", 0)),
                "comments": int(st.get("commentCount", 0)),
                "duration": cd.get("duration", ""),
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

    history = load_history()
    history.extend(records)
    # Keep latest observation per video, while retaining collection history for learning.
    history = history[-1500:]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"FACTVERSE ANALYTICS: {len(records)} videos collected")
    print(f"Channel subscribers: {stats.get('subscriberCount', 'hidden')}")
    print(f"Channel views: {stats.get('viewCount', 0)}")
    print(f"Saved: {OUT}")


if __name__ == "__main__":
    main()
