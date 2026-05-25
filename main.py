import os
import uuid
import re
import unicodedata
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

app = FastAPI()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pastikan file cookies.txt berada di direktori yang sama dengan main.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "cookies.txt")

def slugify_filename(text: str) -> str:
    """Bersihkan judul video untuk dijadikan nama file."""
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^a-zA-Z0-9\s_.-]', '', text)
    text = re.sub(r'[\s]+', '_', text)
    return text.strip('_.-') or "downloaded_audio"

@app.get("/download")
async def download_video(url: str = Query(...), format: str = Query("best")):
    # Validasi sederhana untuk URL TikTok foto
    if 'tiktok.com' in url and '/photo/' in url:
        raise HTTPException(400, "TikTok photo URLs are not supported (only videos).")

    try:
        # Ekstrak metadata (judul)
        with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = slugify_filename(info.get("title", "video"))
            filename = f"{title}.mp3" if format == "bestaudio/best" else f"{title}.mp4"

        # Siapkan direktori dan nama file sementara
        uid = uuid.uuid4().hex[:8]
        outtmpl = f"/tmp/{uid}.%(ext)s"

        # Opsi dasar untuk yt-dlp
        ydl_opts = {
            'outtmpl': outtmpl,
            'quiet': True,
            # -- BERIKUT ADALAH KONFIGURASI PENTING --
            # 1. Pastikan file cookies.txt dikenali
            'cookiefile': COOKIE_FILE if os.path.exists(COOKIE_FILE) else None,
            # 2. Minta yt-dlp untuk meniru client YouTube dari Android (agar lebih aman)
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                },
                'tiktok': {
                    'api_hostname': ['api22-normal-c-alisg.tiktokv.com'],
                },
            },
            # 3. Gunakan User-Agent yang umum
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
            },
        }

        # Konfigurasi khusus untuk unduhan Audio (MP3)
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

        # Eksekusi download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Cari file yang sudah didownload
        actual_file_path = None
        for f in os.listdir("/tmp"):
            if f.startswith(uid):
                actual_file_path = os.path.join("/tmp", f)
                break

        if not actual_file_path or not os.path.exists(actual_file_path):
            raise HTTPException(500, "Downloaded file not found.")

        # Kirim file sebagai streaming response
        def iterfile():
            with open(actual_file_path, "rb") as f:
                yield from f
            os.unlink(actual_file_path)

        media_type = "audio/mpeg" if format == "bestaudio/best" else "video/mp4"
        return StreamingResponse(
            iterfile(),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    except Exception as e:
        raise HTTPException(500, detail=f"Error: {str(e)}")

@app.get("/")
async def root():
    return {"message": "API is running. Use /download?url=...&format=bestaudio/best for MP3 audio."}