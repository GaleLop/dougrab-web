"""
链接解析服务 — 从多种格式的视频链接中提取 aweme_id
保留原 main.py _api_parse_links 的解析逻辑
"""
import re


def parse_links(raw_text: str) -> list[str]:
    """
    解析粘贴的视频链接，提取 aweme_id 列表
    支持格式:
    - /video/数字 路径模式
    - modal_id=数字 参数模式
    - aweme_id=数字 或 video_id=数字 参数模式
    - 直接粘贴纯数字 aweme_id（每行一个）
    """
    ids = []

    # 1. /video/数字 路径模式
    ids.extend(re.findall(r'/video/(\d+)', raw_text))

    # 2. modal_id=数字 参数模式
    ids.extend(re.findall(r'modal_id=(\d+)', raw_text))

    # 3. aweme_id=数字 或 video_id=数字 参数模式
    ids.extend(re.findall(r'(?:aweme_id|video_id)=(\d+)', raw_text))

    # 4. 直接粘贴纯数字 aweme_id（每行一个，去除空行和注释行）
    for line in raw_text.split('\n'):
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and not stripped.startswith('http'):
            if re.match(r'^\d{15,20}$', stripped):
                ids.append(stripped)

    # 去重，保持顺序
    ids = list(dict.fromkeys(ids))
    return ids
