import re
import asyncio
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message
from terabox_downloader import TeraboxFile
import os

API_ID = int(os.environ.get("10006297"))
API_HASH = os.environ.get("8bb6a09b00d359d6081fcfa3ba7db0a4")
BOT_TOKEN = os.environ.get("8363193433:AAEO4op7PZV5TymEdqRaNXkK5fPEhy0KdN4")

app = Client("terabox_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=8)

TERABOX_REGEX = r"(https?://(?:www\.)?(?:terabox|1024tera|4funbox)\.com/[^\s]+)"

# -------- High speed buffer --------
class AsyncStream:
    def __init__(self, maxsize=50):
        self.queue = asyncio.Queue(maxsize=maxsize)
        self.finished = False

    async def write(self, data):
        await self.queue.put(data)

    async def close(self):
        self.finished = True
        await self.queue.put(None)

    def read(self, size=-1):
        return asyncio.run(self._read())

    async def _read(self):
        chunk = await self.queue.get()
        return chunk if chunk else b""

# ---------- Progress ----------
async def progress(current, total, message, text):
    if total == 0:
        return
    percent = current * 100 / total
    bar = "█" * int(percent / 5) + "░" * (20 - int(percent / 5))
    try:
        await message.edit_text(f"{text}\n[{bar}] {percent:.1f}%")
    except:
        pass

# ---------- Turbo downloader ----------
async def turbo_download(url, stream, status):
    connector = aiohttp.TCPConnector(limit=16, force_close=True)
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get(url) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            async for chunk in resp.content.iter_chunked(1024*1024):  # 1MB chunks
                downloaded += len(chunk)
                await stream.write(chunk)
                await progress(downloaded, total, status, "⬇️ Downloading")
    await stream.close()

# ---------- Turbo upload ----------
async def turbo_upload(client, chat_id, stream, filename, status):
    await client.send_video(
        chat_id=chat_id,
        video=stream,
        caption=filename,
        supports_streaming=True,
        progress=lambda c,t: asyncio.create_task(progress(c,t,status,"📤 Uploading"))
    )

async def stream_to_telegram(client, chat_id, url, filename, status):
    stream = AsyncStream(maxsize=100)
    await asyncio.gather(
        turbo_download(url, stream, status),
        turbo_upload(client, chat_id, stream, filename, status)
    )

# ---------- Handle Message ----------
@app.on_message(filters.private & filters.text)
async def handle_link(client: Client, message: Message):
    links = re.findall(TERABOX_REGEX, message.text)

    if not links:
        await message.reply("Send a valid Terabox link.")
        return

    for link in links:
        status = await message.reply(f"🔍 Processing link:\n{link}")
        try:
            tb = TeraboxFile(link)
            files = tb.get_files()

            for file in files:
                name = file["name"]
                mirrors = [file.get("download_url"), file.get("stream_url"), file.get("fast_download")]
                mirrors = [m for m in mirrors if m]

                success = False
                for i, url in enumerate(mirrors,1):
                    await status.edit_text(f"🌐 Trying mirror {i}/{len(mirrors)}")
                    try:
                        await stream_to_telegram(client, message.chat.id, url, name, status)
                        success = True
                        break
                    except:
                        continue

                if not success:
                    await status.edit_text("❌ All mirrors failed")

            await status.edit_text("✅ All files sent!")

        except Exception as e:
            await status.edit_text(f"❌ Failed: {str(e)}")

app.run()
