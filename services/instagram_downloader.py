"""services/instagram_downloader.py

Uses instaloader in thread executor to download a post.
Returns list of downloaded file paths (absolute).
"""
import logging
import os
from pathlib import Path
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

logger = logging.getLogger(__name__)


def _download_yt_dlp(url: str, out_dir: str) -> List[str]:
    from yt_dlp import YoutubeDL
    import glob
    os.makedirs(out_dir, exist_ok=True)
    outtmpl = os.path.join(out_dir, "%(id)s_ytdlp.%(ext)s")
    
    ydl_opts = {
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        # Try to extract best quality video/photo
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
    }
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return []
            
            # yt-dlp can sometimes return a playlist of items (e.g. carousel)
            if "entries" in info:
                entries = info["entries"]
            else:
                entries = [info]
                
            files = []
            for ent in entries:
                if not ent: continue
                raw_path = ydl.prepare_filename(ent)
                base = os.path.splitext(raw_path)[0]
                
                # Check for mp4 or jpg
                for ext in [".mp4", ".jpg", ".webp", ".png", ".webm"]:
                    if os.path.exists(base + ext):
                        files.append(base + ext)
                        break
            
            return list(set(files))
    except Exception:
        logger.exception("yt-dlp fallback failed for Instagram")
        return []


def _download_blocking(url: str, out_dir: str, username: Optional[str], password: Optional[str]) -> List[str]:
    # 1. Try Instaloader first
    try:
        import instaloader
        L = instaloader.Instaloader(
            dirname_pattern=out_dir,
            download_pictures=True,
            download_videos=True,
            save_metadata=False,
            post_metadata_txt_pattern="",
        )
        if username and password:
            try:
                L.login(username, password)
            except Exception:
                pass

        path_part = url.rstrip("/").split("?")[0].rstrip("/")
        shortcode = path_part.split("/")[-1]
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        target_folder = Path(out_dir) / post.shortcode
        target_folder.mkdir(parents=True, exist_ok=True)
        
        L.download_post(post, target=str(target_folder))
        files = [str(p.resolve()) for p in sorted(target_folder.glob("*.*"))]
        if files:
            return files
    except Exception as e:
        logger.warning(f"Instaloader failed ({e}), trying yt-dlp fallback...")
        
    # 2. If Instaloader fails or returns empty, try yt-dlp fallback
    return _download_yt_dlp(url, out_dir)


async def download_instagram(url: str, base_dir: str, username: Optional[str] = None, password: Optional[str] = None) -> List[str]:
    out_dir = os.path.join(base_dir, "instagram")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=2) as pool:
        files = await loop.run_in_executor(pool, _download_blocking, url, out_dir, username, password)
    return files