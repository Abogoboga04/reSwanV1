import discord
from discord.ext import commands
from yt_dlp import YoutubeDL
import asyncio
import json
import os
import random

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'noplaylist': True,
    'default_search': 'ytsearch',
    'extract_flat': False,
    'source_address': '0.0.0.0'
}

class MusicQuiz(commands.Cog):
    QUESTIONS_FILE = "data/questions.json"
    SCORES_FILE = "data/scores.json"

    def __init__(self, bot):
        self.bot = bot
        self.voice_client = None
        self.queue = []
        self.is_playing = False
        self.current_song = None
        self.guild_id_playing = None
        self.quiz_active = False
        self.current_answer = None
        self.current_question = None
        self.quiz_scores = {}
        self.load_scores()

    def load_scores(self):
        if os.path.exists(self.SCORES_FILE):
            with open(self.SCORES_FILE, "r") as f:
                self.quiz_scores = json.load(f)
        else:
            self.quiz_scores = {}

    def save_scores(self):
        with open(self.SCORES_FILE, "w") as f:
            json.dump(self.quiz_scores, f, indent=4)

    async def ensure_voice(self, ctx):
        if self.voice_client and self.voice_client.is_connected():
            if ctx.guild.voice_client and ctx.guild.voice_client.channel != ctx.author.voice.channel:
                await ctx.send("Bot sedang aktif di voice channel lain.")
                return False
            return True

        if ctx.author.voice is None:
            await ctx.send("Kamu harus join voice channel dulu.")
            return False

        self.voice_client = await ctx.author.voice.channel.connect()
        self.guild_id_playing = ctx.guild.id
        return True

    async def play_next(self):
        if len(self.queue) == 0:
            self.is_playing = False
            self.current_song = None
            return

        self.is_playing = True
        url, title, ctx = self.queue.pop(0)
        self.current_song = title

        source = await discord.FFmpegOpusAudio.from_probe(url, **FFMPEG_OPTIONS)
        self.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next(), self.bot.loop))

        await ctx.send(f"🎶 Sekarang memutar: **{title}**")

    async def play_music(self, ctx, query):
        if not await self.ensure_voice(ctx):
            return

        with YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(query, download=False)
            if 'entries' in info:
                info = info['entries'][0]

        url = info['url']
        title = info.get('title', 'Unknown title')
        self.queue.append((url, title, ctx))

        if not self.is_playing:
            await self.play_next()
        else:
            await ctx.send(f"✅ Ditambahkan ke antrian: **{title}**")

    # === Music Commands ===
    @commands.command(name="resp")
    async def resp_play(self, ctx, *, query):
        await self.play_music(ctx, query)

    @commands.command(name="respause")
    async def resp_pause(self, ctx):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            await ctx.send("⏸ Lagu dijeda.")
        else:
            await ctx.send("Tidak ada lagu yang sedang diputar.")

    @commands.command(name="resresume")
    async def resp_resume(self, ctx):
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            await ctx.send("▶️ Lagu dilanjutkan.")
        else:
            await ctx.send("Tidak ada lagu yang dijeda.")

    @commands.command(name="resskip")
    async def resp_skip(self, ctx):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
            await ctx.send("⏭ Lagu dilewati.")
        else:
            await ctx.send("Tidak ada lagu yang sedang diputar.")

    @commands.command(name="resstop")
    async def resp_stop(self, ctx):
        if self.voice_client:
            await self.voice_client.disconnect()
            self.voice_client = None
            self.queue.clear()
            self.is_playing = False
            self.current_song = None
            await ctx.send("⏹ Pemutaran musik dihentikan dan bot keluar dari voice channel.")

    @commands.command(name="resqueue")
    async def res_queue(self, ctx):
        if len(self.queue) == 0:
            await ctx.send("Antrian kosong.")
            return
        msg = "\n".join([f"{i+1}. {title}" for i, (_, title, _) in enumerate(self.queue)])
        await ctx.send(f"📃 Antrian Lagu:\n{msg}")

    # === Quiz Commands ===
    @commands.command(name="quiz")
    async def start_quiz(self, ctx):
        if self.quiz_active:
            await ctx.send("Kuis sedang berlangsung.")
            return

        if not os.path.exists(self.QUESTIONS_FILE):
            await ctx.send("Tidak ada file soal kuis.")
            return

        with open(self.QUESTIONS_FILE, "r") as f:
            data = json.load(f)
            questions = data.get("questions", [])

        if not questions:
            await ctx.send("Daftar pertanyaan kosong.")
            return

        self.quiz_active = True
        score_counter = {}

        for q in random.sample(questions, min(5, len(questions))):
            self.current_question = q
            self.current_answer = q["answer"].lower()
            await ctx.send(f"🎵 Tebak lagu: {q['question']}")
            try:
                msg = await self.bot.wait_for(
                    "message",
                    check=lambda m: m.channel == ctx.channel and not m.author.bot,
                    timeout=15.0
                )
                if msg.content.lower() == self.current_answer:
                    user_id = str(msg.author.id)
                    score_counter[user_id] = score_counter.get(user_id, 0) + 1
                    await ctx.send(f"✅ Benar, {msg.author.mention}!")
                else:
                    await ctx.send(f"❌ Salah! Jawaban benar: **{self.current_answer}**")
            except asyncio.TimeoutError:
                await ctx.send(f"⏰ Waktu habis! Jawaban: **{self.current_answer}**")

        # Update leaderboard
        for uid, score in score_counter.items():
            self.quiz_scores[uid] = self.quiz_scores.get(uid, 0) + score
        self.save_scores()

        leaderboard = sorted(score_counter.items(), key=lambda x: x[1], reverse=True)
        result = "\n".join([f"<@{uid}>: {score} poin" for uid, score in leaderboard])
        await ctx.send("🏆 Skor kuis:\n" + result if result else "Tidak ada yang menjawab dengan benar.")

        self.quiz_active = False

    @commands.command(name="leaderboardd")
    async def show_leaderboard(self, ctx):
        sorted_scores = sorted(self.quiz_scores.items(), key=lambda x: x[1], reverse=True)[:10]
        if not sorted_scores:
            await ctx.send("Belum ada skor kuis.")
            return
        result = "\n".join([f"<@{uid}>: {score} poin" for uid, score in sorted_scores])
        await ctx.send("📈 **Top 10 Leaderboard Kuis Musik:**\n" + result)

async def setup(bot):
    await bot.add_cog(MusicQuiz(bot))
