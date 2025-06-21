import discord
from discord.ext import commands
import json
import random
import asyncio
import os

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
        no_one_answered = True

        for participant in self.participants:
            if participant.id in self.current_answers:
                user_answer = self.current_answers[participant.id].strip().lower()
                if user_answer == correct_answer:
                    no_one_answered = False
                    break

        self.question_active = False
        if no_one_answered:
            await ctx.send(f"❌ Tidak ada yang menjawab benar. Jawabannya: **{correct_answer}**")
            await asyncio.sleep(1)
            await ctx.send("➡️ Pertanyaan berikutnya...")

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
        if message.author.bot or not self.quiz_active or not self.question_active:
            return

        if message.author in self.participants and self.current_question:
            if message.author.voice is None:
                await message.channel.send(f"{message.author.mention}, kamu harus di voice channel untuk menjawab!")
                return

            user_answer = message.content.strip().lower()
            correct_answer = self.current_question['answer'].strip().lower()

            if user_answer == correct_answer:
                if message.author.id not in self.current_answers:
                    self.current_answers[message.author.id] = user_answer
                    self.correct_count[message.author.id] += 1
                    self.bank_data[str(message.author.id)]['balance'] += 25
                    await message.channel.send(f"✅ {message.author.mention} menjawab dengan benar! Jawabannya: **{correct_answer}**")

                    self.question_active = False  # Hentikan soal
                    await asyncio.sleep(1)
                    await message.channel.send("➡️ Pertanyaan berikutnya...")
            else:
                if message.author.id not in self.current_answers:
                    self.current_answers[message.author.id] = user_answer


async def setup(bot):
    await bot.add_cog(EmojiQuiz(bot))
  
