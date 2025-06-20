import discord
from discord.ext import commands
import json
import random
import asyncio
import os
import aiohttp
from io import BytesIO

class EmojiQuiz(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.quiz_data = self.load_quiz_data()
        self.bank_data = self.load_bank_data()
        self.current_question = None
        self.current_answers = {}
        self.participants = []
        self.correct_count = {}
        self.bantuan_used = {}
        self.bantuan_price = 25
        self.quiz_active = False
        self.messages = []
        self.host = None
        self.question_active = False
        self.bot = bot
        self.active_games = {}
        self.bank_data = self.load_bank_data()
        self.level_data = self.load_level_data()
        self.questions = self.load_hangman_data()

        # Debug: cek jumlah pertanyaan yang dimuat
        print(f"Jumlah pertanyaan yang dimuat: {len(self.questions)}")  # Debug: jumlah pertanyaan

        self.game_channel_id = 1379458566452154438  # ID channel yang diizinkan

    def load_quiz_data(self):
        current_dir = os.path.dirname(__file__)
        file_path = os.path.join(current_dir, '..', 'data', 'emoji_questions.json')
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if "questions" in data and isinstance(data["questions"], list):
                return data["questions"]
            else:
                raise ValueError("Data tidak dalam format yang benar!")

    def load_bank_data(self):
        with open('data/bank_data.json', 'r', encoding='utf-8') as f:
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

    @commands.command(name="resmoji", help="Mulai Kuis Emoji")
    async def resmoji(self, ctx):
        if self.quiz_active:
            await ctx.send("Kuis sudah aktif, tunggu hingga sesi ini selesai!", ephemeral=True)
            return

        self.host = ctx.author
        embed = discord.Embed(
            title="✨ Kuis Emoji! ✨",
            description=(
                "Ayo, bersiap-siap untuk menjawab pertanyaan emoji yang menyedihkan, meskipun hati ini terasa hampa. 😢💔\n\n"
                "**Cara Main:**\n"
                "1. Akan ada 10 pertanyaan emoji.\n"
                "2. Semua peserta bisa menjawab dengan sistem yg siapa cepat dia dapat.\n"
                "3. Jawaban benar = +25 RSWN.\n"
                "4. Bonus 50 RSWN jika semua pertanyaan dijawab benar.\n"
                "5. Minimal 2 peserta.\n\n"
                "Klik tombol di bawah untuk mulai."
            ),
            color=0x00ff00
        )

        view = discord.ui.View()
        start_button = discord.ui.Button(label="🎮 Mulai Kuis", style=discord.ButtonStyle.primary)

        async def start_quiz(interaction):
            if self.quiz_active:
                await ctx.send("Kuis sudah dimulai!", ephemeral=True)
                return
            if ctx.author != self.host:
                await ctx.send("Hanya host yang bisa memulai kuis!", ephemeral=True)
                return

            self.quiz_active = True
            await ctx.send("Kuis dimulai!")
            await self.start_quiz(ctx)

        start_button.callback = start_quiz
        view.add_item(start_button)

        help_button = discord.ui.Button(label="🆘 Beli Bantuan", style=discord.ButtonStyle.secondary)

        async def buy_help(interaction):
            if self.quiz_active:
                await ctx.send("Kuis sudah dimulai!", ephemeral=True)
            else:
                await self.buy_help_function(ctx)

        help_button.callback = buy_help
        view.add_item(help_button)

        await ctx.send(embed=embed, view=view)

    async def start_quiz(self, ctx):
        if ctx.guild is None:
            await ctx.send("Kuis hanya dapat dimulai di server!", ephemeral=True)
            return

        self.participants = [ctx.author]
        for member in ctx.guild.members:
            if len(self.participants) >= 5:
                break
            if member != ctx.author and not member.bot and member.voice:
                self.participants.append(member)

        if len(self.participants) < 2:
            await ctx.send("😢 Minimal 2 peserta diperlukan untuk memulai kuis!")
            return

        for participant in self.participants:
            self.correct_count[participant.id] = 0
            self.bantuan_used[participant.id] = 0

        questions_to_ask = random.sample(self.quiz_data, min(10, len(self.quiz_data)))
        for question in questions_to_ask:
            self.current_question = question
            await self.ask_question(ctx, question)

        await self.end_quiz(ctx)

    async def ask_question(self, ctx, question):
        embed = discord.Embed(
            title="⏳ Pertanyaan Emoji!",
            description=f"Tebak frasa ini: {question['emoji']}",
            color=0x0000ff
        )
        message = await ctx.send(embed=embed)
        self.messages.append(message)

        self.current_answers.clear()
        self.question_active = True

        for i in range(15, 0, -1):
            embed.description = f"Tebak frasa ini: {question['emoji']}\nWaktu tersisa: {i} detik"
            await message.edit(embed=embed)
            await asyncio.sleep(1)

        self.question_active = False
        await self.evaluate_answers(ctx, question)

    async def evaluate_answers(self, ctx, question):
        if not self.question_active:
            return
        
        correct_answer = question['answer'].strip().lower()
        answer_found = False

        for participant in self.participants:
            if participant.id in self.current_answers:
                user_answer = self.current_answers[participant.id].strip().lower()

                if user_answer == correct_answer:
                    self.correct_count[participant.id] += 1
                    self.bank_data[str(participant.id)]['balance'] += 25
                    await ctx.send(f"✅ {participant.mention} menjawab dengan benar! Jawabannya: **{correct_answer}**")
                    answer_found = True
                    break

        await asyncio.sleep(2)

        if answer_found:
            await ctx.send("➡️ Pertanyaan berikutnya...")
        self.question_active = False

    async def end_quiz(self, ctx):  # <-- yang kamu minta
        for message in self.messages:
            await message.delete()

        embed = discord.Embed(title="🏆 Leaderboard Kuis Emoji!", color=0x00ff00)

        for participant in self.participants:
            correct = self.correct_count.get(participant.id, 0)
            total_questions = 10
            wrong = total_questions - correct
            earned = correct * 25

            pid = str(participant.id)
            if pid not in self.bank_data:
                self.bank_data[pid] = {"balance": 0}

            final_balance = self.bank_data[pid]['balance']
            initial_balance = final_balance + earned  # karena udah dikurangi pas benar

            embed.add_field(
                name=f"{participant.display_name} {participant.mention}",
                value=(
                    f"Jawaban Benar: {correct}\n"
                    f"Jawaban Salah: {wrong}\n"
                    f"Saldo RSWN Awal: {initial_balance}\n"
                    f"Saldo RSWN Akhir: {final_balance}\n"
                    f"Total RSWN Didapat: {earned}\n"
                ),
                inline=False
            )

        await ctx.send(embed=embed)

        with open('data/bank_data.json', 'w', encoding='utf-8') as f:
            json.dump(self.bank_data, f, indent=4)

        self.quiz_active = False
        self.messages.clear()
        self.participants.clear()
        self.correct_count.clear()
        self.current_answers.clear()

    async def buy_help_function(self, ctx):
        user_id = str(ctx.author.id)

        if user_id not in self.bank_data:
            self.bank_data[user_id] = {"balance": 0}

        if user_id not in self.bantuan_used:
            self.bantuan_used[user_id] = 0

        if self.bantuan_used[user_id] >= 5:
            await ctx.send("❌ Batas bantuan harian tercapai.", ephemeral=True)
            return

        if self.bank_data[user_id]['balance'] < self.bantuan_price:
            await ctx.send("😢 Saldo RSWN tidak cukup.", ephemeral=True)
            return

        self.bank_data[user_id]['balance'] -= self.bantuan_price
        self.bantuan_used[user_id] += 1

        help_msg = await ctx.send("✅ Bantuan dibeli! Gunakan `!resplis` untuk melihat jawaban.", ephemeral=True)
        await asyncio.sleep(2)
        await help_msg.delete()

    @commands.command(name="resplis", help="Gunakan bantuan untuk melihat jawaban.")
    async def resplis(self, ctx):
        user_id = str(ctx.author.id)
        if user_id not in self.bantuan_used or self.bantuan_used[user_id] <= 0:
            await ctx.send("Kamu belum beli bantuan!", ephemeral=True)
            return

        if self.current_question is None:
            await ctx.send("Belum ada pertanyaan aktif!", ephemeral=True)
            return

        answer = self.current_question['answer']
        await ctx.author.send(f"🔐 Jawaban: **{answer}**")
        self.bantuan_used[user_id] -= 1

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not self.quiz_active:
            return

        if message.author in self.participants and self.current_question:
            if message.author.voice is None:
                await message.channel.send(f"{message.author.mention}, kamu harus di voice channel untuk menjawab!")
                return

            user_answer = message.content.strip().lower()
            if user_answer not in self.current_answers.values():
                self.current_answers[message.author.id] = user_answer
                await self.evaluate_answers(message.channel, self.current_question)

async def setup(bot):
    await bot.add_cog(EmojiQuiz(bot))
  
