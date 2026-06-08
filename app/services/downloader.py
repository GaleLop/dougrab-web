"""
视频下载服务 — 代理下载 + 本地存储（MVP 阶段）
后续可替换为 OSS/S3 对象存储
"""
import asyncio
import logging
from pathlib import Path

import httpx

from app.core.config import DOWNLOADS_DIR, REQUEST_TIMEOUT
from app.services.scraper import refresh_video_url

logger = logging.getLogger(__name__)

DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.douyin.com/",
    "Accept": "*/*",
}


async def download_video(aweme_id: str, cdn_url: str = "") -> dict:
    """
    下载单个视频到本地 downloads 目录
    如果没有 cdn_url，先通过 refresh_video_url 获取
    """
    if not cdn_url:
        cdn_url = await refresh_video_url(aweme_id)
    if not cdn_url:
        return {"aweme_id": aweme_id, "status": "fail", "error": "无法获取CDN链接"}

    filename = f"{aweme_id}.mp4"
    filepath = DOWNLOADS_DIR / filename

    try:
        async with httpx.AsyncClient(
            headers=DOWNLOAD_HEADERS,
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        ) as client:
            resp = await client.get(cdn_url)
            if resp.status_code != 200 or len(resp.content) < 1000:
                return {
                    "aweme_id": aweme_id,
                    "status": "fail",
                    "error": f"下载失败 (HTTP {resp.status_code}, {len(resp.content)} bytes)",
                }
            filepath.write_bytes(resp.content)
            return {
                "aweme_id": aweme_id,
                "status": "ok",
                "filepath": str(filepath),
                "size": len(resp.content),
            }
    except Exception as e:
        logger.error("Download failed for %s: %s", aweme_id, e)
        return {"aweme_id": aweme_id, "status": "fail", "error": str(e)}


async def download_batch(aweme_ids: list[str]) -> dict:
    """批量下载视频，逐个刷新 CDN 并保存"""
    results = []
    for idx, aid in enumerate(aweme_ids):
        logger.info("Downloading %d/%d: %s", idx + 1, len(aweme_ids), aid)
        result = await download_video(aid)
        results.append(result)
        if idx < len(aweme_ids) - 1:
            await asyncio.sleep(1.5)

    ok = sum(1 for r in results if r["status"] == "ok")
    fail = sum(1 for r in results if r["status"] == "fail")
    return {
        "ok": ok,
        "fail": fail,
        "results": results,
        "save_dir": str(DOWNLOADS_DIR),
    }


async def stream_download(aweme_id: str, cdn_url: str = ""):
    """
    流式下载，用于 API 直接返回视频流给前端
    返回 AsyncGenerator
    """
    if not cdn_url:
        cdn_url = f"https://www.douyin.com/aweme/v1/play/?video_id={aweme_id}&ratio=1080p"

    async with httpx.AsyncClient(
        headers=DOWNLOAD_HEADERS,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    ) as client:
        async with client.stream("GET", cdn_url) as resp:
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")
            async for chunk in resp.aiter_bytes(chunk_size=65536):
                yield chunk
