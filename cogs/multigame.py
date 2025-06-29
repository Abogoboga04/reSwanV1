import discord
from discord.ext import commands, tasks
import json
import random
import asyncio
import os
from datetime import datetime, time, timedelta

# Helper Functions to handle JSON data from the bot's root directory
def load_json_from_root(file_path):
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        full_path = os.path.join(base_dir, file_path)
        with open(full_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Peringatan Kritis: Gagal memuat atau file rusak -> {file_path}")
        # Mengembalikan struktur data kosong yang aman
        if 'perang_otak' in file_path:
            return {"questions": []}
        return []

def save_json_to_root(data, file_path):
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    full_path = os.path.join(base_dir, file_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

# --- TicTacToe Game View ---
class TicTacToeView(discord.ui.View):
    def __init__(self, game_cog, player1, player2):
        super().__init__(timeout=300)
        self.game_cog = game_cog
        self.player1 = player1
        self.player2 = player2
        self.current_player = player1
        self.board = [None] * 9
        self.winner = None
        for i in range(9):
            self.add_item(TicTacToeButton(row=i // 3))

    async def update_board(self, interaction: discord.Interaction):
        winning_combinations = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]
        for combo in winning_combinations:
            if self.board[combo[0]] is not None and self.board[combo[0]] == self.board[combo[1]] == self.board[combo[2]]:
                self.winner = self.current_player
                break
        is_draw = all(spot is not None for spot in self.board) and self.winner is None
        embed = interaction.message.embeds[0]
        if self.winner:
            embed.description = f"🎉 **{self.winner.mention} Menang!** 🎉"
            embed.color = discord.Color.gold()
            await self.game_cog.give_rewards_with_bonus_check(self.winner, interaction.guild.id, interaction.channel)
            for item in self.children: item.disabled = True
        elif is_draw:
            embed.description = "⚖️ **Permainan Berakhir Seri!**"
            embed.color = discord.Color.light_grey()
            for item in self.children: item.disabled = True
        else:
            self.current_player = self.player2 if self.current_player == self.player1 else self.player1
            embed.description = f"Giliran: **{self.current_player.mention}**"
        await interaction.message.edit(embed=embed, view=self)
        if self.winner or is_draw:
            self.stop()
            self.game_cog.end_game_cleanup(interaction.channel.id)

class TicTacToeButton(discord.ui.Button):
    def __init__(self, row: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", row=row)

    async def callback(self, interaction: discord.Interaction):
        view: TicTacToeView = self.view
        if interaction.user != view.current_player:
            return await interaction.response.send_message("Bukan giliranmu!", ephemeral=True)
        await interaction.response.defer()
        self.style = discord.ButtonStyle.danger if view.current_player == view.player1 else discord.ButtonStyle.success
        self.label = "X" if view.current_player == view.player1 else "O"
        self.disabled = True
        button_index = self.view.children.index(self)
        self.view.board[button_index] = self.label
        await view.update_board(interaction)

class UltimateGameArena(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = set()
        
        # --- PERBAIKAN: Cara memuat data diperbaiki agar aman dari error ---
        self.deskripsi_data = load_json_from_root('data/deskripsi_tebak.json')
        self.perang_otak_data = load_json_from_root('data/perang_otak.json').get('questions', [])
        self.cerita_pembuka_data = load_json_from_root('data/cerita_pembuka.json')
        self.tekateki_harian_data = load_json_from_root('data/teka_teki_harian.json')
        # ------------------------------------------------------------------

        self.reward = {"rsw": 50, "exp": 100}
        self.daily_puzzle = None
        self.daily_puzzle_solvers = set()
        self.daily_puzzle_channel_id = 765140300145360896 # GANTI
        self.post_daily_puzzle.start()

    def cog_unload(self):
        self.post_daily_puzzle.cancel()

    # --- FUNGSI INTEGRASI ---
    def get_anomaly_multiplier(self):
        dunia_cog = self.bot.get_cog('DuniaHidup')
        if dunia_cog and dunia_cog.active_anomaly and dunia_cog.active_anomaly.get('type') == 'exp_boost':
            return dunia_cog.active_anomaly.get('effect', {}).get('multiplier', 1)
        return 1

    async def give_rewards_with_bonus_check(self, user: discord.Member, guild_id: int, channel: discord.TextChannel):
        anomaly_multiplier = self.get_anomaly_multiplier()
        original_reward = self.reward.copy()
        self.reward = {
            "rsw": int(original_reward['rsw'] * anomaly_multiplier),
            "exp": int(original_reward['exp'] * anomaly_multiplier)
        }
        self.give_rewards(user, guild_id)
        self.reward = original_reward
        if anomaly_multiplier > 1 and channel:
            await channel.send(f"✨ **BONUS ANOMALI!** {user.mention} mendapatkan hadiah yang dilipatgandakan!", delete_after=15)
            
    # FUNGSI give_rewards ASLI ANDA (TIDAK DIUBAH)
    def give_rewards(self, user: discord.Member, guild_id: int):
        user_id_str, guild_id_str = str(user.id), str(guild_id)
        bank_data = load_json_from_root('data/bank_data.json')
        bank_data.setdefault(user_id_str, {'balance': 0, 'debt': 0})['balance'] += self.reward['rsw']
        save_json_to_root(bank_data, 'data/bank_data.json')
        level_data = load_json_from_root('data/level_data.json')
        guild_data = level_data.setdefault(guild_id_str, {})
        user_data = guild_data.setdefault(user_id_str, {'exp': 0, 'level': 1})
        user_data.setdefault('exp', 0)
        user_data['exp'] += self.reward['exp']
        save_json_to_root(level_data, 'data/level_data.json')
        
    async def start_game_check(self, ctx):
        if ctx.channel.id in self.active_games:
            await ctx.send("Maaf, sudah ada permainan lain di channel ini. Tunggu selesai ya!", delete_after=10)
            return False
        self.active_games.add(ctx.channel.id)
        return True

    def end_game_cleanup(self, channel_id):
        self.active_games.discard(channel_id)

    # --- SEMUA COMMAND GAME ADA DI SINI ---
    @commands.command(name="deskripsi", help="Mulai game Gartic Phone versi teks.")
    async def deskripsi(self, ctx):
        if not await self.start_game_check(ctx): return
        vc = ctx.author.voice.channel if ctx.author.voice else None
        if not vc or len(vc.members) < 2:
            self.end_game_cleanup(ctx.channel.id)
            return await ctx.send("Game ini butuh minimal 2 orang di voice channel yang sama.")

        players = [m for m in vc.members if not m.bot]
        if len(players) < 2:
            self.end_game_cleanup(ctx.channel.id)
            return await ctx.send("Kurang pemain nih, ajak temanmu!")
        if not self.deskripsi_data:
            self.end_game_cleanup(ctx.channel.id)
            return await ctx.send("Bank soal 'Deskripsi & Tebak' kosong.")

        deskriptor = random.choice(players)
        item = random.choice(self.deskripsi_data)
        word = item['word']

        try:
            await deskriptor.send(f"🤫 Kamu adalah **Deskriptor**! Kata rahasiamu adalah: **{word}**. Deskripsikan kata ini tanpa menyebutkannya langsung!")
        except discord.Forbidden:
            self.end_game_cleanup(ctx.channel.id)
            return await ctx.send(f"Gagal memulai karena tidak bisa mengirim DM ke {deskriptor.mention}. Pastikan DM-nya terbuka.")

        embed = discord.Embed(title="🎨 Deskripsikan & Tebak!", color=0x3498db)
        embed.description = f"{deskriptor.mention} telah menerima kata rahasia! Dia akan mendeskripsikannya sekarang. Yang lain, siap-siap menebak!"
        embed.set_footer(text="Penebak tercepat dan Deskriptor akan mendapat hadiah!")
        await ctx.send(embed=embed)

        def check(m):
            return m.channel == ctx.channel and not m.author.bot and m.author != deskriptor and m.content.lower() == word.lower()

        try:
            winner_msg = await self.bot.wait_for('message', timeout=180.0, check=check)
            winner = winner_msg.author
            
            await ctx.send(f"🎉 **Tepat Sekali!** {winner.mention} berhasil menebak **{word}**!")
            await self.give_rewards_with_bonus_check(winner, ctx.guild.id, ctx.channel)
            await self.give_rewards_with_bonus_check(deskriptor, ctx.guild.id, ctx.channel)
            await ctx.send(f"Selamat untuk {winner.mention} dan {deskriptor.mention}, kalian berdua mendapat hadiah!")
        except asyncio.TimeoutError:
            await ctx.send(f"Waktu habis! Jawaban yang benar adalah **{word}**.")
        self.end_game_cleanup(ctx.channel.id)

    @commands.command(name="perangotak", help="Mulai game Family Feud.")
    async def perangotak(self, ctx):
        if not await self.start_game_check(ctx): return
        if not self.perang_otak_data:
             self.end_game_cleanup(ctx.channel.id)
             return await ctx.send("Bank soal 'Perang Otak' kosong.")
        await ctx.send("Fitur **Perang Otak** sedang dalam pengembangan! Nantikan update selanjutnya. 🙏")
        self.end_game_cleanup(ctx.channel.id)

    @commands.command(name="cerita", help="Mulai game membuat cerita bersama.")
    async def cerita(self, ctx):
        if not await self.start_game_check(ctx): return
        vc = ctx.author.voice.channel if ctx.author.voice else None
        if not vc or len(vc.members) < 2:
            self.end_game_cleanup(ctx.channel.id)
            return await ctx.send("Ayo kumpul di voice channel dulu (minimal 2 orang) buat bikin cerita!")

        players = [m for m in vc.members if not m.bot]
        random.shuffle(players)
        if not self.cerita_pembuka_data:
            self.end_game_cleanup(ctx.channel.id)
            return await ctx.send("Bank kalimat pembuka kosong.")
            
        story = [random.choice(self.cerita_pembuka_data)]
        
        embed = discord.Embed(title="✍️ Mari Membuat Cerita!", color=0x2ecc71)
        embed.description = f"**Kalimat Pembuka:**\n> {story[0]}"
        embed.set_footer(text="Setiap orang mendapat giliran untuk menambahkan satu kalimat.")
        await ctx.send(embed=embed)
        await asyncio.sleep(3)

        for i, player in enumerate(players):
            await ctx.send(f"Giliran {player.mention}, lanjutkan ceritanya! (Waktu 30 detik)")
            def check(m): return m.author == player and m.channel == ctx.channel
            try:
                msg = await self.bot.wait_for('message', timeout=30.0, check=check)
                story.append(msg.content)
                await msg.add_reaction("✅")
            except asyncio.TimeoutError:
                story.append(f"({player.display_name} terdiam kebingungan...)")
        
        final_story = " ".join(story)
        final_embed = discord.Embed(title="📜 Inilah Cerita Kita!", description=f"> {final_story}", color=0x2ecc71)
        await ctx.send(embed=final_embed)
        await ctx.send("Kisah yang unik! Semua yang berpartisipasi mendapat hadiah!")
        for p in players:
            await self.give_rewards_with_bonus_check(p, ctx.guild.id, ctx.channel)
        
        self.end_game_cleanup(ctx.channel.id)
        
    @commands.command(name="tictactoe", help="Tantang temanmu bermain Tic-Tac-Toe.")
    async def tictactoe(self, ctx, opponent: discord.Member):
        if opponent.bot or opponent == ctx.author:
            return await ctx.send("Kamu tidak bisa bermain melawan bot atau dirimu sendiri.")
        if not await self.start_game_check(ctx): return
        
        view = TicTacToeView(self, ctx.author, opponent)
        embed = discord.Embed(title="⚔️ Tic-Tac-Toe ⚔️", description=f"Giliran: **{ctx.author.mention}**", color=discord.Color.blue())
        embed.add_field(name=f"Player 1 (X)", value=ctx.author.mention, inline=True)
        embed.add_field(name=f"Player 2 (O)", value=opponent.mention, inline=True)
        await ctx.send(content=f"{opponent.mention}, kamu ditantang oleh {ctx.author.mention}!", embed=embed, view=view)

    # --- GAME TEKA-TEKI HARIAN ---
    @tasks.loop(time=time(hour=5, minute=0, tzinfo=None))
    async def post_daily_puzzle(self):
        await self.bot.wait_until_ready()
        if not self.tekateki_harian_data: return
        
        self.daily_puzzle = random.choice(self.tekateki_harian_data)
        self.daily_puzzle_solvers.clear()
        
        channel = self.bot.get_channel(self.daily_puzzle_channel_id)
        if channel:
            embed = discord.Embed(title="🤔 Teka-Teki Harian!", description=f"**Teka-teki untuk hari ini:**\n\n> {self.daily_puzzle['riddle']}", color=0x99aab5)
            embed.set_footer(text="Gunakan !jawab <jawabanmu> untuk menebak!")
            await channel.send(embed=embed)

    @post_daily_puzzle.before_loop
    async def before_daily_puzzle(self):
        await self.bot.wait_until_ready()

    @commands.command(name="jawab", help="Jawab teka-teki harian.")
    async def jawab(self, ctx, *, answer: str):
        if not self.daily_puzzle:
            return await ctx.send("Belum ada teka-teki untuk hari ini. Sabar ya!")
        if ctx.author.id in self.daily_puzzle_solvers:
            return await ctx.send("Kamu sudah menjawab dengan benar hari ini!", ephemeral=True)
            
        if answer.lower() == self.daily_puzzle['answer'].lower():
            self.daily_puzzle_solvers.add(ctx.author.id)
            await self.give_rewards_with_bonus_check(ctx.author, ctx.guild.id, ctx.channel)
            await ctx.message.add_reaction("✅")
            await ctx.send(f"🎉 Selamat {ctx.author.mention}! Jawabanmu benar!")
        else:
            await ctx.message.add_reaction("❌")

    # --- GAME TARUHAN BALAP KUDA ---
    @commands.command(name="balapankuda", help="Mulai taruhan balap kuda.")
    async def balapankuda(self, ctx):
        if not await self.start_game_check(ctx): return
        
        horses = {"merah": "🐴", "biru": "🦄", "emas": "🦓", "hijau": "🐎"}
        
        embed = discord.Embed(title="🏇 Taruhan Balap Kuda Dimulai!", color=0xf1c40f)
        embed.description = "Pasang taruhanmu pada kuda jagoanmu! Waktu taruhan: **60 detik**."
        horse_list = "\n".join([f"{emoji} **Kuda {name.capitalize()}**" for name, emoji in horses.items()])
        embed.add_field(name="Daftar Kuda", value=horse_list)
        embed.set_footer(text="Gunakan !taruhan <jumlah> <warna_kuda>")
        await ctx.send(embed=embed)
        
        bets, bank_data = {}, load_json_from_root('data/bank_data.json')
        
        def check(m):
            return m.channel == ctx.channel and m.content.lower().startswith('!taruhan')

        try:
            while True:
                msg = await self.bot.wait_for('message', timeout=60.0, check=check)
                parts = msg.content.split()
                if len(parts) == 3 and parts[1].isdigit() and parts[2].lower() in horses:
                    amount = int(parts[1])
                    if bank_data.get(str(msg.author.id), {}).get('balance', 0) >= amount > 0:
                        bets[msg.author.id] = {'amount': amount, 'horse': parts[2].lower()}
                        await msg.add_reaction("👍")
                    else:
                        await msg.add_reaction("👎")
        except asyncio.TimeoutError:
            pass

        if not bets:
            await ctx.send("Tidak ada yang bertaruh. Balapan dibatalkan.")
            self.end_game_cleanup(ctx.channel.id)
            return

        for user_id, bet in bets.items():
            bank_data.setdefault(str(user_id), {'balance': 0})['balance'] -= bet['amount']
        save_json_to_root(bank_data, 'data/bank_data.json')

        await ctx.send("--- TARUHAN DITUTUP! BALAPAN DIMULAI! ---")
        
        race_embed = discord.Embed(title="🏇 LINTASAN BALAP", color=0x2ecc71)
        progress = {name: 0 for name in horses}
        for name, emoji in horses.items():
            race_embed.add_field(name=f"{emoji} Kuda {name.capitalize()}", value="🏁" + "─" * 20, inline=False)
        race_msg = await ctx.send(embed=race_embed)
        
        winner = None
        for lap in range(10):
            await asyncio.sleep(2)
            for name in progress:
                progress[name] += random.randint(1, 3)
                if progress[name] >= 20 and not winner: winner = name
            
            new_embed = discord.Embed(title=f"🏇 LINTASAN BALAP - Putaran {lap+1}/10", color=0x2ecc71)
            for name, emoji in horses.items():
                p = min(progress[name], 20)
                track = "─" * p + emoji + "─" * (20 - p)
                new_embed.add_field(name=f"Kuda {name.capitalize()}", value=f"🏁{track}🏁", inline=False)
            await race_msg.edit(embed=new_embed)
            if winner: break
        
        if not winner: winner = max(progress, key=progress.get)

        await ctx.send(f"--- BALAPAN SELESAI! --- \n\n🏆 **Kuda {winner.capitalize()}** adalah pemenangnya!")
        
        winners_list = []
        anomaly_multiplier = self.get_anomaly_multiplier()
        
        bank_data = load_json_from_root('data/bank_data.json')
        for user_id, bet in bets.items():
            if bet['horse'] == winner:
                user = ctx.guild.get_member(user_id)
                if user:
                    payout = int(bet['amount'] * 2 * anomaly_multiplier)
                    bank_data[str(user_id)]['balance'] += payout
                    winners_list.append(f"{user.mention} menang **{payout:,} RSWN**!")
        save_json_to_root(bank_data, 'data/bank_data.json')
        
        if winners_list:
            if anomaly_multiplier > 1: await ctx.send("✨ **BONUS ANOMALI!** Semua hadiah pemenang dilipatgandakan!")
            await ctx.send("\n".join(winners_list))
        else:
            await ctx.send("Sayang sekali, tidak ada yang bertaruh pada kuda pemenang.")

        self.end_game_cleanup(ctx.channel.id)

async def setup(bot):
    await bot.add_cog(UltimateGameArena(bot))

