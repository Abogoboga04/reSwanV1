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
from datetime import datetime # Ditambahkan untuk timestamp di MongoDB

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

# =======================================================================================
# ---> BAGIAN INI TELAH DIREVISI SESUAI PERMINTAAN ANDA <---
# =======================================================================================

# Command untuk backup data dari folder root, data/, dan config/
@bot.command()
@commands.is_owner() # Ditambahkan untuk keamanan, hanya pemilik bot yang bisa menjalankan
async def backupnow(ctx):
    await ctx.send("Memulai proses backup...")
    backup_data = {}

    # Daftar direktori yang akan di-backup. '.' merepresentasikan root.
    directories_to_scan = ['.', 'data/', 'config/']

    for directory in directories_to_scan:
        # Cek apakah direktori ada untuk menghindari error
        if not os.path.isdir(directory):
            print(f"Peringatan: Direktori '{directory}' tidak ditemukan, dilewati.")
            continue
        
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            # Pastikan itu adalah file dan berakhiran .json
            if filename.endswith('.json') and os.path.isfile(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                        # Menggunakan path sebagai kunci untuk menghindari duplikasi nama file
                        backup_data[file_path] = json_data 
                        print(f"✅ File '{file_path}' berhasil dibaca.")
                except json.JSONDecodeError:
                    await ctx.send(f"❌ Gagal membaca file JSON: `{file_path}`")
                    print(f"❌ Gagal membaca file JSON: {file_path}")
                except Exception as e:
                    await ctx.send(f"❌ Terjadi error saat membaca `{file_path}`: {e}")

    # Simpan data backup ke dalam koleksi MongoDB
    if backup_data:
        try:
            # ---> DITERAPKAN: Menggunakan update_one dengan upsert=True untuk efisiensi
            # Ini akan selalu menimpa satu dokumen backup saja, tidak membuat yang baru.
            collection.update_one(
                {"_id": "latest_backup"},  # Selalu menargetkan dokumen dengan ID ini
                {"$set": {
                    "backup": backup_data,
                    "timestamp": datetime.utcnow() # Menambahkan waktu backup
                }},
                upsert=True  # Membuat dokumen jika belum ada
            )
            
            print("✅ Data backup berhasil disimpan ke MongoDB.")
            await ctx.send("✅ Data backup berhasil disimpan ke MongoDB!")

        except Exception as e:
            await ctx.send(f"❌ Gagal menyimpan data ke MongoDB: {e}")
            print(f"❌ Gagal menyimpan data ke MongoDB: {e}")
    else:
        await ctx.send("🤷 Tidak ada file .json yang ditemukan untuk dibackup.")

# Command untuk mengirim data backup ke DM
@bot.command()
@commands.is_owner() # Ditambahkan untuk keamanan
async def sendbackup(ctx):
    user_id = 1000737066822410311  # Ganti dengan ID kamu
    user = await bot.fetch_user(user_id)

    try:
        # ---> DITERAPKAN: Mencari dokumen backup berdasarkan ID yang pasti
        stored_data = collection.find_one({"_id": "latest_backup"})
        if not stored_data or 'backup' not in stored_data:
            await ctx.send("❌ Tidak ada data backup yang tersedia.")
            return

        backup_data = stored_data["backup"]
        await ctx.send("📬 Mengirim file backup satu per satu ke DM...")

        # ---> DIREVISI: Menggunakan file_path dari dictionary
        for file_path, content in backup_data.items():
            # Mengambil nama file asli dari path lengkapnya
            filename = os.path.basename(file_path)
            
            string_buffer = io.StringIO()
            json.dump(content, string_buffer, indent=4, ensure_ascii=False)
            string_buffer.seek(0)

            byte_buffer = io.BytesIO(string_buffer.read().encode('utf-8'))
            byte_buffer.seek(0)

            file = discord.File(fp=byte_buffer, filename=filename)

            try:
                # Menambahkan info path asal file untuk kejelasan
                await user.send(content=f"📄 Berikut file backup dari `/{file_path}`:", file=file)
            except discord.HTTPException as e:
                await ctx.send(f"❌ Gagal kirim file `{filename}`: {e}")

        await ctx.send("✅ Semua file backup berhasil dikirim ke DM!")

    except discord.Forbidden:
        await ctx.send("❌ Gagal mengirim DM. Pastikan saya dapat mengirim DM ke pengguna ini.")
    except Exception as e:
        await ctx.send(f"❌ Terjadi kesalahan saat mengambil data backup: {e}")
        print(f"❌ Error saat sendbackup: {e}")

# =======================================================================================
# Kode Anda yang lain di bawah ini tidak diubah sama sekali
# =======================================================================================

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
        await bot.load_extension("cogs.quotes")
        await bot.load_extension("cogs.newgame")
        await bot.load_extension("cogs.multigame")
        await bot.load_extension("cogs.dunia") 
        print("âœ… Semua cogs berhasil dimuat.")
    except Exception as e:
        print(f"âŒ Gagal memuat cogs: {e}")

@bot.event
async def setup_hook():
    await load_cogs()
    print("Command yang terdaftar: {[command.name for command in bot.commands]}")
    print("ðŸ” Memulai setup_hook dan load cogs...")
    print("âœ… Selesai setup_hook dan semua cogs dicoba load.")

save_cookies_from_env()

# Jalankan di Replit
keep_alive()

# Token bot Discord Anda dari secrets
bot.run(os.getenv("DISCORD_TOKEN"))

