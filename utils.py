import os
from datetime import datetime
import json

COOKIES_FILE_PATH = "cookies/bilibili_cookies.json"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "keep-alive"
}

TAG_SET = {'mygo', 'ave', 'mujica', 'gbc', 'girls band cry', 'bang', 'dream', '少女乐团派对', 
           '千早', '爱音', 'anon', '长崎', '素世', '爽世', 'soyo', '高松', '灯', '要', '乐奈', '椎名', '立希',
           '丰川', '祥子', 'saki', '三角', '初华', '若叶', '睦', '八幡', '海铃', '祐天寺', '若麦', '喵梦'}

def load_cookies(file_path = COOKIES_FILE_PATH):
    """
    从JSON文件加载Cookie。
    """
    if not os.path.exists(file_path):
        print(f"[{datetime.now()}] Cookie文件未找到: {file_path}")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        return cookies
    except json.JSONDecodeError as e:
        print(f"[{datetime.now()}] Cookie文件解析失败 (JSON格式错误): {e}")
        return None
    except Exception as e:
        print(f"[{datetime.now()}] 加载Cookie文件时发生错误: {e}")
        return None
    
def cookie_header(cookies):
    cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
    request_headers = DEFAULT_HEADERS.copy()
    request_headers['Cookie'] = cookie_str
    return request_headers
