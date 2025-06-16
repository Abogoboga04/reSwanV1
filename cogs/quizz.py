import discord
from discord.ext import commands
import json
import random
import asyncio
import os

class QuizButton(discord.ui.Button):
    def __init__(self, label, option_letter, parent_view):
        super().__init__(label=f"{option_letter}. {label}", style=discord.ButtonStyle.primary)
        self.parent_view = parent_view
        self.option_letter = option_letter

    async def callback(self, interaction: discord.Interaction):
        if not hasattr(self.parent_view, "participants"):
            await interaction.response.send_message("Sesi kuis tidak valid. Coba lagi.", ephemeral=True)
            return

        if interaction.user.id not in self.parent_view.participants:
            await interaction.response.send_message("Ini bukan pertanyaan untukmu!", ephemeral=True)
            return

        await interaction.response.defer()

        is_correct = self.option_letter.upper() == self.parent_view.correct_answer.upper()
        await self.parent_view.on_answer(interaction, is_correct)

        for child in self.parent_view.children:
            child.disabled = True

        await interaction.message.edit(view=self.parent_view)
        self.parent_view.stop()

class QuizView(discord.ui.View):
    def __init__(self, options, correct_answer, participants, on_answer):
        super().__init__(timeout=15)
        self.correct_answer = correct_answer
        self.participants = participants
        self.on_answer = on_answer

        letters = ["A", "B", "C", "D"]
        for i, option in enumerate(options):
            self.add_item(QuizButton(option, letters[i], self))

class MusicQuiz(commands.Cog):
    SCORES_FILE = "scores.json"
    LEVEL_FILE = "data/level_data.json"
    BANK_FILE = "data/bank_data.json"

    def __init__(self, bot):
        self.bot = bot
        self.load_questions()
        self.scores = {}
        self.active_quizzes = {}  # guild_id: bool

    def load_questions(self):
        with open("questions.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            self.questions = data.get("questions", [])

    def load_json(self, path):
        if not os.path.exists(path):
            return {}
        with open(path, "r") as f:
            return json.load(f)

    def save_json(self, path, data):
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    async def join(self, ctx):
        if not ctx.author.voice:
            await ctx.send("Kamu harus ada di voice channel.")
            return False

        channel = ctx.author.voice.channel

        if not ctx.guild.voice_client or not ctx.guild.voice_client.is_connected():
            await channel.connect()
            await ctx.send(f"Bot telah bergabung ke {channel.name}.\n\n🎉 Siap-siap kuis!\nCara main: Bot akan memberikan pertanyaan pilihan ganda, kamu tinggal klik jawabannya secepat mungkin!\nKamu cuma punya 5 detik! Jawab benar duluan, kamu menang!")
            return True

        if ctx.guild.voice_client.channel != channel:
            await ctx.send("Bot sudah terhubung ke channel lain. Pindahkan bot ke channel ini atau gunakan channel yang sama.")
            return False

        await ctx.send(f"Bot sudah berada di {channel.name}.")
        return True

    @commands.command(name="join", help="Bot akan bergabung ke ruang voice.")
    async def join_command(self, ctx):
        await self.join(ctx)

    @commands.command(name="startquiz")
    async def start_quiz(self, ctx):
        guild_id = ctx.guild.id
        if self.active_quizzes.get(guild_id):
            await ctx.send("❗ Masih ada sesi kuis yang aktif di server ini. Selesaikan dulu sebelum mulai baru.")
            return

        joined = await self.join(ctx)
        if not joined:
            return

        self.active_quizzes[guild_id] = True

        try:
            participants = [member.id for member in ctx.author.voice.channel.members if not member.bot]
            self.scores = {str(member_id): 0 for member_id in participants}
            bonus_winners = []

            await ctx.send("⏳ Bersiaplah... Kuis akan dimulai dalam 3 detik!")
            await asyncio.sleep(3)
            await ctx.send("🎬 Selamat datang di kuis musik! Semoga kalian tidak fals jawabnya! 😎🎶")

            def make_callback(question, is_bonus, correct_users):
                async def callback(interaction, is_correct):
                    uid = str(interaction.user.id)
                    if uid not in self.scores:
                        self.scores[uid] = 0
                    if is_correct:
                        self.scores[uid] += 1
                        if is_bonus:
                            correct_users.append(uid)
                        await ctx.send(f"✅ {interaction.user.mention} Jawaban benar!")
                    else:
                        await ctx.send(f"❌ {interaction.user.mention} Salah! Jawaban yang benar: {question['answer']}")
                return callback

            for nomor in range(1, 21):
                if not self.questions:
                    await ctx.send("Pertanyaan habis.")
                    break

                q = random.choice(self.questions)
                self.questions.remove(q)
                is_bonus = nomor >= 15
                correct_users = []

                view = QuizView(q["options"], q["answer"], participants, make_callback(q, is_bonus, correct_users))
                embed = discord.Embed(
                    title=f"🎤 Pertanyaan {nomor}{' (BONUS)' if is_bonus else ''}",
                    description=q["question"],
                    color=discord.Color.gold() if is_bonus else discord.Color.blurple()
                )
                msg = await ctx.send(embed=embed, view=view)
                view.message = msg
                await view.wait()
                await asyncio.sleep(5)

                if is_bonus and correct_users:
                    bonus_winners.extend(correct_users)

            await self.send_leaderboard(ctx, bonus_winners)
        finally:
            self.active_quizzes[guild_id] = False

    async def send_leaderboard(self, ctx, bonus_winners):
        sorted_scores = sorted(self.scores.items(), key=lambda x: x[1], reverse=True)
        top3 = sorted_scores[:3]

        level_data = self.load_json(self.LEVEL_FILE)
        bank_data = self.load_json(self.BANK_FILE)

        rewards = [(50, 150), (25, 100), (15, 50)]

        embed = discord.Embed(title="🏆 **Leaderboard:**", color=0x1DB954)
        for i, (user_id, score) in enumerate(top3):
            user = self.bot.get_user(int(user_id))
            name = user.name if user else "Unknown"
            exp, rswn = rewards[i]

            level_data.setdefault(str(ctx.guild.id), {}).setdefault(user_id, {}).setdefault("exp", 0)
            bank_data.setdefault(user_id, {}).setdefault("balance", 0)

            level_data[str(ctx.guild.id)][user_id]["exp"] += exp
            bank_data[user_id]["balance"] += rswn

            embed.add_field(name=f"{i+1}. {name}", value=f"Score: {score}\n+{exp} EXP, +{rswn} RSWN", inline=False)

        self.save_json(self.LEVEL_FILE, level_data)
        self.save_json(self.BANK_FILE, bank_data)

        await ctx.send(embed=embed)

        # Bonus Reward Announcement
        bonus_award = {}
        for uid in bonus_winners:
            level_data.setdefault(str(ctx.guild.id), {}).setdefault(uid, {}).setdefault("exp", 0)
            bank_data.setdefault(uid, {}).setdefault("balance", 0)

            level_data[str(ctx.guild.id)][uid]["exp"] += 25
            bank_data[uid]["balance"] += 25

            bonus_award[uid] = True

        self.save_json(self.LEVEL_FILE, level_data)
        self.save_json(self.BANK_FILE, bank_data)

        if bonus_award:
            desc = ""
            for uid in bonus_award:
                user = self.bot.get_user(int(uid))
                desc += f"✅ {user.mention if user else 'Unknown'} mendapatkan +25 EXP & +25 RSWN dari babak bonus!\n"

            embed = discord.Embed(title="🎉 Bonus Reward", description=desc, color=discord.Color.green())
            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(MusicQuiz(bot))
