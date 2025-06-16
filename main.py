import discord
from discord.ext import commands
import aiohttp
import base64
import os
import asyncio
import json
from pymongo import MongoClient
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

# Koneksi ke MongoDB
mongo_uri = os.getenv("MONGODB_URI")  # Pastikan variabel ini sudah diatur
client = MongoClient(mongo_uri)
db = client["reSwan"]  # Nama database
collection = db["Data collection"]  # Nama koleksi

# Import fungsi keep_alive jika Anda menggunakan Replit
from keep_alive import keep_alive

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Variabel global untuk menyimpan data backup terakhir
last_backup_data = {}

# Saat bot menyala
@bot.event
async def on_ready():
    print(f"🤖 Bot {bot.user} is now online!")
    bot.loop.create_task(ping_task())
    bot.loop.create_task(send_backup_data_task())

async def ping_task():
    while True:
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

# Command untuk backup data dari folder data/ dan config/
@bot.command()
async def backupnow(ctx):
    global last_backup_data
    backup_data = {}

    # Backup semua file JSON dari folder data/
    data_folder = 'data/'
    config_folder = 'config/'

    # Backup file dari folder data/
    for filename in os.listdir(data_folder):
        if filename.endswith('.json'):
            file_path = os.path.join(data_folder, filename)
            with open(file_path, 'r') as f:
                try:
                    json_data = json.load(f)
                    backup_data[filename] = json_data
                except json.JSONDecodeError:
                    await ctx.send(f"❌ Gagal membaca file {filename}")

    # Backup file dari folder config/
    for filename in os.listdir(config_folder):
        if filename.endswith('.json'):
            file_path = os.path.join(config_folder, filename)
            with open(file_path, 'r') as f:
                try:
                    json_data = json.load(f)
                    backup_data[filename] = json_data
                except json.JSONDecodeError:
                    await ctx.send(f"❌ Gagal membaca file {filename}")

    # Simpan data backup ke dalam koleksi MongoDB dan ke variabel global
    if backup_data:
        collection.insert_one({"backup": backup_data})
        last_backup_data = backup_data  # Simpan data untuk dikirim nanti
        await ctx.send("✅ Data backup berhasil disimpan!")
    else:
        await ctx.send("❌ Tidak ada data untuk dibackup.")

# Task untuk mengirim data backup ke DM setiap 3 jam
async def send_backup_data_task():
    await bot.wait_until_ready()  # Tunggu hingga bot siap
    user_id = 1000737066822410311  # Ganti dengan ID pengguna kamu
    user = await bot.fetch_user(user_id)

    while not bot.is_closed():
        if last_backup_data:
            try:
                # Kirim data backup ke DM
                await user.send(f"Backup Data: {json.dumps(last_backup_data, indent=4)}")
            except Exception as e:
                print(f"❌ Gagal mengirim DM: {e}")
        
        await asyncio.sleep(10800)  # Tidur selama 3 jam (10800 detik)

# Muat semua cog yang ada
async def load_cogs():
    await bot.load_extension("cogs.livestream")
    await bot.load_extension("cogs.leveling")
    await bot.load_extension("cogs.shop")
    await bot.load_extension("cogs.moderation")
    await bot.load_extension("cogs.backup")
    await bot.load_extension("cogs.quizz")
    await bot.load_extension("cogs.music")
    await bot.load_extension("cogs.inventory")

# Gunakan setup_hook agar loop dan tasks bisa jalan
@bot.event
async def setup_hook():
    await load_cogs()

save_cookies_from_env()

# Jalankan di Replit
keep_alive()

# Token bot Discord Anda dari secrets
bot.run(os.getenv("DISCORD_TOKEN"))
