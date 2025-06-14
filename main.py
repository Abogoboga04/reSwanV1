import discord
from discord.ext import commands
import aiohttp
import base64
import os
import asyncio
from dotenv import load_dotenv
load_dotenv()

def save_cookies_from_env():
    encoded = os.getenv("COOKIES_BASE64")
    if not encoded:
        raise ValueError("Environment variable COOKIES_BASE64 not found.")
    
    try:
        decoded = base64.b64decode(encoded)
        with open("cookies.txt", "wb") as f:
            f.write(decoded)
        print("✅ File cookies.txt berhasil dibuat dari environment variable.")
    except Exception as e:
        print(f"❌ Gagal decode cookies: {e}")
        
# Import fungsi keep_alive jika Anda menggunakan Replit
from keep_alive import keep_alive

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Saat bot menyala
@bot.event
async def on_ready():
    print(f"🤖 Bot {bot.user} is now online!")
    # Memindahkan ping ke dalam task terpisah
    bot.loop.create_task(ping_task())

async def ping_task():
    while True:
        # Ping ke localhost (internal) untuk menjaga bot tetap aktif
        await ping_url('http://localhost:8080/ping')
        await asyncio.sleep(300)  # Ping setiap 5 menit

async def ping_url(url):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                print(f'Ping status: {response.status}')
                if response.status == 200:
                    print("URL is reachable!")
                else:
                    print("Failed to reach the URL.")
        except Exception as e:
            print(f'Error pinging the URL: {e}')

# Muat semua cog yang ada
async def load_cogs():
    await bot.load_extension("cogs.livestream")
    await bot.load_extension("cogs.leveling")
    await bot.load_extension("cogs.shop")
    await bot.load_extension("cogs.moderation")
    await bot.load_extension("cogs.backup")
    await bot.load_extension("cogs.musicquiz")

# Gunakan setup_hook agar loop dan tasks bisa jalan
@bot.event
async def setup_hook():
    await load_cogs()
save_cookies_from_env()
    
# Jalankan di Replit
keep_alive()
 
# Token bot Discord Anda dari secrets
bot.run(os.getenv("DISCORD_TOKEN"))
