import os
import uuid
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
from dotenv import load_dotenv

app = FastAPI()
load_dotenv()

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "cookies.txt")

def slugify_filename(text: str) -> str:
    """Membersihkan string untuk dijadikan nama file yang aman."""
    return "".join(c for c in text if c.isalnum() or c in " ._-").rstrip()

@app.get("/download")
async def download_video(url: str = Query(...), format: str = Query("best")):
    try:
        # 1. Ambil metadata untuk mendapatkan judul
        with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = slugify_filename(info.get("title", "video"))

        uid = uuid.uuid4().hex[:8]
        outtmpl = f"/tmp/{uid}.%(ext)s"

        # 2. Opsi dasar dengan konfigurasi yang kuat
        ydl_opts = {
            'outtmpl': outtmpl,
            'quiet': False,                     # Aktifkan logging untuk debugging
            'cookiefile': COOKIE_FILE if os.path.exists(COOKIE_FILE) else None,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            },
            # --- KONFIGURASI PENTING UNTUK YOUTUBE & TIKTOK ---
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios'],   # Gunakan client mobile
                },
                'tiktok': {
                    'api_hostname': ['api22-normal-c-alisg.tiktokv.com'],
                },
            },
            # --- KONFIGURASI UNTUK MENGHINDARI RATE LIMIT ---
            'sleep_interval': 5,                 # Jeda 5 detik antar request
            'max_sleep_interval': 15,            # Jeda maksimal 15 detik
            'sleep_interval_requests': 1,        # Jeda setelah setiap request
        }

        # 3. Konfigurasi untuk unduhan Audio (MP3)
        if format == "bestaudio/best":
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        else:
            ydl_opts.update({
                'format': format,
                'merge_output_format': 'mp4',
            })

        # 4. Eksekusi download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # 5. Cari file yang sudah di-download
        actual_file_path = None
        for f in os.listdir("/tmp"):
            if f.startswith(uid):
                actual_file_path = os.path.join("/tmp", f)
                break

        if not actual_file_path or not os.path.exists(actual_file_path):
            raise HTTPException(500, "Downloaded file not found.")

        # 6. Kirim file sebagai streaming response
        def iterfile():
            with open(actual_file_path, "rb") as f:
                yield from f
            os.unlink(actual_file_path)

        media_type = "audio/mpeg" if format == "bestaudio/best" else "video/mp4"
        filename = f"{title}.mp3" if format == "bestaudio/best" else f"{title}.mp4"
        return StreamingResponse(
            iterfile(),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    except Exception as e:
        raise HTTPException(500, detail=f"Error: {str(e)}")