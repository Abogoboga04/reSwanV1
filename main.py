import discord
from discord.ext import commands
import aiohttp
import base64
import os
import io
import asyncio
import json
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# Fungsi untuk menyimpan cookies dari environment variable
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
db = client["reSwan"]
collection = db["Data collection"]

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

# Kelas Cog Hangman
class Hangman(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}
        self.bank_data = self.load_bank_data()
        self.level_data = self.load_level_data()
        self.questions = self.load_hangman_data()
        print(f"Jumlah pertanyaan yang dimuat: {len(self.questions)}")  # Debug: jumlah pertanyaan
        self.game_channel_id = 1379458566452154438  # Ganti dengan ID channel yang diizinkan

    def load_bank_data(self):
        with open('data/bank_data.json', 'r', encoding='utf-8') as f:
            return json.load(f)

    def load_level_data(self):
        with open('data/level_data.json', 'r', encoding='utf-8') as f:
            return json.load(f)

    def load_hangman_data(self):
        current_dir = os.path.dirname(__file__)
        file_path = os.path.join(current_dir, "data", "questions_hangman.json")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data["questions"]

    @commands.command(name="resman", help="Mulai permainan Hangman.")
    async def resman(self, ctx):
        if ctx.channel.id != self.game_channel_id:
            await ctx.send("Permainan Hangman hanya bisa dimainkan di channel yang ditentukan.")
            return

        if ctx.author.id in self.active_games:
            await ctx.send("Anda sudah sedang bermain Hangman. Silakan tunggu hingga selesai.")
            return

        self.active_games[ctx.author.id] = {
            "score": 0,
            "correct": 0,
            "wrong": 0,
            "current_question": 0,
            "time_limit": 120,  # 2 menit
            "game_over": False,
            "answers": []
        }

        await ctx.send(f"{ctx.author.mention}, permainan Hangman dimulai! Anda memiliki 2 menit untuk menjawab 10 soal.")
        await self.play_game(ctx)

    async def play_game(self, ctx):
        game_data = self.active_games[ctx.author.id]
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
                f"Sebutkan satu kata: **{'_' * len(question['word'])}**"
            ),
            color=0x00ff00
        )

        await ctx.send(embed=embed)

        try:
            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel

            user_answer = await self.bot.wait_for('message', timeout=game_data["time_limit"], check=check)

            if user_answer.content.strip().lower() == question['word'].lower():
                game_data["correct"] += 1
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

    async def end_game(self, ctx):
        game_data = self.active_games.pop(ctx.author.id, None)
        if game_data:
            embed = discord.Embed(
                title="📝 Hasil Permainan Hangman",
                color=0x00ff00
            )
            embed.add_field(name="Jawaban Benar", value=game_data['correct'])
            embed.add_field(name="Jawaban Salah", value=game_data['wrong'])

            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Hangman(bot))

# Muat semua cog yang ada
async def load_cogs():
    try:
        await setup(bot)  # Memuat cog Hangman
        print("✅ Semua cogs berhasil dimuat.")
    except Exception as e:
        print(f"❌ Gagal memuat cogs: {e}")

# Gunakan setup_hook agar loop dan tasks bisa jalan
@bot.event
async def setup_hook():
    await load_cogs()
    print("✅ Selesai setup_hook dan semua cogs dicoba load.")

save_cookies_from_env()

# Jalankan di Replit
keep_alive()

# Token bot Discord Anda dari secrets
bot.run(os.getenv("DISCORD_TOKEN"))
