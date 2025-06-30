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
        # Menyesuaikan agar path root selalu mengarah ke direktori bot utama
        # Misal jika file ini ada di cogs/game.py, maka rootnya adalah direktori di atas cogs
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        full_path = os.path.join(base_dir, file_path)
        # Pastikan direktori ada sebelum mencoba membaca
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Peringatan: Tidak dapat memuat {file_path}. Pastikan file ada dan formatnya benar.")
        return [] # Mengembalikan list kosong untuk kasus file tidak ditemukan atau error JSON

def save_json_to_root(data, file_path):
    # Menyesuaikan agar path root selalu mengarah ke direktori bot utama
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    full_path = os.path.join(base_dir, file_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

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
        
        # Inisialisasi dictionary untuk menyimpan status game mata-mata
        # Ini akan membantu melacak game mana yang aktif dan apakah fase diskusi sudah berakhir
        self.spyfall_game_states = {} # {channel_id: {'spy': member, 'location': str, 'players': [members], 'discussion_over': bool}}

        # Load data untuk game
        self.siapakah_aku_data = load_json_from_root('data/siapakah_aku.json')
        self.pernah_gak_pernah_data = load_json_from_root('data/pernah_gak_pernah.json')
        self.hitung_cepat_data = load_json_from_root('data/hitung_cepat.json')
        self.mata_mata_locations = load_json_from_root('data/mata_mata_locations.json')
        self.deskripsi_data = load_json_from_root('data/deskripsi_tebak.json')
        self.perang_otak_data = load_json_from_root('data/perang_otak.json').get('questions', [])
        self.cerita_pembuka_data = load_json_from_root('data/cerita_pembuka.json')
        self.tekateki_harian_data = load_json_from_root('data/teka_teki_harian.json')

        self.reward = {"rsw": 50, "exp": 100}
        self.daily_puzzle = None
        self.daily_puzzle_solvers = set()
        self.daily_puzzle_channel_id = 765140300145360896  # Ganti dengan ID channel Anda
        self.post_daily_puzzle.start()

    def cog_unload(self):
        self.post_daily_puzzle.cancel()

    # --- Fungsi untuk mendapatkan multiplier ---
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
        self.reward = original_reward # Kembalikan reward ke nilai semula setelah digunakan
        if anomaly_multiplier > 1 and channel:
            await channel.send(f"✨ **BONUS ANOMALI!** {user.mention} mendapatkan hadiah yang dilipatgandakan!", delete_after=15)

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
        # Pastikan juga menghapus dari state spyfall jika game yang diakhiri adalah spyfall
        if channel_id in self.spyfall_game_states:
            del self.spyfall_game_states[channel_id]

    # --- GAME 1: SIAPAKAH AKU? ---
    @commands.command(name="siapakahaku", help="Mulai sesi 10 soal tebak-tebakan kompetitif.")
    @commands.cooldown(1, 60, commands.BucketType.channel)
    async def siapakahaku(self, ctx):
        if not await self.start_game_check(ctx):
            return
        
        if len(self.siapakah_aku_data) < 10:
            await ctx.send("Tidak cukup soal di database untuk memulai sesi (butuh minimal 10).")
            self.end_game_cleanup(ctx.channel.id)
            return
            
        questions = random.sample(self.siapakah_aku_data, 10)
        leaderboard = {}
        
        game_start_embed = discord.Embed(
            title="🕵️‍♂️ Sesi Kuis 'Siapakah Aku?' Dimulai!",
            description="Akan ada **10 soal** berturut-turut. Petunjuk akan muncul setiap **10 detik**.",
            color=0x1abc9c
        )
        await ctx.send(embed=game_start_embed)
        await asyncio.sleep(5)

        for i, item in enumerate(questions):
            word = item['name'].lower()
            clues = item['clues']
            attempts = {}
            timed_out_users = set()
            winner = None
            round_over = False

            embed = discord.Embed(
                title=f"SOAL #{i+1} dari 10",
                description=f"Kategori: **{item['category']}**",
                color=0x1abc9c
            )
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
                                winner = message.author
                                round_over = True
                                return
                            else:
                                await message.add_reaction("❌")
                                user_attempts = attempts.get(message.author.id, 0) + 1
                                attempts[message.author.id] = user_attempts
                                
                                if user_attempts >= 5:
                                    timed_out_users.add(message.author.id)
                                    try:
                                        # Pastikan bot punya izin untuk timeout
                                        await message.author.timeout(timedelta(seconds=60), reason="Melebihi batas percobaan di game")
                                        await ctx.send(f"🚨 {message.author.mention}, Anda kehabisan kesempatan & di-timeout sementara.", delete_after=10)
                                    except discord.Forbidden:
                                        await ctx.send(f"🚨 {message.author.mention}, Anda kehabisan kesempatan di ronde ini.", delete_after=10)
                    
                    await asyncio.wait_for(listen_for_answer(), timeout=10.0)

                except asyncio.TimeoutError:
                    if clue_index == len(clues) - 1:
                        await ctx.send(f"Waktu habis! Jawaban yang benar adalah **{item['name']}**.")
                    else:
                        continue

            if winner:
                await self.give_rewards_with_bonus_check(winner, ctx.guild.id, ctx.channel)
                await ctx.send(f"🎉 **Benar!** {winner.mention} berhasil menebak **{item['name']}**!")
                leaderboard[winner.name] = leaderboard.get(winner.name, 0) + 1

            # Mengembalikan timeout setelah ronde berakhir untuk semua pemain yang di-timeout
            for user_id in timed_out_users:
                member = ctx.guild.get_member(user_id)
                if member:
                    try:
                        await member.timeout(None, reason="Ronde game telah berakhir.")
                    except discord.Forbidden: # Bot mungkin tidak memiliki izin untuk menghilangkan timeout
                        pass

            if i < len(questions) - 1:
                await ctx.send(f"Soal berikutnya dalam **5 detik**...", delete_after=4.5)
                await asyncio.sleep(5)
        
        if leaderboard:
            sorted_leaderboard = sorted(leaderboard.items(), key=lambda item: item[1], reverse=True)
            leaderboard_text = "\n".join([f"{rank}. {name}: **{score}** poin" for rank, (name, score) in enumerate(sorted_leaderboard, 1)])
            final_embed = discord.Embed(title="🏆 Papan Skor Akhir 'Siapakah Aku?'", description=leaderboard_text, color=0xffd700)
            await ctx.send(embed=final_embed)
        else:
            await ctx.send("Sesi game berakhir tanpa ada pemenang.")
            
        self.end_game_cleanup(ctx.channel.id)

    # --- GAME 2: PERNAH GAK PERNAH ---
    @commands.command(name="pernahgak", help="Mulai game 'Pernah Gak Pernah' di voice channelmu.")
    @commands.cooldown(1, 30, commands.BucketType.channel)
    async def pernahgak(self, ctx):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("Kamu harus berada di voice channel untuk memulai game ini.", delete_after=10)
        vc = ctx.author.voice.channel
        members = [m for m in vc.members if not m.bot]
        if len(members) < 2:
            return await ctx.send("Game ini butuh minimal 2 orang di voice channel.", delete_after=10)
        if not await self.start_game_check(ctx): return
        statement = random.choice(self.pernah_gak_pernah_data)
        embed = discord.Embed(title="🤔 Pernah Gak Pernah...", description=f"## _{statement}_", color=0xf1c40f)
        embed.set_footer(text="Jawab dengan jujur menggunakan reaksi di bawah! Semua peserta dapat hadiah.")
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("✅"); await msg.add_reaction("❌")
        await asyncio.sleep(20) # Waktu untuk bereaksi
        try:
            cached_msg = await ctx.channel.fetch_message(msg.id)
            pernah_count, gak_pernah_count, rewarded_users = 0, 0, set()
            for reaction in cached_msg.reactions:
                if str(reaction.emoji) in ["✅", "❌"]:
                    # Kurangi 1 dari count reaksi karena bot juga menambahkan reaksi
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

    # --- GAME 3: HITUNG CEPAT ---
    @commands.command(name="hitungcepat", help="Selesaikan soal matematika secepat mungkin!")
    @commands.cooldown(1, 15, commands.BucketType.channel)
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
                        # Hanya bereaksi dengan silang jika inputnya mirip angka (bukan chat biasa)
                        if message.content.strip().replace('-', '').isdigit(): 
                            await message.add_reaction("❌")
            winner_msg = await asyncio.wait_for(listen_for_math_answer(), timeout=30.0) # Waktu untuk menjawab
            winner = winner_msg.author
            await self.give_rewards_with_bonus_check(winner, ctx.guild.id, ctx.channel)
            await ctx.send(f"⚡ **Luar Biasa Cepat!** {winner.mention} menjawab **{answer}** dengan benar!")
        except asyncio.TimeoutError:
            await ctx.send(f"Waktu habis! Jawaban yang benar adalah **{answer}**.")
        self.end_game_cleanup(ctx.channel.id)

    # --- GAME 4: MATA-MATA ---
    @commands.command(name="matamata", help="Mulai game Mata-Mata. Temukan siapa mata-matanya!")
    @commands.cooldown(1, 300, commands.BucketType.channel) # Cooldown lebih panjang karena game lebih lama
    async def matamata(self, ctx):
        if not await self.start_game_check(ctx): return
        if not ctx.author.voice or not ctx.author.voice.channel: return await ctx.send("Kamu harus berada di voice channel untuk memulai game ini.", delete_after=10)
        vc = ctx.author.voice.channel
        members = [m for m in vc.members if not m.bot]
        if len(members) < 3: return await ctx.send("Game ini butuh minimal 3 orang di voice channel.", delete_after=10)
        
        # Inisialisasi game state untuk channel ini
        if ctx.channel.id in self.spyfall_game_states:
            return await ctx.send("Game Mata-Mata sudah berjalan di channel ini.", delete_after=10)

        location = random.choice(self.mata_mata_locations)
        spy = random.choice(members)
        
        self.spyfall_game_states[ctx.channel.id] = {
            'spy': spy,
            'location': location,
            'players': members,
            'discussion_over': False # Flag untuk menandakan apakah diskusi sudah selesai
        }

        # Kirim DM ke setiap pemain
        failed_dms = []
        for member in members:
            try:
                if member.id == spy.id:
                    await member.send("🤫 Kamu adalah **Mata-Mata**! Tugasmu adalah menebak lokasi tanpa ketahuan.")
                else:
                    await member.send(f"📍 Lokasi rahasia adalah: **{location}**. Temukan siapa mata-matanya!")
            except discord.Forbidden:
                failed_dms.append(member.mention)
        
        if failed_dms:
            await ctx.send(f"Gagal memulai game karena tidak bisa mengirim DM ke: {', '.join(failed_dms)}. Pastikan DM-nya terbuka."); 
            self.end_game_cleanup(ctx.channel.id) # Cleanup game di channel ini
            return

        embed = discord.Embed(title="🎭 Game Mata-Mata Dimulai!", color=0x7289da)
        embed.description = "Peran dan lokasi telah dikirim melalui DM. Salah satu dari kalian adalah mata-mata!\n\n" \
                            "**Tujuan Pemain Biasa:** Temukan mata-mata.\n" \
                            "**Tujuan Mata-Mata:** Bertahan tanpa ketahuan & menebak lokasi.\n\n" \
                            "Waktu diskusi: **5 menit**. Gunakan `!tuduh @user` untuk menuduh di akhir.\n\n" \
                            "**Diskusi bisa dimulai sekarang!**"
        embed.set_footer(text="Setelah 5 menit, fase penuduhan akan dimulai.")
        await ctx.send(embed=embed)
        
        # Tunggu 5 menit untuk diskusi (300 detik)
        await asyncio.sleep(300) 
        
        # Setelah diskusi 5 menit, perbarui status game
        if ctx.channel.id in self.spyfall_game_states:
            self.spyfall_game_states[ctx.channel.id]['discussion_over'] = True
            
            # Beri tahu pemain bahwa waktu diskusi sudah habis
            await ctx.send(f"⏰ **Waktu diskusi habis!** Sekarang adalah fase penuduhan. "
                           f"Pemain biasa bisa menggunakan `!tuduh @nama_pemain` untuk menuduh mata-mata.\n"
                           f"Mata-mata ({spy.mention}) bisa menggunakan `!ungkap_lokasi <lokasi>` untuk mencoba menebak lokasi. "
                           f"Jika mata-mata menebak lokasi dengan benar dan belum dituduh, mata-mata menang! "
                           f"Jika tidak ada yang menuduh atau mata-mata tidak menebak lokasi dalam waktu tertentu, mata-mata menang."
                           f"\n\n**Permainan akan berakhir otomatis dalam 2 menit jika tidak ada aktivitas tuduhan atau pengungkapan lokasi.**")
            
            # Tambahkan timer untuk fase penuduhan/pengungkapan lokasi
            # Jika dalam 2 menit tidak ada aksi, mata-mata menang secara default
            try:
                await asyncio.sleep(120) # 2 menit untuk fase penuduhan
                if ctx.channel.id in self.spyfall_game_states and self.spyfall_game_states[ctx.channel.id]['discussion_over']:
                    # Jika masih aktif dan belum ada yang menang/kalah, mata-mata menang
                    await ctx.send(f"Waktu penuduhan habis! Mata-mata ({spy.mention}) menang karena tidak ada yang berhasil menuduh atau mata-mata tidak mengungkapkan lokasi! Lokasi sebenarnya adalah **{location}**.")
                    await self.give_rewards_with_bonus_check(spy, ctx.guild.id, ctx.channel)
            except asyncio.CancelledError:
                # Ini akan terjadi jika game diakhiri oleh !tuduh atau !ungkap_lokasi
                pass
        
        self.end_game_cleanup(ctx.channel.id) # Pastikan game dibersihkan setelah ini

    @commands.command(name="tuduh", help="Tuduh seseorang sebagai mata-mata.")
    async def tuduh(self, ctx, member: discord.Member):
        # Pastikan game aktif dan fase diskusi sudah berakhir
        if ctx.channel.id not in self.spyfall_game_states or not self.spyfall_game_states[ctx.channel.id]['discussion_over']:
            return await ctx.send("Game Mata-Mata belum dimulai atau waktu diskusi belum habis. Tunggu hingga fase penuduhan!", ephemeral=True)
        
        game = self.spyfall_game_states[ctx.channel.id]
        spy, location, players = game['spy'], game['location'], game['players']

        # Pastikan penuduh dan yang dituduh adalah pemain yang sah
        if ctx.author not in players or member not in players: 
            return await ctx.send("Hanya pemain yang berpartisipasi yang bisa menuduh atau dituduh.", ephemeral=True)
        
        await ctx.send(f"🚨 **VOTING AKHIR!** {ctx.author.mention} menuduh {member.mention} sebagai mata-mata.")
        
        # Logika kemenangan
        if member.id == spy.id:
            await ctx.send(f"**Tuduhan Benar!** {member.mention} memang mata-matanya. Lokasinya adalah **{location}**. Selamat kepada tim warga, kalian semua mendapat hadiah!")
            for p in players:
                if p.id != spy.id: # Beri reward kepada semua pemain non-mata-mata
                    await self.give_rewards_with_bonus_check(p, ctx.guild.id, ctx.channel)
        else:
            await ctx.send(f"**Tuduhan Salah!** {member.mention} bukan mata-matanya. **Mata-mata ({spy.mention}) menang!** Lokasinya adalah **{location}**.")
            await self.give_rewards_with_bonus_check(spy, ctx.guild.id, ctx.channel)
            
        self.end_game_cleanup(ctx.channel.id) # Bersihkan game setelah ada pemenang

    @commands.command(name="ungkap_lokasi", aliases=['ulokasi'], help="Sebagai mata-mata, coba tebak lokasi rahasia.")
    async def ungkap_lokasi(self, ctx, *, guessed_location: str):
        # Pastikan game aktif dan fase diskusi sudah berakhir
        if ctx.channel.id not in self.spyfall_game_states or not self.spyfall_game_states[ctx.channel.id]['discussion_over']:
            return await ctx.send("Game Mata-Mata belum dimulai atau waktu diskusi belum habis. Tunggu hingga fase penuduhan!", ephemeral=True)

        game = self.spyfall_game_states[ctx.channel.id]
        spy, location = game['spy'], game['location']

        # Hanya mata-mata yang bisa menggunakan perintah ini
        if ctx.author.id != spy.id:
            return await ctx.send("Hanya mata-mata yang bisa menggunakan perintah ini.", ephemeral=True)
        
        if guessed_location.lower() == location.lower():
            await ctx.send(f"🎉 **Mata-Mata Ungkap Lokasi Dengan Benar!** {spy.mention} berhasil menebak lokasi rahasia yaitu **{location}**! Mata-mata menang!")
            await self.give_rewards_with_bonus_check(spy, ctx.guild.id, ctx.channel)
        else:
            await ctx.send(f"❌ **Mata-Mata Gagal Mengungkap Lokasi!** Tebakan {guessed_location} salah. Lokasi sebenarnya adalah **{location}**. Warga menang!")
            # Beri reward kepada semua pemain non-mata-mata
            for p in game['players']:
                if p.id != spy.id:
                    await self.give_rewards_with_bonus_check(p, ctx.guild.id, ctx.channel)

        self.end_game_cleanup(ctx.channel.id) # Bersihkan game setelah ada pemenang

    # --- GAME TEKA-TEKI HARIAN ---
    @tasks.loop(time=time(hour=5, minute=0, tzinfo=None))
    async def post_daily_puzzle(self):
        await self.bot.wait_until_ready()
        # Mengatur zona waktu ke WIB (UTC+7)
        now = datetime.now()
        target_time = now.replace(hour=5, minute=0, second=0, microsecond=0)
        
        # Jika waktu sekarang sudah melewati 05:00 WIB hari ini, jadwalkan untuk besok
        if now > target_time:
            target_time += timedelta(days=1)
        
        # Hitung detik yang tersisa
        time_until_post = (target_time - now).total_seconds()
        
        if time_until_post > 0:
            await asyncio.sleep(time_until_post)

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
