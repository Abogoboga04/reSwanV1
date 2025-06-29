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
        if 'users' in file_path or 'inventory' in file_path:
            return {}
        elif any(name in file_path for name in ['perang_otak']):
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
            # --- PERUBAHAN INTEGRASI: Memanggil fungsi reward baru ---
            await self.game_cog.give_rewards_with_bonus_check(self.winner, interaction.guild.id, interaction.channel)
            # --------------------------------------------------------
            for item in self.children:
                item.disabled = True
        elif is_draw:
            embed.description = "⚖️ **Permainan Berakhir Seri!**"
            embed.color = discord.Color.light_grey()
            for item in self.children:
                item.disabled = True
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

    # --- PENAMBAHAN INTEGRASI: Fungsi "Mata-mata" dan Pemberian Hadiah ---
    def get_anomaly_multiplier(self):
        """Mengecek apakah ada anomali EXP boost aktif dari cog DuniaHidup."""
        dunia_cog = self.bot.get_cog('DuniaHidup')
        if dunia_cog and dunia_cog.active_anomaly and dunia_cog.active_anomaly.get('type') == 'exp_boost':
            return dunia_cog.active_anomaly.get('effect', {}).get('multiplier', 1)
        return 1

    async def give_rewards_with_bonus_check(self, user: discord.Member, guild_id: int, channel: discord.TextChannel):
        """Fungsi baru yang menghitung bonus dan memanggil fungsi give_rewards asli."""
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
    # ----------------------------------------------------------------------

    # FUNGSI give_rewards ASLI ANDA (TIDAK DIUBAH)
    def give_rewards(self, user: discord.Member, guild_id: int):
        user_id_str, guild_id_str = str(user.id), str(guild_id)
        
        bank_data = load_json_from_root('data/bank_data.json')
        if user_id_str not in bank_data: bank_data[user_id_str] = {'balance': 0, 'debt': 0}
        bank_data[user_id_str]['balance'] += self.reward['rsw']
        save_json_to_root(bank_data, 'data/bank_data.json')
        
        level_data = load_json_from_root('data/level_data.json')
        guild_data = level_data.setdefault(guild_id_str, {})
        user_data = guild_data.setdefault(user_id_str, {'exp': 0, 'level': 1})
        if 'exp' not in user_data: user_data['exp'] = 0
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

    # --- SEMUA COMMAND GAME ---
    @commands.command(name="siapakahaku", help="Mulai sesi 10 soal tebak-tebakan kompetitif.")
    @commands.cooldown(1, 60, commands.BucketType.channel)
    async def siapakahaku(self, ctx):
        if not await self.start_game_check(ctx): return
        
        if not ctx.guild.me.guild_permissions.moderate_members:
            await ctx.send("⚠️ **Peringatan Izin:** Saya tidak memiliki izin `Moderate Members` untuk memberikan timeout jika ada yang spam jawaban.")
        
        if not self.siapakah_aku_data or len(self.siapakah_aku_data) < 10:
            await ctx.send("Tidak cukup soal di database untuk memulai sesi (butuh minimal 10).")
            self.end_game_cleanup(ctx.channel.id)
            return
            
        questions = random.sample(self.siapakah_aku_data, 10)
        leaderboard = {}
        
        await ctx.send(embed=discord.Embed(title="🕵️‍♂️ Sesi Kuis 'Siapakah Aku?' Dimulai!", description="Akan ada **10 soal** berturut-turut. Petunjuk akan muncul setiap **10 detik**.", color=0x1abc9c))
        await asyncio.sleep(5)

        for i, item in enumerate(questions):
            word, clues, winner, round_over = item['name'].lower(), item['clues'], None, False
            attempts, timed_out_users = {}, set()

            embed = discord.Embed(title=f"SOAL #{i+1} dari 10", description=f"Kategori: **{item['category']}**", color=0x1abc9c)
            embed.set_footer(text="Anda punya 5x kesempatan menjawab salah per soal!")
            msg = await ctx.send(embed=embed)

            for clue_index, clue in enumerate(clues):
                if round_over: break
                embed.add_field(name=f"Petunjuk #{clue_index + 1}", value=f"_{clue}_", inline=False)
                await msg.edit(embed=embed)
                try:
                    async def listen_for_answer():
                        nonlocal winner, round_over
                        while True:
                            message = await self.bot.wait_for("message", check=lambda m: m.channel == ctx.channel and not m.author.bot)
                            if message.author.id in timed_out_users: continue
                            if message.content.lower() == word:
                                winner, round_over = message.author, True
                                return
                            else:
                                await message.add_reaction("❌")
                                attempts[message.author.id] = attempts.get(message.author.id, 0) + 1
                                if attempts[message.author.id] >= 5:
                                    timed_out_users.add(message.author.id)
                                    try:
                                        await message.author.timeout(timedelta(seconds=60), reason="Melebihi batas percobaan di game")
                                        await ctx.send(f"🚨 {message.author.mention}, Anda kehabisan kesempatan & di-timeout sementara.", delete_after=10)
                                    except discord.Forbidden:
                                        await ctx.send(f"🚨 {message.author.mention}, Anda kehabisan kesempatan di ronde ini.", delete_after=10)
                    await asyncio.wait_for(listen_for_answer(), timeout=10.0)
                except asyncio.TimeoutError:
                    if clue_index == len(clues) - 1: await ctx.send(f"Waktu habis! Jawaban yang benar adalah **{item['name']}**.")
                    else: continue

            if winner:
                await self.give_rewards_with_bonus_check(winner, ctx.guild.id, ctx.channel)
                await ctx.send(f"🎉 **Benar!** {winner.mention} berhasil menebak **{item['name']}**!")
                leaderboard[winner.display_name] = leaderboard.get(winner.display_name, 0) + 1

            for user_id in timed_out_users:
                member = ctx.guild.get_member(user_id)
                if member:
                    try: await member.timeout(None, reason="Ronde game telah berakhir.")
                    except discord.Forbidden: pass

            if i < len(questions) - 1:
                await ctx.send("Soal berikutnya dalam **5 detik**...", delete_after=4.5)
                await asyncio.sleep(5)
        
        if leaderboard:
            sorted_leaderboard = sorted(leaderboard.items(), key=lambda item: item[1], reverse=True)
            leaderboard_text = "\n".join([f"#{rank}. {name}: **{score}** poin" for rank, (name, score) in enumerate(sorted_leaderboard, 1)])
            await ctx.send(embed=discord.Embed(title="🏆 Papan Skor Akhir 'Siapakah Aku?'", description=leaderboard_text, color=0xffd700))
        else:
            await ctx.send("Sesi game berakhir tanpa ada pemenang.")
            
        self.end_game_cleanup(ctx.channel.id)
        
    @commands.command(name="pernahgak")
    async def pernahgak(self, ctx):
        if not await self.start_game_check(ctx): return
        if not ctx.author.voice or not ctx.author.voice.channel:
            self.end_game_cleanup(ctx.channel.id)
            return await ctx.send("Kamu harus berada di voice channel untuk memulai game ini.", delete_after=10)
        
        vc = ctx.author.voice.channel
        members = [m for m in vc.members if not m.bot]
        if len(members) < 2:
            self.end_game_cleanup(ctx.channel.id)
            return await ctx.send("Game ini butuh minimal 2 orang di voice channel.", delete_after=10)
        
        statement = random.choice(self.pernah_gak_pernah_data)
        embed = discord.Embed(title="🤔 Pernah Gak Pernah...", description=f"## _{statement}_", color=0xf1c40f)
        embed.set_footer(text="Jawab dengan jujur menggunakan reaksi di bawah! Semua peserta dapat hadiah.")
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("✅"); await msg.add_reaction("❌")
        await asyncio.sleep(20)
        try:
            cached_msg = await ctx.channel.fetch_message(msg.id)
            pernah_count, gak_pernah_count, rewarded_users = 0, 0, set()
            for reaction in cached_msg.reactions:
                if str(reaction.emoji) in ["✅", "❌"]:
                    if str(reaction.emoji) == "✅": pernah_count = reaction.count - 1
                    if str(reaction.emoji) == "❌": gak_pernah_count = reaction.count - 1
                    async for user in reaction.users():
                        if not user.bot and user.id not in rewarded_users:
                            await self.give_rewards_with_bonus_check(user, ctx.guild.id, ctx.channel)
                            rewarded_users.add(user.id)
            result_embed = discord.Embed(title="Hasil 'Pernah Gak Pernah'", color=0xf1c40f)
            result_embed.description = f"Untuk pernyataan:\n**_{statement}_**\n\n✅ **{pernah_count} orang** mengaku pernah.\n❌ **{gak_pernah_count} orang** mengaku tidak pernah."
            await ctx.send(embed=result_embed)
            if rewarded_users: await ctx.send(f"Terima kasih sudah berpartisipasi! {len(rewarded_users)} pemain telah mendapatkan hadiah.")
        except discord.NotFound: await ctx.send("Pesan game tidak ditemukan.")
        self.end_game_cleanup(ctx.channel.id)

    @commands.command(name="hitungcepat")
    async def hitungcepat(self, ctx):
        if not await self.start_game_check(ctx): return
        item = random.choice(self.hitung_cepat_data)
        problem, answer = item['problem'], str(item['answer'])
        embed = discord.Embed(title="🧮 Hitung Cepat!", description=f"Selesaikan soal matematika ini secepat mungkin!\n\n## `{problem} = ?`", color=0xe74c3c)
        await ctx.send(embed=embed)
        try:
            async def listen_for_math_answer():
                while True:
                    message = await self.bot.wait_for("message", check=lambda m: m.channel == ctx.channel and not m.author.bot)
                    if message.content.strip() == answer: return message
                    else:
                        if message.content.strip().replace('-', '').isdigit(): await message.add_reaction("❌")
            winner_msg = await asyncio.wait_for(listen_for_math_answer(), timeout=30.0)
            winner = winner_msg.author
            await self.give_rewards_with_bonus_check(winner, ctx.guild.id, ctx.channel)
            await ctx.send(f"⚡ **Luar Biasa Cepat!** {winner.mention} menjawab **{answer}** dengan benar!")
        except asyncio.TimeoutError:
            await ctx.send(f"Waktu habis! Jawaban yang benar adalah **{answer}**.")
        self.end_game_cleanup(ctx.channel.id)

    @commands.command(name="matamata")
    async def matamata(self, ctx):
        if not await self.start_game_check(ctx): return
        if not ctx.author.voice or not ctx.author.voice.channel:
            self.end_game_cleanup(ctx.channel.id)
            return await ctx.send("Kamu harus berada di voice channel untuk memulai game ini.", delete_after=10)
        vc = ctx.author.voice.channel
        members = [m for m in vc.members if not m.bot]
        if len(members) < 3:
            self.end_game_cleanup(ctx.channel.id)
            return await ctx.send("Game ini butuh minimal 3 orang di voice channel.", delete_after=10)
        
        location, spy = random.choice(self.mata_mata_locations), random.choice(members)
        for member in members:
            try:
                if member.id == spy.id: await member.send("🤫 Kamu adalah **Mata-Mata**! Tugasmu adalah menebak lokasi tanpa ketahuan.")
                else: await member.send(f"📍 Lokasi rahasia adalah: **{location}**. Temukan siapa mata-matanya!")
            except discord.Forbidden:
                await ctx.send(f"Gagal memulai game karena tidak bisa mengirim DM ke {member.mention}. Pastikan DM-nya terbuka."); self.end_game_cleanup(ctx.channel.id); return
        
        embed = discord.Embed(title="🎭 Game Mata-Mata Dimulai!", color=0x7289da); embed.description = "Peran dan lokasi telah dikirim melalui DM. Salah satu dari kalian adalah mata-mata!\n\n**Tujuan Pemain Biasa:** Temukan mata-mata.\n**Tujuan Mata-Mata:** Bertahan tanpa ketahuan & menebak lokasi.\n\nWaktu diskusi: **3 menit**. Gunakan `!tuduh @user` untuk menuduh di akhir."; embed.set_footer(text="Diskusi bisa dimulai sekarang!"); await ctx.send(embed=embed)
        
        if not hasattr(self.bot, 'active_spyfall_games'): self.bot.active_spyfall_games = {}
        self.bot.active_spyfall_games[ctx.channel.id] = {'spy': spy, 'location': location, 'players': members}
        
        await asyncio.sleep(180) 
        
        if ctx.channel.id in self.active_games:
            await ctx.send("Waktu diskusi habis! Mata-mata menang karena tidak ada yang dituduh!")
            await self.give_rewards_with_bonus_check(spy, ctx.guild.id, ctx.channel)
            self.end_game_cleanup(ctx.channel.id)
            if ctx.channel.id in self.bot.active_spyfall_games: del self.bot.active_spyfall_games[ctx.channel.id]

    @commands.command(name="tuduh")
    async def tuduh(self, ctx, member: discord.Member):
        if not hasattr(self.bot, 'active_spyfall_games') or ctx.channel.id not in self.bot.active_spyfall_games: return
        game = self.bot.active_spyfall_games[ctx.channel.id]
        spy, location, players = game['spy'], game['location'], game['players']
        if ctx.author not in players or member not in players: return await ctx.send("Hanya pemain yang berpartisipasi yang bisa menuduh atau dituduh.")
        
        await ctx.send(f"🚨 **VOTING AKHIR!** {ctx.author.mention} menuduh {member.mention} sebagai mata-mata.")
        if member.id == spy.id:
            await ctx.send(f"**Tuduhan Benar!** {member.mention} memang mata-matanya. Lokasinya adalah **{location}**. Selamat kepada tim warga, kalian semua mendapat hadiah!")
            for p in players:
                if p.id != spy.id: await self.give_rewards_with_bonus_check(p, ctx.guild.id, ctx.channel)
        else:
            await ctx.send(f"**Tuduhan Salah!** {member.mention} bukan mata-matanya. **Mata-mata ({spy.mention}) menang!** Lokasinya adalah **{location}**.")
            await self.give_rewards_with_bonus_check(spy, ctx.guild.id, ctx.channel)
            
        self.end_game_cleanup(ctx.channel.id)
        if ctx.channel.id in self.bot.active_spyfall_games: del self.bot.active_spyfall_games[ctx.channel.id]

async def setup(bot):
    await bot.add_cog(UltimateGameArena(bot))

