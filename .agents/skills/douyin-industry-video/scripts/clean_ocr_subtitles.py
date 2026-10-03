#!/usr/bin/env python3
"""Turn OCR hits from ocr_burned_subtitles.swift into a timed transcript (or, with --screen, a digest
of the on-screen text from a pass over the rest of the frame).

Works for portrait and landscape videos and for Chinese-only, English-only or bilingual
burned-in subtitles (for example a Chinese line above its English translation):
  1. keep horizontally centered boxes and split them into a Chinese and a Latin stream;
  2. drop static overlays (watermarks, logos, diagram labels that stay on screen) and --drop
     patterns; boxes much taller than the subtitle line (a moving watermark crossing the text)
     lose the watermark's words and only count when no clean reading exists;
  3. keep each stream's subtitle row: the height where the text keeps changing;
  4. join the pieces of one frame's subtitle, group consecutive similar frames, and keep the
     reading with the highest count x confidence;
  5. bilingual videos: pair lines by time; a Chinese line hidden by a watermark is filled by
     the English line of the same moment.
"""
import argparse
import difflib
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

CJK = r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
# Platform watermark, @handles, and numbered diagram labels such as "①韩国供应" (spoken
# subtitles practically never start with a circled number).
DEFAULT_DROPS = [r"抖音号\s*[:：]?\s*\S+", r"^@\S+$", r"^\s*[①-⑳]\s*\S{0,7}$"]
LABEL_TAIL = re.compile(r"\s*[①-⑳][^①-⑳]{0,5}$")  # numbered label glued after a subtitle

# --industry: OCR fixes tuned on the 2026-06 AI-chain video. Applied to Chinese lines only.
INDUSTRY_FIXES = [
    (r"(?<![A-Za-z0-9])(?:A1|AD|Al)(?![A-Za-z0-9])", "AI"),
    (r"韓", "韩"), (r"内存公同", "内存公司"), (r"公同", "公司"), (r"企亚", "企业"),
    (r"情況", "情况"), (r"肉存", "内存"), (r"吸价", "溢价"),
]
INDUSTRY_TRAILING_NOISE = [r"[①-⑳¥]+[.。]?$", r"[脆胞啦咂血]+[.。]?$"]
INDUSTRY_NOISE_TEXTS = {"openai", "open", "oen", "dpen", "ien", "al", "抖音", "旁", "岛", "鳥", "鸟", "587911"}


def clean_text(text):
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(rf"(?<={CJK}) (?={CJK})", "", text)


def key_of(text):
    return re.sub(r"[\W_]+", "", text.lower())


def lang_of(text):
    cjk = len(re.findall(CJK, text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if cjk >= 2 and cjk * 4 >= latin:  # Chinese line, maybe with English terms such as MacBook Pro
        return "zh"
    if latin >= 3 and cjk * 4 < latin and re.search(r"[A-Za-z]{2}", text):  # stray CJK = OCR junk
        return "en"
    return None


def similar(a, b):
    if not a or not b:
        return False
    if a in b or b in a:
        return min(len(a), len(b)) / max(len(a), len(b)) > 0.5
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.6


def fmt_time(seconds):
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def load(path):
    meta, hits = None, []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if "meta" in item:
            meta = item["meta"]
            continue
        x, y, w, h = item["bbox"]
        if meta is None:
            # Raw file from the pre-2026-10 script: box relative to a crop of x 5-95%, y 58-86%
            # of the frame, origin bottom-left. Convert to full frame, origin top-left.
            x, y, w, h = 0.05 + 0.9 * x, 0.58 + 0.28 * (1 - y - h), 0.9 * w, 0.28 * h
        text = clean_text(item["text"])
        hits.append({"t": float(item["time"]), "text": text, "key": key_of(text),
                     "conf": float(item["confidence"]), "x": x, "y": y, "w": w, "h": h})
    times = sorted({h["t"] for h in hits})
    if meta and meta.get("interval"):
        interval = float(meta["interval"])
    else:
        steps = [b - a for a, b in zip(times, times[1:]) if b - a > 1e-6]
        interval = statistics.median(steps) if steps else 1.0
    start = float(meta["start"]) if meta else (times[0] if times else 0.0)
    end = float(meta["end"]) if meta else (times[-1] if times else 0.0)
    return meta, hits, interval, start, end


def find_static(hits, interval, span):
    """Short texts that stay on screen for a long share of the video: watermarks, logos, diagram
    labels. OCR reads such a label a little differently from frame to frame, so similar readings
    are pooled before measuring how long they stay. Returns ({key: set of readings}, labels
    ordered by time on screen)."""
    frames, readings = defaultdict(set), defaultdict(set)
    for h in hits:
        if 2 <= len(h["key"]) <= 10:
            frames[h["key"]].add(h["t"])
            readings[h["key"]].add(h["text"].replace(" ", ""))
    groups = []
    for key in sorted(frames, key=lambda k: -len(frames[k])):
        sm = difflib.SequenceMatcher(None, "", key)
        for g in groups:
            sm.set_seq1(g["rep"])
            if sm.real_quick_ratio() >= 0.6 and sm.quick_ratio() >= 0.6 and sm.ratio() >= 0.6:
                g["times"] |= frames[key]
                g["keys"].append(key)
                break
        else:
            groups.append({"rep": key, "times": set(frames[key]), "keys": [key]})
    static, reps = {}, []
    for g in groups:
        ts = g["times"]
        if len(ts) * interval >= max(20.0, 0.12 * span) and max(ts) - min(ts) >= 0.4 * span:
            reps.append((len(ts) * interval, g["rep"]))
            for k in g["keys"]:
                static[k] = readings[k]
    return static, [rep for _, rep in sorted(reps, reverse=True)]


def strip_affixes(h, pieces):
    """Remove a static label glued to the start or end of a centered Chinese subtitle box. A glued
    label widens the box on its side, so the box centre must have moved that way by about half
    the label's width; a subtitle that merely says the label's words stays centered and is kept.
    Labels of 4+ characters also match when OCR misread one character (应用企业 / 2用企亚)."""
    text = h["text"]
    flat = LABEL_TAIL.sub("", text.replace(" ", ""))
    shift = h["x"] + h["w"] / 2 - 0.5
    changed = True
    while changed:
        changed = False
        for p in pieces:
            n = len(p)
            needed = 0.3 * n * h["w"] / max(1, len(flat))
            if len(re.findall(CJK, flat)) - len(re.findall(CJK, p)) < 4:
                continue
            for cut, part, side in ((flat[n:], flat[:n], -1), (flat[:-n], flat[-n:], 1)):
                if side * shift >= needed and (part == p or (n >= 4 and difflib.SequenceMatcher(None, part, p).ratio() >= 0.75)):
                    flat, changed = cut, True
                    break
            if changed:
                break
    return flat if flat != text.replace(" ", "") else text


def is_tall(h, line_h):
    """Much taller than the usual subtitle line: the box also holds something else, typically a
    watermark moving across the subtitle. Boxes cleaned by --strip are exempt (height includes it)."""
    return h["h"] > 1.6 * line_h and not h.get("stripped")


def overlay_words(streams):
    """Latin words of the overlay itself: seen in too-tall boxes in several separate parts of the
    video, and rarely in normal subtitle boxes. Words of a subtitle that one overlay pass happened
    to cover show up in a single stretch only, so they are kept."""
    tall_times, normal = defaultdict(list), Counter()
    for items in streams.values():
        if len(items) < 10:
            continue
        line_h = statistics.median(h["h"] for h in items)
        for h in items:
            words = [w.lower() for w in re.findall(r"[A-Za-z]{2,}", h["text"])]
            if is_tall(h, line_h):
                for w in words:
                    tall_times[w].append(h["t"])
            else:
                normal.update(words)
    common = [u for u, n in normal.items() if n >= 2 and len(u) >= 3]
    vocab = set()
    for w, ts in tall_times.items():
        ts.sort()
        stretches = 1 + sum(1 for a, b in zip(ts, ts[1:]) if b - a > 10)
        misread_of_common = w not in normal and any(difflib.SequenceMatcher(None, w, u).ratio() >= 0.85 for u in common)
        if len(ts) >= 3 and stretches >= 2 and len(ts) >= 4 * (normal[w] + 1) and not misread_of_common:
            vocab.add(w)
    return vocab


def demote_tall(hits, lang, vocab):
    """Remove overlay words from too-tall boxes; keep what is left with low weight, or drop the
    box when too little subtitle text remains."""
    if len(hits) < 10:
        return hits, []
    line_h = statistics.median(h["h"] for h in hits)
    long_vocab = [v for v in vocab if len(v) >= 3]

    def drop_word(m):
        w = m.group(0).lower()
        if w in vocab or (3 <= len(w) <= 8 and any(difflib.SequenceMatcher(None, w, v).ratio() >= 0.8 for v in long_vocab)):
            return ""
        near_digit = (m.start() > 0 and m.string[m.start() - 1].isdigit()) or (m.end() < len(m.string) and m.string[m.end()].isdigit())
        return "" if lang == "zh" and len(w) == 1 and not near_digit else m.group(0)  # stray letter, not the D of 3D

    kept, dropped = [], []
    for h in hits:
        if not is_tall(h, line_h):
            kept.append(h)
            continue
        text = clean_text(re.sub(r"[|•]+", " ", re.sub(r"(?<![A-Za-z])[A-Za-z]+(?![A-Za-z])", drop_word, h["text"])))
        if lang == "zh":  # overlay fragments left at the edges, e.g. "AL 然后…" or "…出掉了 OR"
            text = re.sub(r"^[A-Za-z]{1,4}\s*[、，,.:;]?\s+|\s+[A-Za-z]{1,4}[\W_]*$|[「『（(\s]+$", "", text).strip()
        enough = len(re.findall(CJK, text)) >= 4 if lang == "zh" else len(re.findall(r"[A-Za-z]{2,}", text)) >= 3
        if enough and lang_of(text) == lang:
            kept.append(dict(h, text=text, key=key_of(text), tall=True))
        else:
            dropped.append(h)
    return kept, dropped


def row_bin(h):
    return min(99, max(0, int((h["y"] + h["h"] / 2) * 100)))


def row_zone(hits):
    """Height range of a stream's subtitle row (plus room for a second wrapped line)."""
    texts = defaultdict(set)
    for h in hits:
        texts[row_bin(h)].add(h["key"])
    if not texts:
        return None
    scores = {b: len(s) for b, s in texts.items()}
    peak_bin = max(scores, key=lambda b: (scores[b], b))
    lo = hi = peak_bin
    floor = max(2, scores[peak_bin] * 0.25)
    while lo - 1 in scores and scores[lo - 1] >= floor or lo - 2 in scores and scores[lo - 2] >= floor:
        lo -= 1 if lo - 1 in scores and scores[lo - 1] >= floor else 2
    while hi + 1 in scores and scores[hi + 1] >= floor or hi + 2 in scores and scores[hi + 2] >= floor:
        hi += 1 if hi + 1 in scores and scores[hi + 1] >= floor else 2
    core = [h for h in hits if lo <= row_bin(h) <= hi]
    line_h = statistics.median(h["h"] for h in core)
    return lo / 100 - 1.5 * line_h, (hi + 1) / 100 + 1.5 * line_h, (lo + hi + 1) / 200


def join_frame(boxes, lang):
    """Join one frame's boxes of a stream into lines; return the line nearest the row centre."""
    sep = " " if lang == "en" else ""
    boxes = sorted(boxes, key=lambda b: (b["y"], b["x"]))
    rows = []
    for b in boxes:  # same visual line -> join left to right
        for row in rows:
            r = row[-1]
            overlap = min(r["y"] + r["h"], b["y"] + b["h"]) - max(r["y"], b["y"])
            if overlap > 0.5 * min(r["h"], b["h"]):
                row.append(b)
                break
        else:
            rows.append([b])
    lines = []
    for row in rows:
        row.sort(key=lambda b: b["x"])
        top = min(b["y"] for b in row)
        bottom = max(b["y"] + b["h"] for b in row)
        lines.append({"text": sep.join(b["text"] for b in row), "conf": min(b["conf"] for b in row),
                      "top": top, "bottom": bottom, "h": max(b["h"] for b in row),
                      "tall": any(b.get("tall") for b in row)})
    blocks = []
    for line in sorted(lines, key=lambda l: l["top"]):  # wrapped subtitle (same font size) -> join top to bottom
        prev = blocks[-1] if blocks else None
        if prev and line["top"] - prev["bottom"] <= 0.8 * max(line["h"], prev["h"]) \
                and max(line["h"], prev["h"]) <= 1.35 * min(line["h"], prev["h"]):
            prev.update(text=prev["text"] + sep + line["text"], conf=min(prev["conf"], line["conf"]),
                        bottom=line["bottom"], h=max(prev["h"], line["h"]), tall=prev["tall"] or line["tall"])
        else:
            blocks.append(dict(line))
    return blocks


def cluster(frames, interval):
    """frames: sorted [(t, block)]. Consecutive similar readings form one subtitle line."""
    max_gap = max(1.0, 2.5 * interval)
    clusters = []
    for t, blk in frames:
        k = key_of(blk["text"])
        c = clusters[-1] if clusters else None
        if c and t - c["last_t"] <= max_gap and similar(c["last_key"], k):
            c["reads"].append(blk)
            c["last_t"], c["last_key"] = t, k
        else:
            clusters.append({"start": t, "last_t": t, "last_key": k, "reads": [blk]})
    out = []
    for c in clusters:
        reads = defaultdict(list)
        for blk in c["reads"]:
            reads[blk["text"]].append(blk)

        def score(text):  # count x confidence; readings taken through an overlay count a quarter
            rs = reads[text]
            weight = 0.25 if all(r["tall"] for r in rs) else 1.0
            return (len(rs) * statistics.mean(r["conf"] for r in rs) * weight, len(key_of(text)))

        best = max(reads, key=score)
        item = {"start": c["start"], "end": c["last_t"] + interval, "text": best,
                "conf": max(r["conf"] for r in reads[best]), "frames": len(c["reads"]),
                "obstructed": all(r["tall"] for r in reads[best])}
        prev = out[-1] if out else None
        # A garbled reading (low confidence or through an overlay) right before or after the clean
        # reading of the same line is the same line.
        garbled_tail = prev and (weak(item) or weak(prev)) and item["start"] - prev["end"] <= max_gap and \
            difflib.SequenceMatcher(None, key_of(prev["text"]), key_of(best)).ratio() >= 0.45
        flicker = len(out) >= 2 and prev["frames"] <= 2 and item["start"] - out[-2]["end"] <= max_gap + 2 * interval \
            and similar(key_of(out[-2]["text"]), key_of(best))  # A, misread B, A again -> one line
        if flicker:
            out.pop()
            absorb(out[-1], prev)
            absorb(out[-1], item)
        elif prev and (garbled_tail or item["start"] - prev["end"] <= 3.0 and similar(key_of(prev["text"]), key_of(best))):
            absorb(prev, item)
        else:
            out.append(item)
    return out


def weak(line):
    return line["obstructed"] or line["conf"] <= 0.3


def absorb(line, other):
    """Merge a later piece into a line, keeping the better reading."""
    if (not weak(other), other["frames"], len(other["text"])) > (not weak(line), line["frames"], len(line["text"])):
        line.update(text=other["text"], conf=other["conf"], obstructed=other["obstructed"])
    line["end"] = max(line["end"], other["end"])
    line["frames"] += other["frames"]


def describe_source(meta, interval):
    parts = []
    if meta:
        orientation = {"landscape": "横屏", "portrait": "竖屏"}.get(meta["orientation"], meta["orientation"])
        parts.append(f"画面 {meta['width']}x{meta['height']}（{orientation}）")
        parts.append(f"识别区域为画面高度 {meta['band'][0]:.2f}–{meta['band'][1]:.2f}（{meta['bandSource']}）")
    parts.append(f"每 {interval:g} 秒取一帧")
    return "；".join(parts)


def write_screen(args, meta, hits, interval, span, drops, strips):
    """--screen: digest of on-screen text (data cards, slides, charts) instead of subtitles. A card is a
    run of similar frames; its line lists the frame texts with confidence >= --min-conf in reading
    order, joined by ｜."""
    boxes = []
    for h in hits:
        text = h["text"]
        for p in strips:
            text = p.sub(" ", text)
        text = clean_text(text)
        key = key_of(text)
        if h["conf"] >= args.min_conf and (len(key) > 1 or key.isdigit()) \
                and not any(p.search(text) for p in drops):  # a lone letter or character is a fragment
            boxes.append(dict(h, text=text, key=key))
    static, static_reps = find_static(boxes, interval, span)
    by_time = defaultdict(list)
    for h in boxes:
        if h["key"] not in static:
            by_time[h["t"]].append(h)
    cards, prev_keys = [], set()
    for t in sorted(by_time):
        ordered = sorted(by_time[t], key=lambda h: (round(h["y"] / 0.04), h["x"]))  # top to bottom, left to right
        keys = {h["key"] for h in ordered}
        texts = list(dict.fromkeys(h["text"] for h in ordered))
        if cards and t - cards[-1]["end"] <= 1.01 * interval and len(keys & prev_keys) / len(keys | prev_keys) >= 0.8:
            cards[-1]["end"] = t + interval  # same card as the previous sample: keep any new text
            cards[-1]["texts"] += [x for x in texts if x not in cards[-1]["texts"]]
        else:
            cards.append({"start": t, "end": t + interval, "time": fmt_time(t), "texts": texts})
        prev_keys = keys
    md = [
        f"# 画面文字（OCR，置信度 ≥ {args.min_conf:g}）",
        "",
        "说明：识别区域内的画面文字（数据卡、幻灯片、图表等），用 macOS Vision 识别，不是平台数据；"
        "按阅读顺序用「｜」连接，同一画面连续出现只记第一次的时间。数字、单位和专有名词请对照视频核对。",
        "",
        f"- 来源：{describe_source(meta, interval)}。",
        f"- 结果：{len(cards)} 个画面。" if cards else "- 结果：没有识别到画面文字，检查识别区域（`--band`）是否正确。",
        "",
    ]
    md += [f"- `{c['time']}` " + " ｜ ".join(c["texts"]) for c in cards]
    md.append("")
    Path(args.output_md).write_text("\n".join(md), encoding="utf-8")
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"mode": "screen", "cards": len(cards), "static_overlays_dropped": static_reps[:8]}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_jsonl")
    ap.add_argument("output_md")
    ap.add_argument("--json", dest="output_json", help="also write rows as JSON")
    ap.add_argument("--screen", action="store_true",
                    help="digest on-screen text (data cards, slides) from a pass such as "
                         "`--band 0:0.84 --interval 2` instead of building subtitles")
    ap.add_argument("--min-conf", type=float, default=0.5, help="--screen: lowest OCR confidence to keep (default 0.5)")
    ap.add_argument("--mode", choices=["auto", "bilingual", "zh", "en"], default="auto",
                    help="auto: bilingual when both a Chinese and a Latin subtitle track exist")
    ap.add_argument("--center", type=float, default=0.25,
                    help="keep boxes whose centre is within 0.5 +/- this of the frame width (default 0.25)")
    ap.add_argument("--drop", action="append", default=[], metavar="REGEX",
                    help="drop OCR boxes matching this regex; repeatable")
    ap.add_argument("--strip", action="append", default=[], metavar="REGEX",
                    help="delete matching text but keep the rest of the box, e.g. a creator watermark "
                         "glued to the subtitle; repeatable")
    ap.add_argument("--industry", action="store_true",
                    help="opt-in OCR fixes for Chinese AI / semiconductor / memory videos (A1->AI, 肉存->内存, ...)")
    args = ap.parse_args()

    meta, hits, interval, start, end = load(args.input_jsonl)
    span = max(end - start, interval)
    drops = [re.compile(p, re.I) for p in DEFAULT_DROPS + args.drop]
    strips = [re.compile(p, re.I) for p in args.strip]
    if args.screen:
        write_screen(args, meta, hits, interval, span, drops, strips)
        return

    centered = []
    for h in hits:
        if strips:
            text = h["text"]
            for p in strips:
                text = p.sub(" ", text)
            if text != h["text"]:
                h.update(text=clean_text(text), key=key_of(clean_text(text)), stripped=True)
        if abs(h["x"] + h["w"] / 2 - 0.5) <= args.center:
            centered.append(h)

    # Find static overlays before dropping anything, so every reading of a label counts.
    static, static_reps = find_static(centered, interval, span)
    pieces = sorted({p for readings in static.values() for p in readings if len(p) >= 3}, key=len, reverse=True)
    label_chars = Counter(ch for readings in static.values() for r in readings for ch in set(re.findall(CJK, r)))
    label_chars = {ch for ch, n in label_chars.items() if n >= 2}
    streams = {"zh": [], "en": []}
    for h in centered:
        if h["key"] in static or any(p.search(h["text"]) for p in drops):
            continue
        if args.industry and h["key"] in INDUSTRY_NOISE_TEXTS:
            continue
        chars = re.findall(CJK, h["text"])
        if 0 < len(chars) <= 4 and sum(ch in label_chars for ch in chars) >= 2 / 3 * len(chars):
            continue  # another misreading of a static label
        lang = lang_of(h["text"])
        if lang == "zh":
            text = strip_affixes(h, pieces)
            if text != h["text"]:
                h.update(text=clean_text(text), key=key_of(text))
                lang = lang_of(h["text"])
        if args.industry and lang == "zh":
            for pattern, repl in INDUSTRY_FIXES:
                h["text"] = re.sub(pattern, repl, h["text"])
            for pattern in INDUSTRY_TRAILING_NOISE:
                h["text"] = re.sub(pattern, "", h["text"])
            h["key"] = key_of(h["text"])
            lang = lang_of(h["text"])
        if lang:
            streams[lang].append(h)
    vocab = overlay_words(streams)

    tall_dropped = 0
    lines = {}
    for lang, items in streams.items():
        items, dropped = demote_tall(items, lang, vocab)
        tall_dropped += len(dropped)
        zone = row_zone([h for h in items if not h.get("tall")])
        if zone:
            top, bottom, centre = zone
            items = [h for h in items if top <= h["y"] + h["h"] / 2 <= bottom]
        by_time = defaultdict(list)
        for h in items:
            by_time[h["t"]].append(h)
        frames = []
        for t in sorted(by_time):
            blocks = join_frame(by_time[t], lang)
            if zone:  # nearest the subtitle row; a clean box beats one read through an overlay
                blocks.sort(key=lambda b: (abs((b["top"] + b["bottom"]) / 2 - centre) + (0.03 if b["tall"] else 0), -b["conf"]))
            block = blocks[0]
            if lang == "zh":  # a numbered label line may have been joined under the subtitle
                block["text"] = clean_text(LABEL_TAIL.sub("", block["text"])) or block["text"]
            frames.append((t, block))
        lines[lang] = cluster(frames, interval)

    zh, en = lines["zh"], lines["en"]
    mode = args.mode
    if mode == "auto":
        if zh and en and min(len(zh), len(en)) >= 0.3 * max(len(zh), len(en)):
            mode = "bilingual"
        else:
            mode = "zh" if len(zh) >= len(en) else "en"

    rows = []
    if mode == "bilingual":
        rows = [{"start": z["start"], "end": z["end"], "zh": z["text"], "en": [], "conf": z["conf"],
                 "frames": z["frames"], "obstructed": z["obstructed"]} for z in zh]
        for e in en:  # attach to the Chinese line shown at the same time (overlap >= half the shorter)
            best, best_overlap = None, 0.0
            for r in rows:
                overlap = min(r["end"], e["end"]) - max(r["start"], e["start"])
                shorter = min(r["end"] - r["start"], e["end"] - e["start"])
                if overlap >= 0.5 * shorter and overlap > best_overlap:
                    best, best_overlap = r, overlap
            if best is not None:
                best["en"].append(e["text"])
            elif len(e["text"].split()) > 1 or e["frames"] > 2:  # a lone word seen for under 1 s is OCR debris
                rows.append({"start": e["start"], "end": e["end"], "zh": "", "en": [e["text"]], "conf": e["conf"],
                             "frames": e["frames"], "obstructed": e["obstructed"]})
        rows.sort(key=lambda r: r["start"])
        for r in rows:
            r["en"] = " / ".join(dict.fromkeys(r["en"]))
            r["text"] = r["zh"] or r["en"]
    else:
        for c in lines[mode]:
            rows.append({"start": c["start"], "end": c["end"], "text": c["text"], "conf": c["conf"],
                         "frames": c["frames"], "obstructed": c["obstructed"]})

    out_rows = []
    for r in rows:
        row = {"start": round(r["start"], 2), "end": round(r["end"], 2), "time": fmt_time(r["start"]),
               "text": r["text"], "confidence": round(r["conf"], 3), "frames": r["frames"]}
        if mode == "bilingual":
            row["zh"], row["en"] = r["zh"], r["en"]
        if r["obstructed"]:
            row["obstructed"] = True
        out_rows.append(row)

    covered, last_end, gaps = 0.0, start, []
    for r in out_rows:
        if r["start"] - last_end > 8:
            gaps.append((last_end, r["start"]))
        covered += max(0.0, r["end"] - max(r["start"], last_end))
        last_end = max(last_end, r["end"])
    if end - last_end > 8:
        gaps.append((last_end, end))

    md = [
        "# OCR 字幕",
        "",
        "说明：用 macOS Vision 从视频烧录字幕中识别并去重整理，不是平台官方字幕；同音字和专有名词可能有错。"
        "⚠ 表示该句识别置信度低，或只能透过水印等遮挡读到。",
        "",
        f"- 来源：{describe_source(meta, interval)}。",
    ]
    if out_rows:
        kind = "中英双语" if mode == "bilingual" else ("中文" if mode == "zh" else "英文")
        md.append(f"- 结果：{len(out_rows)} 行，{kind}字幕，覆盖 {covered / span:.0%} 时长。")
    else:
        md.append("- 结果：没有识别到字幕文字。可能这条视频没有烧录字幕，也可能识别区域不对："
                  "抽几帧看字幕的位置，用 `--band 上边界:下边界` 重新识别。")
    if gaps and out_rows:
        md.append("- 超过 8 秒没有字幕的时段（可能是无字幕片段，也可能漏识别，必要时抽帧核对）：" +
                  "，".join(f"{fmt_time(a)}–{fmt_time(b)}" for a, b in gaps[:12]) + "。")
    md.append("")
    for r in out_rows:
        flag = " ⚠" if r["confidence"] < 0.5 or r.get("obstructed") else ""
        if mode == "bilingual":
            zh_text = r["zh"] or "〔中文未识别〕"
            md.append(f"- `{r['time']}` {zh_text}{flag}" + (f" — _{r['en']}_" if r["en"] else ""))
        else:
            md.append(f"- `{r['time']}` {r['text']}{flag}")
    md.append("")
    Path(args.output_md).write_text("\n".join(md), encoding="utf-8")
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(out_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {"rows": len(out_rows), "mode": mode, "zh_lines": len(zh), "en_lines": len(en),
               "coverage": round(covered / span, 3),
               "gaps_over_8s": [f"{fmt_time(a)}-{fmt_time(b)}" for a, b in gaps],
               "static_overlays_dropped": static_reps[:8],
               "overlay_words_removed": sorted(vocab),
               "rows_read_through_overlay": sum(1 for r in out_rows if r.get("obstructed")),
               "overlay_boxes_dropped": tall_dropped}
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
