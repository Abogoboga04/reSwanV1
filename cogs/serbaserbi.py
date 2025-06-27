import discord
from discord.ext import commands
import json
import random
import asyncio
import os

# Helper untuk memuat data JSON dari direktori utama bot
def load_json_from_root(file_path):
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        full_path = os.path.join(base_dir, file_path)
        with open(full_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Peringatan: Tidak dapat memuat {file_path}. Pastikan file ada dan formatnya benar.")
        return []

def save_json_to_root(data, file_path):
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    full_path = os.path.join(base_dir, file_path)
    with open(full_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

class SerbaSerbiGame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Game State Management
        self.active_games = set() # Mencegah game berbeda berjalan bersamaan di channel yang sama
        
        # Game Data
        self.siapakah_aku_data = load_json_from_root('data/siapakah_aku.json')
        self.pernah_gak_pernah_data = load_json_from_root('data/pernah_gak_pernah.json')
        self.hitung_cepat_data = load_json_from_root('data/hitung_cepat.json')
        self.mata_mata_locations = load_json_from_root('data/mata_mata_locations.json')
        
        # Universal Rewards
        self.reward = {"rsw": 50, "exp": 100}

    def give_rewards(self, user: discord.Member, guild_id: int):
        """Memberikan RSWN dan EXP kepada pengguna."""
        user_id_str = str(user.id)
        guild_id_str = str(guild_id)
        
        # Beri RSWN
        bank_data = load_json_from_root('data/bank_data.json')
        if user_id_str not in bank_data:
            bank_data[user_id_str] = {'balance': 0, 'debt': 0}
        bank_data[user_id_str]['balance'] += self.reward['rsw']
        save_json_to_root(bank_data, 'data/bank_data.json')
        
        # Beri EXP
        level_data = load_json_from_root('data/level_data.json')
        if guild_id_str not in level_data:
            level_data[guild_id_str] = {}
        if user_id_str not in level_data[guild_id_str]:
            level_data[guild_id_str][user_id_str] = {'exp': 0, 'level': 1}
        if 'exp' not in level_data[guild_id_str][user_id_str]:
            level_data[guild_id_str][user_id_str]['exp'] = 0
        level_data[guild_id_str][user_id_str]['exp'] += self.reward['exp']
        save_json_to_root(level_data, 'data/level_data.json')
        
    async def start_game_check(self, ctx):
        """Mencegah game duplikat di channel yang sama."""
        if ctx.channel.id in self.active_games:
            await ctx.send("Maaf, sudah ada permainan lain yang sedang berlangsung di channel ini. Mohon tunggu hingga selesai.", delete_after=10)
            return False
        self.active_games.add(ctx.channel.id)
        return True

    def end_game_cleanup(self, channel_id):
        """Membersihkan status game aktif."""
        self.active_games.discard(channel_id)

    # --- GAME 1: SIAPAKAH AKU? ---
    @commands.command(name="siapakahaku", help="Mulai game tebak-tebakan dengan petunjuk bertahap.")
    async def siapakahaku(self, ctx):
        if not await self.start_game_check(ctx): return
        
        item = random.choice(self.siapakah_aku_data)
        word = item['name']
        clues = item['clues']
        
        embed = discord.Embed(title="🕵️‍♂️ Siapakah Aku?", description=f"Kategori: **{item['category']}**", color=0x1abc9c)
        embed.set_thumbnail(url="https://i.imgur.com/b43a2t9.png")
        embed.set_footer(text="Tebak jawabannya kapan saja!")
        msg = await ctx.send(embed=embed)
        
        answered = False
        def check(m):
            return m.channel == ctx.channel and not m.author.bot and m.content.lower() == word.lower()

        for i, clue in enumerate(clues):
            embed.add_field(name=f"Petunjuk #{i+1}", value=f"_{clue}_", inline=False)
            await msg.edit(embed=embed)
            
            try:
                winner_msg = await self.bot.wait_for('message', timeout=15.0, check=check)
                winner = winner_msg.author
                self.give_rewards(winner, ctx.guild.id)
                await ctx.send(f"🎉 **Benar!** {winner.mention} berhasil menebak **{word}** dan mendapatkan hadiah!")
                answered = True
                break
            except asyncio.TimeoutError:
                continue
                
        if not answered:
            await ctx.send(f"Waktu habis! Jawaban yang benar adalah **{word}**.")
            
        self.end_game_cleanup(ctx.channel.id)
        
    # --- GAME 2: PERNAH GAK PERNAH ---
    @commands.command(name="pernahgak", help="Mulai game 'Pernah Gak Pernah' di voice channel.")
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
        await msg.add_reaction("✅") # Pernah
        await msg.add_reaction("❌") # Gak Pernah

        await asyncio.sleep(20) # Waktu untuk bereaksi

        try:
            cached_msg = await ctx.channel.fetch_message(msg.id)
            pernah_count = 0
            gak_pernah_count = 0
            rewarded_users = set()

            for reaction in cached_msg.reactions:
                emoji_str = str(reaction.emoji)
                if emoji_str in ["✅", "❌"]:
                    if emoji_str == "✅": pernah_count = reaction.count - 1
                    if emoji_str == "❌": gak_pernah_count = reaction.count - 1
                    
                    async for user in reaction.users():
                        if not user.bot and user.id not in rewarded_users:
                            self.give_rewards(user, ctx.guild.id)
                            rewarded_users.add(user.id)
            
            result_embed = discord.Embed(title="Hasil 'Pernah Gak Pernah'", color=0xf1c40f)
            result_embed.description = f"Untuk pernyataan:\n**_{statement}_**\n\n✅ **{pernah_count} orang** mengaku pernah.\n❌ **{gak_pernah_count} orang** mengaku tidak pernah."
            await ctx.send(embed=result_embed)
            if rewarded_users:
                await ctx.send(f"Terima kasih sudah berpartisipasi! {len(rewarded_users)} pemain telah mendapatkan hadiah.")
        except discord.NotFound:
            await ctx.send("Pesan game tidak ditemukan.")

        self.end_game_cleanup(ctx.channel.id)

    # --- GAME 3: HITUNG CEPAT ---
    @commands.command(name="hitungcepat", help="Mulai game adu kecepatan berhitung.")
    async def hitungcepat(self, ctx):
        if not await self.start_game_check(ctx): return
        
        item = random.choice(self.hitung_cepat_data)
        problem = item['problem']
        answer = str(item['answer'])

        embed = discord.Embed(title="🧮 Hitung Cepat!", description=f"Selesaikan soal matematika ini secepat mungkin!\n\n## `{problem} = ?`", color=0xe74c3c)
        await ctx.send(embed=embed)
        
        try:
            def check(m):
                return m.channel == ctx.channel and not m.author.bot and m.content.strip() == answer
            
            winner_msg = await self.bot.wait_for('message', timeout=30.0, check=check)
            winner = winner_msg.author
            self.give_rewards(winner, ctx.guild.id)
            await ctx.send(f"⚡ **Luar Biasa Cepat!** {winner.mention} menjawab **{answer}** dengan benar dan mendapat hadiah!")
        except asyncio.TimeoutError:
            await ctx.send(f"Waktu habis! Jawaban yang benar adalah **{answer}**.")
            
        self.end_game_cleanup(ctx.channel.id)

    # --- GAME 4: MATA-MATA (SPYFALL) ---
    @commands.command(name="matamata", help="Mulai game deduksi sosial 'Mata-Mata'.")
    async def matamata(self, ctx):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("Kamu harus berada di voice channel untuk memulai game ini.", delete_after=10)
        
        vc = ctx.author.voice.channel
        members = [m for m in vc.members if not m.bot]
        if len(members) < 3:
            return await ctx.send("Game ini butuh minimal 3 orang di voice channel.", delete_after=10)
        
        if not await self.start_game_check(ctx): return
        
        location = random.choice(self.mata_mata_locations)
        spy = random.choice(members)
        
        for member in members:
            try:
                if member.id == spy.id:
                    await member.send("🤫 Kamu adalah **Mata-Mata**! Tugasmu adalah menebak lokasi tanpa ketahuan.")
                else:
                    await member.send(f"📍 Lokasi rahasia adalah: **{location}**. Temukan siapa mata-matanya!")
            except discord.Forbidden:
                await ctx.send(f"Gagal memulai game karena tidak bisa mengirim DM ke {member.mention}. Pastikan DM-nya terbuka.")
                self.end_game_cleanup(ctx.channel.id)
                return

        embed = discord.Embed(title="🎭 Game Mata-Mata Dimulai!", color=0x7289da)
        embed.description = (
            "Peran dan lokasi telah dikirim melalui DM. Salah satu dari kalian adalah mata-mata!\n\n"
            "**Tujuan Pemain Biasa:** Temukan mata-mata.\n"
            "**Tujuan Mata-Mata:** Bertahan tanpa ketahuan & menebak lokasi.\n\n"
            "Waktu diskusi: **3 menit**. Gunakan `!tuduh @user` untuk menuduh di akhir."
        )
        embed.set_footer(text="Diskusi bisa dimulai sekarang!")
        await ctx.send(embed=embed)
        
        # Simpan state untuk voting
        if not hasattr(self.bot, 'active_spyfall_games'):
            self.bot.active_spyfall_games = {}
        self.bot.active_spyfall_games[ctx.channel.id] = {'spy': spy, 'location': location, 'players': members}
        
        await asyncio.sleep(180) 
        
        if ctx.channel.id in self.active_games:
            await ctx.send("Waktu diskusi habis! Mata-mata menang karena tidak ada yang dituduh!")
            self.give_rewards(spy, ctx.guild.id)
            self.end_game_cleanup(ctx.channel.id)
            if ctx.channel.id in self.bot.active_spyfall_games:
                del self.bot.active_spyfall_games[ctx.channel.id]

    @commands.command(name="tuduh", help="Memulai voting untuk menuduh seorang mata-mata.")
    async def tuduh(self, ctx, member: discord.Member):
        if not hasattr(self.bot, 'active_spyfall_games') or ctx.channel.id not in self.bot.active_spyfall_games:
            return
            
        game = self.bot.active_spyfall_games[ctx.channel.id]
        spy, location, players = game['spy'], game['location'], game['players']
        
        if ctx.author not in players or member not in players:
            return await ctx.send("Hanya pemain yang berpartisipasi yang bisa menuduh atau dituduh.")
        
        await ctx.send(f"🚨 **VOTING AKHIR!** {ctx.author.mention} menuduh {member.mention} sebagai mata-mata.")
        if member.id == spy.id:
            await ctx.send(f"**Tuduhan Benar!** {member.mention} memang mata-matanya. Lokasinya adalah **{location}**. Selamat kepada tim warga, kalian semua mendapat hadiah!")
            for p in players:
                if p.id != spy.id: self.give_rewards(p, ctx.guild.id)
        else:
            await ctx.send(f"**Tuduhan Salah!** {member.mention} bukan mata-matanya. **Mata-mata ({spy.mention}) menang!** Lokasinya adalah **{location}**.")
            self.give_rewards(spy, ctx.guild.id)
            
        self.end_game_cleanup(ctx.channel.id)
        if ctx.channel.id in self.bot.active_spyfall_games:
            del self.bot.active_spyfall_games[ctx.channel.id]

async def setup(bot):
    await bot.add_cog(SerbaSerbiGame(bot))

