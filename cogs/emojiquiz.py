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
        self.active_games = {}
        self.bank_data = self.load_bank_data()
        self.level_data = self.load_level_data()
        self.questions = self.load_quiz_data()
        self.scores = {}  # Menyimpan skor peserta

        self.game_channel_id = 765140300145360896  # ID channel yang diizinkan
        self.bantuan_price = 35  # Harga bantuan
        self.reward_per_correct_answer = 30  # Hadiah per pertanyaan benar
        self.time_limit = 60  # Waktu batas untuk setiap pertanyaan

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

    def load_quiz_data(self):
        current_dir = os.path.dirname(__file__)  # Folder cogs/
        file_path = os.path.join(current_dir, '..', 'data', 'emoji_questions.json')
        with open(file_path, "r", encoding='utf-8') as f:
            try:
                data = json.load(f)
                if isinstance(data["questions"], list) and len(data["questions"]) > 0:
                    return data["questions"]
                else:
                    raise ValueError("Data harus berupa list dan tidak kosong.")
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON from emoji_questions.json: {e}")
                return []
            except Exception as e:
                print(f"Error loading quiz data: {e}")
                return []

    @commands.command(name="resmoji", help="Mulai permainan EmojiQuiz.")
    async def resmoji(self, ctx):
        if ctx.channel.id != self.game_channel_id:
            await ctx.send("Permainan EmojiQuiz hanya bisa dimainkan di channel yang ditentukan.")
            return

        # Memeriksa apakah sesi aktif untuk channel ini
        if ctx.channel.id in self.active_games:
            await ctx.send("Permainan sudah sedang berlangsung di channel ini.")
            return
        
        self.scores = {}  # Reset skor untuk setiap permainan baru

        embed = discord.Embed(
            title="🎮 Cara Bermain EmojiQuiz",
            description=(
                "Selamat datang di **Kuis Emoji** — game buat kamu yang masih mau main meski server sepi... lagi. 💔\n\n"
                "📌 Kamu akan dikasih 1 atau lebih emoji dari bot.\n"
                "🫵 Tebak maksudnya, bisa 1–3 kata. Bebas.\n"
                "⏳ Kalau gak ada yang jawab dalam 1 menit, soal langsung lanjut ke berikutnya.\n"
                "🎁 Jawaban benar dapet **+30 RSWN**. Lumayan buat beli badge atau sekadar merasa berguna.\n\n"
                "💸 Ngerasa buntu? Beli **bantuan** aja pake:\n"
                "**!resplis** – Harga: 35 RSWN. Dibalas via DM.\n"
                "*Bantuan gak dibatasin... karena kami ngerti, kadang kita butuh banyak petunjuk buat ngerti sesuatu.*\n\n"
                "🖤 Terima kasih buat kalian yang masih sering nongol di sini...\n"
                "Walau orangnya itu-itu aja, ... tapi hati kami tetap hangat karena kalian."
                "\n\nKlik tombol di bawah ini kalau kamu siap... atau kalau cuma pengen ditemani sebentar sama bot ini."
            ),
            color=0x5500aa
        )

        view = discord.ui.View()
        start_button = discord.ui.Button(label="🔵 START", style=discord.ButtonStyle.primary)

        async def start_game(interaction):
            # Menambahkan pengguna ke active_games dan mengatur data permainan
            self.active_games[ctx.channel.id] = {
                "user": ctx.author,
                "correct": 0,
                "wrong": 0,
                "current_question": None,
                "questions": [],
                "game_over": False,
                "bantuan_used": 0,
                "start_time": None,
                "total_rsw": 0  # Menyimpan total RSWN yang diperoleh dari sesi ini
            }
            await self.play_game(ctx)

        start_button.callback = start_game
        view.add_item(start_button)

        await ctx.send(embed=embed, view=view)

    @commands.command(name="resplis", help="Membeli bantuan untuk jawaban pertanyaan saat ini.")
    async def resplis(self, ctx):
        user_id = str(ctx.author.id)  # Pastikan ID pengguna adalah string

        # Memastikan bahwa data pengguna ada di bank_data
        if user_id not in self.bank_data:
            # Membuat akun baru untuk pengguna
            self.bank_data[user_id] = {
                "balance": 0,  # Set saldo awal ke 0 atau nilai lainnya sesuai kebutuhan
                "debt": 0
            }
            await ctx.send("Akun Anda telah dibuat. Saldo awal Anda adalah 0 RSWN.")

        user_data = self.bank_data[user_id]

        if user_data.get('balance', 0) < self.bantuan_price:
            await ctx.send("😢 Saldo RSWN tidak cukup untuk membeli bantuan.")
            return

        # Mengurangi saldo RSWN
        initial_balance = user_data['balance']
        user_data['balance'] -= self.bantuan_price
        final_balance = user_data['balance']

        # Mengambil jawaban dari pertanyaan saat ini
        current_question_index = self.active_games[ctx.channel.id]["current_question"]
        current_question = self.active_games[ctx.channel.id]["questions"][current_question_index]

        # Kirim jawaban ke DM pengguna
        await ctx.author.send(f"🔐 Jawaban untuk pertanyaan saat ini adalah: **{current_question['answer']}**")
        await ctx.author.send(f"✅ Pembelian bantuan berhasil! Saldo RSWN Anda berkurang dari **{initial_balance}** menjadi **{final_balance}**.")

        # Memberikan konfirmasi di channel
        await ctx.send(f"{ctx.author.mention}, Anda telah berhasil membeli bantuan!")

        # Simpan perubahan ke file
        with open('data/bank_data.json', 'w', encoding='utf-8') as f:
            json.dump(self.bank_data, f, indent=4)

    async def play_game(self, ctx):
        game_data = self.active_games[ctx.channel.id]
        game_data["start_time"] = asyncio.get_event_loop().time()

        # Cek apakah ada pertanyaan yang tersedia
        if not self.questions:
            await ctx.send("Tidak ada pertanyaan yang tersedia. Pastikan emoji_questions.json diisi dengan benar.")
            return

        if len(self.questions) < 10:
            await ctx.send("Tidak cukup pertanyaan untuk memulai permainan. Pastikan ada setidaknya 10 pertanyaan di emoji_questions.json.")
            return

        game_data["questions"] = random.sample(self.questions, 10)  # Ambil 10 soal acak

        for index, question in enumerate(game_data["questions"]):
            game_data["current_question"] = index  # Simpan indeks pertanyaan saat ini
            await self.ask_question(ctx, question)

            if game_data["game_over"]:
                break

        if not game_data["game_over"]:
            await self.end_game(ctx)

    async def ask_question(self, ctx, question):
        game_data = self.active_games[ctx.channel.id]

        embed = discord.Embed(
            title=f"❓ Pertanyaan {game_data['current_question'] + 1}",
            description=(
                f"Emoji: **{question['emoji']}**\n"
                f"Sebutkan frasa yang sesuai!"
            ),
            color=0x00ff00
        )

        await ctx.send(embed=embed)

        # Menunggu jawaban dalam waktu yang ditentukan
        try:
            def check(m):
                return m.channel == ctx.channel and m.author != self.bot.user  # Memungkinkan semua pengguna di channel untuk menjawab, kecuali pesan dari bot

            while True:
                user_answer = await self.bot.wait_for('message', timeout=self.time_limit, check=check)

                # Cek jawaban
                if user_answer.content.strip().lower() == question['answer'].lower():
                    if user_answer.author.id not in self.scores:
                        self.scores[user_answer.author.id] = {
                            "score": 0,
                            "correct": 0,
                            "wrong": 0,
                            "user": user_answer.author
                        }

                    game_data["correct"] += 1
                    game_data["total_rsw"] += self.reward_per_correct_answer  # Tambahkan RSWN ke total RSWN
                    self.scores[user_answer.author.id]["score"] += self.reward_per_correct_answer
                    self.scores[user_answer.author.id]["correct"] += 1

                    await ctx.send(f"✅ Jawaban Benar dari {user_answer.author.display_name}!")
                    break  # Langsung lanjut ke soal berikutnya
                else:
                    if user_answer.author.id not in self.scores:
                        self.scores[user_answer.author.id] = {
                            "score": 0,
                            "correct": 0,
                            "wrong": 0,
                            "user": user_answer.author
                        }

                    self.scores[user_answer.author.id]["wrong"] += 1
                    await ctx.send(f"❌ Jawaban Salah dari {user_answer.author.display_name}.")

        except asyncio.TimeoutError:
            await ctx.send("Waktu habis! Melanjutkan ke soal berikutnya.")

    async def end_game(self, ctx):
        game_data = self.active_games.pop(ctx.channel.id, None)
        if game_data:
            # Menghitung skor akhir untuk pengguna
            for user_id, score in self.scores.items():
                score["total_rsw"] = score["score"]  # Menyimpan total RSWN yang didapat dari jawaban benar

            # Simpan perubahan ke file
            with open('data/bank_data.json', 'w', encoding='utf-8') as f:
                json.dump(self.bank_data, f, indent=4)

            # Menampilkan leaderboard
            await self.display_leaderboard(ctx)

    async def display_leaderboard(self, ctx):
        sorted_scores = sorted(self.scores.values(), key=lambda x: x["score"], reverse=True)
        embed = discord.Embed(title="🏆 Leaderboard EmojiQuiz", color=0x00ff00)

        # Menampilkan hingga 5 pengguna teratas
        for i in range(min(5, len(sorted_scores))):
            top_user = sorted_scores[i]  # Ambil pengguna peringkat ke-i
            user = top_user['user']
            embed.add_field(
                name=f"{i + 1}. {user.display_name}",
                value=(
                    f"Total RSWN: {top_user['total_rsw']}\n"  # Total RSWN dari sesi kuis
                    f"Jawaban Benar: {top_user['correct']}\n"
                    f"Jawaban Salah: {top_user['wrong']}"
                ),
                inline=False
            )

        # Mengambil gambar pengguna hanya untuk peringkat pertama
        if sorted_scores:
            top_user = sorted_scores[0]  # Ambil pengguna peringkat pertama
            user = top_user['user']
            image_url = str(user.avatar.url) if user.avatar else str(user.default_avatar.url)
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as resp:
                        if resp.status == 200:
                            image_data = BytesIO(await resp.read())
                            await ctx.send(file=discord.File(image_data, filename='avatar.png'))  # Kirim gambar
            except Exception as e:
                print(f"Error fetching image for {user.display_name}: {e}")

        await ctx.send(embed=embed)  # Mengirim leaderboard

async def setup(bot):
    await bot.add_cog(EmojiQuiz(bot))
