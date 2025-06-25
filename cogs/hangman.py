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
        self.scores = {}  # Menyimpan skor peserta

        self.game_channel_id = 1379458566452154438  # ID channel yang diizinkan

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

        if ctx.author.id in self.active_games:
            await ctx.send("Anda sudah sedang bermain Hangman. Silakan tunggu hingga selesai.")
            return

        # Inisialisasi skor untuk pengguna
        if ctx.author.id not in self.scores:
            self.scores[ctx.author.id] = {
                "user": ctx.author,
                "score": 0,
                "correct": 0,
                "wrong": 0,
                "total_rsw": 0  # Inisialisasi total_rsw
            }

        embed = discord.Embed(
            title="🎮 Cara Bermain Hangman",
            description=(
                "Selamat datang di Dunia Sunyi Hangman! 🖤🌧️\n\n"
                "Di sini, kamu tak hanya menebak kata... tapi juga menebak makna dari kesepian yang tak bertepi.\n"
                "Jawablah satu per satu, berharap RSWN bisa sedikit mengisi kekosongan itu.\n"
                "Selesaikan 10 soal dalam 2 menit... kalau kamu masih punya semangat itu.\n\n"
                "✨ *Dev bot udah bikin fitur. Admin & moderator udah berusaha. Tapi server tetap sepi...*\n\n"
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
                return m.channel == ctx.channel  # Setiap orang di channel dapat menjawab

            while True:
                user_answer = await self.bot.wait_for('message', timeout=game_data["time_limit"], check=check)

                # Cek jawaban
                if user_answer.content.strip().lower() == question['word'].lower():
                    game_data["correct"] += 1
                    game_data["answers"].append(user_answer.content.strip().lower())  # Simpan jawaban yang benar
                    await ctx.send(f"✅ Jawaban Benar dari {user_answer.author.display_name}!")

                    # Tambah skor dan RSWN untuk semua pengguna
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
                    self.scores[user_answer.author.id]["total_rsw"] += 30  # contoh hadiah

                    break  # Langsung lanjut ke soal berikutnya jika ada yang benar
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
        """Menampilkan kata dengan huruf yang sudah ditebak dan garis bawah untuk huruf yang belum ditebak."""
        displayed_word = ''.join([letter if letter in guessed_letters else '_' for letter in word])
        return displayed_word

    async def end_game(self, ctx):
        game_data = self.active_games.pop(ctx.author.id, None)
        if game_data:
            # Hitung saldo akhir dari sesi kuis
            earned_rsw = game_data['correct'] * 25  # RSWN yang diperoleh dari hasil kuis

            # Update bank_data.json dengan saldo sesi
            if str(ctx.author.id) not in self.bank_data:
                self.bank_data[str(ctx.author.id)] = {"balance": 0}

            # Tambahkan saldo yang diperoleh
            self.bank_data[str(ctx.author.id)]["balance"] += earned_rsw

            # Update level_data.json dengan EXP
            if str(ctx.author.id) in self.level_data:
                self.level_data[str(ctx.author.id)]["exp"] += game_data['correct'] * 10  # 10 EXP per soal yang benar
            else:
                self.level_data[str(ctx.author.id)] = {
                    "exp": game_data['correct'] * 10
                }

            # Simpan perubahan ke file
            with open('data/bank_data.json', 'w', encoding='utf-8') as f:
                json.dump(self.bank_data, f, indent=4)

            with open('data/level_data.json', 'w', encoding='utf-8') as f:
                json.dump(self.level_data, f, indent=4)

            # Menampilkan leaderboard
            await self.display_leaderboard(ctx)

    async def display_leaderboard(self, ctx):
        sorted_scores = sorted(self.scores.values(), key=lambda x: x["correct"], reverse=True)[:5]  # Hanya ambil 5 teratas
        embed = discord.Embed(title="🏆 Leaderboard Hangman", color=0x00ff00)

        # Mengambil informasi untuk leaderboard
        for i, score in enumerate(sorted_scores, start=1):  # Menampilkan peringkat 1 hingga 5
            user = score['user']
            embed.add_field(
                name=f"{i}. {user.display_name}",
                value=(
                    f"Total RSWN: {score.get('total_rsw', 0)}\n"  # Cek total RSWN
                    f"Jawaban Benar: {score['correct']}\n"
                    f"Jawaban Salah: {score['wrong']}"
                ),
                inline=False
            )

        # Hanya mengirim gambar untuk pengguna peringkat pertama
        if sorted_scores:
            top_user = sorted_scores[0]['user']
            image_url = str(top_user.avatar.url) if top_user.avatar else str(top_user.default_avatar.url)

            # Mengambil gambar pengguna
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as resp:
                        if resp.status == 200:
                            image_data = BytesIO(await resp.read())
                            await ctx.send(file=discord.File(image_data, filename='avatar.png'))  # Kirim gambar
            except Exception as e:
                print(f"Error fetching image for {top_user.display_name}: {e}")

        await ctx.send(embed=embed)  # Mengirim leaderboard

async def setup(bot):
    await bot.add_cog(Hangman(bot))
