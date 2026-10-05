import os
import time
import requests

from config import (
    INSTAGRAM_ACCESS_TOKEN,
    INSTAGRAM_BUSINESS_ACCOUNT_ID,
    META_GRAPH_VERSION,
)

GRAPH_BASE = f"https://graph.facebook.com/{META_GRAPH_VERSION}"


def _graph(path, token, method="POST", **kwargs):
    url = f"{GRAPH_BASE}/{path.lstrip('/')}"
    response = requests.request(
        method,
        url,
        params={"access_token": token},
        timeout=120,
        **kwargs,
    )
    try:
        data = response.json()
    except ValueError:
        data = {"raw": response.text[:4000]}

    if not response.ok or "error" in data:
        raise RuntimeError(
            f"Meta API error HTTP {response.status_code}: {data}"
        )
    return data


def _require_config():
    if not INSTAGRAM_BUSINESS_ACCOUNT_ID:
        raise ValueError("INSTAGRAM_BUSINESS_ACCOUNT_ID is missing.")
    if not INSTAGRAM_ACCESS_TOKEN:
        raise ValueError("INSTAGRAM_ACCESS_TOKEN is missing.")


def _validate_account():
    data = _graph(
        INSTAGRAM_BUSINESS_ACCOUNT_ID,
        INSTAGRAM_ACCESS_TOKEN,
        method="GET",
        params={"fields": "id,username"},
    )
    returned_id = str(data.get("id", ""))
    if returned_id != str(INSTAGRAM_BUSINESS_ACCOUNT_ID):
        raise RuntimeError(
            "Instagram account validation returned a different account ID. "
            f"Configured={INSTAGRAM_BUSINESS_ACCOUNT_ID}, returned={returned_id}"
        )
    print(f"✅ Instagram account validated: @{data.get('username', 'unknown')}")


def _wait_ig(container_id, timeout_seconds=900, poll_seconds=5):
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        data = _graph(
            container_id,
            INSTAGRAM_ACCESS_TOKEN,
            method="GET",
            params={"fields": "status_code,status"},
        )
        status = data.get("status_code") or data.get("status")
        print(f"⏳ Instagram processing status: {status}")

        if status in ("FINISHED", "PUBLISHED"):
            return data

        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(
                f"Instagram container failed: {data}"
            )

        time.sleep(poll_seconds)

    raise TimeoutError(
        f"Instagram media container {container_id} did not finish within "
        f"{timeout_seconds} seconds."
    )


def post_instagram(video_url, caption):
    """
    Publish one Reel using a publicly reachable HTTPS MP4 URL.

    This intentionally follows the working DIVINE_INDIA flow:
      1. Create REELS container with video_url.
      2. Poll until FINISHED.
      3. Publish the container.
    """
    _require_config()

    video_url = (video_url or "").strip()
    if not video_url.startswith("http"):
        raise ValueError(
            "Instagram requires a public HTTPS video URL."
        )

    print(f"📸 Instagram video URL: {video_url}")
    _validate_account()

    print("📦 Creating Instagram Reel container...")
    data = _graph(
        f"{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media",
        INSTAGRAM_ACCESS_TOKEN,
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
        },
    )

    container_id = data.get("id")
    if not container_id:
        raise RuntimeError(
            f"Instagram did not return a media container ID: {data}"
        )

    print(f"📦 Instagram Reel container: {container_id}")
    _wait_ig(container_id)

    print("📤 Publishing Instagram Reel...")
    result = _graph(
        f"{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media_publish",
        INSTAGRAM_ACCESS_TOKEN,
        data={"creation_id": container_id},
    )

    print(f"📸 Instagram Reel published: {result}")
    return result
