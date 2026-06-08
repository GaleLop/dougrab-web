"""
Chrome 浏览器管理服务 — 使用 Playwright 替代 Windows ctypes
负责 Chrome 实例的启动、管理、Cookie 注入等
"""
import asyncio
import logging
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from app.core.config import CHROME_HEADLESS

logger = logging.getLogger(__name__)


class ChromeManager:
    """Playwright Chrome 实例管理器"""

    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._douyin_page: Optional[Page] = None
        self._lock = asyncio.Lock()

    @property
    def is_ready(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    @property
    def has_douyin_page(self) -> bool:
        return self._douyin_page is not None and not self._douyin_page.is_closed()

    async def start(self):
        """启动 Playwright + Chromium"""
        async with self._lock:
            if self.is_ready:
                return
            try:
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=CHROME_HEADLESS,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--single-process",
                    ],
                )
                self._context = await self._browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"
                    ),
                    locale="zh-CN",
                )
                # 注入反检测脚本
                await self._context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                """)
                logger.info("Chrome started (headless=%s)", CHROME_HEADLESS)
            except Exception as e:
                logger.error("Failed to start Chrome: %s", e)
                raise

    async def stop(self):
        """关闭所有 Chrome 实例"""
        async with self._lock:
            if self._douyin_page and not self._douyin_page.is_closed():
                await self._douyin_page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            self._douyin_page = None
            self._context = None
            self._browser = None
            self._playwright = None
            logger.info("Chrome stopped")

    async def restart(self):
        """重启 Chrome"""
        await self.stop()
        await self.start()

    async def open_douyin(self) -> bool:
        """打开抖音页面"""
        async with self._lock:
            if not self.is_ready:
                await self.start()
            try:
                if self._douyin_page and not self._douyin_page.is_closed():
                    await self._douyin_page.bring_to_front()
                    return True
                self._douyin_page = await self._context.new_page()
                await self._douyin_page.goto(
                    "https://www.douyin.com/",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                logger.info("Douyin page opened")
                return True
            except Exception as e:
                logger.error("Failed to open douyin: %s", e)
                return False

    async def check_logged_in(self) -> bool:
        """检查抖音登录状态"""
        if not self.has_douyin_page:
            return False
        try:
            result = await self._douyin_page.evaluate(
                'document.cookie.includes("sessionid_ss") || '
                'document.cookie.includes("passport_csrf_token")'
            )
            return bool(result)
        except Exception:
            return False

    async def get_douyin_page(self) -> Optional[Page]:
        """获取当前抖音页面对象（用于数据抓取）"""
        if not self.has_douyin_page:
            await self.open_douyin()
        return self._douyin_page

    async def inject_cookies(self, cookies: list[dict]) -> bool:
        """注入 Cookie 到浏览器上下文"""
        if not self.is_ready:
            await self.start()
        try:
            await self._context.add_cookies(cookies)
            logger.info("Injected %d cookies", len(cookies))
            return True
        except Exception as e:
            logger.error("Failed to inject cookies: %s", e)
            return False

    async def get_cookies(self) -> list[dict]:
        """获取当前 Cookie"""
        if not self._context:
            return []
        try:
            return await self._context.cookies()
        except Exception:
            return []

    async def get_status(self) -> dict:
        """获取 Chrome 和抖音状态"""
        logged_in = False
        has_douyin = self.has_douyin_page
        if has_douyin:
            logged_in = await self.check_logged_in()
        return {
            "cdp_ready": self.is_ready,
            "chrome_running": self.is_ready,
            "logged_in": logged_in,
            "has_douyin": has_douyin,
        }


# 全局单例
chrome_manager = ChromeManager()
