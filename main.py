import os
import uuid
import re
import unicodedata
import tempfile
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
from dotenv import load_dotenv

app = FastAPI()
load_dotenv()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Baca cookies dari environment variable COOKIE_CONTENT ---
COOKIE_ENV_VAR = "COOKIE_CONTENT"
cookie_content = os.getenv(COOKIE_ENV_VAR)
temp_cookie_file = None
COOKIE_FILE_PATH = None

if cookie_content:
    try:
        # Buat file temporary untuk menyimpan isi cookies
        temp_cookie_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        temp_cookie_file.write(cookie_content)
        temp_cookie_file.flush()
        temp_cookie_file.close()
        COOKIE_FILE_PATH = temp_cookie_file.name
        print(f"Cookies loaded from environment variable to {COOKIE_FILE_PATH}")
    except Exception as e:
        print(f"Failed to create temporary cookie file: {e}")
        COOKIE_FILE_PATH = None
else:
    print("COOKIE_CONTENT environment variable not found. Proceeding without cookies.")

def slugify_filename(text: str) -> str:
    """Bersihkan judul untuk nama file (hanya huruf, angka, spasi, garis bawah, strip)."""
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^a-zA-Z0-9\s_.-]', '', text)
    text = re.sub(r'[\s]+', '_', text)
    return text.strip('_.-') or "downloaded_audio"

@app.get("/download")
async def download_video(url: str = Query(...), format: str = Query("best")):
    try:
        # Ambil metadata (judul)
        with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = slugify_filename(info.get("title", "video"))

        uid = uuid.uuid4().hex[:8]
        outtmpl = f"/tmp/{uid}.%(ext)s"

        # Opsi dasar
        ydl_opts = {
            'outtmpl': outtmpl,
            'quiet': False,               # Biarkan log muncul untuk debug
            'cookiefile': COOKIE_FILE_PATH if COOKIE_FILE_PATH and os.path.exists(COOKIE_FILE_PATH) else None,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
            },
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios'],   # Tiru client mobile
                },
                'tiktok': {
                    'api_hostname': ['api22-normal-c-alisg.tiktokv.com'],
                },
            },
            'sleep_interval': 3,
            'max_sleep_interval': 10,
        }

        # ========== AUDIO MP3 ==========
        if format == "bestaudio/best":
            ydl_opts.update({
                'format': 'bestaudio',                    # ✅ PERBAIKAN: gunakan 'bestaudio'
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
            filename = f"{title}.mp3"
            media_type = "audio/mpeg"
        # ========== VIDEO ==========
        else:
            ydl_opts.update({
                'format': format,
                'merge_output_format': 'mp4',
            })
            filename = f"{title}.mp4"
            media_type = "video/mp4"

        # Eksekusi download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Cari file hasil download
        actual_file_path = None
        for f in os.listdir("/tmp"):
            if f.startswith(uid):
                actual_file_path = os.path.join("/tmp", f)
                break

        if not actual_file_path or not os.path.exists(actual_file_path):
            raise HTTPException(500, "File hasil download tidak ditemukan.")

        # Streaming file
        def iterfile():
            with open(actual_file_path, "rb") as f:
                yield from f
            os.unlink(actual_file_path)

        return StreamingResponse(
            iterfile(),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    except Exception as e:
        raise HTTPException(500, detail=f"Error: {str(e)}")

@app.get("/")
async def root():
    return {"message": "API Social Media Video Downloader berjalan. Gunakan /download?url=...&format=bestaudio/best untuk MP3."}