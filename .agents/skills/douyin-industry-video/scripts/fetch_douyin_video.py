#!/usr/bin/env python3
"""Get Douyin video metadata and (only when asked) the video file.

Douyin's detail API is signed inside the browser, so this script never calls it and
never tries to reproduce the signature. The browser reads the data; this script
normalizes it and downloads the file through the public play endpoint.

  1. fetch_douyin_video.py <url-or-id>
       Resolve the video id (short links too) and print the page URL to open.
  2. In a real browser tab on that page, evaluate scripts/douyin_page_probe.js and
     save the returned object as probe.json.
  3. fetch_douyin_video.py <url-or-id> --probe-json probe.json --out-dir DIR
       Write <name>.metadata.json and report file name, source and size. No video download.
  4. After the user agrees to that download:
     fetch_douyin_video.py <url-or-id> --probe-json probe.json --out-dir DIR --download
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DESKTOP_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
REFERER = "https://www.douyin.com/"
PLAY_ENDPOINT = "https://aweme.snssdk.com/aweme/v1/play/?video_id={uri}&ratio={ratio}&line=0"
ID_RE = re.compile(r"(?:/(?:video|note)/|[?&](?:modal_id|vid|aweme_id)=)(\d{15,21})")


class _KeepHeadOnRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and req.get_method() == "HEAD":
            new.method = "HEAD"
        return new


OPENER = urllib.request.build_opener(_KeepHeadOnRedirect)


def host(url):
    return urllib.parse.urlsplit(url).netloc


def resolve_id(source):
    source = source.strip()
    if re.fullmatch(r"\d{15,21}", source):
        return source
    found = re.search(r"https?://[^\s，。！!）)]+", source)  # share text usually wraps the link
    if not found:
        raise RuntimeError("No Douyin URL or numeric video id in the input")
    url = found.group(0)
    match = ID_RE.search(url)
    if match:
        return match.group(1)
    req = urllib.request.Request(url, headers={"User-Agent": MOBILE_UA})
    with OPENER.open(req, timeout=30) as resp:  # short link such as v.douyin.com/xxxx/
        final_url = resp.geturl()
    match = ID_RE.search(final_url)
    if not match:
        raise RuntimeError(f"Could not find a video id after following {url} -> {final_url}")
    return match.group(1)


def head(url):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": DESKTOP_UA, "Referer": REFERER})
    with OPENER.open(req, timeout=30) as resp:
        return resp.geturl(), resp.headers.get("Content-Type", ""), int(resp.headers.get("Content-Length") or 0)


def download(url, dest, expected):
    part = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": DESKTOP_UA, "Referer": REFERER})
    done = 0
    next_report = 10 * 1024 * 1024
    with OPENER.open(req, timeout=60) as resp, open(part, "wb") as fh:
        total = int(resp.headers.get("Content-Length") or expected or 0)
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if done >= next_report:
                print(f"downloaded {done / 1e6:.1f} / {total / 1e6:.1f} MB", file=sys.stderr)
                next_report += 10 * 1024 * 1024
    if total and done != total:
        raise RuntimeError(f"Download incomplete: {done} of {total} bytes. Partial file kept at {part}")
    part.replace(dest)
    return done


def build_metadata(probe, aweme_id):
    video = probe.get("video") or {}
    author = probe.get("author") or {}
    created = probe.get("create_time")
    return {
        "aweme_id": aweme_id,
        "page_url": f"https://www.douyin.com/video/{aweme_id}",
        "desc": probe.get("desc"),
        "item_title": probe.get("item_title"),
        "author": author.get("nickname"),
        "author_uid": author.get("uid"),
        "create_time": created,
        "create_time_beijing": datetime.fromtimestamp(created, timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M") if created else None,
        "duration_ms": probe.get("duration_ms"),
        "statistics": probe.get("statistics"),
        "orientation": video.get("orientation"),
        "source_resolution": f"{video.get('width')}x{video.get('height')}",
        "chapter_abstract": probe.get("chapter_abstract"),
        "chapters": probe.get("chapters"),
        "official_subtitle_hints": probe.get("subtitle_hints") or [],
        "seo_ocr_length": probe.get("seo_ocr_length", 0),
        "metadata_source": "douyin_page_probe.js in a real browser (douyin.com/video page)",
    }


def pick_url(probe, ratio):
    candidates = []
    uri = (probe.get("video") or {}).get("uri")
    if uri:
        candidates.append(PLAY_ENDPOINT.format(uri=urllib.parse.quote(uri), ratio=ratio))
    if probe.get("play_url_fallback"):
        candidates.append(probe["play_url_fallback"])  # signed CDN link, expires after a few hours
    errors = []
    for url in candidates:
        try:
            final_url, content_type, size = head(url)
        except (urllib.error.URLError, OSError) as exc:
            errors.append(f"{host(url)}: {exc}")
            continue
        if not content_type.startswith("video/") or size <= 0:
            errors.append(f"{host(url)}: got {content_type or 'no content-type'}, {size} bytes")
            continue
        return url, final_url, size
    raise RuntimeError("No downloadable video URL. " + "; ".join(errors or ["probe has no video uri"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="Douyin URL, share text containing one, or numeric video id")
    ap.add_argument("--probe-json", help="object returned by scripts/douyin_page_probe.js, saved as JSON")
    ap.add_argument("--out-dir", default="work/video")
    ap.add_argument("--name", help="file name stem (default: dy-<id>)")
    ap.add_argument("--ratio", default="1080p", choices=["1080p", "720p", "540p"], help="quality to request (default 1080p)")
    ap.add_argument("--download", action="store_true", help="download the video; use only after the user agreed to the reported size")
    args = ap.parse_args()

    aweme_id = resolve_id(args.source)
    page_url = f"https://www.douyin.com/video/{aweme_id}"
    if not args.probe_json:
        print(json.dumps({
            "aweme_id": aweme_id,
            "page_url": page_url,
            "next_step": "Open page_url in a real browser, evaluate scripts/douyin_page_probe.js in that tab, "
                         "save the returned object as JSON, then rerun with --probe-json <file>.",
        }, ensure_ascii=False, indent=2))
        return

    probe = json.loads(Path(args.probe_json).read_text(encoding="utf-8"))
    if not probe.get("ok"):
        raise RuntimeError(f"Browser probe failed: {probe.get('error')}")
    if str(probe.get("aweme_id")) != aweme_id:
        raise RuntimeError(f"{args.probe_json} is for video {probe.get('aweme_id')}, not {aweme_id}")
    if probe.get("media") == "images":
        raise RuntimeError("This post is an image album (图文), not a video")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = args.name or f"dy-{aweme_id}"
    meta_path = out_dir / f"{name}.metadata.json"
    video_path = out_dir / f"{name}.mp4"

    meta = build_metadata(probe, aweme_id)
    play_url, final_url, size = pick_url(probe, args.ratio)
    streams = [s for s in probe.get("streams") or [] if s.get("size") == size]
    stream = f"{streams[0].get('width')}x{streams[0].get('height')} {streams[0].get('gear')}" if streams else "unknown"
    meta["play_url"] = play_url
    meta["download"] = {
        "file": str(video_path),
        "size_bytes": size,
        "size_mb": round(size / 1e6, 1),
        "source": f"{host(play_url)} -> {host(final_url)}",
        "stream": stream,
        "ratio": args.ratio,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    result = {"metadata": str(meta_path), "video": str(video_path), "size_mb": meta["download"]["size_mb"],
              "source": meta["download"]["source"], "stream": stream}
    if not args.download:
        result["downloaded"] = False
        result["next_step"] = "Tell the user the file name, source and size; rerun with --download only after they agree."
    elif video_path.exists() and video_path.stat().st_size == size:
        result["downloaded"] = "already present"
    else:
        download(play_url, video_path, size)
        result["downloaded"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
