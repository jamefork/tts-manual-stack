import streamlit as st
import edge_tts
import os
import subprocess
import asyncio
import tempfile

st.set_page_config(page_title="Text to Speech Server", page_icon="📖")
st.title("📖 Home Server: Text to Audio (Unlimited)")

# --- CẤU HÌNH HỆ THỐNG ---
def get_duration(file_path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", 
        "format=duration", "-of", 
        "default=noprint_wrappers=1:nokey=1", file_path
    ]
    try:
        result = subprocess.check_output(cmd).decode().strip()
        return float(result)
    except:
        return 0.0

async def process_tts_text(text_content, voice, status_text, progress_bar):
    with tempfile.TemporaryDirectory() as temp_dir:
        # Tách văn bản thành các đoạn theo dòng để tạo thanh tiến trình và tránh lỗi text quá dài
        lines = [line.strip() for line in text_content.split('\n') if line.strip()]
        
        if not lines:
            raise ValueError("Văn bản trống!")

        file_list_txt = os.path.join(temp_dir, "mylist.txt")
        final_output_path = os.path.join(temp_dir, "output.mp3")
        concat_list = []
        total_lines = len(lines)

        for index, line in enumerate(lines):
            # Cập nhật tiến trình
            prog = (index / total_lines)
            progress_bar.progress(prog)
            # Hiển thị text ngắn gọn để biết đang đọc đến đâu
            preview_text = (line[:50] + '...') if len(line) > 50 else line
            status_text.text(f"Đang xử lý ({index+1}/{total_lines}): {preview_text}")

            tts_file = os.path.join(temp_dir, f"tts_{index}.mp3")
            
            # Gọi Edge-TTS
            communicate = edge_tts.Communicate(line, voice)
            await communicate.save(tts_file)
            
            # Thêm vào danh sách ghép file
            concat_list.append(f"file '{tts_file}'")

        # Ghi file list cho ffmpeg
        with open(file_list_txt, "w", encoding="utf-8") as f:
            for line in concat_list:
                f.write(line.replace("\\", "/") + "\n")

        status_text.text("Đang gộp file (Finalizing)...")
        
        # Lệnh gộp file MP3
        cmd_merge = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", 
            "-i", file_list_txt, 
            "-c:a", "libmp3lame", "-q:a", "2",
            final_output_path
        ]
        subprocess.run(cmd_merge, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        with open(final_output_path, "rb") as f:
            return f.read()

# --- GIAO DIỆN ---
st.sidebar.header("Cấu hình")
voice_option = st.sidebar.selectbox("Chọn giọng đọc:", 
                            ["vi-VN-HoaiMyNeural (Nữ)", "vi-VN-NamMinhNeural (Nam)"])
voice_code = voice_option.split(" ")[0]

# Tab chọn nguồn nhập liệu
tab1, tab2 = st.tabs(["📝 Nhập văn bản", "📂 Upload File TXT"])

input_text = ""

with tab1:
    text_area_input = st.text_area("Dán văn bản vào đây:", height=300)
    if text_area_input:
        input_text = text_area_input

with tab2:
    uploaded_file = st.file_uploader("Chọn file .txt", type=['txt'])
    if uploaded_file:
        input_text = uploaded_file.getvalue().decode("utf-8")

if st.button("🚀 BẮT ĐẦU CHUYỂN ĐỔI", use_container_width=True):
    if input_text.strip():
        status_text = st.empty()
        progress_bar = st.progress(0)
        try:
            mp3_data = asyncio.run(process_tts_text(input_text, voice_code, status_text, progress_bar))
            
            progress_bar.progress(100)
            status_text.success("✅ Đã xong!")
            
            # Audio player để nghe thử
            st.audio(mp3_data, format='audio/mp3')
            
            st.download_button(
                label="📥 Tải File MP3", 
                data=mp3_data, 
                file_name="tts_output.mp3", 
                mime="audio/mp3",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Lỗi: {e}")
    else:
        st.warning("Vui lòng nhập văn bản hoặc upload file!")