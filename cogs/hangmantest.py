import discord
from discord.ext import commands
import json
import random
import asyncio
import os
import aiohttp
from io import BytesIO

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

    @commands.command(name="resman", help="Mulai permainan Hangman.")
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
                "Selamat datang di Dunia Sunyi Hangman! 🖤🌧️\n\n"
                "Di sini, kamu tak hanya menebak kata... tapi juga menebak makna dari kesepian yang tak bertepi.\n"
                "Jawablah satu per satu, berharap RSWN bisa sedikit mengisi kekosongan itu.\n"
                "Selesaikan 10 soal dalam 2 menit... kalau kamu masih punya semangat itu.\n\n"
                "✨ *Dev udah bikin fitur. Admin udah promosi. Tapi server tetap sepi...*\n\n"
                "Kadang rasanya seperti teriak dalam ruangan kosong. Nggak ada yang jawab. Cuma gema yang balas.\n"
                "Tapi kalau kamu masih di sini... mungkin kamu satu-satunya harapan yang tersisa. 🕯️\n\n"
                "Kalau kamu cukup kuat, cukup tahan, cukup sad... klik tombol di bawah ini. Mulai permainanmu."
            ),
            color=0x5500aa
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

async def setup(bot):
    await bot.add_cog(Hangman(bot))
  