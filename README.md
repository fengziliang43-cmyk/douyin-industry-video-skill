# 抖音产业视频分析技能

**中文** | [English](README_EN.md)

这是一个 Codex 技能：从抖音等短视频链接或本地视频中提取元数据与字幕，
再用中文分析其中的投资观点和产业链逻辑。它是供 Codex 调用的技能源码，
不是独立桌面软件或一键式视频下载器。

技能目录：

```text
.agents/skills/douyin-industry-video
```

## 能做什么

- 解析抖音 reflow 页面，读取页面公开提供的元数据和视频地址。
- 使用 macOS Vision OCR 提取画面中已经烧录的中文字幕。
- 对重复 OCR 帧去重，输出 Markdown 和 JSON 字幕。
- 按“视频主张 → 证据 → 推断 → 风险”的结构分析观点。
- 梳理 AI 硬件、存储、半导体设备、资本开支和“订单最终由谁付款”等
  产业链问题。

## 主要使用场景

- “提取这个抖音视频的完整字幕。”
- “分析视频里的 AI 产业链逻辑。”
- “这些 AI 订单背后真正付款的是谁？”
- “半导体、存储或设备行情处于周期早期、中期还是后期？”

## 运行条件与限制

- 页面获取和字幕清理脚本使用 Python 3 标准库，不需要安装 Python
  第三方包。
- 烧录字幕 OCR 使用 macOS 的 AVFoundation 与 Vision，只能在 macOS
  上运行，不需要全局安装额外 OCR 软件。
- 从链接获取视频需要联网，而且抖音页面必须公开 `play_addr`。页面结构、
  访问限制或风控变化都可能导致解析失败；本项目不会绕过登录、DRM 或其他
  访问控制。
- 如果要用音频转写补充或核对 OCR，需要另行提供本地 Whisper CLI，或支持
  音频转写的 OpenAI 兼容服务。本仓库不捆绑这些工具，也不保存 API 密钥。
- macOS Speech 可能要求系统隐私权限，并且不是默认字幕路径。

## 脚本流程

从可访问的抖音链接获取视频和元数据：

```bash
python3 .agents/skills/douyin-industry-video/scripts/fetch_douyin_video.py \
  "<douyin-url>" --out-dir work/video
```

从本地视频提取烧录字幕，再清理为 Markdown 和 JSON：

```bash
swift .agents/skills/douyin-industry-video/scripts/ocr_burned_subtitles.swift \
  work/video/douyin-video.mp4 work/video/raw.jsonl 1

python3 .agents/skills/douyin-industry-video/scripts/clean_ocr_subtitles.py \
  work/video/raw.jsonl work/video/transcript.md \
  --json work/video/transcript.json
```

也可以直接把已有的本地视频交给技能，从 OCR 步骤开始，不必重复下载。

## 准确性、安全与权利边界

- OCR 字幕是机器从画面提取的结果，不是平台官方字幕；专有名词、数字和
  明显错字仍需结合视频和上下文复核。
- 只有元数据、没有完整视频或字幕时，不能把结果表述为“已观看”或“已完整
  转写”。
- 涉及近期财务数据、资本开支、订单、价格或行情时，应再核对公司公告、
  财报等一手资料。
- 本技能只提供研究辅助，不构成个性化投资建议，也不提供买卖指令。
- 只处理你有权访问和分析的内容，并遵守平台规则与适用法律；不要未经授权
  再发布下载的视频、字幕或他人个人信息。
- 不要把密钥、令牌、账户数据或私人日志写入仓库或分析输出。

本项目是非官方社区工具，与抖音、字节跳动、OpenAI 或其他被提及的平台和
公司没有隶属、授权或背书关系；相关名称和商标归各自权利人所有。

本仓库目前没有提供许可证文件，请勿把公开可见理解为已自动获得复制、
再发布或商用授权。
