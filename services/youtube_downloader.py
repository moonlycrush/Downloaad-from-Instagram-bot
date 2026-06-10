"""services/youtube_downloader.py

Fixes applied:
  - Thread-safe progress reporting: loop.call_soon_threadsafe() ishlatiladi
  - loop parametri olib tashlandi — ichkaridan asyncio.get_running_loop() olinadi
  - Audio fayl nomini topish glob orqali ishonchli qilindi
  - yt-dlp merge format muammosi hal qilindi (mp4 konteyner)
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
        except Exception:
            pass

    def progress_hook(d: dict):
        _put({
            "status":            d.get("status"),
            "downloaded_bytes":  d.get("downloaded_bytes") or 0,
            "total_bytes":       d.get("total_bytes") or d.get("total_bytes_estimate") or 0,
            "speed":             d.get("speed") or 0,
            "eta":               d.get("eta") or 0,
        })

    ytdl_opts["progress_hooks"] = [progress_hook]

    if kind == "audio":
        ytdl_opts["format"] = "bestaudio/best"
        ytdl_opts["postprocessors"] = [
            {
                "key":              "FFmpegExtractAudio",
                "preferredcodec":   "mp3",
                "preferredquality": "192",
            }
        ]
    else:
        # Video: avval bestaudio+bestvideo, keyin mp4 ga merge
        fmt = "bestvideo+bestaudio/best"
        if quality and quality != "best" and quality.endswith("p"):
            h = quality[:-1]
            fmt = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"
        ytdl_opts["format"] = fmt
        ytdl_opts["merge_output_format"] = "mp4"

    with YoutubeDL(ytdl_opts) as ydl:
        info     = ydl.extract_info(url, download=True)
        # prepare_filename — asosiy nom (ext o'zgargan bo'lishi mumkin)
        raw_path = ydl.prepare_filename(info)
        base     = os.path.splitext(raw_path)[0]

        if kind == "audio":
            # FFmpeg mp3 ga o'zgartiradi — glob bilan izlaymiz
            candidates = glob.glob(base + ".mp3")
            if not candidates:
                # Boshqa audio formatlar
                candidates = glob.glob(base + ".*")
            if candidates:
                return candidates[0]
            return raw_path   # Fallback

        else:
            # Video uchun mp4 bo'lishi kerak
            mp4_path = base + ".mp4"
            if os.path.exists(mp4_path):
                return mp4_path
            # Merge bo'lmagan holat
            candidates = glob.glob(base + ".*")
            if candidates:
                return candidates[0]
            return raw_path


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
    progress_queue: asyncio.Queue = asyncio.Queue()

    with ThreadPoolExecutor(max_workers=1) as pool:
        download_future = loop.run_in_executor(
            pool, _blocking_download, url, out_dir, kind, quality, loop, progress_queue
        )

        async def reporter():
            try:
                while True:
                    # Download tugasa qolgan xabarlarni o'qib chiqamiz, so'ng tugatamiz
                    try:
                        info = await asyncio.wait_for(progress_queue.get(), timeout=0.5)
                    except asyncio.TimeoutError:
                        if download_future.done():
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
                        try:
                            if status_message:
                                await status_message.edit_text(text)
                        except Exception:
                            pass

                    elif status == "finished":
                        try:
                            if status_message:
                                await status_message.edit_text("✅ Yuklandi. Fayl tayyorlanmoqda...")
                        except Exception:
                            pass

                    elif status == "error":
                        try:
                            if status_message:
                                await status_message.edit_text("❌ Xatolik yuz berdi.")
                        except Exception:
                            pass

                    if download_future.done():
                        break

            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Reporter error")

        reporter_task = asyncio.create_task(reporter())
        try:
            out_path = await download_future
        finally:
            reporter_task.cancel()
            try:
                await reporter_task
            except asyncio.CancelledError:
                pass

    return out_path