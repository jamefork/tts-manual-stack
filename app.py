from fastapi import FastAPI, Form, Request, Depends
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from fastapi import Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import edge_tts
import tempfile
import os
import json
import asyncio
import base64
import uuid
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = FastAPI()

# Cấu hình CORS cho phép Ghost Blog gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://home.pmtl.site"], # Thay "*" bằng tên miền Ghost blog của bạn (VD: "https://myblog.com") để bảo mật hơn
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lấy API KEY từ biến môi trường. Nếu không cấu hình, ứng dụng sẽ không chạy để đảm bảo an toàn.
API_KEY = os.environ.get('TTS_API_KEY')

if not API_KEY:
    raise RuntimeError("Lỗi bảo mật: Chưa cấu hình biến môi trường TTS_API_KEY trên server!")

# --- CẤU HÌNH BẢO MẬT & GOOGLE SHEET ---
# Secret Key cho Session (Bắt buộc)
SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'tts_secret_key_123456')
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# Cấu hình Google Sheet
SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')
SHEET_TAB_NAME = 'Users'

TEMP_DIR = tempfile.gettempdir()

# --- HÀM KIỂM TRA EMAIL (GIỐNG APP CŨ) ---
def get_allowed_emails():
    """Kết nối Google Sheet và lấy danh sách email được phép"""
    try:
        if not SHEET_ID:
            print("Lỗi: Chưa cấu hình biến môi trường GOOGLE_SHEET_ID")
            return []

        private_key = os.environ.get('GOOGLE_PRIVATE_KEY', '').replace('\\n', '\n')
        client_email = os.environ.get('GOOGLE_SERVICE_ACCOUNT_EMAIL', '')
        
        if not private_key or not client_email:
            print("Lỗi: Thiếu biến môi trường Key hoặc Email Service Account")
            return []

        creds_dict = {
            "type": "service_account",
            "project_id": "generic-project",
            "private_key_id": "generic-key-id",
            "private_key": private_key,
            "client_email": client_email,
            "client_id": "generic-client-id",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{client_email}"
        }

        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_TAB_NAME)
        emails = sheet.col_values(1)
        return [e.strip().lower() for e in emails if '@' in e]
    except Exception as e:
        print(f"Lỗi kết nối Google Sheet: {str(e)}")
        return []

def get_image_base64(image_path):
    if os.path.exists(image_path):
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')
    return ""

# --- GIAO DIỆN HTML: LOGIN ---
LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Đăng Nhập - TTS Server</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f4f1ea; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .container { background: white; padding: 40px 30px; border-radius: 12px; box-shadow: 0 8px 30px rgba(0,0,0,0.1); width: 90%; max-width: 400px; text-align: center; border-top: 5px solid #5d4037; }
        h2 { color: #5d4037; margin-bottom: 10px; }
        p { color: #8d6e63; font-style: italic; margin-bottom: 30px; }
        input { width: 100%; padding: 14px; border: 2px solid #e0e0e0; border-radius: 8px; box-sizing: border-box; font-size: 16px; margin-bottom: 20px; outline: none; }
        input:focus { border-color: #5d4037; }
        button { background: #5d4037; color: white; border: none; padding: 16px; border-radius: 8px; cursor: pointer; font-weight: bold; width: 100%; font-size: 16px; transition: 0.3s; }
        button:hover { background: #3e2723; transform: translateY(-1px); }
        .error { color: #c62828; margin-top: 15px; background: #ffebee; padding: 10px; border-radius: 8px; font-size: 0.9em; }
    </style>
</head>
<body>
    <div class="container">
        <h2>Pháp Môn Tâm Linh</h2>
        <p>Vui lòng đăng nhập để sử dụng TTS</p>
        <form action="/login" method="post">
            <input type="email" name="email" placeholder="Nhập địa chỉ Email..." required>
            <button type="submit">Đăng Nhập</button>
        </form>
        ERROR_BLOCK
    </div>
</body>
</html>
"""

# --- GIAO DIỆN HTML: TRANG CHỦ (TTS) ---
HOME_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>TTS Server Pro</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 650px; margin: 40px auto; padding: 20px; 
            background-color: #f0f2f5; color: #333;
        }
        .container {
            background: white; padding: 30px; border-radius: 16px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            position: relative;
        }
        .logout-btn {
            position: absolute; top: 20px; right: 20px;
            font-size: 12px; color: #666; text-decoration: none;
            border: 1px solid #ccc; padding: 5px 10px; border-radius: 15px;
        }
        .logo {
            display: block; margin: 0 auto 20px auto; max-width: 100px;
            border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        h1 { text-align: center; color: #1a1a1a; margin-bottom: 25px; font-size: 22px; }
        
        textarea { 
            width: 100%; height: 200px; margin-bottom: 15px; padding: 15px; 
            border: 2px solid #e1e4e8; border-radius: 10px; font-size: 16px; 
            box-sizing: border-box; resize: vertical; transition: border 0.2s;
        }
        textarea:focus { outline: none; border-color: #007bff; }
        
        select {
            width: 100%; padding: 12px; margin-bottom: 20px; border-radius: 10px;
            border: 2px solid #e1e4e8; background: white; font-size: 15px;
        }
        
        button { 
            width: 100%; padding: 14px; font-size: 16px; font-weight: 600;
            cursor: pointer; background: #007bff; color: white; 
            border: none; border-radius: 10px; transition: all 0.2s;
        }
        button:hover { background: #0056b3; transform: translateY(-1px); }
        button:disabled { background: #ccc; cursor: not-allowed; }

        #progress-container { display: none; margin-top: 25px; }
        .progress-track { width: 100%; background-color: #e9ecef; border-radius: 20px; height: 10px; overflow: hidden; }
        .progress-bar { width: 0%; height: 100%; background-color: #28a745; transition: width 0.3s ease; }
        #status-text { text-align: center; margin-top: 10px; font-size: 14px; color: #666; }
        #download-area { display: none; margin-top: 20px; text-align: center; }
        .download-btn { display: inline-block; padding: 10px 20px; background: #28a745; color: white; text-decoration: none; border-radius: 8px; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <a href="/logout" class="logout-btn">Đăng xuất</a>
        LOGO_HERE
        
        <h1>Pháp Môn Tâm Linh 心靈法門 (TTS)</h1>
        
        <form id="tts-form">
            <label style="font-weight:bold; display:block; margin-bottom:8px;">Chọn giọng đọc:</label>
            <select name="voice" id="voice">
                <option value="vi-VN-HoaiMyNeural">🇻🇳 Hoài My (Nữ - Truyền cảm)</option>
                <option value="vi-VN-NamMinhNeural">🇻🇳 Nam Minh (Nam - Mạnh mẽ)</option>
            </select>
            
            <textarea name="text" id="text-input" placeholder="Nhập văn bản vào đây..."></textarea>
            
            <button type="submit" id="submit-btn">🚀 Bắt đầu chuyển đổi</button>
        </form>

        <div id="progress-container">
            <div class="progress-track">
                <div class="progress-bar" id="progress-bar"></div>
            </div>
            <div id="status-text">Đang khởi tạo...</div>
        </div>

        <div id="download-area">
            <p>✅ Đã xong!</p>
            <audio id="audio-preview" controls style="width: 100%; margin-bottom: 10px;"></audio>
            <br>
            <a id="download-link" class="download-btn" href="#" download>📥 Tải File MP3</a>
        </div>
    </div>

    <script>
        document.getElementById('tts-form').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const text = document.getElementById('text-input').value.trim();
            const voice = document.getElementById('voice').value;
            const btn = document.getElementById('submit-btn');
            const progressContainer = document.getElementById('progress-container');
            const progressBar = document.getElementById('progress-bar');
            const statusText = document.getElementById('status-text');
            const downloadArea = document.getElementById('download-area');

            if (!text) { alert("Vui lòng nhập văn bản!"); return; }

            btn.disabled = true;
            progressContainer.style.display = 'block';
            downloadArea.style.display = 'none';
            progressBar.style.width = '0%';
            statusText.innerText = 'Đang phân tích văn bản...';

            const formData = new FormData();
            formData.append('text', text);
            formData.append('voice', voice);

            try {
                const response = await fetch('/tts-stream', {
                    method: 'POST',
                    body: formData
                });

                if (response.status === 401) {
                    alert("Phiên đăng nhập hết hạn. Vui lòng đăng nhập lại.");
                    window.location.href = "/login";
                    return;
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\\n');
                    
                    for (const line of lines) {
                        if (!line.trim()) continue;
                        try {
                            const data = JSON.parse(line);
                            if (data.status === 'progress') {
                                progressBar.style.width = data.percent + '%';
                                statusText.innerText = `Đang xử lý: ${Math.round(data.percent)}%`;
                            } 
                            else if (data.status === 'done') {
                                progressBar.style.width = '100%';
                                statusText.innerText = 'Hoàn tất! Đang tải xuống...';
                                const downloadUrl = `/download/${data.filename}`;
                                document.getElementById('download-link').href = downloadUrl;
                                document.getElementById('audio-preview').src = downloadUrl;
                                downloadArea.style.display = 'block';
                                btn.disabled = false;
                            }
                        } catch (err) { console.error(err); }
                    }
                }
            } catch (error) {
                console.error(error);
                statusText.innerText = '❌ Có lỗi xảy ra!';
                btn.disabled = false;
            }
        });
    </script>
</body>
</html>
"""

# --- ROUTE ĐĂNG NHẬP ---
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # Nếu đã đăng nhập thì về trang chủ
    if request.session.get("user"):
        return RedirectResponse(url="/", status_code=303)
    return LOGIN_HTML.replace("ERROR_BLOCK", "")

@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, email: str = Form(...)):
    email_input = email.strip().lower()
    allowed_users = get_allowed_emails()
    
    if not allowed_users:
        error_msg = '<div class="error">Lỗi kết nối Google Sheet (Check ID/Key)</div>'
        return LOGIN_HTML.replace("ERROR_BLOCK", error_msg)
    
    if email_input in allowed_users:
        # Đăng nhập thành công
        request.session["user"] = email_input
        return RedirectResponse(url="/", status_code=303)
    else:
        error_msg = '<div class="error">Email này chưa được cấp quyền truy cập.</div>'
        return LOGIN_HTML.replace("ERROR_BLOCK", error_msg)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

# --- ROUTE CHÍNH (ĐƯỢC BẢO VỆ) ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Kiểm tra Session
    if not request.session.get("user"):
        return RedirectResponse(url="/login", status_code=303)

    # Xử lý chèn Logo
    logo_data = get_image_base64("logo.png")
    logo_tag = f'<img src="data:image/png;base64,{logo_data}" class="logo">' if logo_data else ""
    return HOME_HTML.replace("LOGO_HERE", logo_tag)

# --- XỬ LÝ TTS STREAMING ---
async def tts_generator(text, voice, output_filename):
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    total_lines = len(lines)
    
    if total_lines == 0:
        yield json.dumps({"status": "done", "filename": ""}) + "\n"
        return

    file_path = os.path.join(TEMP_DIR, output_filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    for i, line in enumerate(lines):
        try:
            communicate = edge_tts.Communicate(line, voice)
            with open(file_path, "ab") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
            
            percent = ((i + 1) / total_lines) * 100
            yield json.dumps({"status": "progress", "percent": percent}) + "\n"
        except Exception as e:
            print(f"Lỗi dòng {i}: {e}")

    yield json.dumps({"status": "done", "filename": output_filename}) + "\n"

@app.post("/tts-stream")
async def tts_stream_endpoint(request: Request, text: str = Form(...), voice: str = Form(...)):
    # Bảo vệ API
    if not request.session.get("user"):
        return JSONResponse(status_code=401, content={"message": "Unauthorized"})

    filename = f"{uuid.uuid4()}.mp3"
    return StreamingResponse(tts_generator(text, voice, filename), media_type="application/x-ndjson")

@app.get("/download/{filename}")
async def download_file(request: Request, filename: str):
    # Bảo vệ Link tải
    if not request.session.get("user"):
        return RedirectResponse(url="/login")

    file_path = os.path.join(TEMP_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="audio/mpeg", filename="tts_audio.mp3")
    return HTMLResponse("File not found", status_code=404)

# --- API CHO GHOST BLOG ---

# Schema nhận dữ liệu JSON
class TTSRequest(BaseModel):
    text: str
    voice: str = "vi-VN-HoaiMyNeural" # Giọng mặc định

# Hàm tạo file nhanh (không stream)
async def create_audio_direct(text: str, voice: str, output_filename: str):
    file_path = os.path.join(TEMP_DIR, output_filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(file_path)
    return file_path

# Endpoint để Ghost Blog gọi đến
@app.post("/api/tts")
async def api_generate_tts(req: TTSRequest, x_api_key: str = Header(None)):
    # 1. Kiểm tra API Key
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Sai API Key")
    
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Văn bản trống")

    # 2. Tạo tên file ngẫu nhiên và sinh audio
    filename = f"{uuid.uuid4()}.mp3"
    try:
        await create_audio_direct(req.text, req.voice, filename)
        
        # 3. Trả về đường link trực tiếp đến file Audio
        # Thay YOUR_SERVER_DOMAIN bằng domain hoặc IP server FastAPI của bạn
        # VD: "https://api.domain.com/api/audio/" + filename
        return {
            "status": "success", 
            "audio_url": f"/api/audio/{filename}" 
        }
    except Exception as e:
        print(f"API Error: {e}")
        raise HTTPException(status_code=500, detail="Lỗi server khi tạo giọng đọc")

# Endpoint cho phép thẻ <audio> trên Ghost đọc file (Không cần session)
@app.get("/api/audio/{filename}")
async def get_api_audio(filename: str):
    file_path = os.path.join(TEMP_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="audio/mpeg", filename=filename)
    return JSONResponse(status_code=404, content={"message": "File not found"})
