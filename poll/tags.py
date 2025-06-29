import aiohttp
import asyncio
import json
import os
from datetime import datetime
from utils import *

TAG_API_URL = "https://api.bilibili.com/x/web-interface/view/detail/tag"

async def get_tags(bvid: str):
    headers = cookie_header(load_cookies())
    async with aiohttp.ClientSession(headers=headers) as session:  
        try:
            async with session.get(TAG_API_URL, params={'bvid': bvid}) as response:
                response.raise_for_status()
                response_json = await response.json()
                tags_arr = response_json['data']
                return tags_arr
        except aiohttp.ClientError as e:
            print(f"[{datetime.now()}] 网络请求错误: {e}")
            return None
        except json.JSONDecodeError:
            print(f"[{datetime.now()}] API响应不是有效的JSON格式。")
            return None
        except Exception as e:
            print(f"[{datetime.now()}] 获取推荐列表时发生意外错误: {e}")
            return None
    
if __name__ == '__main__':
    asyncio.run(get_tags('BV1rXKFzBE9y'))