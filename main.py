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

# CORS configuration – allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Path to cookies file (Netscape format) – make sure cookies.txt is in the same directory
COOKIE_FILE = "cookies.txt"

def slugify_filename(text: str) -> str:
    """Convert text to a safe filename."""
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^a-zA-Z0-9\s_.-]', '', text)
    text = re.sub(r'[\s]+', '_', text)
    return text.strip('_.-') or "downloaded_audio"

def is_valid_tiktok_video(url: str) -> bool:
    """Reject TikTok photo links early."""
    return '/photo/' not in url

@app.get("/download")
async def download_video(
    url: str = Query(..., description="Video URL to download"),
    format: str = Query("best", description="Format: 'bestaudio/best' for MP3, or 'best' for video")
):
    # Validate TikTok photo URLs
    if 'tiktok.com' in url and not is_valid_tiktok_video(url):
        raise HTTPException(
            status_code=400,
            detail="TikTok photo URLs are not supported (only videos)."
        )

    try:
        # Extract video info without downloading
        with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = slugify_filename(info.get("title", "video"))

        # Determine output filename and extension
        if format == 'bestaudio/best':
            filename = f"{title}.mp3"
        else:
            filename = f"{title}.mp4"

        # Unique temporary file template
        uid = uuid.uuid4().hex[:8]
        outtmpl = f"/tmp/{uid}.%(ext)s"

        # Base yt-dlp options
        ydl_opts = {
            'outtmpl': outtmpl,
            'quiet': True,
            'cookiefile': COOKIE_FILE if os.path.exists(COOKIE_FILE) else None,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
            },
            # Force TikTok to use mobile API (helps with short links)
            'extractor_args': {
                'tiktok': {
                    'api_hostname': ['api22-normal-c-alisg.tiktokv.com'],
                },
            },
        }

        # Configure for audio or video
        if format == 'bestaudio/best':
            ydl_opts.update({
                'format': 'bestaudio',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        else:
            ydl_opts['format'] = format
            ydl_opts['merge_output_format'] = 'mp4'

        # Download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Find the downloaded file
        actual_file_path = None
        for f in os.listdir("/tmp"):
            if f.startswith(uid):
                actual_file_path = os.path.join("/tmp", f)
                break

        if not actual_file_path or not os.path.exists(actual_file_path):
            raise HTTPException(status_code=500, detail="Downloaded file not found.")

        # Stream file and clean up
        def iterfile():
            with open(actual_file_path, "rb") as f:
                yield from f
            os.unlink(actual_file_path)

        media_type = "audio/mpeg" if format == 'bestaudio/best' else "video/mp4"
        return StreamingResponse(
            iterfile(),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/")
async def root():
    return {"message": "Social Media Video Downloader API. Use /download?url=...&format=bestaudio/best for MP3 audio."}