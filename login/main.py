import aiohttp
from aiohttp import web
import asyncio
import os
import json
from datetime import datetime, timedelta
import qrcode
import io
from urllib.parse import urlparse, parse_qs

# --- 全局变量和配置 ---
sessions = {}

QR_GEN_API = "http://passport.bilibili.com/x/passport-login/web/qrcode/generate"
QR_POLL_API = "http://passport.bilibili.com/x/passport-login/web/qrcode/poll"

from utils import DEFAULT_HEADERS

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com/"
}

# 定义Cookie存储目录
COOKIES_DIR = "cookies"

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
                    "expires_time": datetime.now() + timedelta(seconds=qr_data.get('expire_seconds', 60)),
                    "status": "pending",
                    "cookie_data": None,
                    "poll_task": None 
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
    当登录成功时，直接从B站返回的URL中解析出Cookie并保存。
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
    # 如果会话已经成功登录，直接返回存储的最终Cookie
    if session_info['status'] == 'success' and session_info.get('final_cookies'):
        # 构造一个符合前端预期的成功响应，包含已获取的cookies
        return web.json_response({
            "code": 0, 
            "message": "OK", 
            "data": {
                "url": "logged_in", # 此时url不再需要，给个占位符
                "refresh_token": session_info['cookie_data'].get('refresh_token', 'n/a'), 
                "timestamp": int(datetime.now().timestamp()),
                "extracted_cookies": session_info['final_cookies'] # 额外返回提取到的cookies
            }
        })
    poll_params = {
        "qrcode_key": qrcode_key
    }
    print(f"[{datetime.now()}] Polling QR status for key: {qrcode_key}")
    async with aiohttp.ClientSession() as session:
        try:
            poll_res = await fetch_json(session, QR_POLL_API, params=poll_params)
            print(f"[{datetime.now()}] QR Poll API response for {qrcode_key}: {poll_res}")
            bili_data = poll_res.get('data', {})
            bili_status_code = bili_data.get('code')
            bili_status_message = bili_data.get('message', '未知状态')
            
            # 初始化一个字典用于存储最终提取的Cookie
            extracted_cookies = {}
            if bili_status_code == 0: # 成功登录
                session_info['status'] = 'success'
                session_info['cookie_data'] = bili_data # B站API返回的data字段，包含url(最终登录url)和refresh_token
                print(f"[{datetime.now()}] User logged in successfully for key: {qrcode_key}")
                
                # ==== 核心修改：从URL中直接解析Cookie START ====
                redirect_url = bili_data.get('url')
                if redirect_url:
                    parsed_url = urlparse(redirect_url)
                    query_params = parse_qs(parsed_url.query)
                    
                    # 提取SESSDATA, bili_jct, DedeUserID, DedeUserID__ckMd5
                    # 注意：parse_qs 返回的字典，值是列表，需要取第一个元素
                    if 'SESSDATA' in query_params:
                        extracted_cookies['SESSDATA'] = query_params['SESSDATA'][0]
                    if 'bili_jct' in query_params:
                        extracted_cookies['bili_jct'] = query_params['bili_jct'][0]
                    if 'DedeUserID' in query_params:
                        extracted_cookies['DedeUserID'] = query_params['DedeUserID'][0]
                    if 'DedeUserID__ckMd5' in query_params:
                        extracted_cookies['DedeUserID__ckMd5'] = query_params['DedeUserID__ckMd5'][0]
                    
                    # refresh_token也直接从bili_data中获取
                    if 'refresh_token' in bili_data:
                        extracted_cookies['refresh_token'] = bili_data['refresh_token']
                    
                    # 将提取到的cookies存入session_info
                    session_info['final_cookies'] = extracted_cookies
                    print(f"[{datetime.now()}] Successfully extracted cookies from URL for key {qrcode_key}: {extracted_cookies}")
                    # 保存Cookie到文件
                    cookie_file_path = os.path.join(COOKIES_DIR, "bilibili_cookies.json")
                    try:
                        with open(cookie_file_path, 'w', encoding='utf-8') as f:
                            json.dump(extracted_cookies, f, indent=4, ensure_ascii=False)
                        print(f"[{datetime.now()}] Cookies saved to: {cookie_file_path}")
                    except Exception as e:
                        print(f"[{datetime.now()}] Failed to save cookies to file: {e}")
                else:
                    print(f"[{datetime.now()}] Login successful but no redirect URL found for key: {qrcode_key}")
                # ==== 核心修改：从URL中直接解析Cookie END ====
                # 返回给前端的响应，包含提取到的cookies
                return web.json_response({
                    "code": bili_status_code, 
                    "message": bili_status_message,
                    "data": {**bili_data, "extracted_cookies": extracted_cookies} # 将提取的cookies添加到data中返回给前端
                })
            elif bili_status_code == 86090: # 已扫码，待确认
                session_info['status'] = 'scanned'
                print(f"[{datetime.now()}] QR code scanned, waiting for confirmation for key: {qrcode_key}")
                return web.json_response({
                    "code": bili_status_code, 
                    "message": bili_status_message,
                    "data": bili_data
                })
            elif bili_status_code == 86101: # 未扫码
                session_info['status'] = 'pending' # 明确设置为pending
                print(f"[{datetime.now()}] QR code not scanned yet for key: {qrcode_key}")
                return web.json_response({
                    "code": bili_status_code, 
                    "message": bili_status_message,
                    "data": bili_data
                })
            elif bili_status_code == 86038: # 二维码已失效或过期
                session_info['status'] = 'expired'
                sessions.pop(qrcode_key, None)
                print(f"[{datetime.now()}] QR code expired for key: {qrcode_key}")
                return web.json_response({
                    "code": bili_status_code, 
                    "message": bili_status_message,
                    "data": bili_data
                })
            else: # 其他未知状态
                print(f"[{datetime.now()}] Unexpected QR poll status code {bili_status_code} for key {qrcode_key}: {bili_status_message}")
                sessions.pop(qrcode_key, None) 
                return web.json_response({
                    "code": bili_status_code, 
                    "message": bili_status_message,
                    "data": bili_data
                })
        except aiohttp.ClientError as e:
            print(f"[{datetime.now()}] ClientError polling QR status for {qrcode_key}: {e}")
            return web.json_response({"message": f"Network error polling QR status: {e}", "code": -101}, status=503)
        except Exception as e:
            print(f"[{datetime.now()}] Unexpected error polling QR status for {qrcode_key}: {e}")
            return web.json_response({"message": f"Server error: {e}", "code": -102}, status=500)

# --- Aiohttp 应用启动和命令行接口 ---
async def start_web_server():
    app = web.Application()
    app.router.add_get('/', serve_index_page)
    app.router.add_get('/generate_qrcode', generate_qrcode_handler)
    app.router.add_get('/qrcode_image', serve_qrcode_image)
    app.router.add_get('/check_scan', check_scan_status)
    # 移除 finish_login 路由
    # app.router.add_post('/finish_login', finish_login_handler) 
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8080)
    await site.start()
    os.makedirs(COOKIES_DIR, exist_ok=True) 
    print("-------------------------------------------------------")
    print("B站扫码登录服务已启动，请在浏览器中访问:")
    print("http://localhost:8080")
    print("等待登录成功...")
    print(f"登录成功后，Cookie将保存到 '{COOKIES_DIR}/bilibili_cookies.json'")
    print("-------------------------------------------------------")
    try:
        while True:
            await asyncio.sleep(1)
            
            successful_session = None
            for qrcode_key, info in list(sessions.items()): 
                if info['status'] == 'success' and 'final_cookies' in info and info['final_cookies']:
                    successful_session = info
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
                
                cookie_file_path = os.path.join(COOKIES_DIR, "bilibili_cookies.json")
                print(f"\nCookie已保存到文件: {cookie_file_path}")
                print("您现在可以基于这些登录信息进行后续B站操作了。")
                print("-------------------------------------------------------")
                break 
            
    except asyncio.CancelledError:
        print("\n服务器已停止.")
    except Exception as e:
        print(f"\n服务器发生意外错误: {e}")
    finally:
        await runner.cleanup()
# --- 主入口 ---
if __name__ == "__main__":
    try:
        asyncio.run(start_web_server())
    except KeyboardInterrupt:
        print("\n程序被用户中断，退出。")
