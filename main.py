import os
import uuid
import re
import unicodedata
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
from dotenv import load_dotenv

app = FastAPI()
load_dotenv()

# Allow all origins for testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

COOKIE_FILE = "cookies.txt"

def slugify_filename(text: str) -> str:
    """Make a string safe for a filename."""
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^a-zA-Z0-9\s_.-]', '', text)
    text = re.sub(r'[\s]+', '_', text)
    return text.strip('_.-') or "downloaded_audio"

@app.get("/download")
async def download_video(
    url: str = Query(...),
    format: str = Query("best")
):
    try:
        # --- Extract metadata (title) ---
        with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = slugify_filename(info.get("title", "video"))
            if format == "bestaudio/best":
                filename = f"{title}.mp3"
            else:
                filename = f"{title}.mp4"

        uid = uuid.uuid4().hex[:8]
        outtmpl = f"/tmp/{uid}.%(ext)s"

        # --- Base options (cookies + user-agent + TikTok mobile API) ---
        ydl_opts = {
            'outtmpl': outtmpl,
            'quiet': True,
            'cookiefile': COOKIE_FILE if os.path.exists(COOKIE_FILE) else None,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
            },
            'extractor_args': {
                'tiktok': {
                    'api_hostname': ['api22-normal-c-alisg.tiktokv.com'],
                },
            },
        }

        # --- Audio (MP3) configuration ---
        if format == "bestaudio/best":
            # First try bestaudio, then fallback to any audio + conversion
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        else:
            ydl_opts['format'] = format
            ydl_opts['merge_output_format'] = 'mp4'

        # --- Download ---
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # --- Locate the downloaded file ---
        actual_file_path = None
        for f in os.listdir("/tmp"):
            if f.startswith(uid):
                actual_file_path = os.path.join("/tmp", f)
                break

        if not actual_file_path or not os.path.exists(actual_file_path):
            raise HTTPException(500, "Downloaded file not found.")

        # --- Stream and delete ---
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
        # Send the exact error to the client for debugging
        raise HTTPException(500, detail=f"Error: {str(e)}")

@app.get("/")
async def root():
    return {"message": "API is running. Use /download?url=...&format=bestaudio/best for MP3 audio."}