from fastapi import FastAPI, Form
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
import edge_tts
import tempfile
import os
import json
import asyncio
import base64
import uuid

app = FastAPI()

# --- CẤU HÌNH ---
TEMP_DIR = tempfile.gettempdir()

def get_image_base64(image_path):
    if os.path.exists(image_path):
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')
    return ""

# --- GIAO DIỆN HTML/JS MỚI ---
# Đã thêm: Progress Bar, Javascript để nhận dữ liệu luồng
html_content = """
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
        }
        .logo {
            display: block; margin: 0 auto 20px auto; max-width: 100px;
            border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        h1 { text-align: center; color: #1a1a1a; margin-bottom: 25px; font-size: 22px; }
        
        /* Giao diện Form */
        textarea { 
            width: 100%; height: 300px; margin-bottom: 15px; padding: 15px; 
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

        /* --- THANH TIẾN TRÌNH (MỚI) --- */
        #progress-container {
            display: none; margin-top: 25px;
        }
        .progress-track {
            width: 100%; background-color: #e9ecef; border-radius: 20px;
            height: 10px; overflow: hidden;
        }
        .progress-bar {
            width: 0%; height: 100%; background-color: #28a745;
            transition: width 0.3s ease;
        }
        #status-text {
            text-align: center; margin-top: 10px; font-size: 14px; color: #666;
        }
        #download-area {
            display: none; margin-top: 20px; text-align: center;
        }
        .download-btn {
            display: inline-block; padding: 10px 20px; background: #28a745;
            color: white; text-decoration: none; border-radius: 8px; font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        LOGO_HERE
        
        <h1>Pháp Môn Tâm Linh 心靈法門</h1>
        
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

            // Reset giao diện
            btn.disabled = true;
            progressContainer.style.display = 'block';
            downloadArea.style.display = 'none';
            progressBar.style.width = '0%';
            statusText.innerText = 'Đang phân tích văn bản...';

            // Tạo FormData
            const formData = new FormData();
            formData.append('text', text);
            formData.append('voice', voice);

            try {
                // Gọi API Streaming
                const response = await fetch('/tts-stream', {
                    method: 'POST',
                    body: formData
                });

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
                                // Cập nhật thanh tiến trình
                                progressBar.style.width = data.percent + '%';
                                statusText.innerText = `Đang xử lý: ${Math.round(data.percent)}%`;
                            } 
                            else if (data.status === 'done') {
                                // Hoàn tất
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

@app.get("/", response_class=HTMLResponse)
async def home():
    # Xử lý chèn Logo
    logo_data = get_image_base64("logo.png")
    logo_tag = f'<img src="data:image/png;base64,{logo_data}" class="logo">' if logo_data else ""
    return html_content.replace("LOGO_HERE", logo_tag)

# --- XỬ LÝ TTS STREAMING ---
async def tts_generator(text, voice, output_filename):
    # 1. Tách văn bản thành các dòng/câu để tính tiến trình
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    total_lines = len(lines)
    
    if total_lines == 0:
        yield json.dumps({"status": "done", "filename": ""}) + "\n"
        return

    # File tạm để nối các đoạn audio
    file_path = os.path.join(TEMP_DIR, output_filename)
    
    # Xóa file cũ nếu trùng tên
    if os.path.exists(file_path):
        os.remove(file_path)

    # 2. Xử lý từng dòng và nối vào file
    for i, line in enumerate(lines):
        try:
            # Tạo audio cho từng dòng
            communicate = edge_tts.Communicate(line, voice)
            
            # Ghi trực tiếp (append) vào file cuối cùng
            # Lưu ý: file MP3 có thể nối tiếp nhau (concatenate) mà vẫn nghe được
            with open(file_path, "ab") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
            
            # Tính phần trăm
            percent = ((i + 1) / total_lines) * 100
            
            # Gửi tín hiệu tiến trình về Browser (JSON format)
            yield json.dumps({"status": "progress", "percent": percent}) + "\n"
            
            # Nghỉ một chút để tránh quá tải CPU nếu cần (tùy chọn)
            # await asyncio.sleep(0.01) 

        except Exception as e:
            print(f"Lỗi dòng {i}: {e}")

    # 3. Gửi tín hiệu hoàn tất
    yield json.dumps({"status": "done", "filename": output_filename}) + "\n"

@app.post("/tts-stream")
async def tts_stream_endpoint(text: str = Form(...), voice: str = Form(...)):
    # Tạo tên file ngẫu nhiên
    filename = f"{uuid.uuid4()}.mp3"
    return StreamingResponse(tts_generator(text, voice, filename), media_type="application/x-ndjson")

@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = os.path.join(TEMP_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="audio/mpeg", filename="tts_audio.mp3")
    return HTMLResponse("File not found", status_code=404)
