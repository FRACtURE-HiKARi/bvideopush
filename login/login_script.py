import aiohttp
from aiohttp import web
import asyncio
import os
import json
from datetime import datetime, timedelta
import qrcode
import io

# --- 全局变量和配置 ---
sessions = {}

QR_GEN_API = "http://passport.bilibili.com/x/passport-login/web/qrcode/generate"
QR_POLL_API = "http://passport.bilibili.com/x/passport-login/web/qrcode/poll"
COOKIES_DIR = "cookies"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com/"
}

# --- 辅助函数 ---

async def fetch_json(session, url, params=None, headers=None):
    """异步GET请求并解析JSON"""
    final_headers = {**DEFAULT_HEADERS, **(headers or {})}
    async with session.get(url, params=params, headers=final_headers) as response:
        response.raise_for_status()
        return await response.json()

async def fetch_bytes(session, url, params=None, headers=None):
    """异步GET请求并返回字节流"""
    final_headers = {**DEFAULT_HEADERS, **(headers or {})}
    async with session.get(url, params=params, headers=final_headers) as response:
        response.raise_for_status()
        return await response.read()
    
def generate_qrcode_image(data_string: str) -> bytes:
    """
    生成包含给定字符串的二维码图片（PNG格式）的字节数据。
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data_string)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    # 将图片保存到内存中，并获取字节数据
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    return img_byte_arr.getvalue()

# --- Aiohttp Web 路由处理函数 ---

async def serve_index_page(request):
    """
    根路径，直接返回主登录页面。
    """
    current_dir = os.path.dirname(__file__)
    template_path = os.path.join(current_dir, 'templates', 'index.html')
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        return web.Response(text=html_content, content_type='text/html')
    except FileNotFoundError:
        return web.Response(text="<h1>服务器错误: HTML模板文件未找到。</h1>", content_type='text/html', status=500)


async def generate_qrcode_handler(request):
    """
    处理 /generate_qrcode 请求，生成B站二维码信息。
    """
    print(f"[{datetime.now()}] Request to /generate_qrcode received.")
    async with aiohttp.ClientSession() as session:
        try:
            qr_gen_data = await fetch_json(session, QR_GEN_API)
            print(f"[{datetime.now()}] QR Generate API response: {qr_gen_data}")

            if qr_gen_data and qr_gen_data.get('code') == 0 and 'data' in qr_gen_data:
                qr_data = qr_gen_data['data']
                qrcode_key = qr_data['qrcode_key']
                
                # 存储会话信息
                sessions[qrcode_key] = {
                    "qr_data": qr_data,
                    "expires_time": datetime.now() + timedelta(seconds=qr_data.get('expire_seconds', 60)), # 使用API返回的有效期
                    "status": "pending",
                    "cookie_data": None, # 最终的cookie数据
                    "poll_task": None # 用于存储检查任务
                }
                print(f"[{datetime.now()}] QR code generated for key: {qrcode_key}, expires at {sessions[qrcode_key]['expires_time']}")
                return web.json_response({"qrcode_key": qrcode_key})
            else:
                return web.json_response({"message": qr_gen_data.get('message', 'Failed to generate QR code'), "code": qr_gen_data.get('code', -1)}, status=500)
        except aiohttp.ClientError as e:
            print(f"[{datetime.now()}] ClientError generating QR code: {e}")
            return web.json_response({"message": f"Network error generating QR code: {e}"}, status=503)
        except Exception as e:
            print(f"[{datetime.now()}] Unexpected error generating QR code: {e}")
            return web.json_response({"message": f"Server error: {e}"}, status=500)

async def serve_qrcode_image(request):
    """
    提供二维码图片数据。
    不再从B站API下载图片，而是我们自己生成二维码图片。
    """
    qrcode_key = request.query.get('qrcode_key')
    if not qrcode_key or qrcode_key not in sessions:
        print(f"[{datetime.now()}] QR image request with invalid/missing key: {qrcode_key}")
        return web.Response(text="无效的二维码会话或已过期", status=400)
    session_info = sessions.get(qrcode_key)
    
    if session_info['expires_time'] < datetime.now():
        sessions.pop(qrcode_key, None)
        print(f"[{datetime.now()}] QR image request for expired key: {qrcode_key}")
        return web.Response(text="会话已过期", status=404)
    # 核心修改：使用 B站提供的 deep link URL 作为二维码的内容
    bilibili_deep_link_url = session_info['qr_data']['url']
    print(f"[{datetime.now()}] Generating QR image for deep link URL: {bilibili_deep_link_url} for key: {qrcode_key}")
    try:
        image_bytes = generate_qrcode_image(bilibili_deep_link_url)
        print(f"[{datetime.now()}] Successfully generated QR image for key: {qrcode_key}")
        return web.Response(body=image_bytes, content_type='image/png')
    except Exception as e:
        print(f"[{datetime.now()}] Error generating QR image for {qrcode_key}: {e}")
        return web.Response(text=f"Server error generating QR image: {e}", status=500)


async def check_scan_status(request):
    """
    处理 /check_scan 请求，检查B站二维码扫码状态。
    """
    qrcode_key = request.query.get('qrcode_key')
    if not qrcode_key:
        return web.json_response({"message": "qrcode_key is required", "code": -100}, status=400)
    session_info = sessions.get(qrcode_key)
    if not session_info:
        return web.json_response({"message": "QR session expired or not found (maybe already successful)", "code": -1}, status=404)
    if session_info['expires_time'] < datetime.now():
        sessions.pop(qrcode_key, None)
        print(f"[{datetime.now()}] QR code expired during poll for key: {qrcode_key}")
        return web.json_response({"message": "QR code expired", "code": -1})
    if session_info['status'] == 'success':
        # 如果已经成功登录，直接返回成功状态和数据
        return web.json_response({"code": 0, "message": "OK", "data": {"url": session_info['cookie_data'].get('url', 'already_logged_in'), "refresh_token": session_info['cookie_data'].get('refresh_token', 'n/a'), "timestamp": int(datetime.now().timestamp())}})
    poll_params = {
        "qrcode_key": qrcode_key
    }
    print(f"[{datetime.now()}] Polling QR status for key: {qrcode_key}")
    async with aiohttp.ClientSession() as session:
        try:
            poll_res = await fetch_json(session, QR_POLL_API, params=poll_params)
            print(f"[{datetime.now()}] QR Poll API response for {qrcode_key}: {poll_res}")
            # === 核心修改部分 START ===
            # 获取B站API返回的data字段中的code和message，这才是真正的扫码状态
            bili_data = poll_res.get('data', {})
            bili_status_code = bili_data.get('code')
            bili_status_message = bili_data.get('message', '未知状态')
            # 这里根据B站文档来判断
            # 0: 成功登录 (此时data中会有url和refresh_token)
            # 86038: 已扫码，待确认
            # 86090: 未扫码
            # 86101: 二维码已失效 (或过期)
            # 根据B站官方文档，这里外层code基本都是0，真正状态在data.code
            
            # 由于前端需要 code, message, data 这样的结构来判断，所以我们构造一个相似的响应
            response_to_frontend = {
                "code": bili_status_code, # 将B站内部的code作为我们返回给前端的code
                "message": bili_status_message,
                "data": bili_data
            }
            if bili_status_code == 0: # 成功登录
                session_info['status'] = 'success'
                session_info['cookie_data'] = bili_data # B站API返回的data字段，包含url(最终登录url)和refresh_token
                print(f"[{datetime.now()}] User logged in successfully for key: {qrcode_key}")
                return web.json_response(response_to_frontend)
            elif bili_status_code == 86038: # 已扫码，待确认
                session_info['status'] = 'scanned'
                print(f"[{datetime.now()}] QR code scanned, waiting for confirmation for key: {qrcode_key}")
                return web.json_response(response_to_frontend)
            elif bili_status_code == 86090: # 未扫码
                print(f"[{datetime.now()}] QR code not scanned yet for key: {qrcode_key}")
                return web.json_response(response_to_frontend)
            elif bili_status_code == 86101: # 二维码已失效或过期
                session_info['status'] = 'expired'
                sessions.pop(qrcode_key, None)
                print(f"[{datetime.now()}] QR code expired for key: {qrcode_key}")
                return web.json_response(response_to_frontend)
            else: # 其他未知状态
                print(f"[{datetime.now()}] Unexpected QR poll status code {bili_status_code} for key {qrcode_key}: {bili_status_message}")
                sessions.pop(qrcode_key, None) # 认为这是一个无效或已结束的会话
                return web.json_response(response_to_frontend) # 返回B站的原始响应，让前端处理
            # === 核心修改部分 END ===
        except aiohttp.ClientError as e:
            print(f"[{datetime.now()}] ClientError polling QR status for {qrcode_key}: {e}")
            return web.json_response({"message": f"Network error polling QR status: {e}", "code": -101}, status=503)
        except Exception as e:
            print(f"[{datetime.now()}] Unexpected error polling QR status for {qrcode_key}: {e}")
            return web.json_response({"message": f"Server error: {e}", "code": -102}, status=500)


async def finish_login_handler(request):
    """
    处理前端发来的包含url_with_token的请求，从中提取完整Cookie。
    """
    data = await request.json()
    url_with_token = data.get('url_with_token')
    
    if not url_with_token:
        print(f"[{datetime.now()}] finish_login: No url_with_token provided.")
        return web.json_response({"success": False, "message": "No url_with_token provided."}, status=400)

    print(f"[{datetime.now()}] Receiving login finish request for URL: {url_with_token[:100]}...")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url_with_token, allow_redirects=True) as response:
                response.raise_for_status()
                
                # 获取最终的Set-Cookie头部
                cookies = {}
                for key, morsel in session.cookie_jar:
                    cookies[key] = morsel.value
                
                if cookies:
                    print(f"[{datetime.now()}] Successfully extracted cookies: {cookies}")
                    # 可以在这里将这些Cookie与某个会话ID关联，以便在命令行中取用
                    # 为了演示，我们将把这些cookie打印到主程序的控制台
                    
                    # 查找哪个会话与此url_with_token相关联，并更新其cookie_data
                    # 注意：url_with_token本身不带qrcode_key，所以这里需要更复杂的匹配逻辑
                    # 简单的办法是，只要有任何成功登录的会话，就用这些cookie更新
                    # 或者前端在post /finish_login时也把qrcode_key带过来
                    # 为了简化，我们假设这是一个全局的登录完成事件
                    for key, info in list(sessions.items()): # 使用list()避免在迭代时修改字典
                        if info['status'] == 'success':
                            info['final_cookies'] = cookies # 存储最终获取到的cookie
                            print(f"[{datetime.now()}] Updated final cookies for session {key}.")
                            break
                    
                    return web.json_response({"success": True, "message": "Cookies extracted.", "cookies": cookies})
                else:
                    print(f"[{datetime.now()}] No cookies extracted from final redirect.")
                    return web.json_response({"success": False, "message": "No cookies extracted from the final redirect."}, status=500)

        except aiohttp.ClientError as e:
            print(f"[{datetime.now()}] ClientError during cookie extraction: {e}")
            return web.json_response({"success": False, "message": f"Network error during cookie extraction: {e}"}, status=503)
        except Exception as e:
            print(f"[{datetime.now()}] Unexpected error during cookie extraction: {e}")
            return web.json_response({"success": False, "message": f"Server error during cookie extraction: {e}"}, status=500)


# --- Aiohttp 应用启动和命令行接口 ---
async def start_web_server():
    os.makedirs(COOKIES_DIR, exist_ok=True)
    app = web.Application()
    app.router.add_get('/', serve_index_page) # 主入口，直接加载主页面
    app.router.add_get('/generate_qrcode', generate_qrcode_handler) # 生成二维码的API
    # 移除了 /qrcode_popup 路由，因为不再弹窗
    app.router.add_get('/qrcode_image', serve_qrcode_image) # 提供二维码图片
    app.router.add_get('/check_scan', check_scan_status) # 检查扫码状态的API
    app.router.add_post('/finish_login', finish_login_handler) # 接收前端的url_with_token并获取Cookie

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8080)
    await site.start()
    print("-------------------------------------------------------")
    print("B站扫码登录服务已启动，请在浏览器中访问:")
    print("http://localhost:8080")
    print("等待登录成功...")
    print("-------------------------------------------------------")

    # 命令行继续操作的部分
    try:
        while True:
            await asyncio.sleep(1) # 每秒检查一次，减少CPU占用
            
            successful_session = None
            for qrcode_key, info in list(sessions.items()): # 遍历拷贝以防修改
                if info['status'] == 'success' and 'final_cookies' in info and info['final_cookies']:
                    successful_session = info
                    # 从sessions中移除这个会话，表示已经处理过
                    sessions.pop(qrcode_key, None)
                    break
            
            if successful_session:
                print("\n")
                print("-------------------------------------------------------")
                print("登录成功！")
                print("获取到的完整Cookie:")
                final_cookies = successful_session['final_cookies']
                for k, v in final_cookies.items():
                    print(f"  {k}: {v}")
                
                print("\n您现在可以基于这些登录信息进行后续B站操作了。")
                print("-------------------------------------------------------")
                # 可以在这里调用其他函数进行后续的命令行操作，例如：
                # await do_some_bilibili_operations(final_cookies)
                # 由于可能只进行一次登录，我们选择退出循环
                break 
            
    except asyncio.CancelledError:
        print("\n服务器已停止.")
    finally:
        await runner.cleanup()

# --- 主入口 ---
if __name__ == "__main__":
    try:
        asyncio.run(start_web_server())
    except KeyboardInterrupt:
        print("\n程序被用户中断，退出。")

