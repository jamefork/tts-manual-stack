from fastapi import FastAPI, Form
from fastapi.responses import FileResponse, HTMLResponse
import edge_tts
import tempfile
import base64
import os

app = FastAPI()

# Hàm đọc ảnh và chuyển sang mã Base64 để hiển thị trong HTML
def get_image_base64(image_path):
    if os.path.exists(image_path):
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')
    return ""

# Đọc logo khi khởi động
logo_data = get_image_base64("logo.png")
logo_html = f'<img src="data:image/png;base64,{logo_data}" class="logo">' if logo_data else ""

html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>TTS Home Server</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            max-width: 600px; 
            margin: 40px auto; 
            padding: 20px; 
            background-color: #f4f7f6;
            color: #333;
        }}
        .container {{
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}
        /* --- CSS CHO LOGO --- */
        .logo {{
            display: block;
            margin: 0 auto 20px auto; /* Căn giữa và cách dưới 20px */
            max-width: 120px;         /* Giới hạn chiều rộng */
            border-radius: 15px;      /* Bo góc mềm mại */
            box-shadow: 0 4px 6px rgba(0,0,0,0.1); /* Đổ bóng nhẹ */
        }}
        h1 {{ text-align: center; color: #2c3e50; margin-bottom: 20px; font-size: 24px; }}
        textarea {{ 
            width: 100%; 
            height: 400px;  /* Đã sửa thành 400px cho rộng rãi */
            margin-bottom: 15px; 
            padding: 12px; 
            border: 1px solid #ddd; 
            border-radius: 8px; 
            font-size: 16px; 
            box-sizing: border-box;
            font-family: inherit; /* Giữ font chữ đẹp */
        }}
        select {{
            width: 100%;
            padding: 10px;
            margin-bottom: 15px;
            border-radius: 8px;
            border: 1px solid #ddd;
            background: white;
        }}
        button {{ 
            width: 100%; 
            padding: 12px; 
            font-size: 16px; 
            font-weight: bold;
            cursor: pointer; 
            background: #007bff; 
            color: white; 
            border: none; 
            border-radius: 8px; 
            transition: background 0.2s;
        }}
        button:hover {{ background: #0056b3; }}
        .loading {{ 
            display: none; 
            text-align: center; 
            margin-top: 15px; 
            color: #666; 
            font-style: italic;
        }}
    </style>
</head>
<body>
    <div class="container">
        {logo_html}
        
        <h1>Pháp Môn Tâm Linh 心靈法門</h1>
        <form action="/tts" method="post" onsubmit="document.getElementById('msg').style.display='block'">
            <label><b>Giọng đọc:</b></label>
            <select name="voice">
                <option value="vi-VN-HoaiMyNeural">🇻🇳 Hoài My (Nữ - Truyền cảm)</option>
                <option value="vi-VN-NamMinhNeural">🇻🇳 Nam Minh (Nam - Mạnh mẽ)</option>
            </select>
            
            <textarea name="text" placeholder="Nhập văn bản cần đọc vào đây..."></textarea>
            
            <button type="submit">🔊 Chuyển đổi & Tải về</button>
        </form>
        <p id="msg" class="loading">⏳ Đang xử lý, vui lòng chờ chút xíu...</p>
    </div>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def home():
    return html_content

@app.post("/tts")
async def text_to_speech(text: str = Form(...), voice: str = Form(...)):
    if not text.strip():
        return HTMLResponse("Vui lòng nhập nội dung!", status_code=400)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
        temp_path = fp.name
    
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(temp_path)
    
    return FileResponse(temp_path, media_type="audio/mpeg", filename="tts_output.mp3")

