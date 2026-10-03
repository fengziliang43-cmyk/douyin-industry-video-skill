// Douyin page probe (read-only).
// Evaluate this whole file as one expression inside a real browser tab that has
// https://www.douyin.com/video/<id> fully loaded. It sends no requests: it reads the
// video data the page itself already loaded (React props) and returns a small object.
// Save the returned object as JSON and pass it to fetch_douyin_video.py --probe-json.
(() => {
  const PROBE = 'douyin_page_probe/1';
  const idMatch = location.pathname.match(/\/(?:video|note)\/(\d{15,21})/) || location.search.match(/[?&]modal_id=(\d{15,21})/);
  const id = idMatch ? idMatch[1] : null;
  const base = { probe: PROBE, page_url: location.href, page_title: document.title };
  if (!id) return { ...base, ok: false, error: 'No video id in this URL. Open https://www.douyin.com/video/<id> first.' };

  // The page always carries a hidden verify iframe; only a visible one means a challenge is shown.
  const shown = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 40 && r.height > 40 && cs.display !== 'none' && cs.visibility !== 'hidden';
  };
  const bodyText = (document.body && document.body.innerText || '').slice(0, 5000);
  const challenge = [...document.querySelectorAll('#captcha_container, .captcha_verify_container, iframe[src*="verify"], iframe[src*="captcha"]')].some(shown);
  if (challenge || /拖动.{0,6}滑块|安全验证|请完成验证/.test(bodyText)) {
    return { ...base, ok: false, aweme_id: id, error: 'Douyin is showing a verification/captcha. Ask the user to complete it manually, then reload and rerun. Never automate it.' };
  }

  // Locate the aweme object the page rendered, by walking React fibers from the video area.
  const isTarget = (o) => o && typeof o === 'object' && String(o.awemeId || o.aweme_id || '') === id && o.video && typeof o.video === 'object';
  const depthSeen = new WeakMap();
  const search = (o, depth) => {
    if (!o || typeof o !== 'object' || depth > 4) return null;
    const prev = depthSeen.get(o);
    if (prev !== undefined && prev <= depth) return null;
    depthSeen.set(o, depth);
    if (isTarget(o)) return o;
    for (const k of Object.keys(o)) {
      if (k === 'children' || k === '_owner' || k.startsWith('__react')) continue;
      let v;
      try { v = o[k]; } catch (e) { continue; }
      const found = search(v, depth + 1);
      if (found) return found;
    }
    return null;
  };
  const fiberOf = (el) => {
    const key = Object.keys(el).find((k) => k.startsWith('__reactFiber$') || k.startsWith('__reactInternalInstance$'));
    return key ? el[key] : null;
  };
  const roots = [...document.querySelectorAll('[data-e2e="video-detail"]'), ...document.querySelectorAll('[data-e2e], video, div[id]')];
  let info = null;
  let visited = 0;
  for (const el of roots) {
    for (let f = fiberOf(el), hops = 0; f && hops < 60 && !info; f = f.return, hops++) {
      visited += 1;
      if (f.memoizedProps) info = search(f.memoizedProps, 0);
    }
    if (info || visited > 30000) break;
  }
  if (!info) {
    return { ...base, ok: false, aweme_id: id, error: 'Video data not found in the page. Wait until the player has loaded (close any login popup), then rerun.' };
  }

  const v = info.video || {};
  const stats = info.stats || info.statistics || {};
  const chapterInfo = info.chapterInfo || {};
  const streams = (v.bitRateList || [])
    .filter((b) => String(b.format || b.videoFormat || '').toLowerCase() === 'mp4')
    .map((b) => ({ gear: b.gearName, width: b.width, height: b.height, h265: !!b.isH265, fps: b.fps, size: b.dataSize }))
    .sort((a, b) => (b.size || 0) - (a.size || 0))
    .slice(0, 8);
  const width = v.width || (streams[0] && streams[0].width) || 0;
  const height = v.height || (streams[0] && streams[0].height) || 0;

  // Official / auto caption fields, if Douyin exposes any for this video.
  const subtitleHints = [];
  const hintSeen = new WeakSet();
  const findHints = (o, path, depth) => {
    if (!o || typeof o !== 'object' || depth > 5 || hintSeen.has(o) || subtitleHints.length >= 8) return;
    hintSeen.add(o);
    for (const k of Object.keys(o)) {
      let val;
      try { val = o[k]; } catch (e) { continue; }
      const p = path + '.' + k;
      const nonEmpty = Array.isArray(val) ? val.length > 0 : (val && typeof val === 'object' ? Object.keys(val).length > 0 : !!val);
      if (/^(cla_?info|caption_?infos?|subtitle_?infos?|subtitles?|subtitle_?list)$/i.test(k) && nonEmpty) {
        subtitleHints.push({ path: p, preview: JSON.stringify(val).slice(0, 400) });
      } else if (val && typeof val === 'object') {
        findHints(val, p, depth + 1);
      }
    }
  };
  findHints(info, 'aweme', 0);
  const seoOcr = (info.seoInfo && info.seoInfo.ocrContent) || '';

  return {
    ...base,
    ok: true,
    aweme_id: id,
    media: info.images && info.images.length ? 'images' : 'video',
    desc: info.desc || '',
    item_title: info.itemTitle || '',
    caption: info.caption || '',
    author: { nickname: (info.authorInfo || info.author || {}).nickname || '', uid: String((info.authorInfo || info.author || {}).uid || '') },
    create_time: info.createTime || null,
    duration_ms: v.duration || null,
    statistics: {
      digg_count: stats.diggCount, comment_count: stats.commentCount, collect_count: stats.collectCount,
      share_count: stats.shareCount, recommend_count: stats.recommendCount, play_count: stats.playCount,
    },
    chapter_abstract: chapterInfo.chapterAbstract || '',
    chapters: (chapterInfo.list || []).map((c) => ({ start_ms: c.timestamp, title: c.desc || '', detail: c.detail || '' })),
    video: { uri: v.uri || '', width, height, orientation: width > height ? 'landscape' : (width < height ? 'portrait' : 'square'), default_size: v.dataSize || null },
    streams,
    play_url_fallback: ((v.playAddr || [])[0] || {}).src || '',
    subtitle_hints: subtitleHints,
    seo_ocr_preview: seoOcr.slice(0, 300),
    seo_ocr_length: seoOcr.length,
  };
})()
