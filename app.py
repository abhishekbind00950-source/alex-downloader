from flask import (
    Flask,
    request,
    jsonify,
    send_file
)

import yt_dlp
import os
import uuid
import threading
import time
import re
from urllib.parse import urlparse


# ==========================================
# ALEX DOWNLOADER API
# ==========================================

app = Flask(__name__)

# Temporary download directory
DOWNLOAD_DIR = "/tmp/alex_downloads"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# ==========================================
# CONFIGURATION
# ==========================================

MAX_VIDEO_DURATION = 60 * 60  # 1 hour


# ==========================================
# URL VALIDATION
# ==========================================

def is_youtube_url(url):

    try:
        parsed = urlparse(url)

        if parsed.scheme not in ["http", "https"]:
            return False

        hostname = (parsed.hostname or "").lower()

        allowed_domains = [
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "youtu.be",
            "www.youtu.be"
        ]

        return hostname in allowed_domains

    except Exception:
        return False


# ==========================================
# CLEAN FILE NAME
# ==========================================

def clean_filename(filename):

    filename = re.sub(
        r'[\\/*?:"<>|]',
        "",
        filename
    )

    return filename[:150]


# ==========================================
# HEALTH CHECK
# ==========================================

@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "status": "success",
        "app": "Alex Downloader API",
        "version": "1.0.0",
        "message": "API is running!",
        "endpoints": {
            "health": "/health",
            "video_info": "/api/info",
            "video_download": "/api/download/video",
            "audio_download": "/api/download/audio"
        }
    })


# ==========================================
# HEALTH API
# ==========================================

@app.route("/health", methods=["GET"])
def health():

    return jsonify({
        "status": "healthy",
        "service": "Alex Downloader API"
    })


# ==========================================
# VIDEO INFORMATION API
# ==========================================

@app.route("/api/info", methods=["GET"])
def video_info():

    url = request.args.get("url", "").strip()

    if not url:
        return jsonify({
            "success": False,
            "error": "YouTube URL is required"
        }), 400

    if not is_youtube_url(url):

        return jsonify({
            "success": False,
            "error": "Only YouTube URLs are supported"
        }), 400

    try:

        options = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True
        }

        with yt_dlp.YoutubeDL(options) as ydl:

            info = ydl.extract_info(
                url,
                download=False
            )

        return jsonify({
            "success": True,
            "data": {
                "id": info.get("id"),
                "title": info.get("title"),
                "description": info.get("description"),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "uploader": info.get("uploader"),
                "channel": info.get("channel"),
                "webpage_url": info.get("webpage_url")
            }
        })

    except Exception as error:

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


# ==========================================
# DOWNLOAD HELPER
# ==========================================

def download_media(url, media_type):

    unique_id = str(uuid.uuid4())

    output_template = os.path.join(
        DOWNLOAD_DIR,
        unique_id + "_%(title)s.%(ext)s"
    )

    if media_type == "video":

        options = {
            # Prefer a single MP4 file to avoid requiring ffmpeg
            "format": "best[ext=mp4][vcodec!=none]/best",
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "restrictfilenames": True,
            "max_filesize": 500 * 1024 * 1024
        }

    else:

        options = {
            # M4A audio generally avoids post-processing
            "format": "bestaudio[ext=m4a]/bestaudio",
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "restrictfilenames": True,
            "max_filesize": 200 * 1024 * 1024
        }

    with yt_dlp.YoutubeDL(options) as ydl:

        info = ydl.extract_info(
            url,
            download=False
        )

        duration = info.get("duration")

        if duration and duration > MAX_VIDEO_DURATION:

            raise ValueError(
                "Video duration exceeds the 1-hour limit"
            )

        ydl.download([url])

    matching_files = []

    for filename in os.listdir(DOWNLOAD_DIR):

        if filename.startswith(unique_id + "_"):

            matching_files.append(
                os.path.join(DOWNLOAD_DIR, filename)
            )

    if not matching_files:

        raise FileNotFoundError(
            "Downloaded file was not found"
        )

    return matching_files[0]


# ==========================================
# VIDEO DOWNLOAD API
# ==========================================

@app.route("/api/download/video", methods=["GET", "POST"])
def download_video():

    if request.method == "POST":

        data = request.get_json(silent=True) or {}

        url = str(data.get("url", "")).strip()

    else:

        url = request.args.get("url", "").strip()

    if not url:

        return jsonify({
            "success": False,
            "error": "YouTube URL is required"
        }), 400

    if not is_youtube_url(url):

        return jsonify({
            "success": False,
            "error": "Only YouTube URLs are supported"
        }), 400

    try:

        filepath = download_media(
            url,
            "video"
        )

        return send_file(
            filepath,
            as_attachment=True,
            download_name=os.path.basename(filepath),
            mimetype="video/mp4"
        )

    except Exception as error:

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


# ==========================================
# AUDIO DOWNLOAD API
# ==========================================

@app.route("/api/download/audio", methods=["GET", "POST"])
def download_audio():

    if request.method == "POST":

        data = request.get_json(silent=True) or {}

        url = str(data.get("url", "")).strip()

    else:

        url = request.args.get("url", "").strip()

    if not url:

        return jsonify({
            "success": False,
            "error": "YouTube URL is required"
        }), 400

    if not is_youtube_url(url):

        return jsonify({
            "success": False,
            "error": "Only YouTube URLs are supported"
        }), 400

    try:

        filepath = download_media(
            url,
            "audio"
        )

        return send_file(
            filepath,
            as_attachment=True,
            download_name=os.path.basename(filepath),
            mimetype="audio/mp4"
        )

    except Exception as error:

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


# ==========================================
# TEMPORARY FILE CLEANUP
# ==========================================

def cleanup_old_files():

    while True:

        try:

            current_time = time.time()

            for filename in os.listdir(DOWNLOAD_DIR):

                filepath = os.path.join(
                    DOWNLOAD_DIR,
                    filename
                )

                if os.path.isfile(filepath):

                    file_age = (
                        current_time -
                        os.path.getmtime(filepath)
                    )

                    # Delete files older than 10 minutes
                    if file_age > 600:

                        os.remove(filepath)

        except Exception as error:

            print("Cleanup error:", error)

        time.sleep(300)


# Start cleanup thread
cleanup_thread = threading.Thread(
    target=cleanup_old_files,
    daemon=True
)

cleanup_thread.start()


# ==========================================
# START SERVER
# ==========================================

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
