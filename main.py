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

# Saat bot menyala
@bot.event
async def on_ready():
    print(f"🤖 Bot {bot.user} is now online!")

# Command untuk backup data dari folder data/ dan config/
@bot.command()
async def backupnow(ctx):
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
                    print(f"✅ File {filename} berhasil dibaca dari data/")
                except json.JSONDecodeError:
                    await ctx.send(f"❌ Gagal membaca file {filename} dari data/")
                    print(f"❌ Gagal membaca file {filename} dari data/")

    # Backup file dari folder config/
    for filename in os.listdir(config_folder):
        if filename.endswith('.json'):
            file_path = os.path.join(config_folder, filename)
            with open(file_path, 'r') as f:
                try:
                    json_data = json.load(f)
                    backup_data[filename] = json_data
                    print(f"✅ File {filename} berhasil dibaca dari config/")
                except json.JSONDecodeError:
                    await ctx.send(f"❌ Gagal membaca file {filename} dari config/")
                    print(f"❌ Gagal membaca file {filename} dari config/")

    # Simpan data backup ke dalam koleksi MongoDB
    if backup_data:
        try:
            print(f"✅ Data yang akan disimpan ke MongoDB: {backup_data}")  # Logging data sebelum disimpan
            result = collection.insert_one({"backup": backup_data})
            
            if result.inserted_id:
                print(f"✅ Data backup berhasil disimpan ke MongoDB dengan ID: {result.inserted_id}")

                # Kirim data ke pengguna dengan ID tertentu
                user_id = 1000737066822410311  # Ganti dengan ID pengguna kamu
                user = await bot.fetch_user(user_id)
                await user.send(f"Backup Data: {json.dumps(backup_data, indent=4)}")
                print(f"✅ Data backup berhasil dikirim ke DM pengguna dengan ID {user_id}.")
                await ctx.send("✅ Data backup berhasil disimpan dan dikirim ke DM!")
            else:
                await ctx.send("❌ Gagal menyimpan data ke MongoDB, ID tidak ditemukan.")
        except Exception as e:
            await ctx.send("❌ Gagal menyimpan data ke MongoDB.")
            print(f"❌ Gagal menyimpan data ke MongoDB: {e}")
    else:
        await ctx.send("❌ Tidak ada data untuk dibackup.")

# Command untuk mengirim data backup ke DM
@bot.command()
async def sendbackup(ctx):
    user_id = 1000737066822410311  # Ganti dengan ID pengguna yang ingin kamu kirimi data
    user = await bot.fetch_user(user_id)

    try:
        # Ambil data terbaru dari MongoDB
        stored_data = collection.find_one(sort=[('_id', -1)])  # Ambil data terbaru
        if stored_data:
            # Kirim data dalam format JSON
            await user.send(f"Backup Data: {json.dumps(stored_data['backup'], indent=4)}")
            await ctx.send("✅ Data backup terbaru berhasil dikirim ke DM!")
            print(f"✅ DM berhasil dikirim kepada {user.name} dengan data dari MongoDB.")
        else:
            await ctx.send("❌ Tidak ada data backup yang tersedia.")
            print(f"❌ Tidak ada data backup yang ditemukan untuk {user.name}.")
    
    except Exception as e:
        await ctx.send("❌ Gagal mengirim DM atau mengambil data dari MongoDB.")
        print(f"❌ Gagal mengirim DM atau mengambil data dari MongoDB: {e}")

# Muat semua cog yang ada
async def load_cogs():
    try:
        await bot.load_extension("cogs.livestream")
        await bot.load_extension("cogs.leveling")
        await bot.load_extension("cogs.shop")
        await bot.load_extension("cogs.moderation")
        await bot.load_extension("cogs.backup")
        await bot.load_extension("cogs.quizz")
        await bot.load_extension("cogs.music")
        await bot.load_extension("cogs.inventory")
        print("✅ Semua cogs berhasil dimuat.")
    except Exception as e:
        print(f"❌ Gagal memuat cogs: {e}")

# Gunakan setup_hook agar loop dan tasks bisa jalan
@bot.event
async def setup_hook():
    await load_cogs()

save_cookies_from_env()

# Jalankan di Replit
keep_alive()

# Token bot Discord Anda dari secrets
bot.run(os.getenv("DISCORD_TOKEN"))
