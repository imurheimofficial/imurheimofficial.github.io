import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

CHANNEL_ID = "UCnY0YBsyxKj6RTFEU9uObQg"
CHANNEL_URL_FALLBACK = "https://www.youtube.com/@imurheimofficial"
JSON_PATH = Path("api/latest-video.json")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()

ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015"
}


def fetch_url(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, application/atom+xml, application/xml, text/xml, */*"
        }
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8")


def normalize_date(value: str) -> str:
    return value[:10] if value else ""


def extract_video_id(entry: ET.Element) -> str:
    video_id_el = entry.find("yt:videoId", ATOM_NS)
    if video_id_el is not None and video_id_el.text:
        return video_id_el.text.strip()

    link_el = entry.find("atom:link", ATOM_NS)
    if link_el is not None:
        href = link_el.attrib.get("href", "")
        match = re.search(r"v=([A-Za-z0-9_-]{11})", href)
        if match:
            return match.group(1)

    return ""


def load_existing_json() -> dict:
    if JSON_PATH.exists():
        try:
            return json.loads(JSON_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_json(data: dict) -> None:
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )


def fetch_latest_video_from_feed() -> dict:
    """
    Vrací data o nejnovějším videu.
    Když na kanálu zatím žádné video není, vrátí placeholder místo pádu.
    """
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
    xml_text = fetch_url(feed_url)
    root = ET.fromstring(xml_text)

    entry = root.find("atom:entry", ATOM_NS)
    if entry is None:
        return {
            "title": "[Song Title]",
            "releaseDate": "",
            "videoUrl": CHANNEL_URL_FALLBACK,
            "thumbnailUrl": ""
        }

    title = (entry.findtext("atom:title", default="", namespaces=ATOM_NS) or "").strip()
    published = (entry.findtext("atom:published", default="", namespaces=ATOM_NS) or "").strip()
    release_date = normalize_date(published)

    video_id = extract_video_id(entry)
    if not video_id:
        return {
            "title": title or "[Song Title]",
            "releaseDate": release_date,
            "videoUrl": CHANNEL_URL_FALLBACK,
            "thumbnailUrl": ""
        }

    return {
        "title": title or "[Song Title]",
        "releaseDate": release_date,
        "videoUrl": f"https://www.youtube.com/watch?v={video_id}",
        "thumbnailUrl": f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
    }


def fetch_channel_data_from_api() -> dict:
    """
    Vrací subscribers + avatar.
    Když API key nebude fungovat, chyba se odchytí výš a použije se fallback.
    """
    if not YOUTUBE_API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY není nastavený v prostředí.")

    params = urllib.parse.urlencode({
        "part": "snippet,statistics",
        "id": CHANNEL_ID,
        "key": YOUTUBE_API_KEY
    })
    api_url = f"https://www.googleapis.com/youtube/v3/channels?{params}"
    raw = fetch_url(api_url)
    data = json.loads(raw)

    items = data.get("items", [])
    if not items:
        raise RuntimeError("YouTube API nevrátila data kanálu.")

    item = items[0]
    snippet = item.get("snippet", {})
    statistics = item.get("statistics", {})
    thumbnails = snippet.get("thumbnails", {})

    avatar = (
        thumbnails.get("high", {}).get("url")
        or thumbnails.get("medium", {}).get("url")
        or thumbnails.get("default", {}).get("url")
        or "assets/URHEIM GOLDEN PROFILE.png"
    )

    subscribers_raw = statistics.get("subscriberCount", "0")
    try:
        subscribers_int = int(subscribers_raw)
        subscribers = f"{subscribers_int:,}".replace(",", " ")
    except Exception:
        subscribers = "0"

    return {
        "subscribers": subscribers,
        "channelAvatarUrl": avatar
    }


def main() -> int:
    if CHANNEL_ID == "YOUR_CHANNEL_ID_HERE":
        print("ERROR: Doplň CHANNEL_ID ve scripts/update_latest_video.py", file=sys.stderr)
        return 1

    existing = load_existing_json()

    # nejnovější video – nově bez pádu, i když žádné video zatím není
    latest_video = fetch_latest_video_from_feed()

    # channel data z API – když to selže, použije se fallback a workflow NESPADNE
    try:
        channel_data = fetch_channel_data_from_api()
    except Exception as exc:
        print(f"WARNING: Nepodařilo se načíst channel data z YouTube API: {exc}")
        channel_data = {
            "subscribers": existing.get("subscribers", "0"),
            "channelAvatarUrl": existing.get("channelAvatarUrl", "assets/URHEIM GOLDEN PROFILE.png")
        }

    result = {
        "title": latest_video["title"],
        "releaseDate": latest_video["releaseDate"],
        "videoUrl": latest_video["videoUrl"],
        "thumbnailUrl": latest_video["thumbnailUrl"],
        "subscribers": channel_data["subscribers"],
        "channelAvatarUrl": channel_data["channelAvatarUrl"]
    }

    save_json(result)

    print("OK: latest-video.json updated")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
