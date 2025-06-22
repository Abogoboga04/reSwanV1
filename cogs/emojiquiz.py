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

        if ctx.author.id in self.active_games:
            await ctx.send("Anda sudah sedang bermain EmojiQuiz. Silakan tunggu hingga selesai.")
            return

        self.scores[ctx.author.id] = {
            "score": 0,
            "correct": 0,
            "wrong": 0,
            "user": ctx.author
        }

        embed = discord.Embed(
            title="🎮 Cara Bermain EmojiQuiz",
            description=(
                "Selamat datang di Kuis Emoji! 🎉\n\n"
                "Di sini, kamu akan diberikan emoji dan kamu harus menebak frasa yang sesuai.\n"
                "Selesaikan 10 soal dalam 2 menit... kalau kamu masih punya semangat itu.\n\n"
                "Kalau kamu cukup kuat, cukup tahan, cukup sad... klik tombol di bawah ini. Mulai permainanmu."
            ),
            color=0x5500aa
        )

        view = discord.ui.View()
        start_button = discord.ui.Button(label="🔵 START", style=discord.ButtonStyle.primary)

        async def start_game(interaction):
            if ctx.author.id in self.active_games:
                await ctx.send("Anda sudah sedang bermain EmojiQuiz. Silakan tunggu hingga selesai.")
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

            await ctx.send(f"{ctx.author.mention}, permainan EmojiQuiz dimulai! Anda memiliki 2 menit untuk menjawab 10 soal.")
            await self.play_game(ctx)

        start_button.callback = start_game
        view.add_item(start_button)

        message = await ctx.send(embed=embed, view=view)

        # Tunggu 1 menit sebelum reset jika tidak ada yang menekan tombol
        await asyncio.sleep(60)
        if ctx.author.id not in self.active_games:
            await message.delete()
            await ctx.send("Waktu habis! Permainan EmojiQuiz di-reset. Silakan coba lagi.")
        else:
            await message.delete()  # Hapus pesan instruksi jika game dimulai

    async def play_game(self, ctx):
        game_data = self.active_games[ctx.author.id]
        game_data["start_time"] = asyncio.get_event_loop().time()

        # Cek apakah ada pertanyaan yang tersedia
        if not self.questions:
            await ctx.send("Tidak ada pertanyaan yang tersedia. Pastikan emoji_questions.json diisi dengan benar.")
            return

        if len(self.questions) < 10:
            await ctx.send("Tidak cukup pertanyaan untuk memulai permainan. Pastikan ada setidaknya 10 pertanyaan di emoji_questions.json.")
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
                f"Emoji: **{question['emoji']}**\n"
                f"Sebutkan frasa yang sesuai!"
            ),
            color=0x00ff00
        )
        
        await ctx.send(embed=embed)

        # Menunggu jawaban dalam waktu yang ditentukan
        try:
            def check(m):
                return m.channel == ctx.channel and m.author in self.participants  # Setiap peserta dapat menjawab

            user_answer = await self.bot.wait_for('message', timeout=game_data["time_limit"], check=check)

            # Cek jawaban
            if user_answer.content.strip().lower() == question['answer'].lower():
                game_data["correct"] += 1
                await ctx.send(f"✅ Jawaban Benar dari {user_answer.author.display_name}!")
            else:
                game_data["wrong"] += 1
                await ctx.send(f"❌ Jawaban Salah dari {user_answer.author.display_name}.")

            if game_data["current_question"] == 10:
                await self.end_game(ctx)

        except asyncio.TimeoutError:
            await ctx.send("Waktu habis! Permainan berakhir.")
            game_data["game_over"] = True
            await self.end_game(ctx)

    async def end_game(self, ctx):
        game_data = self.active_games.pop(ctx.author.id, None)
        if game_data:
            # Hitung saldo awal dan akhir
            initial_balance = self.bank_data.get(str(ctx.author.id), {}).get('balance', 0)
            earned_rsw = game_data['correct'] * 25  # RSWN yang diperoleh dari hasil kuis
            final_balance = initial_balance + earned_rsw + (50 if game_data['correct'] == 10 else 0)  # Bonus jika benar semua

            # Kartu hasil
            embed = discord.Embed(
                title="📝 Hasil Permainan EmojiQuiz",
                color=0x00ff00
            )
            embed.add_field(name="Nama", value=ctx.author.display_name)
            embed.add_field(name="Jawaban Benar", value=game_data['correct'])
            embed.add_field(name="Jawaban Salah", value=game_data['wrong'])
            embed.add_field(name="RSWN yang Diperoleh", value=earned_rsw)
            embed.add_field(name="Saldo RSWN Awal", value=initial_balance)
            embed.add_field(name="Saldo RSWN Akhir", value=final_balance)

            # Menyimpan skor untuk leaderboard
            self.scores[ctx.author.id] = {
                "score": final_balance,
                "correct": game_data['correct'],
                "wrong": game_data['wrong'],
                "user": ctx.author
            }

            # Mengambil gambar pengguna
            user_data = self.level_data.get(str(ctx.guild.id), {}).get(str(ctx.author.id), {})
            image_data = await self.get_user_image(ctx, user_data)

            # Mengirimkan kartu hasil dengan gambar pengguna
            await ctx.send(file=discord.File(image_data, "avatar.png"), embed=embed)

            # Update bank_data.json
            self.bank_data[str(ctx.author.id)] = {
                "balance": final_balance
            }

            # Simpan perubahan ke file
            with open('data/bank_data.json', 'w', encoding='utf-8') as f:
                json.dump(self.bank_data, f, indent=4)

            # Menampilkan leaderboard jika ada 2 atau lebih peserta
            if len(self.scores) >= 2:
                await self.display_leaderboard(ctx)

    async def display_leaderboard(self, ctx):
        sorted_scores = sorted(self.scores.values(), key=lambda x: x["score"], reverse=True)
        embed = discord.Embed(title="🏆 Leaderboard EmojiQuiz", color=0x00ff00)

        # Mengambil peserta dari peringkat 2 hingga 5
        for i, score in enumerate(sorted_scores[1:5], start=2):  # Mulai dari index 1 untuk juara 2
            embed.add_field(
                name=f"{i}. {score['user'].display_name}",
                value=(
                    f"Saldo Akhir: {score['score']}\n"
                    f"Jawaban Benar: {score['correct']}\n"
                    f"Jawaban Salah: {score['wrong']}\n"
                    f"RSWN yang Diperoleh: {score['correct'] * 25}"
                ),
                inline=False
            )

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(EmojiQuiz(bot))
