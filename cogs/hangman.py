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
        self.scores = {}  # Menyimpan skor peserta per sesi

        self.game_channel_id = 765140300145360896  # ID channel yang diizinkan
        self.bantuan_price = 40 # Harga bantuan, bisa disesuaikan

    def load_bank_data(self):
        with open('data/bank_data.json', 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
                else:
                    raise ValueError("Data harus dalam format dictionary.")
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON from bank_data.json: {e}")
                return {}
            except Exception as e:
                print(f"Error loading bank data: {e}")
                return {}

    def load_level_data(self):
        with open('data/level_data.json', 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
                else:
                    raise ValueError("Data harus dalam format dictionary.")
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON from level_data.json: {e}")
                return {}
            except Exception as e:
                print(f"Error loading level data: {e}")
                return {}

    def load_hangman_data(self):
        current_dir = os.path.dirname(__file__)  # Folder cogs/
        file_path = os.path.join(current_dir, "..", "data", "questions_hangman.json")
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
                else:
                    raise ValueError("Data harus berupa list dan tidak kosong.")
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON from questions_hangman.json: {e}")
                return []
            except Exception as e:
                print(f"Error loading hangman data: {e}")
                return []

    @commands.command(name="resman", help="Mulai permainan Hangman.")
    async def hangman(self, ctx):
        if ctx.channel.id != self.game_channel_id:
            await ctx.send("Permainan Hangman hanya bisa dimainkan di channel yang ditentukan.")
            return

        if ctx.channel.id in self.active_games:
            await ctx.send("Permainan sudah sedang berlangsung di channel ini. Silakan tunggu hingga selesai.")
            return

        self.scores = {}

        self.active_games[ctx.channel.id] = {
            "score": 0,
            "correct": 0,
            "wrong": 0,
            "current_question": 0,
            "time_limit": 120,
            "start_time": None,
            "question": None,
            "game_over": False,
            "answers": []
        }

        embed = discord.Embed(
            title="🎮 Cara Bermain Hangman",
            description=(
                "Selamat datang di Dunia Sunyi Hangman! 🖤🌧️\n\n"
                "Di sini, kamu tak hanya menebak kata... tapi juga menebak makna dari kesepian yang tak bertepi.\n"
                "Jawablah satu per satu, berharap RSWN bisa sedikit mengisi kekosongan itu.\n"
                "Selesaikan 10 soal dalam 2 menit... kalau kamu masih punya semangat itu.\n\n"
                "💸 Ngerasa buntu? Beli **bantuan** aja pake:\n"
                "**!hmanplis** – Harga: 40 RSWN. Jawaban dikirim via DM.\n"
                "*Karena terkadang, kita semua butuh sedikit cahaya di dalam gelap.*\n\n"
                "Kalau kamu cukup kuat, cukup tahan, cukup sad... klik tombol di bawah ini. Mulai permainanmu."
            ),
            color=0x5500aa
        )

        view = discord.ui.View()
        start_button = discord.ui.Button(label="🔵 START", style=discord.ButtonStyle.primary)

        async def start_game(interaction):
            self.active_games[ctx.channel.id]["current_question"] = 0
            await ctx.send(f"{ctx.author.mention}, permainan Hangman dimulai! Anda memiliki 2 menit untuk menjawab 10 soal.")
            await self.play_game(ctx)

        start_button.callback = start_game
        view.add_item(start_button)
        message = await ctx.send(embed=embed, view=view)

        await asyncio.sleep(60)
        if ctx.channel.id not in self.active_games:
            # Periksa apakah 'message' masih ada sebelum mencoba menghapusnya
            try:
                await message.delete()
                await ctx.send("Waktu habis! Permainan Hangman di-reset. Silakan coba lagi.")
            except discord.NotFound:
                pass # Pesan sudah dihapus, tidak perlu melakukan apa-apa
        else:
            try:
                await message.delete()
            except discord.NotFound:
                pass

    # --- PERINTAH BANTUAN BARU ---
    @commands.command(name="hmanplis", help="Membeli bantuan untuk jawaban Hangman.")
    async def hmanplis(self, ctx):
        user_id = str(ctx.author.id)
        channel_id = ctx.channel.id

        if channel_id not in self.active_games:
            await ctx.send("Tidak ada permainan Hangman yang sedang berlangsung di channel ini.")
            return

        game_data = self.active_games[channel_id]
        
        # Memastikan bahwa data pengguna ada di bank_data
        if user_id not in self.bank_data:
            self.bank_data[user_id] = {"balance": 0, "debt": 0}
            await ctx.send("Akun Anda baru saja dibuat. Saldo awal Anda adalah 0 RSWN.")

        user_data = self.bank_data[user_id]

        if user_data.get('balance', 0) < self.bantuan_price:
            await ctx.send(f"😢 Saldo RSWN tidak cukup untuk membeli bantuan. Harga: {self.bantuan_price} RSWN.")
            return

        # Mengurangi saldo RSWN
        initial_balance = user_data.get('balance', 0)
        user_data['balance'] -= self.bantuan_price
        final_balance = user_data['balance']

        # Mengambil jawaban dari pertanyaan saat ini
        # game_data["current_question"] adalah index+1, jadi index sebenarnya adalah current_question-1
        current_question_index = game_data["current_question"] - 1
        
        # Pastikan index valid
        if 0 <= current_question_index < len(game_data["question"]):
            current_question_obj = game_data["question"][current_question_index]
            correct_word = current_question_obj['word']

            try:
                # Kirim jawaban ke DM pengguna
                await ctx.author.send(f"🔐 Jawaban untuk pertanyaan Hangman saat ini adalah: **{correct_word}**")
                await ctx.author.send(f"✅ Pembelian bantuan berhasil! Saldo RSWN Anda berkurang dari **{initial_balance}** menjadi **{final_balance}**.")

                # Memberikan konfirmasi di channel
                await ctx.send(f"{ctx.author.mention}, bantuan telah berhasil dikirim ke DM Anda!")

                # Simpan perubahan ke file
                with open('data/bank_data.json', 'w', encoding='utf-8') as f:
                    json.dump(self.bank_data, f, indent=4)
            except discord.Forbidden:
                await ctx.send(f"{ctx.author.mention}, saya tidak bisa mengirim DM. Mohon aktifkan izin DM dari server ini.")
                # Kembalikan uang jika DM gagal
                user_data['balance'] += self.bantuan_price
                with open('data/bank_data.json', 'w', encoding='utf-8') as f:
                    json.dump(self.bank_data, f, indent=4)
        else:
            await ctx.send("Tidak bisa mendapatkan pertanyaan saat ini. Mungkin game sedang berganti soal.")
            # Kembalikan uang jika terjadi error
            user_data['balance'] += self.bantuan_price
            with open('data/bank_data.json', 'w', encoding='utf-8') as f:
                    json.dump(self.bank_data, f, indent=4)


    async def play_game(self, ctx):
        game_data = self.active_games[ctx.channel.id]
        game_data["start_time"] = asyncio.get_event_loop().time()

        if not self.questions or len(self.questions) < 10:
            await ctx.send("Tidak cukup pertanyaan untuk memulai permainan. Hubungi admin.")
            self.active_games.pop(ctx.channel.id, None)
            return

        game_data["question"] = random.sample(self.questions, 10)

        for index, question in enumerate(game_data["question"]):
            if game_data["game_over"]:
                break
            game_data["current_question"] = index + 1
            await self.ask_question(ctx, question)

        if not game_data["game_over"]:
            await self.end_game(ctx)

    async def ask_question(self, ctx, question):
        game_data = self.active_games[ctx.channel.id]

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

        try:
            def check(m):
                return m.channel == ctx.channel

            while True:
                user_answer = await self.bot.wait_for('message', timeout=game_data["time_limit"], check=check)

                if user_answer.content.strip().lower() == question['word'].lower():
                    game_data["correct"] += 1
                    game_data["answers"].append(user_answer.content.strip().lower())
                    await ctx.send(f"✅ Jawaban Benar dari {user_answer.author.display_name}!")

                    if user_answer.author.id not in self.scores:
                        self.scores[user_answer.author.id] = {
                            "user": user_answer.author,
                            "score": 0,
                            "correct": 0,
                            "wrong": 0,
                            "total_rsw": 0
                        }

                    self.scores[user_answer.author.id]["score"] += 1
                    self.scores[user_answer.author.id]["correct"] += 1
                    self.scores[user_answer.author.id]["total_rsw"] += 30

                    break
                else:
                    game_data["wrong"] += 1
                    await ctx.send(f"❌ Jawaban Salah dari {user_answer.author.display_name}.")

            if game_data["current_question"] == 10:
                await self.end_game(ctx)

        except asyncio.TimeoutError:
            await ctx.send("Waktu habis! Permainan berakhir.")
            game_data["game_over"] = True
            await self.end_game(ctx)

    def display_word(self, word, guessed_letters):
        displayed_word = ''.join([letter if letter in guessed_letters else '_' for letter in word])
        return displayed_word

    async def end_game(self, ctx):
        game_data = self.active_games.pop(ctx.channel.id, None)
        if game_data:
            earned_rsw = game_data['correct'] * 25

            if str(ctx.author.id) not in self.bank_data:
                self.bank_data[str(ctx.author.id)] = {"balance": 0}

            self.bank_data[str(ctx.author.id)]["balance"] += earned_rsw

            if str(ctx.author.id) in self.level_data:
                self.level_data[str(ctx.author.id)]["exp"] += game_data['correct'] * 10
            else:
                self.level_data[str(ctx.author.id)] = {"exp": game_data['correct'] * 10}

            with open('data/bank_data.json', 'w', encoding='utf-8') as f:
                json.dump(self.bank_data, f, indent=4)
            with open('data/level_data.json', 'w', encoding='utf-8') as f:
                json.dump(self.level_data, f, indent=4)
            await self.display_leaderboard(ctx)

    async def display_leaderboard(self, ctx):
        if not self.scores:
            await ctx.send("Tidak ada yang berpartisipasi dalam sesi Hangman kali ini. 💔")
            return
            
        sorted_scores = sorted(self.scores.values(), key=lambda x: x["correct"], reverse=True)[:5]
        embed = discord.Embed(title="🏆 Leaderboard Hangman", color=0x00ff00)

        for i, score in enumerate(sorted_scores, start=1):
            user = score['user']
            embed.add_field(
                name=f"{i}. {user.display_name}",
                value=(
                    f"Total RSWN: {score.get('total_rsw', 0)}\n"
                    f"Jawaban Benar: {score['correct']}\n"
                    f"Jawaban Salah: {score['wrong']}"
                ),
                inline=False
            )

        if sorted_scores:
            top_user = sorted_scores[0]['user']
            image_url = str(top_user.avatar.url) if top_user.avatar else str(top_user.default_avatar.url)
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as resp:
                        if resp.status == 200:
                            image_data = BytesIO(await resp.read())
                            await ctx.send(file=discord.File(image_data, filename='avatar.png'))
            except Exception as e:
                print(f"Error fetching image for {top_user.display_name}: {e}")

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Hangman(bot))

