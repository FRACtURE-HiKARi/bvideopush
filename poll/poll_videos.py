import asyncio
import aiohttp
from datetime import datetime
from .recommend import fetch_items
from .tags import get_tags
from utils import DEFAULT_HEADERS, TAG_SET

def test_tag(tags):
    for tag in tags:
        for expected in TAG_SET:
            if expected in tag['tag_name'].lower():
                return True
    return False

async def poll_videos(max_videos = 10, max_polls = 10):
    num_polls = 0
    result = []
    try:
        while num_polls < max_polls:
            items = await fetch_items()
            num_polls += 1
            for item in items:
                bvid = item['bvid']
                if test_tag(await get_tags(bvid)):
                    result.append(item['title'] + ' ' + f"https://www.bilibili.com/video/{bvid}")
                    print(f"[{datetime.now()}] {result[-1]}")
                    if len(result) >= max_videos:
                        return result
    except KeyboardInterrupt:
        return result
    return result

async def main():
    results = await poll_videos()
    with open('results.txt', 'w+', encoding='utf-8') as f:
        for line in results:
            f.write(line + '\n')

if __name__ == "__main__":
    asyncio.run(main())