import os
import uuid
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
from dotenv import load_dotenv

app = FastAPI()
load_dotenv()

# Allow all origins (adjust if needed)
app.add_middleware(CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Path to your cookies file (make sure cookies.txt is in the same directory) ---
COOKIE_FILE = "cookies.txt"

# --- Helper function to validate TikTok video (no '/photo/') ---
def is_valid_tiktok_video(url: str) -> bool:
    return '/photo/' not in url

@app.get("/download")
async def download_video(url: str = Query(...), format: str = Query("best")):
    # Optional but good: reject TikTok photo links early
    if 'tiktok.com' in url and not is_valid_tiktok_video(url):
        raise HTTPException(status_code=400, detail="TikTok photo URLs are not supported (only videos).")

    try:
        # Extract metadata (title, etc.)
        with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get("title", "video").replace("/", "-").replace("\\", "-")
            extension = "mp4"  # fallback
            filename = f"{title}.{extension}"

        # Unique ID for temporary file
        uid = uuid.uuid4().hex[:8]
        output_template = f"/tmp/{uid}.%(ext)s"

        # --- Base yt-dlp options ---
        ydl_opts = {
            'format': format,
            'outtmpl': output_template,
            'quiet': True,
            'merge_output_format': 'mp4',
            'cookiefile': COOKIE_FILE if os.path.exists(COOKIE_FILE) else None,
            'extractor_args': {
                'tiktok': {
                    'api_hostname': ['api22-normal-c-alisg.tiktokv.com'],
                },
            },
        }

        # --- Force audio extraction when format is 'bestaudio/best' ---
        if format == 'bestaudio/best':
            ydl_opts.update({
                'format': 'bestaudio',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        # --- handle the normal 'best' video format ---
        else:
            ydl_opts['format'] = format
            ydl_opts['merge_output_format'] = 'mp4'

        # --- Perform the download ---
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # --- Locate the downloaded file ---
        actual_file_path = None
        for f in os.listdir("/tmp"):
            if f.startswith(uid):
                actual_file_path = os.path.join("/tmp", f)
                break

        if not actual_file_path or not os.path.exists(actual_file_path):
            raise HTTPException(status_code=500, detail="Download failed or file not found.")

        # --- Stream the file back to the client ---
        def iterfile():
            with open(actual_file_path, "rb") as f:
                yield from f
            os.unlink(actual_file_path)  # clean up

        # --- Dynamically set media type based on format ---
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
    return {"message": "Welcome to the Social Media Video Downloader API. Use /download?url=<video_url>&format=<video_format> to download videos."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)