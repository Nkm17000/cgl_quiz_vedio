import json
import time
from pathlib import Path

import requests

from config import (
    INSTAGRAM_ACCESS_TOKEN,
    INSTAGRAM_BUSINESS_ACCOUNT_ID,
    META_GRAPH_VERSION,
)

MAX_REEL_BYTES = 1_000 * 1024 * 1024
GRAPH_BASE = f"https://graph.facebook.com/{META_GRAPH_VERSION}"

# Meta returns this error when the Instagram Content Publishing API quota has
# been reached. It is a platform/account limit, not a video-format problem.
PUBLISHING_LIMIT_CODE = 9
PUBLISHING_LIMIT_SUBCODES = {2207069}


def _require_config():
    if not INSTAGRAM_ACCESS_TOKEN:
        raise ValueError("INSTAGRAM_ACCESS_TOKEN is missing.")

    if not INSTAGRAM_BUSINESS_ACCOUNT_ID:
        raise ValueError("INSTAGRAM_BUSINESS_ACCOUNT_ID is missing.")

    print("📸 Instagram Business Account ID: configured")


def _response_details(response: requests.Response) -> str:
    """Return Meta's JSON error without exposing access tokens."""
    try:
        payload = response.json()
        return json.dumps(payload, ensure_ascii=False)
    except ValueError:
        return response.text[:4000]


def _meta_error_payload(response: requests.Response):
    try:
        payload = response.json()
        return payload.get("error") or {}
    except ValueError:
        return {}


def _is_publishing_limit_error(response: requests.Response) -> bool:
    """Detect Meta's account-level Content Publishing API limit error."""
    error = _meta_error_payload(response)
    try:
        code = int(error.get("code", -1))
    except (TypeError, ValueError):
        code = -1

    try:
        subcode = int(error.get("error_subcode", -1))
    except (TypeError, ValueError):
        subcode = -1

    return (
        code == PUBLISHING_LIMIT_CODE
        and subcode in PUBLISHING_LIMIT_SUBCODES
    )


def _raise_meta_error(response: requests.Response, action: str):
    if response.ok:
        return

    details = _response_details(response)
    raise RuntimeError(
        f"Instagram {action} failed: HTTP {response.status_code}. "
        f"Meta response: {details}"
    )


def _validate_account():
    """Confirm that the configured ID is an Instagram professional account."""
    url = f"{GRAPH_BASE}/{INSTAGRAM_BUSINESS_ACCOUNT_ID}"
    response = requests.get(
        url,
        params={
            "fields": "id,username",
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        },
        timeout=60,
    )
    _raise_meta_error(response, "account validation")

    data = response.json()
    returned_id = str(data.get("id", ""))
    username = data.get("username") or "unknown"

    if returned_id != str(INSTAGRAM_BUSINESS_ACCOUNT_ID):
        raise RuntimeError(
            "Instagram account validation returned a different account ID. "
            f"Configured={INSTAGRAM_BUSINESS_ACCOUNT_ID}, returned={returned_id}"
        )

    print(f"✅ Instagram account validated: @{username}")


def _check_publishing_limit():
    """
    Best-effort quota preflight.

    Meta's exact quota response can vary by Graph API version/app setup, so a
    failure of this optional check does not block publishing. The authoritative
    POST error is still handled by _create_resumable_container().
    """
    url = f"{GRAPH_BASE}/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/content_publishing_limit"
    try:
        response = requests.get(
            url,
            params={
                "fields": "config,quota_usage",
                "access_token": INSTAGRAM_ACCESS_TOKEN,
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        print(f"ℹ️ Instagram publishing-limit preflight unavailable: {exc}")
        return False

    if not response.ok:
        print(
            "ℹ️ Instagram publishing-limit preflight unavailable; "
            "continuing to the normal publish request."
        )
        return False

    try:
        data = response.json()
    except ValueError:
        return False

    config = data.get("config") or {}
    quota_usage = data.get("quota_usage")

    # Handle the common response shape without depending on one exact schema.
    limit = (
        config.get("quota_total")
        or config.get("limit")
        or config.get("max_posts")
    )

    try:
        if limit is not None and quota_usage is not None:
            usage = float(quota_usage)
            maximum = float(limit)
            if maximum > 0 and usage >= maximum:
                print(
                    f"⛔ Instagram Content Publishing quota reached "
                    f"({usage:g}/{maximum:g})."
                )
                return True
    except (TypeError, ValueError):
        pass

    return False


def _create_resumable_container(caption):
    """Create an Instagram Reel upload container for a local MP4."""
    url = f"{GRAPH_BASE}/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media"
    response = requests.post(
        url,
        data={
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption,
            "share_to_feed": "true",
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        },
        timeout=60,
    )

    if _is_publishing_limit_error(response):
        error = _meta_error_payload(response)
        message = error.get("error_user_msg") or error.get("message") or "Media creation limit exceeded"
        print(
            "⛔ Instagram Content Publishing API limit reached. "
            f"Meta: {message}"
        )
        print(
            "ℹ️ No video upload was attempted. The generated MP4 is kept in "
            "the output directory. Try again after Meta's publishing window resets."
        )
        return None, None

    if not response.ok:
        _raise_meta_error(response, "Reel container creation")

    data = response.json()
    container_id = data.get("id")
    upload_uri = data.get("uri")

    if not container_id or not upload_uri:
        raise RuntimeError(
            "Instagram Reel container response is incomplete: "
            f"{json.dumps(data, ensure_ascii=False)}"
        )

    print(f"📦 Instagram Reel container created: {container_id}")
    return container_id, upload_uri


def _upload_video(upload_uri, video_path):
    """Upload the local MP4 to Meta's resumable upload endpoint."""
    path = Path(video_path)
    if not path.is_file():
        raise FileNotFoundError(f"Instagram video not found: {path}")

    file_size = path.stat().st_size
    if file_size <= 0:
        raise ValueError(f"Instagram video is empty: {path}")
    if file_size > MAX_REEL_BYTES:
        raise ValueError(
            f"Instagram Reel is {file_size / 1024 / 1024:.1f} MB; "
            f"maximum supported size is {MAX_REEL_BYTES / 1024 / 1024:.0f} MB."
        )

    headers = {
        "Authorization": f"OAuth {INSTAGRAM_ACCESS_TOKEN}",
        "offset": "0",
        "file_size": str(file_size),
        "Content-Type": "video/mp4",
    }

    print(f"📤 Uploading video to Instagram: {file_size / 1024 / 1024:.1f} MB")
    with path.open("rb") as video_file:
        response = requests.post(
            upload_uri,
            headers=headers,
            data=video_file,
            timeout=900,
        )

    if not response.ok:
        _raise_meta_error(response, "binary video upload")

    try:
        result = response.json()
    except ValueError:
        result = {"raw_response": response.text[:4000]}

    if result.get("success") is not True:
        raise RuntimeError(f"Instagram binary upload was not successful: {result}")

    print("✅ Instagram video upload completed")


def _wait_until_ready(container_id, timeout_seconds=900, poll_seconds=10):
    url = f"{GRAPH_BASE}/{container_id}"
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        response = requests.get(
            url,
            params={
                "fields": "status_code,status",
                "access_token": INSTAGRAM_ACCESS_TOKEN,
            },
            timeout=60,
        )
        _raise_meta_error(response, "container status check")

        data = response.json()
        status = data.get("status_code") or data.get("status")
        print(f"⏳ Instagram processing status: {status}")

        if status == "FINISHED":
            return
        if status in {"ERROR", "EXPIRED"}:
            raise RuntimeError(
                "Instagram video processing failed: "
                f"{json.dumps(data, ensure_ascii=False)}"
            )

        time.sleep(poll_seconds)

    raise TimeoutError(
        f"Instagram Reel container {container_id} did not finish within "
        f"{timeout_seconds} seconds."
    )


def _publish_container(container_id):
    url = f"{GRAPH_BASE}/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media_publish"
    response = requests.post(
        url,
        data={
            "creation_id": container_id,
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        },
        timeout=60,
    )

    if not response.ok:
        _raise_meta_error(response, "Reel publishing")

    result = response.json()
    media_id = result.get("id")
    if not media_id:
        raise RuntimeError(
            "Instagram publish response has no media ID: "
            f"{json.dumps(result, ensure_ascii=False)}"
        )

    print(f"📸 Instagram Reel published: {media_id}")
    return result


def publish_video_to_instagram(video_path, caption):
    """
    Upload one local MP4 as a Reel and publish it.

    Returns:
      dict  -> successfully published
      None  -> Meta Content Publishing quota is currently exhausted
    """
    _require_config()
    _validate_account()

    # Avoid creating another media container when Meta already reports that
    # the account has exhausted its publishing allowance.
    if _check_publishing_limit():
        print(
            "⏭️ Skipping Instagram publish because the Content Publishing "
            "limit is currently exhausted."
        )
        return None

    container_id, upload_uri = _create_resumable_container(caption)

    # The POST above can be the authoritative source of the limit status when
    # the optional preflight endpoint is unavailable.
    if not container_id or not upload_uri:
        return None

    _upload_video(upload_uri, video_path)
    _wait_until_ready(container_id)
    return _publish_container(container_id)
