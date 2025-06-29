import discord
from discord.ext import commands, tasks
import json
import random
import asyncio
import os
from datetime import datetime, time

# Helper Functions to handle JSON data from the bot's root directory
def load_json_from_root(file_path):
    """Memuat data JSON dari direktori utama bot dengan aman."""
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        full_path = os.path.join(base_dir, file_path)
        with open(full_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Peringatan Kritis: Gagal memuat '{file_path}'. Error: {e}")
        # Mengembalikan struktur data kosong yang sesuai untuk menghindari error
        if any(name in file_path for name in ['bank_data', 'level_data']):
            return {}
        return []

def save_json_to_root(data, file_path):
    """Menyimpan data ke file JSON di direktori utama bot."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    full_path = os.path.join(base_dir, file_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

class GameLanjutan(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Game State Management
        self.active_scramble_games = {}
        self.active_sambung_games = {}
        
        # Load Data
        self.scramble_questions = load_json_from_root('data/questions_hangman.json')
        self.sambung_kata_words = load_json_from_root('data/sambung_kata_words.json')

        # Game Configuration
        self.game_channel_id = 765140300145360896 # ID channel yang diizinkan
        self.scramble_reward = {"rsw": 50, "exp": 100}
        self.sambung_kata_winner_reward = {"rsw": 50, "exp": 100}
        self.scramble_time_limit = 30 # Detik per soal acak kata
        self.sambung_kata_time_limit = 20 # Detik per giliran sambung kata

    # --- FUNGSI INTEGRASI & PEMBERIAN HADIAH ---
    def get_anomaly_multiplier(self):
        """Mengecek apakah ada anomali EXP boost aktif dari cog DuniaHidup."""
        dunia_cog = self.bot.get_cog('DuniaHidup')
        if dunia_cog and dunia_cog.active_anomaly and dunia_cog.active_anomaly.get('type') == 'exp_boost':
            return dunia_cog.active_anomaly.get('effect', {}).get('multiplier', 1)
        return 1

    async def give_rewards_with_bonus_check(self, user: discord.Member, reward_base: dict, channel: discord.TextChannel):
        """Fungsi baru yang menghitung bonus dan memberikan hadiah."""
        anomaly_multiplier = self.get_anomaly_multiplier()
        
        final_reward = {
            "rsw": int(reward_base['rsw'] * anomaly_multiplier),
            "exp": int(reward_base['exp'] * anomaly_multiplier)
        }
        
        # Logika give_rewards disatukan di sini agar lebih efisien
        user_id_str, guild_id_str = str(user.id), str(user.guild.id)
        bank_data = load_json_from_root('data/bank_data.json')
        level_data = load_json_from_root('data/level_data.json')

        bank_data.setdefault(user_id_str, {'balance': 0, 'debt': 0})['balance'] += final_reward.get('rsw', 0)
        
        guild_data = level_data.setdefault(guild_id_str, {})
        user_data = guild_data.setdefault(user_id_str, {'exp': 0, 'level': 1})
        user_data.setdefault('exp', 0)
        user_data['exp'] += final_reward.get('exp', 0)

        save_json_to_root(bank_data, 'data/bank_data.json')
        save_json_to_root(level_data, 'data/level_data.json')
        
        if anomaly_multiplier > 1 and channel:
            await channel.send(f"✨ **BONUS ANOMALI!** {user.mention} mendapatkan hadiah yang dilipatgandakan!", delete_after=15)

    # --- GAME 1: TEBAK KATA ACAK (WORD SCRAMBLE) ---
    @commands.command(name="resacak", help="Mulai permainan Tebak Kata Acak.")
    async def resacak(self, ctx):
        if ctx.channel.id != self.game_channel_id:
            return await ctx.send("Permainan ini hanya bisa dimainkan di channel yang ditentukan.", delete_after=10)
        if ctx.channel.id in self.active_scramble_games:
            return await ctx.send("Permainan Tebak Kata Acak sudah berlangsung. Mohon tunggu hingga selesai.", delete_after=10)
        
        embed = discord.Embed(title="🎲 Siap Bermain Tebak Kata Acak?", color=0x3498db)
        embed.description = (
            "Uji kecepatan berpikir dan kosakatamu dalam game seru ini!\n\n"
            "**Aturan Main:**\n"
            "1. Bot akan memberikan kata yang hurufnya diacak.\n"
            "2. Tebak kata aslinya secepat mungkin.\n"
            f"3. Jawaban benar pertama mendapat **{self.scramble_reward['rsw']} RSWN** & **{self.scramble_reward['exp']} EXP**.\n"
            "4. Permainan terdiri dari 10 ronde.\n\n"
            "Klik tombol di bawah untuk memulai petualangan katamu!"
        )
        embed.set_thumbnail(url="https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/AB6.jpeg")
        embed.set_footer(text="Hanya pemanggil perintah yang bisa memulai permainan.")
        
        view = discord.ui.View(timeout=60)
        start_button = discord.ui.Button(label="MULAI SEKARANG", style=discord.ButtonStyle.primary, emoji="▶️")

        async def start_callback(interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message("Hanya pemanggil perintah yang bisa memulai permainan.", ephemeral=True)
            
            self.active_scramble_games[ctx.channel.id] = True
            await interaction.message.delete()
            await ctx.send(f"**Permainan Tebak Kata Acak Dimulai!** Diselenggarakan oleh {ctx.author.mention}", delete_after=10)
            await self.play_scramble_game(ctx)
            
        start_button.callback = start_callback
        view.add_item(start_button)
        await ctx.send(embed=embed, view=view)

    async def play_scramble_game(self, ctx):
        if not self.scramble_questions or len(self.scramble_questions) < 10:
            await ctx.send("Maaf, bank soal Tebak Kata Acak tidak ditemukan atau tidak cukup.")
            self.active_scramble_games.pop(ctx.channel.id, None)
            return
            
        questions = random.sample(self.scramble_questions, 10)
        leaderboard = {}

        for i, question_data in enumerate(questions):
            word = question_data['word']
            clue = question_data['clue']
            scrambled_word = "".join(random.sample(word, len(word)))

            embed = discord.Embed(title=f"📝 Soal #{i+1}", color=0x2ecc71)
            embed.add_field(name="Kata Teracak", value=f"## `{scrambled_word.upper()}`", inline=False)
            embed.add_field(name="Petunjuk", value=f"_{clue}_", inline=False)
            
            question_msg = await ctx.send(embed=embed)
            winner = await self.wait_for_answer_with_timer(ctx, word, question_msg, self.scramble_time_limit)

            if winner:
                await self.give_rewards_with_bonus_check(winner, self.scramble_reward, ctx.channel)
                await ctx.send(f"🎉 Selamat {winner.mention}! Jawabanmu benar!")
                leaderboard[winner.display_name] = leaderboard.get(winner.display_name, 0) + 1
            else: 
                await ctx.send(f"Waktu habis! Jawaban yang benar adalah: **{word}**.")

        await ctx.send("🏁 Permainan Tebak Kata Acak selesai! Terima kasih sudah bermain.")
        if leaderboard:
            sorted_lb = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
            desc = "\n".join([f"**#{n}.** {user}: {score} poin" for n, (user, score) in enumerate(sorted_lb, 1)])
            final_embed = discord.Embed(title="🏆 Papan Skor Akhir", description=desc, color=discord.Color.gold())
            await ctx.send(embed=final_embed)

        self.active_scramble_games.pop(ctx.channel.id, None)

    # --- GAME 2: SAMBUNG KATA ---
    @commands.command(name="ressambung", help="Mulai permainan Sambung Kata di Voice Channel.")
    async def ressambung(self, ctx):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("Kamu harus berada di dalam voice channel untuk memulai game ini.", delete_after=10)
        vc = ctx.author.voice.channel
        if vc.id in self.active_sambung_games:
            return await ctx.send(f"Sudah ada permainan Sambung Kata yang berlangsung di voice channel ini.", delete_after=10)

        members = [m for m in vc.members if not m.bot]
        if len(members) < 2:
            return await ctx.send("Permainan ini membutuhkan minimal 2 orang di dalam voice channel.", delete_after=10)

        game_state = {
            "players": {p.id: p for p in members}, "turn_index": 0, "current_word": "",
            "used_words": set(), "channel": ctx.channel, "guild_id": ctx.guild.id
        }
        self.active_sambung_games[vc.id] = game_state
        
        player_mentions = ", ".join([p.mention for p in game_state["players"].values()])
        embed = discord.Embed(title="🔗 Siap Bermain Sambung Kata?", color=0xe91e63)
        embed.description = (
            "Uji kosakatamu dan bertahanlah sampai akhir!\n\n"
            "**Aturan Main:**\n"
            "1. Pemain bergiliran menyambung kata berdasarkan **2 huruf terakhir**.\n"
            "2. Waktu menjawab **20 detik** per giliran.\n"
            "3. Pemain yang gagal atau salah kata akan tereliminasi.\n"
            f"4. Pemenang terakhir mendapat **{self.sambung_kata_winner_reward['rsw']} RSWN** & **{self.sambung_kata_winner_reward['exp']} EXP**.\n"
        )
        embed.add_field(name="👥 Pemain Bergabung", value=player_mentions)
        embed.set_thumbnail(url="https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/AB5.jpeg")
        
        await ctx.send(embed=embed)
        await asyncio.sleep(5)
        await self.play_sambung_kata_game(vc.id)

    async def play_sambung_kata_game(self, vc_id):
        game = self.active_sambung_games.get(vc_id)
        if not game: return

        player_ids = list(game["players"].keys())
        random.shuffle(player_ids)
        
        if not self.sambung_kata_words:
            await game["channel"].send("Bank kata untuk memulai tidak ditemukan.")
            self.active_sambung_games.pop(vc_id, None)
            return

        game["current_word"] = random.choice(self.sambung_kata_words).lower()
        game["used_words"].add(game["current_word"])
        
        await game["channel"].send(f"Kata pertama dari bot adalah: **{game['current_word'].upper()}**")

        while len(player_ids) > 1:
            current_player_id = player_ids[game["turn_index"]]
            current_player = game["players"][current_player_id]
            prefix = game["current_word"][-2:].lower()
            
            embed = discord.Embed(title=f"Giliran {current_player.display_name}!", description=f"Sebutkan kata yang diawali dengan **`{prefix.upper()}`**", color=current_player.color)
            prompt_msg = await game["channel"].send(embed=embed)

            try:
                async def timer_task():
                    for i in range(self.sambung_kata_time_limit, -1, -1):
                        new_embed = embed.copy()
                        new_embed.set_footer(text=f"Waktu tersisa: {i} detik ⏳")
                        try: await prompt_msg.edit(embed=new_embed)
                        except discord.NotFound: break
                        await asyncio.sleep(1)
                
                def check(m): return m.author.id == current_player_id and m.channel == game["channel"]
                
                wait_for_msg = self.bot.loop.create_task(self.bot.wait_for('message', check=check))
                timer = self.bot.loop.create_task(timer_task())
                done, pending = await asyncio.wait([wait_for_msg, timer], return_when=asyncio.FIRST_COMPLETED)
                timer.cancel()
                for task in pending: task.cancel()
                
                if wait_for_msg in done:
                    msg = wait_for_msg.result()
                    new_word = msg.content.strip().lower()
                    if not new_word.startswith(prefix):
                        await game["channel"].send(f"❌ Salah! {current_player.mention} tereliminasi!")
                        player_ids.pop(game["turn_index"])
                    elif new_word in game["used_words"]:
                        await game["channel"].send(f"❌ Kata sudah digunakan! {current_player.mention} tereliminasi!")
                        player_ids.pop(game["turn_index"])
                    else:
                        await msg.add_reaction("✅")
                        game["current_word"], game["used_words"] = new_word, game["used_words"] | {new_word}
                        game["turn_index"] = (game["turn_index"] + 1) % len(player_ids)
                else: raise asyncio.TimeoutError

            except asyncio.TimeoutError:
                await game["channel"].send(f"⌛ Waktu habis! {current_player.mention} tereliminasi!")
                player_ids.pop(game["turn_index"])
            
            if len(player_ids) > 0 and game["turn_index"] >= len(player_ids):
                game["turn_index"] = 0
            await asyncio.sleep(2)

        if len(player_ids) == 1:
            winner = game["players"][player_ids[0]]
            is_bonus = await self.give_rewards_with_bonus_check(winner, self.sambung_kata_winner_reward, game["channel"])
            if is_bonus:
                await game["channel"].send(f"🏆 Pemenangnya adalah {winner.mention}! Karena ada Anomali, hadiahmu dilipatgandakan!")
            else:
                await game["channel"].send(f"🏆 Pemenangnya adalah {winner.mention}! Kamu mendapatkan hadiah!")
        else:
            await game["channel"].send("Permainan berakhir tanpa pemenang.")
        self.active_sambung_games.pop(vc_id, None)
    
    # --- HELPER FUNCTION FOR TIMER ---
    async def wait_for_answer_with_timer(self, ctx, correct_answer, question_msg, time_limit):
        async def timer_task():
            for i in range(time_limit, -1, -1):
                new_embed = question_msg.embeds[0].copy()
                new_embed.set_footer(text=f"Waktu tersisa: {i} detik ⏳")
                try: await question_msg.edit(embed=new_embed)
                except discord.NotFound: break
                await asyncio.sleep(1)

        def check(m): return m.channel == ctx.channel and not m.author.bot and m.content.lower() == correct_answer.lower()

        wait_for_msg_task = self.bot.loop.create_task(self.bot.wait_for('message', check=check))
        timer = self.bot.loop.create_task(timer_task())
        done, pending = await asyncio.wait([wait_for_msg_task, timer], return_when=asyncio.FIRST_COMPLETED)
        timer.cancel()
        for task in pending: task.cancel()
        if wait_for_msg_task in done: return wait_for_msg_task.result().author
        else: return None

async def setup(bot):
    await bot.add_cog(GameLanjutan(bot))
