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
    
    logger.info("🔄 [yt-dlp fallback] Starting Instagram download - URL: %s", url)
    
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
            logger.debug("📥 [yt-dlp] Extracting info from URL - %s", url)
            info = ydl.extract_info(url, download=True)
            if not info:
                logger.warning("⚠️ [yt-dlp] No info extracted from URL - %s", url)
                return []
            
            # yt-dlp can sometimes return a playlist of items (e.g. carousel)
            if "entries" in info:
                entries = info["entries"]
                logger.info("📋 [yt-dlp] Carousel detected - Items: %d", len(entries))
            else:
                entries = [info]
                logger.debug("📁 [yt-dlp] Single item detected")
                
            files = []
            for idx, ent in enumerate(entries, 1):
                if not ent:
                    logger.debug("⏭️ [yt-dlp] Skipping empty entry %d", idx)
                    continue
                raw_path = ydl.prepare_filename(ent)
                base = os.path.splitext(raw_path)[0]
                
                logger.debug("🔍 [yt-dlp] Processing entry %d - Base: %s", idx, base)
                
                # Check for mp4 or jpg
                for ext in [".mp4", ".jpg", ".webp", ".png", ".webm"]:
                    if os.path.exists(base + ext):
                        full_path = base + ext
                        file_size_mb = os.path.getsize(full_path) / (1024 * 1024)
                        logger.info("✅ [yt-dlp] File found - Path: %s | Size: %.2f MB | Ext: %s", 
                                  os.path.basename(full_path), file_size_mb, ext)
                        files.append(full_path)
                        break
            
            unique_files = list(set(files))
            logger.info("✅ [yt-dlp fallback] Download completed - Total files: %d", len(unique_files))
            return unique_files
    except Exception as e:
        logger.error("❌ [yt-dlp fallback] Download failed - Error: %s | Type: %s | URL: %s", 
                   str(e), type(e).__name__, url, exc_info=True)
        return []


def _download_blocking(url: str, out_dir: str, username: Optional[str], password: Optional[str]) -> List[str]:
    logger.info("🔄 [Instagram] Download started - URL: %s", url)
    
    # 1. Try Instaloader first
    try:
        import instaloader
        logger.info("📦 [Instaloader] Initializing Instaloader...")
        L = instaloader.Instaloader(
            dirname_pattern=out_dir,
            download_pictures=True,
            download_videos=True,
            save_metadata=False,
            post_metadata_txt_pattern="",
        )
        
        if username and password:
            try:
                logger.info("🔐 [Instaloader] Attempting login with username: %s", username)
                L.login(username, password)
                logger.info("✅ [Instaloader] Login successful")
            except Exception as login_error:
                logger.warning("⚠️ [Instaloader] Login failed - Will continue as guest - Error: %s", 
                             str(login_error))

        path_part = url.rstrip("/").split("?")[0].rstrip("/")
        shortcode = path_part.split("/")[-1]
        logger.info("📍 [Instaloader] Extracted shortcode: %s", shortcode)
        
        logger.debug("🔄 [Instaloader] Fetching post data...")
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        target_folder = Path(out_dir) / post.shortcode
        target_folder.mkdir(parents=True, exist_ok=True)
        
        logger.info("📥 [Instaloader] Downloading post - Shortcode: %s | Folder: %s", 
                   post.shortcode, target_folder)
        L.download_post(post, target=str(target_folder))
        
        files = [str(p.resolve()) for p in sorted(target_folder.glob("*.*"))]
        logger.info("✅ [Instaloader] Post downloaded successfully - Files found: %d", len(files))
        
        for idx, f in enumerate(files, 1):
            file_size_mb = os.path.getsize(f) / (1024 * 1024)
            logger.debug("📁 [Instaloader] File %d: %s | Size: %.2f MB", 
                       idx, os.path.basename(f), file_size_mb)
        
        if files:
            logger.info("✅ [Instaloader] Download completed successfully - Total: %d files", len(files))
            return files
    except Exception as e:
        logger.warning("⚠️ [Instaloader] Download failed - Error: %s | Type: %s | Will try yt-dlp fallback...", 
                     str(e), type(e).__name__)
        
    # 2. If Instaloader fails or returns empty, try yt-dlp fallback
    logger.info("🔄 Switching to yt-dlp fallback method...")
    return _download_yt_dlp(url, out_dir)


async def download_instagram(url: str, base_dir: str, username: Optional[str] = None, password: Optional[str] = None) -> List[str]:
    out_dir = os.path.join(base_dir, "instagram")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    
    logger.info("🚀 [Instagram] Starting async download - URL: %s | Output dir: %s", url, out_dir)
    
    try:
        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=2) as pool:
            logger.debug("⏳ [Instagram] Running download in thread pool executor...")
            files = await loop.run_in_executor(pool, _download_blocking, url, out_dir, username, password)
        
        logger.info("✅ [Instagram] Async download completed - Files: %d", len(files) if files else 0)
        return files
    except Exception as e:
        logger.error("❌ [Instagram] Async download error - Error: %s | Type: %s | URL: %s", 
                   str(e), type(e).__name__, url, exc_info=True)
        return []
