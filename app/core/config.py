"""
DouGrab Web 配置
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)
FRONTEND_DIR = BASE_DIR / "frontend"

CHROME_HEADLESS = os.getenv("CHROME_HEADLESS", "true").lower() == "true"
CHROME_TIMEOUT = int(os.getenv("CHROME_TIMEOUT", "1800000"))
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("PORT", os.getenv("API_PORT", "8765")))
REQUEST_TIMEOUT = 1800
MAX_RETRIES = 3
PAGE_SIZE = 35
MAX_PAGES = 50
