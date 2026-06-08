"""
API 请求/响应模型
"""
from pydantic import BaseModel
from typing import Optional


class ParseLinksRequest(BaseModel):
    links: str


class ParseLinksResponse(BaseModel):
    aweme_ids: list[str]
    count: int


class DownloadBatchRequest(BaseModel):
    aweme_ids: list[str]


class InjectCookiesRequest(BaseModel):
    cookies: list[dict]


class VideoInfo(BaseModel):
    aweme_id: str
    desc: str = ""
    create_time: int = 0
    duration: int = 0
    video: Optional[dict] = None


class FetchResponse(BaseModel):
    aweme_list: list[VideoInfo]
    has_more: bool = False
    total: int = 0
    source: str = ""


class StatusResponse(BaseModel):
    cdp_ready: bool
    chrome_running: bool
    logged_in: bool
    has_douyin: bool
    version: str
