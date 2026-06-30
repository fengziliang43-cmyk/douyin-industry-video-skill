#!/usr/bin/env python3
import argparse
import difflib
import json
import re
from pathlib import Path

BAD_PATTERNS = ["OpenAI", "OPen", "Oen", "DPen", "Ien", "AL", "抖音", "旁", "岛", "鳥", "鸟", "587911"]


def normalize(text: str) -> str:
    text = re.sub(r"\s+", "", text.strip())
    replacements = {
        "A1": "AI",
        "AD": "AI",
        "Al": "AI",
        "韓": "韩",
        "内存公同": "内存公司",
        "公同": "公司",
        "企亚": "企业",
        "情況": "情况",
        "肉存": "内存",
        "吸价": "溢价",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"[①②③④⑤0-9¥]+$", "", text)
    text = re.sub(r"[脆胞啦咂血]+$", "", text)
    return text


def is_bad(text: str, conf: float, bbox) -> bool:
    if len(text) < 2 or any(p in text for p in BAD_PATTERNS):
        return True
    y = bbox[1]
    if not (0.12 <= y <= 0.34):
        return True
    if conf < 0.45 and len(text) < 8:
        return True
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    if chinese < max(2, len(text) * 0.35):
        return True
    return False


def similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a in b or b in a:
        return min(len(a), len(b)) / max(len(a), len(b)) > 0.55
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.76


def score(item):
    return float(item["confidence"]) * 2 + item["bbox"][2] + min(len(item["text"]), 28) / 28


def fmt_time(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_jsonl")
    ap.add_argument("output_md")
    ap.add_argument("--json", dest="output_json")
    args = ap.parse_args()

    by_time = {}
    for line in Path(args.input_jsonl).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        text = normalize(item["text"])
        if is_bad(text, float(item["confidence"]), item["bbox"]):
            continue
        item["text"] = text
        t = int(round(float(item["time"])))
        old = by_time.get(t)
        if old is None or score(item) > score(old):
            by_time[t] = item

    clusters = []
    for item in [by_time[t] for t in sorted(by_time)]:
        text = item["text"]
        t = float(item["time"])
        if clusters and similar(clusters[-1]["best"]["text"], text):
            clusters[-1]["end"] = t
            if score(item) > score(clusters[-1]["best"]):
                clusters[-1]["best"] = item
        else:
            clusters.append({"start": t, "end": t, "best": item})

    rows = []
    for c in clusters:
        text = c["best"]["text"]
        if text in {"算力", "AI模型公司", "应用企业"}:
            continue
        if rows and similar(rows[-1]["text"], text):
            rows[-1]["end"] = c["end"]
            if len(text) > len(rows[-1]["text"]):
                rows[-1]["text"] = text
            continue
        rows.append({"start": c["start"], "end": c["end"], "time": fmt_time(c["start"]), "text": text, "confidence": round(float(c["best"]["confidence"]), 3)})

    lines = [
        "# OCR 字幕",
        "",
        "说明：从视频烧录字幕 OCR 提取并去重整理；不是平台官方字幕，仍需按上下文校正专有名词和明显错字。",
        "",
    ]
    lines.extend(f"- `{r['time']}` {r['text']}" for r in rows)
    lines.append("")
    Path(args.output_md).write_text("\n".join(lines), encoding="utf-8")
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"kept {len(rows)} subtitle rows")


if __name__ == "__main__":
    main()
