import os

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEO_PATH = os.path.join(ROOT, "output", "factverse.mp4")
METADATA_PATH = os.path.join(ROOT, "output", "metadata.json")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_URI = "https://oauth2.googleapis.com/token"


def get_credentials():
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    missing = [
        name
        for name, value in {
            "YOUTUBE_CLIENT_ID": client_id,
            "YOUTUBE_CLIENT_SECRET": client_secret,
            "YOUTUBE_REFRESH_TOKEN": refresh_token,
        }.items()
        if not value
    ]

    if missing:
        raise RuntimeError(
            "Missing YouTube OAuth GitHub Secrets: " + ", ".join(missing)
        )

    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )


def load_metadata():
    if not os.path.exists(METADATA_PATH):
        raise FileNotFoundError(f"Metadata not found: {METADATA_PATH}")

    with open(METADATA_PATH, "r", encoding="utf-8") as file:
        return __import__("json").load(file)


def upload_video():
    print("\n======================================")
    print("       FACTVERSE YOUTUBE UPLOAD")
    print("======================================\n")

    if not os.path.exists(VIDEO_PATH):
        raise FileNotFoundError(f"Video not found: {VIDEO_PATH}")

    metadata = load_metadata()

    title = metadata.get("title", "Amazing Facts You Didn't Know! #Shorts")[:100]
    description = metadata.get(
        "description", "Discover fascinating facts with FACTVERSE."
    )
    keywords = metadata.get(
        "keywords",
        [
            "facts", "did you know", "amazing facts", "interesting facts",
            "mystery facts", "science facts", "shorts", "factverse"
        ],
    )
    hashtags = metadata.get(
        "hashtags",
        ["#facts", "#didyouknow", "#amazingfacts", "#mystery", "#shorts", "#factverse"],
    )

    hashtag_text = " ".join(hashtags)
    if hashtag_text:
        description += "\n\n" + hashtag_text

    credentials = get_credentials()
    youtube = build("youtube", "v3", credentials=credentials)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": keywords,
            "categoryId": "24",
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": os.environ.get("YOUTUBE_PRIVACY_STATUS", "public"),
            "selfDeclaredMadeForKids": False,
        },
    }

    print("Title:", title)
    print("Privacy:", body["status"]["privacyStatus"])

    media = MediaFileUpload(VIDEO_PATH, mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload progress: {int(status.progress() * 100)}%")

    video_id = response.get("id")
    if not video_id:
        raise RuntimeError("YouTube upload completed but no video ID was returned.")

    print("\n======================================")
    print("    FACTVERSE UPLOAD SUCCESS 🎉")
    print("======================================")
    print("Video ID:", video_id)
    print("YouTube URL:", f"https://www.youtube.com/watch?v={video_id}")
    print("======================================")


if __name__ == "__main__":
    upload_video()
