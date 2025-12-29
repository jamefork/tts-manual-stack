from fastapi import FastAPI, Form
from fastapi.responses import FileResponse, HTMLResponse
import edge_tts
import tempfile
import os

app = FastAPI()

# Giao diện HTML đơn giản nhúng thẳng vào code cho gọn
html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>TTS Server Lite</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: sans-serif; max-width: 800px; margin: 20px auto; padding: 0 10px; }
        textarea { width: 100%; height: 200px; margin-bottom: 10px; }
        button { padding: 10px 20px; font-size: 16px; cursor: pointer; background: #007bff; color: white; border: none; }
        button:hover { background: #0056b3; }
        .loading { display: none; color: #666; }
    </style>
</head>
<body>
    <h1>Pháp Môn Tâm Linh 心靈法門</h1>
    <form action="/tts" method="post" onsubmit="document.getElementById('msg').style.display='block'">
        <label><b>Chọn giọng đọc:</b></label><br>
        <select name="voice" style="margin: 10px 0; padding: 5px;">
            <option value="vi-VN-HoaiMyNeural">Hoài My (Nữ)</option>
            <option value="vi-VN-NamMinhNeural">Nam Minh (Nam)</option>
        </select>
        <br>
        <textarea name="text" placeholder="Nhập văn bản vào đây..."></textarea>
        <br>
        <button type="submit">🚀 Chuyển đổi & Tải về</button>
    </form>
    <p id="msg" class="loading">⏳ Đang xử lý, vui lòng chờ...</p>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def home():
    return html_content

@app.post("/tts")
async def text_to_speech(text: str = Form(...), voice: str = Form(...)):
    # Tạo file tạm
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
        temp_path = fp.name
    
    # Xử lý TTS
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(temp_path)
    
    # Trả về file và đặt tên file tải về
    return FileResponse(temp_path, media_type="audio/mpeg", filename="tts_audio.mp3")
