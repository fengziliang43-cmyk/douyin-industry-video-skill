#!/usr/bin/env python3
import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"


def request(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def find_video_url(page: str):
    match = re.search(r"window\._ROUTER_DATA\s*=\s*(\{.*?\})</script>", page, re.S)
    if not match:
        raise RuntimeError("Could not find window._ROUTER_DATA in Douyin page")
    data = json.loads(html.unescape(match.group(1)))
    loader = data.get("loaderData", {})
    video_page = None
    for key, value in loader.items():
        if "video" in key and isinstance(value, dict) and "videoInfoRes" in value:
            video_page = value
            break
    if not video_page:
        raise RuntimeError("Could not find videoInfoRes in router data")
    items = video_page.get("videoInfoRes", {}).get("item_list", [])
    if not items:
        raise RuntimeError("Douyin item_list is empty")
    item = items[0]
    urls = item.get("video", {}).get("play_addr", {}).get("url_list", [])
    if not urls:
        raise RuntimeError("No video play_addr URL exposed")
    meta = {
        "aweme_id": item.get("aweme_id"),
        "desc": item.get("desc"),
        "create_time": item.get("create_time"),
        "author": (item.get("author") or {}).get("nickname"),
        "duration_ms": (item.get("video") or {}).get("duration"),
        "statistics": item.get("statistics"),
    }
    return urls[0].replace("\\u002F", "/"), meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out-dir", default="work/video")
    ap.add_argument("--name", default="douyin-video")
    ap.add_argument("--metadata-only", action="store_true", help="Parse metadata and exposed play URL without downloading the video")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    page = request(args.url).decode("utf-8", errors="replace")
    video_url, meta = find_video_url(page)

    meta_path = out_dir / f"{args.name}.metadata.json"
    meta["play_url"] = video_url
    if args.metadata_only:
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"metadata": str(meta_path), "meta": meta}, ensure_ascii=False))
        return

    video_path = out_dir / f"{args.name}.mp4"
    with urllib.request.urlopen(urllib.request.Request(video_url, headers={"User-Agent": UA}), timeout=60) as resp:
        video_path.write_bytes(resp.read())
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"video": str(video_path), "metadata": str(meta_path), "meta": meta}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
