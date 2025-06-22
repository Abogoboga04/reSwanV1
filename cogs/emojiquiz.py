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

        self.game_channel_id = 1379458566452154438  # ID channel yang diizinkan
        self.bantuan_price = 35  # Harga bantuan
        self.max_bantuan_per_session = 8  # Maksimal bantuan per sesi
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
        with open(file_path, "r", encoding="utf-8") as f:
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

    async def get_user_image(self, ctx, user_data):
        """Mengambil gambar pengguna dari URL yang disimpan atau menggunakan avatar pengguna."""
        custom_image_url = user_data.get("image_url") or str(ctx.author.avatar.url)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(custom_image_url) as resp:
                    if resp.status == 200:
                        image_data = BytesIO(await resp.read())
                        return image_data
                    else:
                        raise Exception("Invalid image URL")
        except Exception:
            default_image_url = str(ctx.author.avatar.url)
            async with aiohttp.ClientSession() as session:
                async with session.get(default_image_url) as resp:
                    return BytesIO(await resp.read())

    @commands.command(name="resmoji", help="Mulai permainan EmojiQuiz.")
    async def resmoji(self, ctx):
        if ctx.channel.id != self.game_channel_id:
            await ctx.send("Permainan EmojiQuiz hanya bisa dimainkan di channel yang ditentukan.")
            return

        # Memeriksa apakah sesi aktif untuk pengguna lain
        if ctx.channel.id in self.active_games:
            await ctx.send("Permainan sudah sedang berlangsung di channel ini.")
            return
        
        self.scores[ctx.author.id] = {
            "score": 0,
            "correct": 0,
            "wrong": 0,
            "user": ctx.author,
            "bantuan_used": 0,  # Menghitung bantuan yang digunakan per sesi
            "current_question": None  # Menyimpan pertanyaan saat ini
        }

        embed = discord.Embed(
            title="🎮 Cara Bermain EmojiQuiz",
            description=(
                "Selamat datang di Kuis Emoji! 🎉\n\n"
                "Di sini, kamu akan diberikan emoji dan kamu harus menebak frasa yang sesuai.\n"
                "Setiap peserta dapat menjawab, dan jika tidak ada yang benar dalam waktu 1 menit, soal akan dilanjutkan.\n"
                "Gunakan command **!resplis** untuk membeli bantuan jika diperlukan (maksimal 8 per sesi).\n"
                "Harga bantuan adalah 35 RSWN.\n"
                "Siap untuk mulai? Klik tombol di bawah ini untuk memulai permainan."
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
                "time_limit": self.time_limit  # Menetapkan waktu batas
            }
            await self.play_game(ctx)

        start_button.callback = start_game
        view.add_item(start_button)

        await ctx.send(embed=embed, view=view)

    @commands.command(name="resplis", help="Membeli bantuan untuk jawaban pertanyaan saat ini.")
    async def resplis(self, ctx):
        user_id = ctx.author.id

        if user_id not in self.bank_data:
            await ctx.send("Anda tidak memiliki akun di sistem ini.")
            return

        user_data = self.bank_data[str(user_id)]

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
            if game_data["game_over"]:
                break

            game_data["current_question"] = index  # Simpan indeks pertanyaan saat ini
            await self.ask_question(ctx, question)

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
                return m.channel == ctx.channel  # Memungkinkan semua pengguna di channel untuk menjawab

            while True:
                try:
                    user_answer = await self.bot.wait_for('message', timeout=self.time_limit, check=check)

                    # Cek jawaban
                    if user_answer.content.strip().lower() == question['answer'].lower():
                        game_data["correct"] += 1
                        await ctx.send(f"✅ Jawaban Benar dari {user_answer.author.display_name}!")
                        # Tambahkan reward untuk jawaban benar
                        self.bank_data[str(user_answer.author.id)]['balance'] += self.reward_per_correct_answer
                        break
                    else:
                        game_data["wrong"] += 1
                        await ctx.send(f"❌ Jawaban Salah dari {user_answer.author.display_name}.")
                except asyncio.TimeoutError:
                    await ctx.send("Waktu habis! Melanjutkan ke soal berikutnya.")
                    break

        except asyncio.TimeoutError:
            await ctx.send("Waktu habis! Melanjutkan ke soal berikutnya.")

    async def end_game(self, ctx):
        game_data = self.active_games.pop(ctx.channel.id, None)
        if game_data:
            # Hitung saldo awal dan akhir
            initial_balance = self.bank_data.get(str(game_data['user'].id), {}).get('balance', 0)
            earned_rsw = game_data['correct'] * self.reward_per_correct_answer  # RSWN yang diperoleh dari hasil kuis
            final_balance = initial_balance + earned_rsw + (50 if game_data['correct'] == 10 else 0)  # Bonus jika benar semua

            # Memperbarui skor untuk leaderboard
            self.scores[game_data['user'].id] = {
                "score": final_balance,
                "correct": game_data['correct'],
                "wrong": game_data['wrong'],
                "user": game_data['user']
            }

            # Menyimpan data bank
            self.bank_data[str(game_data['user'].id)] = {
                "balance": final_balance
            }

            # Simpan perubahan ke file
            with open('data/bank_data.json', 'w', encoding='utf-8') as f:
                json.dump(self.bank_data, f, indent=4)

            # Menampilkan leaderboard
            await self.display_leaderboard(ctx)

    async def display_leaderboard(self, ctx):
        sorted_scores = sorted(self.scores.values(), key=lambda x: x["score"], reverse=True)
        embed = discord.Embed(title="🏆 Leaderboard EmojiQuiz", color=0x00ff00)

        # Menampilkan gambar juara 1
        if sorted_scores:
            top_player = sorted_scores[0]['user']
            avatar_url = top_player.avatar.url if top_player.avatar else None
            image_url = top_player.image_url if hasattr(top_player, 'image_url') and top_player.image_url else avatar_url

            # Kirim gambar juara 1
            if image_url:
                await ctx.send(image_url)  # Mengirim gambar sebagai pesan terpisah

        # Menampilkan peserta dari peringkat 1 hingga 5
        for i, score in enumerate(sorted_scores[:5], start=1):  # Hanya 5 peserta teratas
            user = score['user']
            embed.add_field(
                name=f"{i}. {user.display_name}",
                value=(
                    f"Saldo Akhir: {score['score']}\n"
                    f"Jawaban Benar: {score['correct']}\n"
                    f"Jawaban Salah: {score['wrong']}\n"
                    f"RSWN yang Diperoleh: {score['correct'] * self.reward_per_correct_answer}"
                ),
                inline=False
            )

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(EmojiQuiz(bot))
