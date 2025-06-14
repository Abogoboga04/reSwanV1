import discord
from discord.ext import commands
import json
import random
import asyncio

class Quiz(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.load_questions()
        self.scores = {}
        self.voice_client = None  # Menyimpan instance voice client
        self.quiz_running = False  # Menyimpan status kuis

    def load_questions(self):
        with open("questions.json", "r") as f:
            data = json.load(f)
            self.questions = data["questions"]

    @commands.command(name="join")
    async def join(self, ctx):
        """Bot bergabung ke voice channel pengguna."""
        if ctx.author.voice:
            channel = ctx.author.voice.channel
            self.voice_client = await channel.connect()
            await ctx.send(f"Bot bergabung ke channel: {channel.name}")
            # Memutar musik tema kuis
            self.voice_client.play(discord.FFmpegPCMAudio("path/to/your/quiz_theme_music.mp3"))
        else:
            await ctx.send("Anda harus berada di voice channel untuk menggunakan command ini.")

    @commands.command(name="startquiz")
    async def start_quiz(self, ctx):
        """Memulai kuis."""
        if self.voice_client is None or not self.voice_client.is_connected():
            await ctx.send("Bot harus berada di voice channel untuk memulai kuis. Gunakan !join terlebih dahulu.")
            return

        await ctx.send("Kuis dimulai! Siap untuk menjawab pertanyaan!")
        self.scores[ctx.author.id] = 0  # Inisialisasi skor pengguna
        self.quiz_running = True

        for _ in range(20):  # Total pertanyaan
            if len(self.questions) == 0:
                await ctx.send("Semua pertanyaan telah digunakan!")
                break

            question = random.choice(self.questions)
            self.questions.remove(question)  # Menghindari pertanyaan yang berulang

            options = question["options"]
            embed = discord.Embed(
                title="Kuis!",
                description=question["question"],
                color=discord.Color.blue()
            )

            # Membuat tombol untuk setiap opsi
            buttons = [
                discord.ui.Button(label=options[0], style=discord.ButtonStyle.primary, custom_id='A'),
                discord.ui.Button(label=options[1], style=discord.ButtonStyle.primary, custom_id='B'),
                discord.ui.Button(label=options[2], style=discord.ButtonStyle.primary, custom_id='C'),
                discord.ui.Button(label=options[3], style=discord.ButtonStyle.primary, custom_id='D')
            ]

            view = discord.ui.View()
            for button in buttons:
                view.add_item(button)

            message = await ctx.send(embed=embed, view=view)

            # Memutar musik hitung mundur
            self.voice_client.play(discord.FFmpegPCMAudio("https://github.com/Abogoboga04/reSwanV1/blob/main/assets/10sec.mp3"))

            # Menunggu jawaban dari pengguna
            def check(interaction):
                return interaction.user.id == ctx.author.id and interaction.message.id == message.id

            try:
                interaction = await self.bot.wait_for('interaction', check=check, timeout=10.0)
            except asyncio.TimeoutError:
                await ctx.send(f"Waktu habis! Jawaban yang benar adalah: {question['answer']}")
            else:
                if interaction.custom_id == question["answer"]:
                    self.scores[ctx.author.id] += 1  # Tambah skor jika benar
                    await ctx.send("✅ Jawaban Anda benar!")
                else:
                    await ctx.send(f"❌ Jawaban Anda salah! Jawaban yang benar adalah: {question['answer']}")

                # Jika pengguna menjawab sebelum waktu habis, ulang musik hitung mundur
                self.voice_client.stop()  # Hentikan musik hitung mundur
                self.voice_client.play(discord.FFmpegPCMAudio("https://github.com/Abogoboga04/reSwanV1/blob/main/assets/quiz.mp3"))

            await interaction.response.defer()  # Menonaktifkan tombol setelah kuis selesai

        # Menampilkan skor akhir
        final_score = self.scores[ctx.author.id]
        await ctx.send(f"Kuis selesai! Skor Anda: {final_score}")

    @commands.command(name="leave")
    async def leave(self, ctx):
        """Bot meninggalkan voice channel."""
        if self.voice_client:
            await self.voice_client.disconnect()
            await ctx.send("Bot meninggalkan voice channel.")
            self.quiz_running = False
        else:
            await ctx.send("Bot tidak sedang berada di voice channel.")

async def setup(bot):
    await bot.add_cog(Quiz(bot))
