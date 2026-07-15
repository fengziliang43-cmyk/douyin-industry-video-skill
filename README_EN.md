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

- Parses Douyin reflow pages for publicly exposed metadata and video URLs.
- Extracts burned-in Chinese subtitles with macOS Vision OCR.
- Deduplicates repeated OCR frames into Markdown and JSON transcripts.
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

- The page-fetching and transcript-cleaning scripts use the Python 3 standard
  library and require no third-party Python packages.
- Burned-in subtitle OCR uses macOS AVFoundation and Vision. It works only on
  macOS and requires no global OCR installation.
- Fetching from a link requires internet access and a Douyin page that exposes
  `play_addr`. Page-layout, access-policy, or anti-abuse changes may break the
  parser; the project does not bypass login, DRM, or other access controls.
- Audio transcription for OCR fallback or cross-checking requires a separately
  available local Whisper CLI or an OpenAI-compatible provider that supports
  audio transcription. These tools are not bundled, and the repository does not
  store API keys.
- macOS Speech may require system privacy permission and is not the default
  subtitle path.

## Script Workflow

Fetch the video and metadata from an accessible Douyin URL:

```bash
python3 .agents/skills/douyin-industry-video/scripts/fetch_douyin_video.py \
  "<douyin-url>" --out-dir work/video
```

Extract burned-in subtitles from a local video, then clean them into Markdown
and JSON:

```bash
swift .agents/skills/douyin-industry-video/scripts/ocr_burned_subtitles.swift \
  work/video/douyin-video.mp4 work/video/raw.jsonl 1

python3 .agents/skills/douyin-industry-video/scripts/clean_ocr_subtitles.py \
  work/video/raw.jsonl work/video/transcript.md \
  --json work/video/transcript.json
```

If a local video is already available, the skill can start at the OCR step and
skip downloading.

## Accuracy, Safety, and Rights Boundaries

- OCR subtitles are machine-derived from burned-in text, not official platform
  transcripts. Proper nouns, numbers, and obvious OCR errors still require
  review against the video and its context.
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
