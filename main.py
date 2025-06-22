import discord
from discord.ext import commands
import aiohttp
import base64
import logging
import os
import io
import asyncio
import json
from io import BytesIO
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)

def save_cookies_from_env():
    encoded = os.getenv("COOKIES_BASE64")
    if not encoded:
        raise ValueError("Environment variable COOKIES_BASE64 not found.")
    
    try:
        decoded = base64.b64decode(encoded)
        with open("cookies.txt", "wb") as f:
            f.write(decoded)
        print("âœ… File cookies.txt berhasil dibuat dari environment variable.")
    except Exception as e:
        print(f"âŒ Gagal decode cookies: {e}")

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
    print(f"ðŸ¤– Bot {bot.user} is now online!")
    print(f"Command yang terdaftar: {[command.name for command in bot.commands]}")

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
                    print(f"âœ… File {filename} berhasil dibaca dari data/")
                except json.JSONDecodeError:
                    await ctx.send(f"âŒ Gagal membaca file {filename} dari data/")
                    print(f"âŒ Gagal membaca file {filename} dari data/")

    # Backup file dari folder config/
    for filename in os.listdir(config_folder):
        if filename.endswith('.json'):
            file_path = os.path.join(config_folder, filename)
            with open(file_path, 'r') as f:
                try:
                    json_data = json.load(f)
                    backup_data[filename] = json_data
                    print(f"âœ… File {filename} berhasil dibaca dari config/")
                except json.JSONDecodeError:
                    await ctx.send(f"âŒ Gagal membaca file {filename} dari config/")
                    print(f"âŒ Gagal membaca file {filename} dari config/")

    # Simpan data backup ke dalam koleksi MongoDB
    if backup_data:
        try:
            print(f"âœ… Data yang akan disimpan ke MongoDB: {backup_data}")  # Logging data sebelum disimpan
            result = collection.insert_one({"backup": backup_data})
            
            if result.inserted_id:
                print(f"âœ… Data backup berhasil disimpan ke MongoDB dengan ID: {result.inserted_id}")

                # Kirim data ke pengguna dengan ID tertentu
                user_id = 1000737066822410311  # Ganti dengan ID pengguna kamu
                user = await bot.fetch_user(user_id)
                await user.send(f"Backup Data: {json.dumps(backup_data, indent=4)}")
                print(f"âœ… Data backup berhasil dikirim ke DM pengguna dengan ID {user_id}.")
                await ctx.send("âœ… Data backup berhasil disimpan dan dikirim ke DM!")
            else:
                await ctx.send("âŒ Gagal menyimpan data ke MongoDB, ID tidak ditemukan.")
        except Exception as e:
            await ctx.send("âŒ Gagal menyimpan data ke MongoDB.")
            print(f"âŒ Gagal menyimpan data ke MongoDB: {e}")
    else:
        await ctx.send("âŒ Tidak ada data untuk dibackup.")

# Command untuk mengirim data backup ke DM
@bot.command()
async def sendbackup(ctx):
    user_id = 1000737066822410311  # Ganti dengan ID kamu
    user = await bot.fetch_user(user_id)

    try:
        stored_data = collection.find_one(sort=[('_id', -1)])
        if not stored_data or 'backup' not in stored_data:
            await ctx.send("âŒ Tidak ada data backup yang tersedia.")
            return

        backup_data = stored_data["backup"]
        await ctx.send("ðŸ“¤ Mengirim file backup satu per satu ke DM...")

        for filename, content in backup_data.items():
            string_buffer = io.StringIO()
            json.dump(content, string_buffer, indent=4, ensure_ascii=False)
            string_buffer.seek(0)

            byte_buffer = io.BytesIO(string_buffer.read().encode('utf-8'))
            byte_buffer.seek(0)

            file = discord.File(fp=byte_buffer, filename=filename)

            try:
                await user.send(content=f"ðŸ“„ Berikut file backup: **{filename}**", file=file)
            except discord.HTTPException as e:
                await ctx.send(f"âŒ Gagal kirim file {filename}: {e}")

        await ctx.send("âœ… Semua file backup berhasil dikirim ke DM!")

    except discord.Forbidden:
        await ctx.send("âŒ Gagal mengirim DM. Pastikan saya dapat mengirim DM ke pengguna ini.")
    except Exception as e:
        await ctx.send("âŒ Terjadi kesalahan saat mengambil data backup.")
        print(f"âŒ Error: {e}")


# Muat semua cog yang ada
async def load_cogs():
    try:
        await bot.load_extension("cogs.leveling")
        await bot.load_extension("cogs.shop")
        await bot.load_extension("cogs.quizz")
        await bot.load_extension("cogs.music")
        await bot.load_extension("cogs.itemmanage")
        await bot.load_extension("cogs.moderation")
        await bot.load_extension("cogs.emojiquiz")
        await bot.load_extension("cogs.hangman") 
        await bot.load_extension("cogs.kuisaja")
        print("âœ… Semua cogs berhasil dimuat.")
    except Exception as e:
        print(f"âŒ Gagal memuat cogs: {e}")

@bot.event
async def setup_hook():
    await load_cogs()
    await load_extensions()
    print("Command yang terdaftar: {[command.name for command in bot.commands]}")
    print("ðŸ” Memulai setup_hook dan load cogs...")
    print("âœ… Selesai setup_hook dan semua cogs dicoba load.")

save_cookies_from_env()

# Jalankan di Replit
keep_alive()

# Token bot Discord Anda dari secrets
bot.run(os.getenv("DISCORD_TOKEN"))
