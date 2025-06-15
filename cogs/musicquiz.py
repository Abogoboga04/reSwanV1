import discord
from discord.ext import commands
import json
import random
import asyncio
import os
import yt_dlp

# Opsi untuk YTDL
ytdl_opts = {
    'format': 'bestaudio/best',
    'cookiefile': 'cookies.txt',  # Penting untuk menghindari masalah hak cipta
    'quiet': True,
    'outtmpl': 'downloads/%(title)s.%(ext)s',
    'noplaylist': True,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -b:a 128k'  # Menurunkan bitrate audio menjadi 128 kbps untuk kualitas medium
}

ytdl = yt_dlp.YoutubeDL(ytdl_opts)

class MusicQueueItem:
    def __init__(self, url, title):
        self.url = url
        self.title = title

class QuizButton(discord.ui.Button):
    def __init__(self, label, option_letter, parent_view):
        super().__init__(label=f"{option_letter}. {label}", style=discord.ButtonStyle.primary)
        self.parent_view = parent_view
        self.option_letter = option_letter

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in self.parent_view.participants:
            await interaction.response.send_message("Ini bukan pertanyaan untukmu!", ephemeral=True)
            return

        await interaction.response.defer()
        if self.parent_view.voice_client.is_playing():
            self.parent_view.voice_client.stop()

        is_correct = self.option_letter.upper() == self.parent_view.correct_answer.upper()
        await self.parent_view.on_answer(interaction, is_correct)

        for child in self.parent_view.children:
            child.disabled = True
        await interaction.message.edit(view=self.parent_view)
        self.parent_view.stop()

class QuizView(discord.ui.View):
    def __init__(self, options, correct_answer, participants, voice_client, on_answer):
        super().__init__(timeout=15)
        self.correct_answer = correct_answer
        self.participants = participants
        self.voice_client = voice_client
        self.on_answer = on_answer
        self.message = None

        letters = ["A", "B", "C", "D"]
        for i, option in enumerate(options):
            self.add_item(QuizButton(option, letters[i], self))

class MusicQuiz(commands.Cog):
    SCORES_FILE = "scores.json"

    def __init__(self, bot):
        self.bot = bot
        self.load_questions()
        self.voice_client = None
        self.queue = []
        self.current = None
        self.is_playing = False
        self.quiz_running = False
        self.scores = self.load_scores()

    def load_questions(self):
        with open("questions.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            self.questions = data.get("questions", [])

    def load_scores(self):
        if not os.path.exists(self.SCORES_FILE):
            return {}
        with open(self.SCORES_FILE, "r") as f:
            return json.load(f)

    def save_scores(self):
        with open(self.SCORES_FILE, "w") as f:
            json.dump(self.scores, f, indent=2)

    async def play_next(self, ctx):
        if self.queue:
            self.current = self.queue.pop(0)
            source = discord.FFmpegPCMAudio(self.current.url, **FFMPEG_OPTIONS)
            self.voice_client.play(source, after=lambda e: self.bot.loop.create_task(self.play_next(ctx)))
            await ctx.send(f"🔊 Sekarang memutar: **{self.current.title}**")
        else:
            self.current = None
            self.is_playing = False

    async def join(self, ctx):
        if not ctx.author.voice:
            await ctx.send("Kamu harus ada di voice channel.")
            return False

        channel = ctx.author.voice.channel

        if not self.voice_client or not self.voice_client.is_connected():
            self.voice_client = await channel.connect()
            await ctx.send(f"Bot telah bergabung ke {channel.name}.")
            return True

        if self.voice_client.channel != channel:
            await ctx.send("Bot sudah terhubung ke channel lain. Pindahkan bot ke channel ini atau gunakan channel yang sama.")
            return False

        await ctx.send(f"Bot sudah berada di {channel.name}.")
        return True

    async def start_quiz_music(self):
        if self.voice_client.is_playing():
            self.voice_client.stop()  # Hentikan musik yang sedang diputar

        # Memutar musik kuis
        quiz_music_source = discord.FFmpegPCMAudio("https://raw.githubusercontent.com/Abogoboga04/reSwanV1/main/assets/quiz.mp3", **FFMPEG_OPTIONS)
        self.voice_client.play(quiz_music_source)  # Mulai memutar musik kuis

    async def restart_music(self):
        if self.voice_client.is_playing():
            self.voice_client.stop()  # Hentikan musik yang sedang diputar
        quiz_music_source = discord.FFmpegPCMAudio("https://raw.githubusercontent.com/Abogoboga04/reSwanV1/main/assets/quiz.mp3", **FFMPEG_OPTIONS)
        self.voice_client.play(quiz_music_source)  # Putar ulang musik kuis

    @commands.command(name="resp")
    async def play(self, ctx, *, search: str):
        joined = await self.join(ctx)
        if not joined:
            return

        info = ytdl.extract_info(search, download=False)
        entry = info['entries'][0] if 'entries' in info else info
        url = entry['url']
        title = entry['title']
        self.queue.append(MusicQueueItem(url, title))
        await ctx.send(f"🎵 Ditambahkan ke antrean: **{title}**")

        if not self.is_playing:
            self.is_playing = True
            await self.play_next(ctx)

    @commands.command(name="resleave")
    async def leave(self, ctx):
        if self.voice_client:
            await self.voice_client.disconnect()
            self.voice_client = None
            self.queue.clear()
            await ctx.send("👋 Bot keluar dari voice channel.")

    @commands.command(name="resstop")
    async def stop(self, ctx):
        self.queue.clear()
        if self.voice_client:
            self.voice_client.stop()
            await ctx.send("⏹️ Pemutaran dihentikan dan antrean dikosongkan.")

    @commands.command(name="startquiz")
    async def start_quiz(self, ctx):
        if not self.voice_client or not self.voice_client.is_connected():
            await ctx.send("Gunakan !join dulu sebelum memulai kuis.")
            return

        participants = [member.id for member in ctx.author.voice.channel.members]
        self.scores = {str(member.id): 0 for member in ctx.author.voice.channel.members}
        self.quiz_running = True
        await self.start_quiz_music()
        await ctx.send("🎉 Kuis dimulai!")

        def make_callback(question):
            async def callback(interaction, is_correct):
                if is_correct:
                    self.scores[str(interaction.user.id)] += 1
                    await ctx.send(f"✅ {interaction.user.mention} Jawaban benar!")
                else:
                    await ctx.send(f"❌ {interaction.user.mention} Salah! Jawaban: {question['answer']}")
                await self.restart_music()  # Memutar ulang musik setelah jawaban

            return callback

        for _ in range(20):
            if not self.questions:
                await ctx.send("Pertanyaan habis.")
                break

            q = random.choice(self.questions)
            self.questions.remove(q)

            view = QuizView(q["options"], q["answer"], participants, self.voice_client, make_callback(q))
            embed = discord.Embed(title="🎤 Kuis Musik!", description=q["question"], color=discord.Color.blurple())
            msg = await ctx.send(embed=embed, view=view)
            view.message = msg

            await asyncio.sleep(10)
            await view.wait()

        self.quiz_running = False
        await self.send_leaderboard(ctx)

    async def send_leaderboard(self, ctx):
        sorted_scores = sorted(self.scores.items(), key=lambda x: x[1], reverse=True)[:3]

        embed = discord.Embed(title="🏆 **Leaderboard:**", color=0x1DB954)
        for i, (user_id, score) in enumerate(sorted_scores, 1):
            user = self.bot.get_user(int(user_id))
            embed.add_field(name=f"{i}. {user.name if user else 'Unknown'}", value=f"Score: {score}", inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="resume")
    async def resume(self, ctx):
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            await ctx.send("🎶 Musik dilanjutkan.")
        else:
            await ctx.send("Tidak ada musik yang sedang diputar atau musik tidak dalam keadaan dijeda.")

    @commands.command(name="skip")
    async def skip(self, ctx):
        if self.voice_client and self.is_playing:
            self.voice_client.stop()
            await ctx.send("⏭️ Lagu dipindahkan ke lagu berikutnya.")
            await self.play_next(ctx)
        else:
            await ctx.send("Tidak ada lagu yang sedang diputar.")

async def setup(bot):
    await bot.add_cog(MusicQuiz(bot))
