import discord
from discord.ext import commands
import aiohttp
import base64
import logging
import os
import io
import asyncio
import json
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

class Hangman(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}
        self.bank_data = self.load_bank_data()
        self.level_data = self.load_level_data()
        self.questions = self.load_hangman_data()
        
        # Debug: cek jumlah pertanyaan yang dimuat
        print(f"Jumlah pertanyaan yang dimuat: {len(self.questions)}")  # Debug: jumlah pertanyaan

        self.game_channel_id = 1379458566452154438  # ID channel yang diizinkan

    def load_bank_data(self):
        with open('data/bank_data.json', 'r', encoding='utf-8') as f:
            return json.load(f)

    def load_level_data(self):
        with open('data/level_data.json', 'r', encoding='utf-8') as f:
            return json.load(f)

    def load_hangman_data(self):
        current_dir = os.path.dirname(__file__)  # Folder cogs/
        file_path = os.path.join(current_dir, "..", "data", "questions_hangman.json")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data["questions"]

    async def get_user_image(self, ctx, user_data):
        """Mengambil gambar pengguna dari URL yang disimpan atau menggunakan avatar pengguna."""
        # Mengambil URL gambar
        custom_image_url = user_data.get("image_url") or str(ctx.author.avatar.url)

        # Cek validitas URL gambar
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(custom_image_url) as resp:
                    if resp.status == 200:
                        image_data = BytesIO(await resp.read())
                        return image_data
                    else:
                        raise Exception("Invalid image URL")
        except Exception:
            # Jika URL tidak valid, ambil gambar profil default
            default_image_url = str(ctx.author.avatar.url)
            async with aiohttp.ClientSession() as session:
                async with session.get(default_image_url) as resp:
                    return BytesIO(await resp.read())

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

@bot.command(name="resman", help="Mulai permainan Hangman.")
    async def resman(self, ctx):
        if ctx.channel.id != self.game_channel_id:
            await ctx.send("Permainan Hangman hanya bisa dimainkan di channel yang ditentukan.")
            return

        if ctx.author.id in self.active_games:
            await ctx.send("Anda sudah sedang bermain Hangman. Silakan tunggu hingga selesai.")
            return

        embed = discord.Embed(
            title="🎮 Cara Bermain Hangman",
            description=(
                "Selamat datang di permainan Hangman! 😢✨\n\n"
                "Kamu akan diberikan satu kata untuk ditebak.\n"
                "Jawab dengan satu kata. Jika benar, kamu akan mendapatkan RSWN!\n"
                "Jika kamu berhasil menjawab semua dengan benar, ada bonus menunggu!\n\n"
                "Tapi ingat, waktu adalah musuh terbesarmu. 2 menit untuk menyelesaikan 10 soal.\n\n"
                "Siap untuk memulai? Klik tombol di bawah ini untuk memulai permainan!"
            ),
            color=0x00ff00
        )

        view = discord.ui.View()
        start_button = discord.ui.Button(label="🔵 START", style=discord.ButtonStyle.primary)

        async def start_game(interaction):
            if ctx.author.id in self.active_games:
                await ctx.send("Anda sudah sedang bermain Hangman. Silakan tunggu hingga selesai.")
                return

            self.active_games[ctx.author.id] = {
                "score": 0,
                "correct": 0,
                "wrong": 0,
                "current_question": 0,
                "time_limit": 120,  # 2 menit
                "start_time": None,
                "question": None,
                "game_over": False,
                "answers": []
            }

            await ctx.send(f"{ctx.author.mention}, permainan Hangman dimulai! Anda memiliki 2 menit untuk menjawab 10 soal.")
            await self.play_game(ctx)

        start_button.callback = start_game
        view.add_item(start_button)

        message = await ctx.send(embed=embed, view=view)

        # Tunggu 1 menit sebelum reset jika tidak ada yang menekan tombol
        await asyncio.sleep(60)
        if ctx.author.id not in self.active_games:
            await message.delete()
            await ctx.send("Waktu habis! Permainan Hangman di-reset. Silakan coba lagi.")
        else:
            await message.delete()  # Hapus pesan instruksi jika game dimulai

    async def play_game(self, ctx):
        game_data = self.active_games[ctx.author.id]
        game_data["start_time"] = asyncio.get_event_loop().time()

        # Cek apakah ada pertanyaan yang tersedia
        if not self.questions:
            await ctx.send("Tidak ada pertanyaan yang tersedia. Pastikan questions_hangman.json diisi dengan benar.")
            return

        print(f"Jumlah pertanyaan yang tersedia: {len(self.questions)}")  # Debug: jumlah pertanyaan
        if len(self.questions) < 10:
            await ctx.send("Tidak cukup pertanyaan untuk memulai permainan. Pastikan ada setidaknya 10 pertanyaan di questions_hangman.json.")
            return

        game_data["question"] = random.sample(self.questions, 10)  # Ambil 10 soal acak

        for index, question in enumerate(game_data["question"]):
            if game_data["game_over"]:
                break

            game_data["current_question"] = index + 1
            await self.ask_question(ctx, question)

        if not game_data["game_over"]:
            await self.end_game(ctx)

    async def ask_question(self, ctx, question):
        game_data = self.active_games[ctx.author.id]

        embed = discord.Embed(
            title=f"❓ Pertanyaan {game_data['current_question']}",
            description=(
                f"Kategori: **{question['category']}**\n"
                f"Kisi-kisi: {question['clue']}\n"
                f"Sebutkan satu kata: **{self.display_word(question['word'], game_data['answers'])}**"
            ),
            color=0x00ff00
        )
        
        await ctx.send(embed=embed)

        # Menunggu jawaban dalam waktu yang ditentukan
        try:
            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel

            user_answer = await self.bot.wait_for('message', timeout=game_data["time_limit"], check=check)

            # Cek jawaban
            if user_answer.content.strip().lower() == question['word'].lower():
                game_data["correct"] += 1
                game_data["answers"].append(user_answer.content.strip().lower())  # Simpan jawaban yang benar
                await ctx.send("✅ Jawaban Benar!")
            else:
                game_data["wrong"] += 1
                await ctx.send("❌ Jawaban Salah.")

            if game_data["current_question"] == 10:
                await self.end_game(ctx)

        except asyncio.TimeoutError:
            await ctx.send("Waktu habis! Permainan berakhir.")
            game_data["game_over"] = True
            await self.end_game(ctx)

    def display_word(self, word, guessed_letters):
        """Menampilkan kata dengan huruf yang sudah ditebak dan garis bawah untuk huruf yang belum ditebak."""
        displayed_word = ''.join([letter if letter in guessed_letters else '_' for letter in word])
        return displayed_word

    async def end_game(self, ctx):
        game_data = self.active_games.pop(ctx.author.id, None)
        if game_data:
            # Hitung saldo awal dan akhir
            initial_balance = self.bank_data[str(ctx.author.id)]['balance']
            final_balance = initial_balance + (game_data['correct'] * 25) + (50 if game_data['correct'] == 10 else 0)  # Bonus jika benar semua

            # Kartu hasil
            embed = discord.Embed(
                title="📝 Hasil Permainan Hangman",
                color=0x00ff00
            )
            embed.add_field(name="Nama", value=ctx.author.display_name)
            embed.add_field(name="Jawaban Benar", value=game_data['correct'])
            embed.add_field(name="Jawaban Salah", value=game_data['wrong'])
            embed.add_field(name="Saldo RSWN Awal", value=initial_balance)
            embed.add_field(name="Saldo RSWN Akhir", value=final_balance)

            # Mengambil gambar pengguna
            user_data = self.level_data.get(str(ctx.guild.id), {}).get(str(ctx.author.id), {})
            image_data = await self.get_user_image(ctx, user_data)

            # Mengirimkan kartu hasil dengan gambar pengguna
            await ctx.send(file=discord.File(image_data, "avatar.png"), embed=embed)

# Command untuk mengirim data backup ke DM
@bot.command()
async def sendbackup(ctx):
    user_id = 1000737066822410311  # Ganti dengan ID kamu
    user = await bot.fetch_user(user_id)

    try:
        stored_data = collection.find_one(sort=[('_id', -1)])
        if not stored_data or 'backup' not in stored_data:
            await ctx.send("❌ Tidak ada data backup yang tersedia.")
            return

        backup_data = stored_data["backup"]
        await ctx.send("📤 Mengirim file backup satu per satu ke DM...")

        for filename, content in backup_data.items():
            string_buffer = io.StringIO()
            json.dump(content, string_buffer, indent=4, ensure_ascii=False)
            string_buffer.seek(0)

            byte_buffer = io.BytesIO(string_buffer.read().encode('utf-8'))
            byte_buffer.seek(0)

            file = discord.File(fp=byte_buffer, filename=filename)

            try:
                await user.send(content=f"📄 Berikut file backup: **{filename}**", file=file)
            except discord.HTTPException as e:
                await ctx.send(f"❌ Gagal kirim file {filename}: {e}")

        await ctx.send("✅ Semua file backup berhasil dikirim ke DM!")

    except discord.Forbidden:
        await ctx.send("❌ Gagal mengirim DM. Pastikan saya dapat mengirim DM ke pengguna ini.")
    except Exception as e:
        await ctx.send("❌ Terjadi kesalahan saat mengambil data backup.")
        print(f"❌ Error: {e}")


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
        await bot.load_extension("cogs.kuisaja")
        await bot.load_extension("cogs.hangman")
        print("✅ Semua cogs berhasil dimuat.")
    except Exception as e:
        print(f"❌ Gagal memuat cogs: {e}")

# Gunakan setup_hook agar loop dan tasks bisa jalan
@bot.event
async def setup_hook():
    await load_cogs()
    print("🔁 Memulai setup_hook dan load cogs...")
    await load_cogs()
    print("✅ Selesai setup_hook dan semua cogs dicoba load.")

save_cookies_from_env()

# Jalankan di Replit
keep_alive()

# Token bot Discord Anda dari secrets
bot.run(os.getenv("DISCORD_TOKEN"))
