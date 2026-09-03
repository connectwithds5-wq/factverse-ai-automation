import os
import json

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


# ==========================================================
# PATHS
# ==========================================================

ROOT = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

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


# ==========================================================
# YOUTUBE SETTINGS
# ==========================================================

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload"
]

TOKEN_URI = "https://oauth2.googleapis.com/token"


# ==========================================================
# LOAD YOUTUBE CREDENTIALS
# ==========================================================

def get_credentials():

    raw = os.environ.get(
        "YOUTUBE_OAUTH_JSON"
    )

    if not raw:
        raise RuntimeError(
            "YOUTUBE_OAUTH_JSON GitHub Secret is missing."
        )

    try:

        data = json.loads(raw)

    except json.JSONDecodeError as e:

        raise RuntimeError(
            f"YOUTUBE_OAUTH_JSON is not valid JSON: {e}"
        )


    required = [
        "client_id",
        "client_secret",
        "refresh_token"
    ]

    for field in required:

        if not data.get(field):

            raise RuntimeError(
                f"YOUTUBE_OAUTH_JSON missing: {field}"
            )


    credentials = Credentials(

        token=None,

        refresh_token=data["refresh_token"],

        token_uri=TOKEN_URI,

        client_id=data["client_id"],

        client_secret=data["client_secret"],

        scopes=SCOPES

    )

    return credentials


# ==========================================================
# LOAD METADATA
# ==========================================================

def load_metadata():

    if not os.path.exists(
        METADATA_PATH
    ):

        raise FileNotFoundError(
            f"Metadata not found: {METADATA_PATH}"
        )


    with open(
        METADATA_PATH,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


# ==========================================================
# UPLOAD VIDEO
# ==========================================================

def upload_video():

    print("")
    print("======================================")
    print("       FACTVERSE YOUTUBE UPLOAD")
    print("======================================")
    print("")


    # ------------------------------------------------------
    # CHECK VIDEO
    # ------------------------------------------------------

    if not os.path.exists(
        VIDEO_PATH
    ):

        raise FileNotFoundError(
            f"Video not found: {VIDEO_PATH}"
        )


    # ------------------------------------------------------
    # LOAD METADATA
    # ------------------------------------------------------

    metadata = load_metadata()


    title = metadata.get(
        "title",
        "Amazing Facts You Didn't Know! #Shorts"
    )


    description = metadata.get(
        "description",
        "Discover fascinating facts with FACTVERSE."
    )


    keywords = metadata.get(
        "keywords",
        [
            "facts",
            "did you know",
            "amazing facts",
            "interesting facts",
            "mystery facts",
            "science facts",
            "shorts",
            "factverse"
        ]
    )


    hashtags = metadata.get(
        "hashtags",
        [
            "#facts",
            "#didyouknow",
            "#amazingfacts",
            "#mystery",
            "#shorts",
            "#factverse"
        ]
    )


    # ------------------------------------------------------
    # ADD HASHTAGS TO DESCRIPTION
    # ------------------------------------------------------

    hashtag_text = " ".join(
        hashtags
    )


    if hashtag_text:

        description = (
            description
            + "\n\n"
            + hashtag_text
        )


    # ------------------------------------------------------
    # LIMIT TITLE
    # ------------------------------------------------------

    title = title[:100]


    # ------------------------------------------------------
    # CREATE CREDENTIALS
    # ------------------------------------------------------

    credentials = get_credentials()


    # ------------------------------------------------------
    # CREATE YOUTUBE CLIENT
    # ------------------------------------------------------

    youtube = build(
        "youtube",
        "v3",
        credentials=credentials
    )


    # ------------------------------------------------------
    # YOUTUBE VIDEO DATA
    # ------------------------------------------------------

    body = {

        "snippet": {

            "title": title,

            "description": description,

            "tags": keywords,

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


    print(
        "Title:",
        title
    )

    print(
        "Privacy:",
        body["status"]["privacyStatus"]
    )

    print("")


    # ------------------------------------------------------
    # MEDIA UPLOAD
    # ------------------------------------------------------

    media = MediaFileUpload(

        VIDEO_PATH,

        mimetype="video/mp4",

        resumable=True

    )


    # ------------------------------------------------------
    # CREATE UPLOAD REQUEST
    # ------------------------------------------------------

    request = youtube.videos().insert(

        part="snippet,status",

        body=body,

        media_body=media

    )


    # ------------------------------------------------------
    # UPLOAD
    # ------------------------------------------------------

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


    # ------------------------------------------------------
    # SUCCESS
    # ------------------------------------------------------

    video_id = response.get(
        "id"
    )


    if not video_id:

        raise RuntimeError(
            "YouTube upload completed but no video ID was returned."
        )


    print("")
    print("======================================")
    print("    FACTVERSE UPLOAD SUCCESS 🎉")
    print("======================================")
    print("")
    print(
        "Video ID:",
        video_id
    )

    print(
        "YouTube URL:",
        f"https://www.youtube.com/watch?v={video_id}"
    )

    print("")
    print("======================================")


# ==========================================================
# MAIN
# ==========================================================

if __name__ == "__main__":

    upload_video()
