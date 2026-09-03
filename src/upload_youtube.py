import os
import json
import subprocess

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VIDEO_PATH = os.path.join(
    ROOT,
    "output",
    "factverse.mp4"
)

METADATA_PATH = os.path.join(
    ROOT,
    "output",
    "metadata.json"
)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload"
]


def get_credentials():

    raw = os.environ.get("YOUTUBE_OAUTH_JSON")

    if not raw:
        raise RuntimeError(
            "YOUTUBE_OAUTH_JSON GitHub Secret is missing."
        )

    data = json.loads(raw)

    return Credentials(
        token=None,
        refresh_token=data["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        scopes=SCOPES
    )


def upload_video():

    if not os.path.exists(VIDEO_PATH):
        raise FileNotFoundError(
            f"Video not found: {VIDEO_PATH}"
        )

    if not os.path.exists(METADATA_PATH):
        raise FileNotFoundError(
            f"Metadata not found: {METADATA_PATH}"
        )

    with open(
        METADATA_PATH,
        "r",
        encoding="utf-8"
    ) as f:

        metadata = json.load(f)


    title = metadata.get(
        "title",
        "Amazing Fact | FACTVERSE #Shorts"
    )

    description = metadata.get(
        "description",
        "Discover amazing facts with FACTVERSE."
    )

    hashtags = metadata.get(
        "hashtags",
        [
            "#facts",
            "#didyouknow",
            "#shorts",
            "#factverse"
        ]
    )

    hashtag_text = " ".join(hashtags)

    description = (
        description
        + "\n\n"
        + hashtag_text
    )


    credentials = get_credentials()

    youtube = build(
        "youtube",
        "v3",
        credentials=credentials
    )


    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": metadata.get(
                "keywords",
                [
                    "facts",
                    "did you know",
                    "amazing facts",
                    "interesting facts",
                    "mystery facts",
                    "shorts",
                    "factverse"
                ]
            ],
            "categoryId": "24",
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en"
        },

        "status": {
            "privacyStatus": os.environ.get(
                "YOUTUBE_PRIVACY_STATUS",
                "public"
            ),
            "selfDeclaredMadeForKids": False
        }
    }


    print("====================================")
    print("UPLOADING FACTVERSE VIDEO")
    print("====================================")
    print("Title:", title)
    print("Privacy:", body["status"]["privacyStatus"])
    print("====================================")


    media = MediaFileUpload(
        VIDEO_PATH,
        mimetype="video/mp4",
        resumable=True
    )


    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )


    response = None

    while response is None:

        status, response = request.next_chunk()

        if status:

            progress = int(
                status.progress() * 100
            )

            print(
                f"Upload progress: {progress}%"
            )


    video_id = response["id"]

    print("====================================")
    print("FACTVERSE UPLOAD SUCCESS")
    print("====================================")
    print("Video ID:", video_id)
    print(
        "YouTube URL:",
        f"https://www.youtube.com/watch?v={video_id}"
    )
    print("====================================")


if __name__ == "__main__":

    upload_video()
