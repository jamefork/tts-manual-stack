from fastapi import FastAPI, Form, Request, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import edge_tts
import tempfile
import os
import json
import asyncio
import base64
import uuid

app = FastAPI()

# Cấu hình CORS cho phép Ghost Blog gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://home.pmtl.site"], # Thay "*" bằng tên miền Ghost blog
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lấy API KEY từ biến môi trường cho API Ghost Blog
API_KEY = os.environ.get('TTS_API_KEY')
if not API_KEY:
    raise RuntimeError("Lỗi bảo mật: Chưa cấu hình biến môi trường TTS_API_KEY trên server!")

TEMP_DIR = tempfile.gettempdir()

# --- CẤU HÌNH GIỚI HẠN KHÁCH TRUY CẬP ---
MAX_USAGE_PER_IP = 3 # Giới hạn 3 lần mỗi IP
MAX_CHARS = 1000     # Giới hạn 1000 ký tự
user_usage_counts = {} # Dictionary lưu trữ số lần sử dụng: { "ip_address": count }

def get_image_base64(image_path):
    if os.path.exists(image_path):
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')
    return ""

# --- GIAO DIỆN HTML: TRANG CHỦ (TTS) ---
HOME_HTML = f"""
<!DOCTYPE html>
<html>
<head>
    <title>TTS Server Pro</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 650px; margin: 40px auto; padding: 20px; 
            background-color: #f0f2f5; color: #333;
        }}
        .container {{
            background: white; padding: 30px; border-radius: 16px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            position: relative;
        }}
        .logo {{
            display: block; margin: 0 auto 20px auto; max-width: 100px;
            border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        h1 {{ text-align: center; color: #1a1a1a; margin-bottom: 25px; font-size: 22px; }}
        
        textarea {{ 
            width: 100%; height: 200px; margin-bottom: 5px; padding: 15px; 
            border: 2px solid #e1e4e8; border-radius: 10px; font-size: 16px; 
            box-sizing: border-box; resize: vertical; transition: border 0.2s;
        }}
        textarea:focus {{ outline: none; border-color: #007bff; }}
        .char-counter {{ text-align: right; font-size: 13px; color: #666; margin-bottom: 15px; }}
        
        select {{
            width: 100%; padding: 12px; margin-bottom: 20px; border-radius: 10px;
            border: 2px solid #e1e4e8; background: white; font-size: 15px;
        }}
        
        button {{ 
            width: 100%; padding: 14px; font-size: 16px; font-weight: 600;
            cursor: pointer; background: #007bff; color: white; 
            border: none; border-radius: 10px; transition: all 0.2s;
        }}
        button:hover {{ background: #0056b3; transform: translateY(-1px); }}
        button:disabled {{ background: #ccc; cursor: not-allowed; }}

        #progress-container {{ display: none; margin-top: 25px; }}
        .progress-track {{ width: 100%; background-color: #e9ecef; border-radius: 20px; height: 10px; overflow: hidden; }}
        .progress-bar {{ width: 0%; height: 100%; background-color: #28a745; transition: width 0.3s ease; }}
        #status-text {{ text-align: center; margin-top: 10px; font-size: 14px; color: #666; }}
        #download-area {{ display: none; margin-top: 20px; text-align: center; }}
        .download-btn {{ display: inline-block; padding: 10px 20px; background: #28a745; color: white; text-decoration: none; border-radius: 8px; font-weight: bold; }}
        .error-box {{ display: none; color: white; background: #dc3545; padding: 10px; border-radius: 8px; margin-top: 15px; text-align: center; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        LOGO_HERE
        
        <h1>Pháp Môn Tâm Linh 心靈法門 (TTS)</h1>
        
        <form id="tts-form">
            <label style="font-weight:bold; display:block; margin-bottom:8px;">Chọn giọng đọc:</label>
            <select name="voice" id="voice">
                <option value="vi-VN-HoaiMyNeural">🇻🇳 Hoài My (Nữ - Truyền cảm)</option>
                <option value="vi-VN-NamMinhNeural">🇻🇳 Nam Minh (Nam - Mạnh mẽ)</option>
            </select>
            
            <textarea name="text" id="text-input" placeholder="Nhập văn bản vào đây... (Tối đa {MAX_CHARS} ký tự)" maxlength="{MAX_CHARS}"></textarea>
            <div class="char-counter"><span id="char-count">0</span>/{MAX_CHARS} ký tự</div>
            
            <button type="submit" id="submit-btn">🚀 Bắt đầu chuyển đổi</button>
        </form>

        <div id="error-message" class="error-box"></div>

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
        const textInput = document.getElementById('text-input');
        const charCount = document.getElementById('char-count');
        
        // Cập nhật số ký tự
        textInput.addEventListener('input', () => {{
            charCount.innerText = textInput.value.length;
        }});

        document.getElementById('tts-form').addEventListener('submit', async function(e) {{
            e.preventDefault();
            
            const text = textInput.value.trim();
            const voice = document.getElementById('voice').value;
            const btn = document.getElementById('submit-btn');
            const progressContainer = document.getElementById('progress-container');
            const progressBar = document.getElementById('progress-bar');
            const statusText = document.getElementById('status-text');
            const downloadArea = document.getElementById('download-area');
            const errorBox = document.getElementById('error-message');

            if (!text) {{ alert("Vui lòng nhập văn bản!"); return; }}
            
            btn.disabled = true;
            errorBox.style.display = 'none';
            progressContainer.style.display = 'block';
            downloadArea.style.display = 'none';
            progressBar.style.width = '0%';
            statusText.innerText = 'Đang phân tích văn bản...';

            const formData = new FormData();
            formData.append('text', text);
            formData.append('voice', voice);

            try {{
                const response = await fetch('/tts-stream', {{
                    method: 'POST',
                    body: formData
                }});

                // Bắt lỗi HTTP từ máy chủ (Quá 3 lần hoặc quá ký tự)
                if (!response.ok) {{
                    const errData = await response.json();
                    errorBox.innerText = errData.detail || "Có lỗi xảy ra!";
                    errorBox.style.display = 'block';
                    progressContainer.style.display = 'none';
                    btn.disabled = false;
                    return;
                }}

                const reader = response.body.getReader();
                const decoder = new TextDecoder();

                while (true) {{
                    const {{ done, value }} = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\\n');
                    
                    for (const line of lines) {{
                        if (!line.trim()) continue;
                        try {{
                            const data = JSON.parse(line);
                            if (data.status === 'progress') {{
                                progressBar.style.width = data.percent + '%';
                                statusText.innerText = `Đang xử lý: ${{Math.round(data.percent)}}%`;
                            }} 
                            else if (data.status === 'done') {{
                                progressBar.style.width = '100%';
                                statusText.innerText = 'Hoàn tất! Đang tải xuống...';
                                const downloadUrl = `/download/${{data.filename}}`;
                                document.getElementById('download-link').href = downloadUrl;
                                document.getElementById('audio-preview').src = downloadUrl;
                                downloadArea.style.display = 'block';
                                btn.disabled = false;
                            }}
                        }} catch (err) {{ console.error(err); }}
                    }}
                }}
            }} catch (error) {{
                console.error(error);
                statusText.innerText = '❌ Có lỗi kết nối xảy ra!';
                btn.disabled = false;
            }}
        }});
    </script>
</body>
</html>
"""

# --- ROUTE CHÍNH ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    logo_data = get_image_base64("logo.png")
    logo_tag = f'<img src="data:image/png;base64,{logo_data}" class="logo">' if logo_data else ""
    return HOME_HTML.replace("LOGO_HERE", logo_tag)

# --- XỬ LÝ TTS STREAMING CHO GIAO DIỆN WEB ---
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
    # 1. Kiểm tra giới hạn 1000 ký tự
    if len(text) > MAX_CHARS:
        raise HTTPException(status_code=400, detail=f"Văn bản quá dài! Vui lòng nhập tối đa {MAX_CHARS} ký tự.")

    # 2. Kiểm tra giới hạn số lần sử dụng qua IP
    client_ip = request.client.host
    usage = user_usage_counts.get(client_ip, 0)
    
    if usage >= MAX_USAGE_PER_IP:
        raise HTTPException(status_code=429, detail="Bạn đã hết 3 lượt tạo giọng đọc miễn phí.")

    # 3. Ghi nhận lượt sử dụng mới
    user_usage_counts[client_ip] = usage + 1

    filename = f"{uuid.uuid4()}.mp3"
    return StreamingResponse(tts_generator(text, voice, filename), media_type="application/x-ndjson")

@app.get("/download/{filename}")
async def download_file(request: Request, filename: str):
    file_path = os.path.join(TEMP_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="audio/mpeg", filename="tts_audio.mp3")
    return HTMLResponse("File not found", status_code=404)

# --- API CHO GHOST BLOG (GIỮ NGUYÊN ĐỂ KHÔNG LÀM HỎNG BLOG) ---

class TTSRequest(BaseModel):
    text: str
    voice: str = "vi-VN-HoaiMyNeural"

async def create_audio_direct(text: str, voice: str, output_filename: str):
    file_path = os.path.join(TEMP_DIR, output_filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if not lines:
        raise Exception("Văn bản rỗng sau khi xử lý")

    for i, line in enumerate(lines):
        try:
            communicate = edge_tts.Communicate(line, voice)
            with open(file_path, "ab") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
        except Exception as e:
            print(f"Lỗi khi đọc đoạn {i}: {e}")
            
    return file_path

@app.post("/api/tts")
async def api_generate_tts(req: TTSRequest, x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Sai API Key")
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Văn bản trống")

    filename = f"{uuid.uuid4()}.mp3"
    try:
        await create_audio_direct(req.text, req.voice, filename)
        return {
            "status": "success", 
            "audio_url": f"/api/audio/{filename}" 
        }
    except Exception as e:
        print(f"API Error: {e}")
        raise HTTPException(status_code=500, detail="Lỗi server khi tạo giọng đọc")

@app.get("/api/audio/{filename}")
async def get_api_audio(filename: str):
    file_path = os.path.join(TEMP_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="audio/mpeg", filename=filename)
    return JSONResponse(status_code=404, content={"message": "File not found"})

async def tts_generator_api(text, voice, output_filename):
    lines = [line.strip() for line in text.split('\n') if len(line.strip()) > 2]
    total_lines = len(lines)
    
    if total_lines == 0:
        yield json.dumps({"status": "done", "filename": ""}) + "\n"
        return

    file_path = os.path.join(TEMP_DIR, output_filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    for i, line in enumerate(lines):
        try:
            if i > 0:
                await asyncio.sleep(1)
                
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

@app.post("/api/tts-stream")
async def api_tts_stream_endpoint(req: TTSRequest, x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Sai API Key")
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Văn bản trống")

    filename = f"{uuid.uuid4()}.mp3"
    return StreamingResponse(tts_generator_api(req.text, req.voice, filename), media_type="application/x-ndjson")
