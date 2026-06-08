"""
抖音视频数据抓取服务 — 使用 Playwright page.evaluate 替代 CDP WebSocket
保留原有的 JS 注入抓取逻辑，适配为 Playwright 异步调用
"""
import asyncio
import json
import logging
import random
import re
from typing import Optional

from app.services.chrome_manager import chrome_manager
from app.core.config import PAGE_SIZE, MAX_PAGES

logger = logging.getLogger(__name__)


def _sanitize(s: str) -> str:
    """移除 JSON 非法控制字符"""
    if not s:
        return ""
    return re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', str(s))


async def fetch_videos(sec_uid: str) -> dict:
    """
    通过 Playwright 从抖音页面提取指定用户的视频数据
    等价于原 main.py 的 _fetch_videos()，但用 page.evaluate 替代 CDP WebSocket
    """
    page = await chrome_manager.get_douyin_page()
    if not page:
        raise Exception("Chrome 未就绪，请先打开抖音页面")

    # 模拟人类随机延迟
    await asyncio.sleep(random.uniform(0.5, 2.0))

    # Step 1: 尝试从 SSR/DOM 获取初始数据
    dom_script = '''
    () => {
        var r = {videos:[], source:'none'};
        try {
            var app = window.SSR_RENDER_DATA && window.SSR_RENDER_DATA.app;
            if (app && app.user && app.user.user_post_data) {
                var list = app.user.user_post_data.aweme_list || [];
                if (list.length) {
                    r.videos = list.map(function(a) {
                        return {
                            aweme_id: a.aweme_id,
                            desc: a.desc || '',
                            create_time: a.create_time || 0,
                            duration: a.duration || 0,
                            statistics: a.statistics || {},
                            video: a.video || {}
                        };
                    });
                    r.source = 'SSR';
                    return r;
                }
            }
        } catch(e) {}
        var links = document.querySelectorAll('a[href*="/video/"]');
        var seen = {};
        links.forEach(function(a) {
            var m = a.href && a.href.match(/\\/video\\/(\\d+)/);
            if (m && !seen[m[1]]) {
                seen[m[1]] = true;
                var desc = (a.textContent || '').trim().slice(0, 200);
                var img = a.querySelector('img');
                var cover = img ? (img.src || img.getAttribute('src') || '') : '';
                r.videos.push({aweme_id: m[1], desc: desc, cover: cover});
            }
        });
        if (r.videos.length) { r.source = 'DOM'; return r; }
        return r;
    }
    '''
    await asyncio.sleep(random.uniform(2, 4))
    extracted = await page.evaluate(dom_script)
    dom_videos = extracted.get("videos", [])
    source = extracted.get("source", "none")

    # Step 2: 通过 fetch API 翻页抓取所有视频
    await asyncio.sleep(random.uniform(1.0, 2.5))
    all_videos = []
    max_cursor = 0
    has_more = True
    page_count = 0

    while has_more and page_count < MAX_PAGES:
        page_count += 1
        if page_count > 1:
            await asyncio.sleep(random.uniform(1.5, 3.0))

        api_data = None
        for retry in range(3):
            if retry > 0:
                await asyncio.sleep(4)
            fetch_script = f'''
            async () => {{
                try {{
                    const resp = await fetch(
                        'https://www.douyin.com/aweme/v1/web/aweme/post/?sec_user_id={sec_uid}&count={PAGE_SIZE}&max_cursor={max_cursor}&aid=6383',
                        {{credentials: 'include'}}
                    );
                    const text = await resp.text();
                    return text;
                }} catch(e) {{
                    return '';
                }}
            }}
            '''
            raw = await page.evaluate(fetch_script)
            if raw:
                try:
                    api_data = json.loads(raw)
                    sc = api_data.get("status_code")
                    if sc and sc != 0:
                        api_data = None
                except (json.JSONDecodeError, TypeError):
                    api_data = None
            if api_data and api_data.get("aweme_list"):
                break

        if not api_data or not api_data.get("aweme_list"):
            break

        all_videos.extend(api_data["aweme_list"])
        has_more = api_data.get("has_more", False)
        max_cursor = api_data.get("max_cursor", 0)
        if not has_more or max_cursor == 0:
            break

    # Step 3: 去重
    seen_ids = set()
    videos = []
    for v in all_videos:
        aid = str(v.get("aweme_id", ""))
        if aid and aid not in seen_ids:
            seen_ids.add(aid)
            videos.append(v)

    if videos:
        source = "fetch+paginated"
    elif dom_videos:
        videos = dom_videos
        source = "DOM"
    else:
        raise Exception(
            "No videos found. 请先在 Chrome 中打开用户页面，等待视频加载后重试。"
        )

    # Step 4: 构建返回数据
    aweme_list = []
    for v in videos:
        aid = v.get("aweme_id", "")
        if not aid:
            continue
        vid = v.get("video", {}) or {}
        cover = vid.get("cover", {}) or {}
        play_addr = vid.get("play_addr", {}) or {}
        play_urls = play_addr.get("url_list", [])
        dl_url = (
            play_urls[0]
            if play_urls
            else f"https://www.douyin.com/aweme/v1/play/?video_id={aid}&ratio=1080p"
        )
        cover_urls = cover.get("url_list", [])
        raw_cover = v.get("cover", "")
        cover_url = (
            cover_urls[0]
            if cover_urls
            else (
                raw_cover
                if raw_cover
                else f"https://www.douyin.com/aweme/v1/web/cover/?aweme_id={aid}&s=0"
            )
        )
        aweme_list.append({
            "aweme_id": aid,
            "desc": _sanitize(v.get("desc", "")),
            "create_time": v.get("create_time", 0),
            "duration": v.get("duration", 0),
            "video": {
                "play_addr": {"url_list": [dl_url]},
                "cover": {"url_list": [cover_url]},
                "duration": v.get("duration", 0),
            },
        })

    return {
        "aweme_list": aweme_list,
        "has_more": False,
        "total": len(aweme_list),
        "source": source,
    }


async def refresh_video_url(aweme_id: str) -> str:
    """
    实时从抖音页面获取视频最新 CDN 地址
    等价于原 main.py 的 _refresh_video_url()
    """
    page = await chrome_manager.get_douyin_page()
    if not page:
        raise Exception("Chrome 未就绪")

    script = f'''
    async () => {{
        try {{
            const resp = await fetch(
                'https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={aweme_id}&aid=6383',
                {{credentials: 'include'}}
            );
            const data = await resp.json();
            const aweme = data.aweme_detail || {{}};
            const video = aweme.video || {{}};
            const urls = (video.play_addr || {{}}).url_list || [];
            return urls[0] || '';
        }} catch(e) {{
            return '';
        }}
    }}
    '''
    url = await page.evaluate(script)
    if not url:
        raise Exception("无法获取视频 CDN 地址")
    return url
