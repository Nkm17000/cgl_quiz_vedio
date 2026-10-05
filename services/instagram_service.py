import hashlib
import json
import mimetypes
import subprocess
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


def _require_config():
    if not INSTAGRAM_ACCESS_TOKEN:
        raise ValueError("INSTAGRAM_ACCESS_TOKEN is missing.")
    if not INSTAGRAM_BUSINESS_ACCOUNT_ID:
        raise ValueError("INSTAGRAM_BUSINESS_ACCOUNT_ID is missing.")
    print("📸 Instagram Business Account ID: configured")
    print(f"🔧 Meta Graph API version: {META_GRAPH_VERSION}")


def _response_details(response: requests.Response) -> str:
    try:
        payload = response.json()
        return json.dumps(payload, ensure_ascii=False)
    except ValueError:
        return response.text[:4000]


def _raise_meta_error(response: requests.Response, action: str):
    if response.ok:
        return
    details = _response_details(response)
    print(f"❌ Meta {action}: HTTP {response.status_code}")
    print(f"📋 Meta response: {details}")
    print(f"📋 Response content-type: {response.headers.get('content-type')}")
    print(f"📋 Response request-id: "
          f"{response.headers.get('x-fb-request-id') or response.headers.get('x-fb-trace-id')}")
    raise RuntimeError(
        f"Instagram {action} failed: HTTP {response.status_code}. "
        f"Meta response: {details}"
    )


def _validate_account():
    url = f"{GRAPH_BASE}/{INSTAGRAM_BUSINESS_ACCOUNT_ID}"
    print(f"🔎 Validating Instagram account ID: {INSTAGRAM_BUSINESS_ACCOUNT_ID}")
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
    return username


def _video_diagnostics(video_path):
    """Print detailed MP4/codec information without changing the file."""
    path = Path(video_path)
    size = path.stat().st_size
    sha256 = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha256.update(chunk)

    print("\n🔬 VIDEO DIAGNOSTICS")
    print(f"   path: {path}")
    print(f"   exists: {path.is_file()}")
    print(f"   size_bytes: {size}")
    print(f"   size_mb: {size / 1024 / 1024:.3f}")
    print(f"   extension: {path.suffix.lower()}")
    print(f"   sha256: {sha256.hexdigest()}")

    ffprobe = __import__("shutil").which("ffprobe")
    if not ffprobe:
        print("⚠️ ffprobe not found; codec/container diagnostics unavailable.")
        return

    cmd = [
        ffprobe, "-v", "error",
        "-show_entries",
        "format=format_name,format_long_name,duration,size,bit_rate:"
        "stream=index,codec_type,codec_name,profile,pix_fmt,width,height,"
        "r_frame_rate,avg_frame_rate,sample_rate,channels,channel_layout,"
        "bit_rate,duration",
        "-of", "json",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        print("❌ ffprobe failed:")
        print(result.stderr[:4000])
        return

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("❌ Could not parse ffprobe output.")
        print(result.stdout[:4000])
        return

    print("   ffprobe:")
    print(json.dumps(data, ensure_ascii=False, indent=2))

    fmt = data.get("format", {})
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    print("📐 NORMALIZATION CHECK")
    if video:
        print(f"   video_codec: {video.get('codec_name')}")
        print(f"   profile: {video.get('profile')}")
        print(f"   pixel_format: {video.get('pix_fmt')}")
        print(f"   resolution: {video.get('width')}x{video.get('height')}")
        print(f"   fps: {video.get('avg_frame_rate')}")
    else:
        print("   ❌ No video stream found.")

    if audio:
        print(f"   audio_codec: {audio.get('codec_name')}")
        print(f"   sample_rate: {audio.get('sample_rate')}")
        print(f"   channels: {audio.get('channels')}")
        print(f"   channel_layout: {audio.get('channel_layout')}")
    else:
        print("   ⚠️ No audio stream found.")

    print(f"   container: {fmt.get('format_name')}")
    print(f"   duration: {fmt.get('duration')}")
    print(f"   container_size: {fmt.get('size')}")
    print(f"   bitrate: {fmt.get('bit_rate')}")


def _create_resumable_container(caption, attempt):
    url = f"{GRAPH_BASE}/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media"

    print(f"\n📦 Creating Instagram Reel container (attempt {attempt}/3)")
    print(f"   media_type=REELS")
    print(f"   upload_type=resumable")
    print(f"   share_to_feed=true")
    print(f"   caption_length={len(caption)}")

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

    _raise_meta_error(response, "Reel container creation")

    data = response.json()
    print(f"📋 Container creation response: "
          f"{json.dumps({k: v for k, v in data.items() if k not in {'access_token'}}, ensure_ascii=False)}")

    container_id = data.get("id")
    upload_uri = data.get("uri")

    if not container_id or not upload_uri:
        raise RuntimeError(
            "Instagram Reel container response is incomplete: "
            f"{json.dumps(data, ensure_ascii=False)}"
        )

    print(f"📦 Instagram Reel container created: {container_id}")
    print(f"🔗 Upload URI host/path: {upload_uri.split('?')[0]}")
    return container_id, upload_uri


def _upload_video(upload_uri, video_path, attempt):
    """Keep the original working resumable upload contract and add diagnostics."""
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

    print(f"\n📤 INSTAGRAM BINARY UPLOAD {attempt}/3")
    print(f"   file: {path}")
    print(f"   size: {file_size} bytes ({file_size / 1024 / 1024:.3f} MB)")
    print(f"   content-type: video/mp4")
    print("   offset: 0")
    print(f"   file_size header: {file_size}")
    print("   upload mode: resumable")
    print("   timeout: 900s")

    headers = {
        # This matches the original version that successfully worked.
        "Authorization": f"OAuth {INSTAGRAM_ACCESS_TOKEN}",
        "offset": "0",
        "file_size": str(file_size),
        "Content-Type": "video/mp4",
    }

    started = time.monotonic()
    try:
        with path.open("rb") as video_file:
            response = requests.post(
                upload_uri,
                headers=headers,
                data=video_file,
                timeout=900,
            )
    except requests.RequestException as exc:
        print(f"❌ Network exception during binary upload: {type(exc).__name__}: {exc}")
        raise

    elapsed = time.monotonic() - started
    print(f"⏱️ Binary upload HTTP time: {elapsed:.2f}s")
    print(f"📥 Upload HTTP status: {response.status_code}")
    print(f"📥 Upload response content-type: {response.headers.get('content-type')}")
    print(f"📥 Upload response request-id: "
          f"{response.headers.get('x-fb-request-id') or response.headers.get('x-fb-trace-id')}")
    print(f"📥 Upload response length: {len(response.content)} bytes")
    print(f"📥 Upload response body: {_response_details(response)}")

    if not response.ok:
        _raise_meta_error(response, "binary video upload")

    try:
        result = response.json()
    except ValueError:
        result = {"raw_response": response.text[:4000]}

    if result.get("success") is not True:
        raise RuntimeError(f"Instagram binary upload was not successful: {result}")

    print("✅ Instagram video binary upload completed")
    return result


def _get_container_status(container_id):
    url = f"{GRAPH_BASE}/{container_id}"
    response = requests.get(
        url,
        params={
            "fields": "id,status_code,status",
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        },
        timeout=60,
    )
    _raise_meta_error(response, "container status check")
    return response.json()


def _wait_until_ready(container_id, timeout_seconds=900, poll_seconds=10):
    print(f"\n⏳ Waiting for Instagram processing: {container_id}")
    deadline = time.monotonic() + timeout_seconds
    poll = 0

    while time.monotonic() < deadline:
        poll += 1
        data = _get_container_status(container_id)
        status = data.get("status_code") or data.get("status")

        print(
            f"⏳ Poll #{poll}: status_code={data.get('status_code')} "
            f"status={data.get('status')} full={json.dumps(data, ensure_ascii=False)}"
        )

        if status == "FINISHED":
            print("✅ Instagram container processing FINISHED")
            return data

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
    print(f"\n🚀 Publishing Instagram container: {container_id}")

    response = requests.post(
        url,
        data={
            "creation_id": container_id,
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        },
        timeout=60,
    )

    print(f"📥 Publish HTTP status: {response.status_code}")
    print(f"📥 Publish response: {_response_details(response)}")
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


def publish_video_to_instagram(video_path, caption, max_attempts=3):
    """
    Upload exactly one Reel at a time.

    Each retry creates a fresh container and uploads the same source file,
    while detailed diagnostics identify whether the failure occurs during
    container creation, binary upload, processing, or publishing.
    """
    _require_config()
    username = _validate_account()
    print(f"🎯 Instagram target: @{username}")
    print(f"🎯 Video: {video_path}")

    path = Path(video_path)
    if not path.is_file():
        raise FileNotFoundError(path)

    _video_diagnostics(path)

    last_error = None

    for attempt in range(1, max_attempts + 1):
        print("\n" + "=" * 90)
        print(f"📸 INSTAGRAM REEL ATTEMPT {attempt}/{max_attempts}")
        print("=" * 90)

        container_id = None
        try:
            container_id, upload_uri = _create_resumable_container(caption, attempt)
            _upload_video(upload_uri, path, attempt)
            _wait_until_ready(container_id)
            result = _publish_container(container_id)

            print(f"🎉 Instagram Reel completed successfully on attempt {attempt}")
            return result

        except Exception as exc:
            last_error = exc
            print(f"❌ Instagram attempt {attempt}/{max_attempts} failed")
            print(f"   error_type: {type(exc).__name__}")
            print(f"   error: {exc}")
            if container_id:
                try:
                    status = _get_container_status(container_id)
                    print(f"   container_after_failure: "
                          f"{json.dumps(status, ensure_ascii=False)}")
                except Exception as status_exc:
                    print(f"   could not inspect failed container: {status_exc}")

            if attempt < max_attempts:
                wait = 10 * attempt
                print(f"🔄 Retrying with a NEW Instagram container in {wait}s...")
                time.sleep(wait)

    raise RuntimeError(
        f"Instagram publishing failed after {max_attempts} attempts. "
        f"Last error: {last_error}"
    )
