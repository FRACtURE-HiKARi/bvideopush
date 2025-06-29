import aiohttp
import asyncio
import json
import os
from datetime import datetime

# --- 配置常量 ---
COOKIES_FILE_PATH = "cookies/bilibili_cookies.json"
RECOMMEND_API_URL = "https://api.bilibili.com/x/web-interface/index/top/feed/rcmd" # B站推荐列表API
OUTPUT_DIR = "api_responses" # 保存API响应的目录

# 默认请求头，模拟浏览器
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "keep-alive"
}

# --- 辅助函数 ---

def load_cookies(file_path):
    """
    从JSON文件加载Cookie。
    """
    if not os.path.exists(file_path):
        print(f"[{datetime.now()}] Cookie文件未找到: {file_path}")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        print(f"[{datetime.now()}] 成功加载Cookie: {file_path}")
        return cookies
    except json.JSONDecodeError as e:
        print(f"[{datetime.now()}] Cookie文件解析失败 (JSON格式错误): {e}")
        return None
    except Exception as e:
        print(f"[{datetime.now()}] 加载Cookie文件时发生错误: {e}")
        return None

async def fetch_bilibili_recommendations(cookies):
    """
    使用提供的Cookie获取B站首页推荐列表。
    """
    if not cookies:
        print(f"[{datetime.now()}] 未提供Cookie，无法获取推荐列表。")
        return None

    # aiohttp的ClientSession可以传入cookies参数，或者通过cookie_jar管理
    # 简单起见，这里直接传入cookies字典，aiohttp会将其转换为相应的Cookie头
    # 但更严谨的做法是构建一个ClientCookieJar并加载这些morsels，尤其是当需要跨域或管理Path/Domain时
    # 对于B站这种，直接传入字典通常也够用，但为了更像浏览器，我们可以手动设置Cookie头
    
    # 方式一: 直接在headers中构建Cookie字符串 (更直接)
    cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
    request_headers = DEFAULT_HEADERS.copy()
    request_headers['Cookie'] = cookie_str
    
    # 方式二: 使用aiohttp的cookie_jar (推荐，更符合HTTP规范)
    # client_session = aiohttp.ClientSession()
    # for k, v in cookies.items():
    #     client_session.cookie_jar.update_cookies({k: v}, response_url=RECOMMEND_API_URL)
    # request_headers = DEFAULT_HEADERS.copy() # 此时headers不再需要手动加Cookie

    print(f"[{datetime.now()}] 正在请求B站推荐列表API: {RECOMMEND_API_URL}")
    print(f"[{datetime.now()}] 使用的Cookie键: {list(cookies.keys())}")

    async with aiohttp.ClientSession() as session:
        try:
            # 使用方式一：直接在headers中传入Cookie字符串
            async with session.get(RECOMMEND_API_URL, headers=request_headers) as response:
                response.raise_for_status() # 检查HTTP状态码，如果不是2xx则抛出异常
                
                api_response_json = await response.json()
                print(f"[{datetime.now()}] B站推荐列表API响应状态码: {response.status}")
                print(f"[{datetime.now()}] B站推荐列表API响应数据（部分）: {str(api_response_json)[:500]}...")

                if api_response_json.get('code') == 0:
                    print(f"[{datetime.now()}] 成功获取B站推荐列表。")
                    return api_response_json
                else:
                    print(f"[{datetime.now()}] 获取推荐列表API返回错误码: {api_response_json.get('code')}")
                    print(f"[{datetime.now()}] 错误信息: {api_response_json.get('message', '无')}")
                    return None
        except aiohttp.ClientError as e:
            print(f"[{datetime.now()}] 网络请求错误: {e}")
            return None
        except json.JSONDecodeError:
            print(f"[{datetime.now()}] API响应不是有效的JSON格式。")
            return None
        except Exception as e:
            print(f"[{datetime.now()}] 获取推荐列表时发生意外错误: {e}")
            return None

def save_data_to_json(data, filename_prefix="bilibili_recommendations"):
    """
    将数据保存为JSON文件。
    """
    if not data:
        print(f"[{datetime.now()}] 没有数据可保存。")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join(OUTPUT_DIR, f"{filename_prefix}_{timestamp}.json")

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"[{datetime.now()}] 推荐列表数据已保存到: {file_path}")
    except Exception as e:
        print(f"[{datetime.now()}] 保存数据到文件时发生错误: {e}")

# --- 主执行函数 ---

async def main():
    print("-------------------------------------------------------")
    print("B站API客户端：获取首页推荐视频列表")
    print("-------------------------------------------------------")

    # 1. 加载Cookie
    cookies = load_cookies(COOKIES_FILE_PATH)
    if not cookies:
        print(f"[{datetime.now()}] 无法继续，请确保 '{COOKIES_FILE_PATH}' 文件存在且内容正确。")
        print("-------------------------------------------------------")
        return

    # 2. 使用Cookie获取推荐列表
    recommendations_data = await fetch_bilibili_recommendations(cookies)

    # 3. 保存数据
    save_data_to_json(recommendations_data)

    print("-------------------------------------------------------")
    print("B站API客户端操作完成。")
    print("-------------------------------------------------------")

# --- 程序入口 ---
if __name__ == "__main__":
    asyncio.run(main())

