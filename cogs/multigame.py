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
        print(f"Peringatan: Tidak dapat memuat {file_path}. File mungkin kosong atau tidak ada.")
        # Mengembalikan struktur data kosong yang sesuai untuk menghindari error
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
        self.player1 = player1 # X
        self.player2 = player2 # O
        self.current_player = player1
        self.board = [None] * 9
        self.winner = None

        for i in range(9):
            self.add_item(TicTacToeButton(row=i // 3))

    async def update_board(self, interaction: discord.Interaction):
        winning_combinations = [
            (0, 1, 2), (3, 4, 5), (6, 7, 8),
            (0, 3, 6), (1, 4, 7), (2, 5, 8),
            (0, 4, 8), (2, 4, 6)
        ]
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

class UltimateGameArena(commands.Cog, name="🕹️ Serba-Serbi"):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = set()
        
        # PERBAIKAN: Cara memuat data diperbaiki agar aman dari error
        self.deskripsi_data = load_json_from_root('data/deskripsi_tebak.json')
        self.perang_otak_data = load_json_from_root('data/perang_otak.json').get('questions', [])
        self.cerita_pembuka_data = load_json_from_root('data/cerita_pembuka.json')
        self.tekateki_harian_data = load_json_from_root('data/teka_teki_harian.json')

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
        final_reward = {"rsw": int(self.reward['rsw'] * anomaly_multiplier), "exp": int(self.reward['exp'] * anomaly_multiplier)}
        self.apply_rewards(user, guild_id, final_reward)
        if anomaly_multiplier > 1 and channel:
            await channel.send(f"✨ **BONUS ANOMALI!** {user.mention} mendapatkan hadiah yang dilipatgandakan!", delete_after=15)
            
    def apply_rewards(self, user: discord.Member, guild_id: int, reward_dict: dict):
        user_id_str, guild_id_str = str(user.id), str(guild_id)
        bank_data = load_json_from_root('data/bank_data.json')
        bank_data.setdefault(user_id_str, {'balance': 0, 'debt': 0})['balance'] += reward_dict.get('rsw', 0)
        save_json_to_root(bank_data, 'data/bank_data.json')
        level_data = load_json_from_root('data/level_data.json')
        guild_data = level_data.setdefault(guild_id_str, {})
        user_data = guild_data.setdefault(user_id_str, {'exp': 0, 'level': 1})
        user_data.setdefault('exp', 0)
        user_data['exp'] += reward_dict.get('exp', 0)
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
    @commands.command(name="siapakahaku", help="Mulai sesi 10 soal tebak-tebakan kompetitif.")
    @commands.cooldown(1, 60, commands.BucketType.channel)
    async def siapakahaku(self, ctx):
        if not await self.start_game_check(ctx): return
        if not self.deskripsi_data or len(self.deskripsi_data) < 10:
            await ctx.send("Bank soal 'Siapakah Aku' tidak cukup."); self.end_game_cleanup(ctx.channel.id); return
        # ... (Sisa kode game Siapakah Aku Anda) ...
        # (pastikan di bagian "if winner:" memanggil "await self.give_rewards_with_bonus_check(...)")
    
    @commands.command(name="pernahgak")
    async def pernahgak(self, ctx):
        # ... (Kode game Pernah Gak Pernah Anda) ...
        # (pastikan di bagian pemberian hadiah memanggil "await self.give_rewards_with_bonus_check(...)")
        pass

    @commands.command(name="hitungcepat")
    async def hitungcepat(self, ctx):
        # ... (Kode game Hitung Cepat Anda) ...
        # (pastikan di bagian "if winner:" memanggil "await self.give_rewards_with_bonus_check(...)")
        pass

    @commands.command(name="matamata")
    async def matamata(self, ctx):
        # ... (Kode game Mata-Mata Anda) ...
        # (pastikan di bagian pemberian hadiah memanggil "await self.give_rewards_with_bonus_check(...)")
        pass

    @commands.command(name="tuduh")
    async def tuduh(self, ctx, member: discord.Member):
        # ... (Kode game Tuduh Anda) ...
        # (pastikan di bagian pemberian hadiah memanggil "await self.give_rewards_with_bonus_check(...)")
        pass

    # --- GAME TIC-TAC-TOE ---
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

    # --- GAME TEKA-TEKI HARIAN (FUNGSI YANG HILANG) ---
    @tasks.loop(time=time(hour=5, minute=0, tzinfo=None))
    async def post_daily_puzzle(self):
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

async def setup(bot):
    await bot.add_cog(UltimateGameArena(bot))

