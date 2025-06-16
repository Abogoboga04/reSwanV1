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

# Command untuk backup data ke MongoDB dan mengirim DM dengan data terbaru
@bot.command()
async def backupnow(ctx):
    # Simulasi pengambilan data terbaru yang ingin disimpan ke MongoDB
    new_data = {
        "example_key_1": "example_value_1",
        "example_key_2": "example_value_2",
    }

    try:
        # Simpan data terbaru ke MongoDB
        collection.insert_one({"backup": new_data})
        print(f"✅ Data baru disimpan ke MongoDB: {new_data}")  # Debug: Cek data yang disimpan

        # Kirim DM dengan data terbaru setelah backup
        user_id = ctx.author.id  # Menggunakan ID pengguna yang menjalankan command
        user = await bot.fetch_user(user_id)
        await user.send(f"Backup Data Terbaru: {json.dumps(new_data, indent=4)}")
        await ctx.send("✅ Data backup terbaru berhasil disimpan dan dikirim ke DM!")
        print(f"✅ DM berhasil dikirim kepada {user.name} dengan data terbaru.")
    
    except Exception as e:
        print(f"❌ Gagal melakukan backup atau mengirim DM: {e}")

# Command untuk mengirim data backup yang ada di MongoDB ke DM
@bot.command()
async def sendbackup(ctx):
    user_id = ctx.author.id  # Menggunakan ID pengguna yang menjalankan command
    user = await bot.fetch_user(user_id)

    try:
        # Ambil data terbaru dari MongoDB
        stored_data = collection.find_one(sort=[('_id', -1)])  # Ambil data terbaru
        if stored_data:
            await user.send(f"Backup Data: {json.dumps(stored_data['backup'], indent=4)}")
            await ctx.send("✅ Data backup terbaru berhasil dikirim ke DM!")
            print(f"✅ DM berhasil dikirim kepada {user.name} dengan data dari MongoDB.")
        else:
            await ctx.send("❌ Tidak ada data backup yang tersedia.")
            print(f"❌ Tidak ada data backup yang ditemukan untuk {user.name}.")
    
    except Exception as e:
        print(f"❌ Gagal mengirim DM atau mengambil data dari MongoDB: {e}")

# Jalankan di Replit
keep_alive()

# Token bot Discord Anda dari secrets
bot.run(os.getenv("DISCORD_TOKEN"))
