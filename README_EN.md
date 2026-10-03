# Douyin Industry Video Skill

[中文](README.md) | **English**

This repository contains a Codex skill that extracts metadata and subtitles
from Douyin-style short-video links or local videos, then analyzes investment
claims and industry-chain logic in Chinese. It is skill source code for Codex,
not a standalone desktop application or a one-click video downloader.

Skill path:

```text
.agents/skills/douyin-industry-video
```

## What It Does

- Uses a real browser to read the public metadata a Douyin video page has
  already loaded (title, author, statistics, Douyin's AI chapters), then
  downloads the video through the public play endpoint. Before downloading, it
  reports the file name, source, and size, and downloads only after the user
  agrees.
- Extracts burned-in subtitles with macOS Vision OCR: it detects portrait or
  landscape framing and finds the subtitle band itself, and handles Chinese,
  English, and bilingual subtitles. Text on data cards, slides, and charts can
  be scanned separately and digested.
- Drops static watermarks and diagram labels automatically, deduplicates
  repeated OCR frames, and writes Markdown and JSON transcripts together with a
  summary of coverage and gaps.
- Separates video claims, evidence, inference, and risk.
- Guides industry-chain analysis for AI hardware, memory, semiconductor
  equipment, capex, and "who pays" order-chain claims.

## Main Use Cases

- "Get the full subtitles from this Douyin video."
- "Analyze this video's AI industry-chain logic."
- "Who is the real payer behind all these AI orders?"
- "Is this semiconductor, memory, or equipment rally early, middle, or late
  cycle?"

## Requirements and Limitations

- The video-fetching and transcript-cleaning scripts use the Python 3.9+
  standard library and require no third-party Python packages. The browser
  probe is a read-only piece of JavaScript.
- Fetching from a link requires internet access and a real browser your agent
  can drive, for example Claude Code's browser pane, Claude in Chrome, or a
  Codex browser or computer-use tool. Douyin signs its video-detail API inside
  the browser; this project neither replays nor reverse-engineers those
  signatures. It stops at a captcha and leaves it to the user, and it does not
  bypass login, DRM, or other access controls. Page-layout or anti-abuse changes
  may break the probe; `SKILL.md` describes a fallback that reads the network
  log.
- Burned-in subtitle OCR uses macOS AVFoundation and Vision (macOS 13 or
  later). It works only on macOS and requires no global OCR installation.
- Verified scope: the whole flow ran on macOS with one portrait video
  (Chinese-only subtitles) and one landscape video (bilingual subtitles). The
  Codex browser route and the official-subtitle route are not verified.
- Audio transcription for OCR fallback or cross-checking requires a separately
  available local Whisper CLI or an OpenAI-compatible provider that supports
  audio transcription. These tools are not bundled, and the repository does not
  store API keys.
- macOS Speech may require system privacy permission and is not the default
  subtitle path.

## Script Workflow

Resolve the video id and get the page to open in a browser:

```bash
python3 .agents/skills/douyin-industry-video/scripts/fetch_douyin_video.py \
  "<douyin-url>"
```

Open that page in the browser, run `scripts/douyin_page_probe.js`, and save the
returned JSON as `probe.json`. Then write the metadata and report the file size
(nothing is downloaded yet), and download after confirming:

```bash
python3 .agents/skills/douyin-industry-video/scripts/fetch_douyin_video.py \
  <video-id> --probe-json probe.json --out-dir work/video

python3 .agents/skills/douyin-industry-video/scripts/fetch_douyin_video.py \
  <video-id> --probe-json probe.json --out-dir work/video --download
```

Extract burned-in subtitles from a local video, then clean them into Markdown
and JSON:

```bash
swift .agents/skills/douyin-industry-video/scripts/ocr_burned_subtitles.swift \
  work/video/dy-<video-id>.mp4 work/video/raw.jsonl

python3 .agents/skills/douyin-industry-video/scripts/clean_ocr_subtitles.py \
  work/video/raw.jsonl work/video/transcript.md \
  --json work/video/transcript.json
```

To digest text on data cards and charts, scan the rest of the frame separately:

```bash
swift .agents/skills/douyin-industry-video/scripts/ocr_burned_subtitles.swift \
  work/video/dy-<video-id>.mp4 work/video/screen-raw.jsonl \
  --band 0:0.84 --interval 2

python3 .agents/skills/douyin-industry-video/scripts/clean_ocr_subtitles.py \
  work/video/screen-raw.jsonl work/video/screen.md --screen
```

If a local video is already available, the skill can start at the OCR step and
skip downloading.

## Accuracy, Safety, and Rights Boundaries

- OCR subtitles are machine-derived from burned-in text, not official platform
  transcripts. Proper nouns, numbers, and obvious OCR errors still require
  review against the video and its context. The cleaning script marks unstable
  lines with ⚠.
- If only metadata is available, the result must not be represented as having
  watched or fully transcribed the video.
- Claims that depend on current financials, capex guidance, orders, prices, or
  market moves should be verified against primary sources such as filings and
  earnings materials.
- The skill provides research support, not personalized investment advice or
  buy/sell instructions.
- Process only content you are authorized to access and analyze, and follow the
  platform's rules and applicable law. Do not redistribute downloaded videos,
  transcripts, or other people's personal information without permission.
- Never write secrets, tokens, account data, or private logs into the repository
  or analysis output.

This is an unofficial community tool. It is not affiliated with or endorsed by
Douyin, ByteDance, OpenAI, or any other platform or company mentioned. Their
names and trademarks belong to their respective owners.

This repository currently provides no license file. Public visibility should
not be interpreted as automatic permission to copy, redistribute, or use the
work commercially.
