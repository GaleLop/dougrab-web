"""
API 路由定义
"""
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pathlib import Path

from app.models.schemas import (
    ParseLinksRequest,
    ParseLinksResponse,
    DownloadBatchRequest,
    InjectCookiesRequest,
)
from app.services.chrome_manager import chrome_manager
from app.services.scraper import fetch_videos, refresh_video_url
from app.services.downloader import download_video, download_batch, stream_download
from app.services.link_parser import parse_links
from app.core.config import DOWNLOADS_DIR

VERSION = "3.2.0-web"

router = APIRouter(prefix="/api")


@router.get("/status")
async def api_status():
    """获取 Chrome 和抖音登录状态"""
    status = await chrome_manager.get_status()
    status["version"] = VERSION
    return status


@router.get("/open_douyin")
async def api_open_douyin():
    """打开抖音页面"""
    ok = await chrome_manager.open_douyin()
    return {"ok": ok}


@router.get("/restart_chrome")
async def api_restart_chrome():
    """重启 Chrome"""
    await chrome_manager.restart()
    return {"ok": True, "msg": "Chrome restarted"}


@router.get("/fetch")
async def api_fetch(sec_uid: str = Query(..., description="用户 sec_uid")):
    """抓取指定用户的所有视频"""
    if not sec_uid:
        raise HTTPException(status_code=400, detail="need sec_uid parameter")
    try:
        result = await fetch_videos(sec_uid)
        return result
    except Exception as e:
        return {"error": str(e)}


@router.get("/refresh_url")
async def api_refresh_url(aweme_id: str = Query(..., description="视频 aweme_id")):
    """刷新视频 CDN 链接"""
    if not aweme_id:
        raise HTTPException(status_code=400, detail="need aweme_id")
    try:
        url = await refresh_video_url(aweme_id)
        return {"url": url}
    except Exception as e:
        return {"error": str(e)}


@router.get("/video_url")
async def api_video_url(aweme_id: str = Query(..., description="视频 aweme_id")):
    """获取视频播放地址（不刷新 CDN）"""
    if not aweme_id:
        raise HTTPException(status_code=400, detail="need aweme_id")
    return {
        "url": f"https://www.douyin.com/aweme/v1/play/?video_id={aweme_id}&ratio=1080p"
    }


@router.get("/download")
async def api_download(
    url: str = Query("", description="CDN 直链"),
    aweme_id: str = Query("", description="视频 aweme_id"),
):
    """代理下载视频 — 流式返回"""
    if not url and not aweme_id:
        raise HTTPException(status_code=400, detail="need url or aweme_id")

    filename = f"{aweme_id}.mp4" if aweme_id else "video.mp4"

    try:
        return StreamingResponse(
            stream_download(aweme_id=aweme_id, cdn_url=url),
            media_type="video/mp4",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Access-Control-Allow-Origin": "*",
            },
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/parse_links")
async def api_parse_links(req: ParseLinksRequest):
    """解析粘贴的视频链接"""
    if not req.links:
        raise HTTPException(status_code=400, detail="need links")

    ids = parse_links(req.links)
    if not ids:
        return {
            "error": "未识别到视频链接，请粘贴类似 https://www.douyin.com/video/xxx 的链接"
        }
    return ParseLinksResponse(aweme_ids=ids, count=len(ids))


@router.post("/download_batch")
async def api_download_batch(req: DownloadBatchRequest):
    """批量下载视频到服务器 downloads 目录"""
    if not req.aweme_ids:
        raise HTTPException(status_code=400, detail="need aweme_ids")
    result = await download_batch(req.aweme_ids)
    return result


@router.post("/inject_cookies")
async def api_inject_cookies(req: InjectCookiesRequest):
    """注入 Cookie（用于云端登录）"""
    ok = await chrome_manager.inject_cookies(req.cookies)
    return {"ok": ok}


@router.get("/cookies")
async def api_get_cookies():
    """获取当前 Cookie"""
    cookies = await chrome_manager.get_cookies()
    return {"cookies": cookies}
