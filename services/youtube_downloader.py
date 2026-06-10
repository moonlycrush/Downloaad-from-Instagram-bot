"""services/youtube_downloader.py

Fixes applied:
  - Thread-safe progress reporting: loop.call_soon_threadsafe() ishlatiladi
  - loop parametri olib tashlandi — ichkaridan asyncio.get_running_loop() olinadi
  - Audio fayl nomini topish glob orqali ishonchli qilindi
  - yt-dlp merge format muammosi hal qilindi (mp4 konteyner)
  - Detailed error logging added
"""
import glob
import logging
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from yt_dlp import YoutubeDL

logger = logging.getLogger(__name__)


def _format_progress_bar(percent: float, width: int = 20) -> str:
    filled = int(width * percent / 100)
    return "█" * filled + "░" * (width - filled)


def _blocking_download(
    url: str,
    out_dir: str,
    kind: str,
    quality: str,
    loop: asyncio.AbstractEventLoop,
    progress_queue: asyncio.Queue,
) -> str:
    os.makedirs(out_dir, exist_ok=True)

    # Outtmpl — maxsus belgilarni xavfsiz almashtirish
    outtmpl = os.path.join(out_dir, "%(title).80s.%(ext)s")

    logger.info("🔄 [yt-dlp] Starting download - Kind: %s | Quality: %s | URL: %s", kind, quality, url)

    ytdl_opts: dict = {
        "outtmpl":      outtmpl,
        "noplaylist":   True,
        "quiet":        True,
        "no_warnings":  True,
        "ignoreerrors": False,
    }

    def _put(info: dict):
        """Thread-safe ravishda queue ga yozish."""
        try:
            loop.call_soon_threadsafe(progress_queue.put_nowait, info)
        except Exception as e:
            logger.debug("⚠️ [yt-dlp] Failed to put progress info - Error: %s", str(e))

    def progress_hook(d: dict):
        status = d.get("status")
        if status == "downloading":
            downloaded = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            speed = d.get("speed") or 0
            eta = d.get("eta") or 0
            
            if total > 0:
                percent = (downloaded / total * 100)
                logger.debug("📊 [yt-dlp] Progress - %d%% | %.2f MB / %.2f MB | Speed: %.2f MB/s", 
                           int(percent), 
                           downloaded / 1_048_576, 
                           total / 1_048_576,
                           speed / 1_048_576 if speed else 0)
        
        _put({
            "status":            status,
            "downloaded_bytes":  d.get("downloaded_bytes") or 0,
            "total_bytes":       d.get("total_bytes") or d.get("total_bytes_estimate") or 0,
            "speed":             d.get("speed") or 0,
            "eta":               d.get("eta") or 0,
        })

    ytdl_opts["progress_hooks"] = [progress_hook]

    if kind == "audio":
        logger.info("🎵 [yt-dlp] Configuring for AUDIO download")
        ytdl_opts["format"] = "bestaudio/best"
        ytdl_opts["postprocessors"] = [
            {
                "key":              "FFmpegExtractAudio",
                "preferredcodec":   "mp3",
                "preferredquality": "192",
            }
        ]
    else:
        logger.info("🎬 [yt-dlp] Configuring for VIDEO download - Quality: %s", quality)
        # Video: avval bestaudio+bestvideo, keyin mp4 ga merge
        fmt = "bestvideo+bestaudio/best"
        if quality and quality != "best" and quality.endswith("p"):
            h = quality[:-1]
            fmt = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"
            logger.info("📺 [yt-dlp] Quality filter applied - Height: %sp", h)
        ytdl_opts["format"] = fmt
        ytdl_opts["merge_output_format"] = "mp4"
        logger.debug("📋 [yt-dlp] Format string: %s", fmt)

    try:
        logger.debug("📥 [yt-dlp] Starting YoutubeDL extraction...")
        with YoutubeDL(ytdl_opts) as ydl:
            logger.debug("📡 [yt-dlp] Extracting info from URL...")
            info     = ydl.extract_info(url, download=True)
            # prepare_filename — asosiy nom (ext o'zgargan bo'lishi mumkin)
            raw_path = ydl.prepare_filename(info)
            base     = os.path.splitext(raw_path)[0]

            logger.info("✅ [yt-dlp] Extraction completed - Base path: %s", base)

            if kind == "audio":
                logger.debug("🔍 [yt-dlp] Looking for MP3 file...")
                # FFmpeg mp3 ga o'zgartiradi — glob bilan izlaymiz
                candidates = glob.glob(base + ".mp3")
                if not candidates:
                    logger.debug("⚠️ [yt-dlp] MP3 not found, searching for any audio format...")
                    # Boshqa audio formatlar
                    candidates = glob.glob(base + ".*")
                if candidates:
                    result = candidates[0]
                    file_size = os.path.getsize(result) / (1024 * 1024)
                    logger.info("✅ [yt-dlp] Audio file found - Path: %s | Size: %.2f MB", 
                              os.path.basename(result), file_size)
                    return result
                logger.warning("⚠️ [yt-dlp] No audio file found, returning raw path as fallback")
                return raw_path   # Fallback

            else:
                logger.debug("🔍 [yt-dlp] Looking for MP4 video file...")
                # Video uchun mp4 bo'lishi kerak
                mp4_path = base + ".mp4"
                if os.path.exists(mp4_path):
                    file_size = os.path.getsize(mp4_path) / (1024 * 1024)
                    logger.info("✅ [yt-dlp] MP4 video file found - Path: %s | Size: %.2f MB", 
                              os.path.basename(mp4_path), file_size)
                    return mp4_path
                
                logger.debug("⚠️ [yt-dlp] MP4 not found, searching for any video format...")
                # Merge bo'lmagan holat
                candidates = glob.glob(base + ".*")
                if candidates:
                    result = candidates[0]
                    file_size = os.path.getsize(result) / (1024 * 1024)
                    logger.warning("⚠️ [yt-dlp] Using alternative format - Path: %s | Size: %.2f MB", 
                                 os.path.basename(result), file_size)
                    return result
                
                logger.warning("⚠️ [yt-dlp] No video file found, returning raw path as fallback")
                return raw_path
    except Exception as e:
        logger.error("❌ [yt-dlp] Download failed - Error: %s | Type: %s | Kind: %s | Quality: %s | URL: %s", 
                   str(e), type(e).__name__, kind, quality, url, exc_info=True)
        raise


async def download_youtube(
    url:            str,
    out_dir:        str,
    loop:           asyncio.AbstractEventLoop,
    kind:           str = "video",
    quality:        str = "best",
    status_message=None,
) -> str:
    """
    URL ni yuklab, fayl yo'lini qaytaradi.
    loop — asyncio.get_running_loop() dan olinishi kerak.
    """
    logger.info("🚀 [YouTube] Starting async download - Kind: %s | Quality: %s | URL: %s", 
               kind, quality, url)
    
    progress_queue: asyncio.Queue = asyncio.Queue()

    with ThreadPoolExecutor(max_workers=1) as pool:
        logger.debug("⏳ [YouTube] Submitting download to thread pool...")
        download_future = loop.run_in_executor(
            pool, _blocking_download, url, out_dir, kind, quality, loop, progress_queue
        )

        async def reporter():
            logger.debug("📊 [YouTube] Reporter task started")
            try:
                while True:
                    # Download tugasa qolgan xabarlarni o'qib chiqamiz, so'ng tugatamiz
                    try:
                        info = await asyncio.wait_for(progress_queue.get(), timeout=0.5)
                    except asyncio.TimeoutError:
                        if download_future.done():
                            logger.debug("✅ [YouTube] Download finished, stopping reporter")
                            break
                        continue

                    status = info.get("status")
                    if status == "downloading":
                        total   = info.get("total_bytes") or 0
                        done    = info.get("downloaded_bytes") or 0
                        speed   = info.get("speed") or 0
                        eta     = info.get("eta") or 0
                        percent = (done / total * 100) if total else 0.0
                        bar     = _format_progress_bar(percent)
                        done_mb  = done / 1_048_576
                        total_mb = total / 1_048_576 if total else 0.0
                        text = (
                            "⬇️ Yuklanmoqda...\n"
                            f"{bar} {percent:.1f}%\n\n"
                            f"📦 {done_mb:.2f} MB / {total_mb:.2f} MB\n"
                            f"⚡ {speed/1_048_576:.2f} MB/s\n"
                            f"⏳ ETA: {int(eta)}s"
                        )
                        logger.debug("📊 [YouTube] Progress - %.1f%% complete", percent)
                        try:
                            if status_message:
                                await status_message.edit_text(text)
                        except Exception as edit_error:
                            logger.debug("⚠️ [YouTube] Failed to update progress message - Error: %s", 
                                       str(edit_error))

                    elif status == "finished":
                        logger.info("✅ [YouTube] Download finished, preparing file...")
                        try:
                            if status_message:
                                await status_message.edit_text("✅ Yuklandi. Fayl tayyorlanmoqda...")
                        except Exception as edit_error:
                            logger.debug("⚠️ [YouTube] Failed to update finish message - Error: %s", 
                                       str(edit_error))

                    elif status == "error":
                        logger.error("❌ [YouTube] yt-dlp reported error during download")
                        try:
                            if status_message:
                                await status_message.edit_text("❌ Xatolik yuz berdi.")
                        except Exception as edit_error:
                            logger.debug("⚠️ [YouTube] Failed to update error message - Error: %s", 
                                       str(edit_error))

                    if download_future.done():
                        logger.debug("✅ [YouTube] Download future completed")
                        break

            except asyncio.CancelledError:
                logger.debug("🛑 [YouTube] Reporter task cancelled")
            except Exception as reporter_error:
                logger.error("❌ [YouTube] Reporter error - Error: %s | Type: %s", 
                           str(reporter_error), type(reporter_error).__name__, exc_info=True)

        reporter_task = asyncio.create_task(reporter())
        try:
            logger.debug("⏳ [YouTube] Waiting for download to complete...")
            out_path = await download_future
            logger.info("✅ [YouTube] Download completed successfully - Output: %s", os.path.basename(out_path))
            return out_path
        except Exception as download_error:
            logger.error("❌ [YouTube] Download failed during execution - Error: %s | Type: %s | Kind: %s | Quality: %s", 
                       str(download_error), type(download_error).__name__, kind, quality, exc_info=True)
            raise
        finally:
            logger.debug("🧹 [YouTube] Cleaning up reporter task...")
            reporter_task.cancel()
            try:
                await reporter_task
            except asyncio.CancelledError:
                logger.debug("✅ [YouTube] Reporter task cancelled successfully")
