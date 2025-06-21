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

        # Debug: cek jumlah pertanyaan yang dimuat
        print(f"Jumlah pertanyaan yang dimuat: {len(self.questions)}")

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
        print(f"Loading hangman data from: {file_path}")  # Debug: Cek lokasi file
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                print("Data loaded from JSON:", data)  # Debug: Cek data yang dimuat
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
            # Jika URL tidak valid, ambil gambar profil default
            default_image_url = str(ctx.author.avatar.url)
            async with aiohttp.ClientSession() as session:
                async with session.get(default_image_url) as resp:
                    return BytesIO(await resp.read())

    @commands.command(name="hangman", help="Mulai permainan Hangman.")
    async def hangman(self, ctx):
        # Pastikan pengguna berada di voice channel
        if ctx.author.voice is None:
            await ctx.send("Anda harus berada dalam ruangan suara untuk bermain Hangman.")
            return
        
        # Pastikan command dijalankan di teks channel yang sesuai
        if ctx.channel.id != ctx.author.voice.channel.id:
            await ctx.send("Command ini hanya dapat dijalankan di teks channel yang terkait dengan ruangan suara Anda.")
            return

        if ctx.author.id in self.active_games:
            await ctx.send("Anda sudah sedang bermain Hangman. Silakan tunggu hingga selesai.")
            return

        # Menyimpan skor untuk peserta yang ingin bermain
        self.scores[ctx.author.id] = {
            "score": 0,
            "correct": 0,
            "wrong": 0,
            "user": ctx.author
        }

        embed = discord.Embed(
            title="🎮 Cara Bermain Hangman",
            description=(
                "Selamat datang di Dunia Sunyi Hangman! 🖤🌧️\n\n"
                "Di sini, kamu tak hanya menebak kata... tapi juga menebak makna dari kesepian yang tak bertepi.\n"
                "Jawablah satu per satu, berharap RSWN bisa sedikit mengisi kekosongan itu.\n"
                "Selesaikan 10 soal dalam 3 menit... jika Anda masih memiliki semangat itu.\n\n"
                "✨ *Dev udah bikin fitur. Admin udah promosi. Tapi server tetap sepi...*\n\n"
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

            # Menentukan peserta yang ada di voice channel
            voice_members = [member for member in ctx.author.voice.channel.members if not member.bot]
            if len(voice_members) < 1:
                await ctx.send("Tidak ada peserta lain yang dapat bermain. Minimal 1 peserta diperlukan.")
                return
            
            self.active_games[ctx.author.id] = {
                "score": 0,
                "correct": 0,
                "wrong": 0,
                "current_question": 0,
                "time_limit": 180,  # 3 menit total untuk 10 soal
                "start_time": None,
                "questions": [],  # Menyimpan pertanyaan yang akan diacak
                "game_over": False,
                "answers": []
            }

            # Ambil 10 soal acak dari pertanyaan yang tersedia
            game_data = self.active_games[ctx.author.id]
            game_data["questions"] = random.sample(self.questions, 10)

            await ctx.send(f"{ctx.author.mention}, permainan Hangman dimulai! Anda memiliki 3 menit untuk menjawab 10 soal.")
            await self.play_game(ctx, voice_members)

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

    async def play_game(self, ctx, voice_members):
        game_data = self.active_games[ctx.author.id]
        game_data["start_time"] = asyncio.get_event_loop().time()

        # Cek apakah ada pertanyaan yang tersedia
        if not game_data["questions"]:
            await ctx.send("Tidak ada pertanyaan yang tersedia. Pastikan questions_hangman.json diisi dengan benar.")
            return

        print(f"Jumlah pertanyaan yang tersedia: {len(self.questions)}")  # Debug: jumlah pertanyaan

        for index, question in enumerate(game_data["questions"]):
            if game_data["game_over"]:
                break

            game_data["current_question"] = index + 1
            await self.ask_question(ctx, question, voice_members)

        if not game_data["game_over"]:
            await self.end_game(ctx)

    async def ask_question(self, ctx, question, voice_members):
        game_data = self.active_games[ctx.author.id]

        embed = discord.Embed(
            title=f"❓ Pertanyaan {game_data['current_question']}",
            description=(
                f"Kategori: **{question['category']}**\n"
                f"Kisi-kisi: {question['clue']} \n"
                f"Sebutkan satu kata: **{self.display_word(question['word'], game_data['answers'])}**\n"
                f"Waktu: **15 detik**"
            ),
            color=0x00ff00
        )
        
        question_message = await ctx.send(embed=embed)

        # Timer untuk 15 detik
        for remaining in range(15, 0, -1):
            embed.description = (
                f"Kategori: **{question['category']}**\n"
                f"Kisi-kisi: {question['clue']}\n"
                f"Sebutkan satu kata: **{self.display_word(question['word'], game_data['answers'])}**\n"
                f"Waktu: **{remaining} detik**"
            )
            await question_message.edit(embed=embed)
            await asyncio.sleep(1)

        # Cek jawaban setelah waktu habis
        if game_data["current_question"] == 10:
            await self.end_game(ctx)
            return

        participant_correct = False  # Menandakan apakah ada peserta yang menjawab benar
        for member in voice_members:
            if member.id in self.active_games:
                try:
                    user_answer = await self.bot.wait_for('message', timeout=15.0)
                    if user_answer.author == member and user_answer.channel == ctx.channel:
                        if user_answer.content.strip().lower() == question['word'].lower():
                            game_data["correct"] += 1
                            game_data["answers"].append(user_answer.content.strip().lower())  # Simpan jawaban yang benar
                            participant_correct = True
                            await ctx.send(f"✅ Jawaban Benar dari {member.display_name}!")
                            break  # Langsung lanjut ke soal berikutnya jika ada yang benar
                        else:
                            game_data["wrong"] += 1
                            await ctx.send(f"❌ Jawaban Salah dari {member.display_name}.")
                except asyncio.TimeoutError:
                    continue  # Jika waktu habis, abaikan dan lanjutkan

        # Jika tidak ada jawaban benar, soal akan berlanjut
        if not participant_correct:
            await ctx.send("Tidak ada jawaban benar, soal berlanjut.")

        # Lanjut ke pertanyaan berikutnya
        if game_data["current_question"] < 10:
            await self.ask_question(ctx, game_data["questions"][game_data["current_question"]], voice_members)
        else:
            await self.end_game(ctx)

    def display_word(self, word, guessed_letters):
        """Menampilkan kata dengan huruf yang sudah ditebak dan garis bawah untuk huruf yang belum ditebak."""
        displayed_word = ''.join([letter if letter in guessed_letters else '_' for letter in word])
        return displayed_word

    async def end_game(self, ctx):
        game_data = self.active_games.pop(ctx.author.id, None)
        if game_data:
            # Hitung saldo awal dan akhir
            initial_balance = self.bank_data.get(str(ctx.author.id), {}).get('balance', 0)
            earned_rsw = game_data['correct'] * 25  # RSWN yang diperoleh dari hasil kuis
            final_balance = initial_balance + earned_rsw + (50 if game_data['correct'] == 10 else 0)  # Bonus jika benar semua

            # Kartu hasil
            embed = discord.Embed(
                title="📝 Hasil Permainan Hangman",
                color=0x00ff00
            )
            embed.add_field(name="Nama", value=ctx.author.display_name)
            embed.add_field(name="Jawaban Benar", value=game_data['correct'])
            embed.add_field(name="Jawaban Salah", value=game_data['wrong'])
            embed.add_field(name="RSWN yang Diperoleh", value=earned_rsw)
            embed.add_field(name="Saldo RSWN Awal", value=initial_balance)
            embed.add_field(name="Saldo RSWN Akhir", value=final_balance)

            # Menyimpan skor untuk leaderboard
            self.scores[ctx.author.id]["score"] = final_balance
            self.scores[ctx.author.id]["correct"] = game_data['correct']
            self.scores[ctx.author.id]["wrong"] = game_data['wrong']

            # Mengambil gambar pengguna
            user_data = self.level_data.get(str(ctx.guild.id), {}).get(str(ctx.author.id), {})
            image_data = await self.get_user_image(ctx, user_data)

            # Mengirimkan kartu hasil dengan gambar pengguna
            await ctx.send(file=discord.File(image_data, "avatar.png"), embed=embed)

            # Menampilkan leaderboard jika ada 2 atau lebih peserta
            if len(self.scores) >= 2:
                await self.display_leaderboard(ctx)

    async def display_leaderboard(self, ctx):
        sorted_scores = sorted(self.scores.values(), key=lambda x: x["score"], reverse=True)
        embed = discord.Embed(title="🏆 Leaderboard Hangman", color=0x00ff00)

        # Hanya tampilkan juara 2-5
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
    await bot.add_cog(Hangman(bot))
