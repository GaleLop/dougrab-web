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
        self._start_error: Optional[str] = None
        self._retry_count: int = 0

    @property
    def is_ready(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    @property
    def has_douyin_page(self) -> bool:
        return self._douyin_page is not None and not self._douyin_page.is_closed()

    async def _cleanup_unlocked(self):
        """清理资源（调用时已持有 _lock 或在 start 异常路径中）"""
        try:
            if self._douyin_page and not self._douyin_page.is_closed():
                await self._douyin_page.close()
        except Exception:
            pass
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._douyin_page = None
        self._context = None
        self._browser = None
        self._playwright = None

    async def start(self):
        """启动 Playwright + Chromium"""
        async with self._lock:
            # 必须 browser + context 都正常才算就绪
            if self.is_ready and self._context is not None:
                return
            # 先清理上次残留的资源（防止重试时泄漏）
            await self._cleanup_unlocked()
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
                self._start_error = None
                self._retry_count = 0
                logger.info("Chrome started (headless=%s)", CHROME_HEADLESS)
            except Exception as e:
                # 启动失败时清理已分配的资源
                await self._cleanup_unlocked()
                self._start_error = str(e)
                self._retry_count += 1
                logger.error("Failed to start Chrome: %s", e)
                raise

    async def stop(self):
        """关闭所有 Chrome 实例"""
        async with self._lock:
            await self._cleanup_unlocked()
            logger.info("Chrome stopped")

    async def restart(self):
        """重启 Chrome"""
        await self.stop()
        await self.start()

    async def open_douyin(self) -> bool:
        """打开抖音页面，崩溃时自动重启并重试一次"""
        for attempt in range(2):
            if not self.is_ready or self._context is None:
                await self.start()
            async with self._lock:
                try:
                    if self._douyin_page and not self._douyin_page.is_closed():
                        try:
                            await self._douyin_page.bring_to_front()
                            return True
                        except Exception:
                            logger.warning("Existing page crashed, recreating...")
                            self._douyin_page = None
                    self._douyin_page = await self._context.new_page()
                    await self._douyin_page.goto(
                        "https://www.douyin.com/",
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                    logger.info("Douyin page opened")
                    return True
                except Exception as e:
                    logger.error("Failed to open douyin (attempt %d): %s", attempt + 1, e)
                    # context/browser 可能崩了，彻底清理
                    self._douyin_page = None
                    try:
                        await self._cleanup_unlocked()
                    except Exception:
                        pass
                    self._browser = None
                    self._context = None
                    self._playwright = None
                    if attempt == 0:
                        logger.info("Restarting Chrome for retry...")
                        continue
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

    async def safe_evaluate(self, script: str, timeout: float = 30.0):
        """安全执行 page.evaluate，页面崩溃时自动恢复并重试一次"""
        page = await self.get_douyin_page()
        if not page:
            raise Exception("Chrome 未就绪")
        try:
            return await asyncio.wait_for(page.evaluate(script), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("page.evaluate timed out after %.0fs", timeout)
            raise Exception(f"page.evaluate 超时 ({timeout}s)")
        except Exception as e:
            err_msg = str(e).lower()
            if "crash" in err_msg or "target closed" in err_msg or "target crashed" in err_msg:
                logger.warning("Page crashed, recovering: %s", e)
                # 重置页面状态，重新打开
                self._douyin_page = None
                await self.restart()
                page = await self.get_douyin_page()
                if not page:
                    raise Exception("Chrome 崩溃后恢复失败")
                return await asyncio.wait_for(page.evaluate(script), timeout=timeout)
            raise

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
            "start_error": self._start_error,
            "retry_count": self._retry_count,
        }


# 全局单例
chrome_manager = ChromeManager()
