import discord
from discord.ext import commands
import json
import random
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
        self.bantuan_used = {}
        self.bantuan_price = 25
        self.quiz_active = False

    def load_bank_data(self):
        with open('data/bank_data.json', 'r', encoding='utf-8') as f:
            return json.load(f)

    def load_level_data(self):
        with open('data/level_data.json', 'r', encoding='utf-8') as f:
            return json.load(f)

    def load_quiz_data(self):
        current_dir = os.path.dirname(__file__)
        file_path = os.path.join(current_dir, '..', 'data', 'emoji_questions.json')
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data["questions"], list) and len(data["questions"]) > 0:
                return data["questions"]
            else:
                raise ValueError("Data harus berupa list dan tidak kosong.")

    async def get_user_image(self, ctx, user_data):
        custom_image_url = user_data.get("image_url") or str(ctx.author.avatar.url)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(custom_image_url) as resp:
                    if resp.status == 200:
                        return BytesIO(await resp.read())
                    else:
                        raise Exception("Invalid image URL")
        except Exception:
            default_image_url = str(ctx.author.avatar.url)
            async with aiohttp.ClientSession() as session:
                async with session.get(default_image_url) as resp:
                    return BytesIO(await resp.read())

    @commands.command(name="resmoji", help="Mulai permainan EmojiQuiz.")
    async def resmoji(self, ctx):
        if self.quiz_active:
            await ctx.send("Kuis sudah aktif, tunggu hingga sesi ini selesai!")
            return

        if ctx.channel.id != self.game_channel_id:
            await ctx.send("Kuis hanya dapat dimulai di channel yang ditentukan!")
            return

        self.quiz_active = True
        self.current_question = random.choice(self.questions)
        self.current_answer = self.current_question['answer'].lower()
        self.current_guesses = []
        self.participants = [ctx.author]

        for member in ctx.guild.members:
            if len(self.participants) >= 5:
                break
            if member != ctx.author and not member.bot:
                self.participants.append(member)

        if len(self.participants) < 2:
            await ctx.send("😢 Minimal 2 peserta diperlukan untuk memulai kuis!")
            self.quiz_active = False
            return

        for participant in self.participants:
            self.bantuan_used[participant.id] = 0

        embed = discord.Embed(
            title="🎮 Cara Bermain EmojiQuiz",
            description=(
                "Selamat datang di Kuis Emoji! 🎉\n\n"
                "Di sini, kamu akan diberikan emoji dan kamu harus menebak frasa yang sesuai.\n"
                "Gunakan emoji yang ditampilkan untuk membantu menebak frasa yang benar.\n"
                "Setiap peserta memiliki kesempatan untuk menebak.\n"
                "Jika kamu memerlukan bantuan, kamu dapat membeli bantuan dengan menggunakan tombol di bawah.\n"
                "Siap untuk mulai? Klik tombol di bawah ini untuk memulai permainan."
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

            await ctx.send(f"{ctx.author.mention}, permainan EmojiQuiz dimulai! Anda memiliki 2 menit untuk menjawab.")
            await self.send_game_state(ctx)

        start_button.callback = start_game
        view.add_item(start_button)

        await ctx.send(embed=embed, view=view)

    async def send_game_state(self, ctx):
        displayed_word = ''.join([letter if letter in self.current_guesses else '_' for letter in self.current_answer])
        embed = discord.Embed(
            title="🔤 Kuis Emoji!",
            description=f"Tebak frasa ini: `{displayed_word}`\n\nGunakan `!resplis` untuk melihat jawaban.",
            color=0x00ff00
        )

        # Tombol untuk membeli bantuan
        view = discord.ui.View()
        help_button = discord.ui.Button(label="🆘 Beli Bantuan", style=discord.ButtonStyle.secondary)

        async def buy_help(interaction):
            await self.buy_help_function(ctx)

        help_button.callback = buy_help
        view.add_item(help_button)

        await ctx.send(embed=embed, view=view)

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

        await ctx.send("✅ Bantuan dibeli! Gunakan `!resplis` untuk melihat jawaban.", ephemeral=True)

    @commands.command(name="resplis", help="Gunakan bantuan untuk melihat jawaban.")
    async def resplis(self, ctx):
        user_id = str(ctx.author.id)
        if user_id not in self.bantuan_used or self.bantuan_used[user_id] <= 0:
            await ctx.send("Kamu belum beli bantuan!", ephemeral=True)
            return

        if self.current_answer is None:
            await ctx.send("Belum ada pertanyaan aktif!", ephemeral=True)
            return

        await ctx.author.send(f"🔐 Jawaban: **{self.current_answer}**")
        self.bantuan_used[user_id] -= 1

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
