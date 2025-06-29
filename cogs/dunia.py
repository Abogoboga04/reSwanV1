import discord
from discord.ext import commands, tasks
import json
import random
import asyncio
import os
from datetime import datetime, timedelta, time
import string

# --- Helper Functions (Wajib ada di awal) ---
def load_json_from_root(file_path):
    """Memuat data JSON dari file yang berada di root direktori proyek."""
    try:
        # Mengambil direktori dasar (root) dari bot
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        full_path = os.path.join(base_dir, file_path)
        with open(full_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Critical Warning: Failed to load or corrupted file -> {file_path}")
        # Mengembalikan struktur data default tergantung jenis file
        if 'users' in file_path or 'inventory' in file_path: return {}
        elif any(k in file_path for k in ['monsters', 'anomalies', "medicines"]): 
            # Untuk file seperti monsters.json, anomalies.json, medicines.json yang berisi daftar
            return {os.path.basename(file_path).replace('.json', ''): []}
        return {}

def save_json_to_root(data, file_path):
    """Menyimpan data ke file JSON di root direktori proyek."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    full_path = os.path.join(base_dir, file_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True) # Pastikan direktori 'data/' ada
    with open(full_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

# --- UI View untuk Pertarungan Monster ---
class MonsterBattleView(discord.ui.View):
    def __init__(self, bot_cog, monster, party):
        super().__init__(timeout=600) # Timeout 10 menit
        self.cog = bot_cog
        self.monster = monster
        self.party = list(party) # Mengubah set menjadi list untuk pengindeksan giliran
        self.turn_index = 0
        self.battle_log = ["Pertarungan dimulai!"]

    def get_current_player(self):
        """Mendapatkan pemain yang gilirannya saat ini."""
        return self.party[self.turn_index]

    def create_battle_embed(self, status_text):
        """Membuat atau memperbarui embed status pertarungan."""
        hp_percentage = self.monster['current_hp'] / self.monster['max_hp']
        bar_length = 20
        bar_filled = max(0, int(hp_percentage * bar_length))
        bar_empty = bar_length - bar_filled
        hp_bar = "█" * bar_filled + "─" * bar_empty
        
        embed = discord.Embed(title=f"⚔️ Battling {self.monster['name']} ⚔️", description=status_text, color=discord.Color.red())
        embed.set_thumbnail(url=self.monster['image_url'])
        embed.add_field(name="❤️ Monster HP Remaining", value=f"`[{hp_bar}]`\n**{self.monster['current_hp']:,} / {self.monster['max_hp']:,}**", inline=False)
        party_status = "\n".join([f"**{p.display_name}**" for p in self.party])
        embed.add_field(name="👥 Attacking Party", value=party_status, inline=True)
        log_text = "\n".join([f"> {log}" for log in self.battle_log[-5:]]) # Hanya menampilkan 5 log terakhir
        embed.add_field(name="📜 Battle Log", value=log_text, inline=False)
        return embed

    async def update_view(self, interaction: discord.Interaction):
        """Memperbarui pesan interaksi dengan embed dan view terbaru."""
        if self.monster['current_hp'] <= 0:
            embed = self.create_battle_embed(f"🎉 **MONSTER DEFEATED!** 🎉")
            embed.color = discord.Color.gold()
            for item in self.children: item.disabled = True # Menonaktifkan semua tombol
            await interaction.message.edit(embed=embed, view=self)
            self.stop() # Menghentikan view
            await self.cog.handle_monster_defeat(interaction.channel)
        else:
            embed = self.create_battle_embed(f"Turn: **{self.get_current_player().display_name}**")
            await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Attack ⚔️", style=discord.ButtonStyle.danger)
    async def attack(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Tombol serangan untuk pertarungan monster."""
        current_player = self.get_current_player()
        if interaction.user != current_player:
            return await interaction.response.send_message("It's not your turn!", ephemeral=True)

        await interaction.response.defer() # Defer respons agar bot tidak timeout

        # Ambil level pengguna dari data level
        level_data = load_json_from_root('data/level_data.json').get(str(interaction.guild.id), {})
        user_level = level_data.get(str(interaction.user.id), {}).get('level', 1)
        
        # Hitung damage berdasarkan level pengguna
        damage = random.randint(50, 150) + (user_level * 20)
        self.monster['current_hp'] -= damage
        self.cog.monster_attackers.add(interaction.user.id) # Menambahkan penyerang ke set

        self.battle_log.append(f"{interaction.user.display_name} attacked, dealing **{damage}** damage!")
        
        if self.monster['current_hp'] > 0:
            monster_damage = random.randint(100, 300)
            self.battle_log.append(f"{self.monster['name']} attacked back, dealing **{monster_damage}** damage to {interaction.user.display_name}!")
        
        # Pindah ke giliran pemain berikutnya
        self.turn_index = (self.turn_index + 1) % len(self.party)
        await self.update_view(interaction)

class DuniaHidup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = set() # Tidak jelas digunakan untuk apa, bisa dihapus jika tidak terpakai
        self.current_monster = None
        self.monster_attack_queue = []
        self.monster_attackers = set()
        self.active_anomaly = None
        self.anomaly_end_time = None
        self.sick_users_cooldown = {}
        self.protected_users = load_json_from_root('data/protected_users.json') 
        self.dropped_codes = {}

        # Ganti dengan ID channel pengumuman di server Discord Anda
        self.event_channel_id = 765140300145360896 
        # Ganti dengan ID role 'Sakit' di server Discord Anda
        self.sick_role_id = 1388744189063200860 
        self.sickness_cooldown_minutes = 1.5
        
        # Memuat data dari file JSON
        self.monsters_data = load_json_from_root('data/monsters.json')
        self.anomalies_data = load_json_from_root('data/world_anomalies.json').get('anomalies', [])
        self.medicines_data = load_json_from_root('data/medicines.json').get('medicines', [])
        
        # Memulai tasks loop
        self.world_event_loop.start()
        self.monster_attack_processor.start()
        self.protection_cleaner.start()

    def cog_unload(self):
        """Dipanggil saat cog dibongkar."""
        self.world_event_loop.cancel()
        self.monster_attack_processor.cancel()
        self.protection_cleaner.cancel()

    @tasks.loop(hours=random.randint(3, 6)) # Event dunia terjadi setiap 3-6 jam
    async def world_event_loop(self):
        """Memulai event dunia secara berkala."""
        await self.bot.wait_until_ready() # Pastikan bot sudah online
        if self.current_monster or self.active_anomaly: return # Jangan mulai event baru jika ada yang sedang berjalan

        event_type = random.choice(['monster', 'anomaly', 'monster_quiz'])
        if event_type == 'monster' and self.monsters_data.get('monsters'): await self.spawn_monster()
        elif event_type == 'anomaly' and self.anomalies_data: await self.trigger_anomaly()
        elif event_type == 'monster_quiz' and self.monsters_data.get('monster_quiz'): await self.trigger_monster_quiz()

    @tasks.loop(minutes=30)
    async def protection_cleaner(self):
        """Membersihkan perlindungan pengguna yang sudah kadaluarsa."""
        now = datetime.utcnow()
        expired_users = [uid for uid, expiry in list(self.protected_users.items()) if now >= datetime.fromisoformat(expiry)]
        for uid in expired_users:
            del self.protected_users[uid]
        if expired_users: save_json_to_root(self.protected_users, 'data/protected_users.json')

    async def spawn_monster(self):
        """Memunculkan monster baru di channel event."""
        self.current_monster = random.choice(self.monsters_data['monsters']).copy()
        self.current_monster['current_hp'] = self.current_monster['max_hp']
        self.monster_attackers.clear() # Reset daftar penyerang
        channel = self.bot.get_channel(self.event_channel_id)
        if not channel: return
        embed = discord.Embed(title=f"🚨 NEW THREAT APPEARS! 🚨\n{self.current_monster['name']}", description=f"_{self.current_monster['story']}_", color=discord.Color.red())
        embed.set_thumbnail(url=self.current_monster['image_url'])
        embed.add_field(name="❤️ HP", value=f"**{self.current_monster['current_hp']:,}/{self.current_monster['max_hp']:,}**", inline=True)
        embed.add_field(name="⚔️ Type", value=self.current_monster['type'], inline=True)
        embed.set_footer(text="Use !serangmonster to form a party and fight it!")
        await channel.send(embed=embed)
        await self.schedule_monster_attacks(channel.guild)

    async def schedule_monster_attacks(self, guild):
        """Menjadwalkan serangan monster terhadap pengguna aktif."""
        level_data = load_json_from_root(f'data/level_data.json').get(str(guild.id), {})
        if not level_data: return
        # Ambil 10 pengguna teratas berdasarkan EXP
        sorted_users = sorted(level_data.items(), key=lambda x: x[1].get('exp', 0), reverse=True)
        top_users_ids = [uid for uid, data in sorted_users if guild.get_member(int(uid))] # Pastikan member masih ada di guild

        # Pilih 3 target acak dari top 10 (atau kurang jika kurang dari 3)
        if len(top_users_ids) < 3: targets = top_users_ids
        else: targets = random.sample(top_users_ids, 3)
        
        if not targets: return
        
        now = datetime.utcnow()
        # Jadwalkan serangan dengan waktu yang berbeda
        self.monster_attack_queue = [
            {'user_id': uid, 'attack_time': (now + timedelta(hours=random.randint(i*4+1, (i+1)*4))).isoformat()} 
            for i, uid in enumerate(targets)
        ]

    @tasks.loop(minutes=10)
    async def monster_attack_processor(self):
        """Memproses serangan monster yang terjadwal."""
        if not self.monster_attack_queue or not self.current_monster: return # Tidak ada serangan atau monster
        
        now = datetime.utcnow()
        # Periksa apakah sudah waktunya serangan pertama dalam antrean
        if now < datetime.fromisoformat(self.monster_attack_queue[0]['attack_time']): return
        
        attack = self.monster_attack_queue.pop(0) # Ambil serangan pertama
        user_id_to_attack = attack['user_id']

        # Lewati jika pengguna dilindungi
        if str(user_id_to_attack) in self.protected_users: return

        guild = self.bot.guilds[0] # Asumsi bot hanya di satu guild atau ambil guild yang relevan
        member = guild.get_member(int(user_id_to_attack))
        if not member: return # Lewati jika member tidak ditemukan

        exp_loss, rswn_loss = random.randint(250, 500), random.randint(250, 500)
        
        level_data = load_json_from_root('data/level_data.json')
        bank_data = load_json_from_root('data/bank_data.json')

        guild_id_str = str(guild.id)
        user_id_str = str(user_id_to_attack)

        # Kurangi EXP
        if guild_id_str in level_data and user_id_str in level_data[guild_id_str]:
            level_data[guild_id_str][user_id_str]['exp'] = max(0, level_data[guild_id_str][user_id_str].get('exp', 0) - exp_loss)
        
        # Kurangi RSWN
        if user_id_str in bank_data:
            bank_data[user_id_str]['balance'] = max(0, bank_data[user_id_str].get('balance', 0) - rswn_loss)
        
        save_json_to_root(level_data, 'data/level_data.json')
        save_json_to_root(bank_data, 'data/bank_data.json')
        
        channel = self.bot.get_channel(self.event_channel_id)
        if channel:
            embed = discord.Embed(title="⚔️ MONSTER ATTACK! ⚔️", description=f"{self.current_monster['name']} attacked {member.mention} from the shadows!", color=discord.Color.dark_red())
            embed.set_thumbnail(url="https://i.imgur.com/8Qk8S1k.png")
            embed.add_field(name="Losses", value=f"You lost **{exp_loss} EXP** and **{rswn_loss} RSWN**!")
            await channel.send(embed=embed)

    @commands.command(name="serangmonster")
    async def serangmonster(self, ctx):
        """Memulai sesi pembentukan party untuk menyerang monster."""
        if not self.current_monster: 
            return await ctx.send("There is no monster to attack currently.", delete_after=10)
        
        view = discord.ui.View(timeout=60.0) # View akan nonaktif setelah 60 detik
        party = {ctx.author} # Inisialisasi party dengan pembuat perintah

        embed = discord.Embed(
            title="⚔️ Forming an Attack Party!", 
            description=f"**{ctx.author.display_name}** started an attack against **{self.current_monster['name']}**!\n\nOther players, click 'Join' to participate! 60 seconds remaining.", 
            color=discord.Color.blurple()
        )
        
        async def join_callback(interaction: discord.Interaction):
            """Callback untuk tombol 'Gabung Pertarungan'."""
            if interaction.user not in party:
                party.add(interaction.user)
                await interaction.response.send_message(f"{interaction.user.mention} has joined!", ephemeral=True)
            else:
                await interaction.response.send_message("You have already joined.", ephemeral=True)

        join_button = discord.ui.Button(label="Join Battle", style=discord.ButtonStyle.success, emoji="🤝")
        join_button.callback = join_callback
        view.add_item(join_button)
        
        msg = await ctx.send(embed=embed, view=view)
        await asyncio.sleep(60) # Tunggu 60 detik untuk pemain bergabung
        
        try: 
            await msg.delete() # Hapus pesan pembentukan party
        except discord.NotFound: 
            pass # Pesan mungkin sudah dihapus secara manual

        if not party: 
            return await ctx.send("No one joined the party. The monster continues to roam free!", delete_after=10)
        
        # Mulai pertarungan dengan party yang terbentuk
        battle_view = MonsterBattleView(self, self.current_monster, party)
        initial_embed = battle_view.create_battle_embed(f"Turn: **{battle_view.get_current_player().display_name}**")
        await ctx.send(embed=initial_embed, view=battle_view)

    async def handle_monster_defeat(self, channel):
        """Menangani logika setelah monster dikalahkan."""
        reward_rswn, reward_exp = 5000, 5000
        await channel.send(f"🎉 **CONGRATULATIONS!** You have defeated **{self.current_monster['name']}**! All **{len(self.monster_attackers)} warriors** who participated receive **{reward_rswn:,} RSWN** and **{reward_exp:,} EXP**!")
        
        bank_data = load_json_from_root('data/bank_data.json')
        level_data = load_json_from_root('data/level_data.json')

        guild_id_str = str(channel.guild.id)
        
        for user_id in self.monster_attackers:
            member = channel.guild.get_member(int(user_id))
            if member: # Pastikan member masih ada
                user_id_str = str(user_id)
                # Berikan RSWN
                bank_data.setdefault(user_id_str, {'balance': 0})['balance'] += reward_rswn
                # Berikan EXP
                level_data.setdefault(guild_id_str, {}).setdefault(user_id_str, {'exp': 0})['exp'] += reward_exp
        
        save_json_to_root(bank_data, 'data/bank_data.json')
        save_json_to_root(level_data, 'data/level_data.json')
        
        # Reset status monster dan antrean serangan
        self.current_monster, self.monster_attack_queue, self.monster_attackers = None, [], set()

    async def trigger_anomaly(self):
        """Memicu event anomali dunia."""
        anomaly = random.choice(self.anomalies_data)
        self.active_anomaly = anomaly
        self.anomaly_end_time = datetime.utcnow() + timedelta(seconds=anomaly['duration_seconds'])
        
        channel = self.bot.get_channel(self.event_channel_id)
        if not channel: return
        
        embed = discord.Embed(title=f"{anomaly['emoji']} ANOMALY: {anomaly['name']} {anomaly['emoji']}", description=anomaly['description'], color=discord.Color.from_str(anomaly['color']))
        embed.set_thumbnail(url=anomaly['thumbnail_url'])
        await channel.send(embed=embed)
        
        if anomaly['type'] == 'code_drop': 
            self.bot.loop.create_task(self.code_dropper(anomaly['duration_seconds']))
        elif anomaly['type'] == 'sickness_plague': 
            await self.start_sickness_plague(channel.guild)

        # Tunggu sampai anomali berakhir
        await asyncio.sleep(anomaly['duration_seconds'])
        await channel.send(f"The anomaly **{anomaly['name']}** has ended.")
        self.active_anomaly, self.anomaly_end_time = None, None # Reset anomali

    async def code_dropper(self, duration):
        """Menjatuhkan kode secara berkala selama anomali 'code_drop'."""
        end_time = datetime.utcnow() + timedelta(seconds=duration)
        while datetime.utcnow() < end_time:
            await asyncio.sleep(random.randint(300, 900)) # Jatuhkan kode setiap 5-15 menit
            if not self.active_anomaly or self.active_anomaly.get('type') != 'code_drop': break # Berhenti jika anomali berubah/berakhir
            
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8)) # Buat kode acak
            self.dropped_codes[code] = {"rswn": random.randint(500, 2000), "exp": random.randint(500, 2000)}
            
            channel = self.bot.get_channel(self.event_channel_id)
            if channel: 
                await channel.send(f"☄️ **METEOR SHOWER!** A code has fallen! Type `!claim {code}` for rewards!")
            
            self.bot.loop.create_task(self.expire_code(code)) # Jadwalkan penghapusan kode

    async def expire_code(self, code):
        """Menghapus kode yang dijatuhkan setelah waktu tertentu."""
        await asyncio.sleep(120) # Kode akan kadaluarsa dalam 2 menit
        if code in self.dropped_codes: 
            del self.dropped_codes[code]
            channel = self.bot.get_channel(self.event_channel_id)
            if channel:
                # Opsi: Beri tahu bahwa kode telah kadaluarsa
                # await channel.send(f"Code `{code}` has expired.")
                pass

    @commands.command(name="klaim")
    async def klaim(self, ctx, code: str):
        """Mengklaim hadiah dari kode yang dijatuhkan."""
        if code in self.dropped_codes:
            reward = self.dropped_codes.pop(code) # Hapus kode setelah diklaim
            
            bank_data = load_json_from_root('data/bank_data.json')
            level_data = load_json_from_root('data/level_data.json')

            user_id_str = str(ctx.author.id)
            guild_id_str = str(ctx.guild.id)

            bank_data.setdefault(user_id_str, {'balance': 0})['balance'] += reward['rswn']
            level_data.setdefault(guild_id_str, {}).setdefault(user_id_str, {'exp': 0})['exp'] += reward['exp']
            
            save_json_to_root(bank_data, 'data/bank_data.json')
            save_json_to_root(level_data, 'data/level_data.json')
            
            await ctx.send(f"🎉 Congratulations {ctx.author.mention}! You successfully claimed **{reward['rswn']} RSWN** and **{reward['exp']} EXP**!")
        else:
            await ctx.send("Invalid or expired code.", delete_after=10)

    async def trigger_monster_quiz(self):
        """Memicu event kuis monster."""
        channel = self.bot.get_channel(self.event_channel_id)
        if not channel or not self.monsters_data.get('monster_quiz'): return
        
        quiz_monster = random.choice(self.monsters_data['monster_quiz'])
        self.active_anomaly = quiz_monster # Menggunakan anomaly untuk menandai kuis aktif
        
        embed = discord.Embed(title=f"❓ CHALLENGE FROM {quiz_monster['name'].upper()} ❓", description=quiz_monster['intro'], color=discord.Color.dark_purple())
        embed.set_thumbnail(url=quiz_monster['image_url'])
        embed.add_field(name="Riddle:", value=f"**{quiz_monster['riddle']}**\n\n_Hint: {quiz_monster['hint']}_")
        embed.set_footer(text="Answer in this channel! 5 minutes remaining.")
        await channel.send(embed=embed)

        def check(m): 
            return m.channel == channel and not m.author.bot and m.content.lower() == quiz_monster['answer'].lower()

        try:
            winner_msg = await self.bot.wait_for('message', timeout=300.0, check=check) # Tunggu 5 menit
            await channel.send(f"🧠 **Genius!** {winner_msg.author.mention} answered correctly and saved the server from the curse! You received a great reward!")
            
            # Beri hadiah besar untuk pemenang
            reward_rswn_quiz, reward_exp_quiz = 7500, 7500
            bank_data = load_json_from_root('data/bank_data.json')
            level_data = load_json_from_root('data/level_data.json')
            
            winner_id_str = str(winner_msg.author.id)
            guild_id_str = str(winner_msg.guild.id)

            bank_data.setdefault(winner_id_str, {'balance': 0})['balance'] += reward_rswn_quiz
            level_data.setdefault(guild_id_str, {}).setdefault(winner_id_str, {'exp': 0})['exp'] += reward_exp_quiz
            
            save_json_to_root(bank_data, 'data/bank_data.json')
            save_json_to_root(level_data, 'data/level_data.json')

        except asyncio.TimeoutError:
            await channel.send(f"Time's up! No one could answer. The correct answer was: **{quiz_monster['answer']}**. A curse has befallen the server!")
            # Terapkan efek negatif jika tidak ada yang menjawab
            # Misalnya, mengurangi EXP acak dari beberapa pengguna
        
        self.active_anomaly = None # Reset anomali

    async def start_sickness_plague(self, guild):
        """Menyebarkan wabah penyakit ke pengguna aktif."""
        level_data = load_json_from_root('data/level_data.json').get(str(guild.id), {})
        # Filter pengguna yang aktif dalam 3 hari terakhir
        active_users = [
            uid for uid, data in level_data.items() 
            if 'last_active' in data and datetime.utcnow() - datetime.fromisoformat(data['last_active']) < timedelta(days=3)
            and guild.get_member(int(uid)) # Pastikan member masih ada di guild
        ]
        
        num_to_infect = min(len(active_users), random.randint(3, 7)) # Infeksi 3-7 pengguna
        if num_to_infect == 0: return # Tidak ada yang bisa diinfeksi

        infected_users_ids = random.sample(active_users, num_to_infect)
        
        role = guild.get_role(self.sick_role_id)
        if not role: return # Tidak ada role sakit

        infected_mentions = []
        for user_id in infected_users_ids:
            member = guild.get_member(int(user_id))
            if member:
                await member.add_roles(role)
                infected_mentions.append(member.mention)
        
        channel = self.bot.get_channel(self.event_channel_id)
        if channel and infected_mentions:
            await channel.send(f"😷 **PLAGUE SPREADS!** {', '.join(infected_mentions)} have fallen ill. Their interactions will be limited. Quickly find medicine in `!shop`!")

    @commands.Cog.listener()
    async def on_message(self, message):
        """
        Listener untuk setiap pesan. Digunakan untuk logika cooldown sakit.
        PENTING: Tidak memanggil bot.process_commands(message) di sini
        karena sudah ditangani di on_message global di main.py.
        """
        # Abaikan pesan dari bot itu sendiri atau pesan di luar guild (DM)
        if message.author.bot or not message.guild:
            return
        
        user_id = message.author.id
        sick_role = message.guild.get_role(self.sick_role_id)

        # Logika untuk role "sakit" dan cooldown
        if sick_role and sick_role in message.author.roles:
            now = datetime.utcnow()
            last_message_time = self.sick_users_cooldown.get(user_id)
            if last_message_time:
                cooldown = timedelta(minutes=self.sickness_cooldown_minutes)
                if now - last_message_time < cooldown:
                    time_left = cooldown - (now - last_message_time)
                    try:
                        # Hapus pesan dan beritahu pengguna secara ephemeral
                        await message.delete()
                        await message.author.send(
                            f"You are sick and still weak... You need to rest for **{int(time_left.total_seconds())} seconds** before you can speak again.", 
                            delete_after=60
                        )
                    except (discord.Forbidden, discord.NotFound): 
                        pass # Gagal menghapus pesan atau mengirim DM
                    return # Hentikan pemrosesan lebih lanjut jika user sedang dalam cooldown
            self.sick_users_cooldown[user_id] = now # Update waktu pesan terakhir

        # Tidak perlu memanggil `await self.bot.process_commands(message)` di sini.
        # Itu sudah ditangani oleh on_message global di `main.py`.

    @commands.command(name="minumobat")
    async def minumobat(self, ctx):
        """Menggunakan 'Kotak Obat Misterius' untuk mencoba menyembuhkan penyakit."""
        user_id_str = str(ctx.author.id)
        sick_role = ctx.guild.get_role(self.sick_role_id)
        
        if not sick_role or sick_role not in ctx.author.roles:
            return await ctx.send("You are not sick, no need to drink medicine.")
        
        inventory_data = load_json_from_root('data/inventory.json')
        user_inventory = inventory_data.setdefault(user_id_str, [])
        
        # Cari Kotak Obat Misterius di inventaris
        medicine_box = next((item for item in user_inventory if item.get('type') == 'gacha_medicine_box'), None)
        if not medicine_box: 
            return await ctx.send("You don't have a Mysterious Medicine Box. Buy one from `!shop` first.")
        
        # Hapus satu Kotak Obat Misterius dari inventaris
        user_inventory.remove(medicine_box)
        save_json_to_root(inventory_data, 'data/inventory.json')
        
        embed = discord.Embed(title="💊 Crafting Medicine...", description="You open the Mysterious Medicine Box and start shaking it...", color=discord.Color.light_grey())
        embed.set_thumbnail(url="https://i.imgur.com/gL9pA8v.gif") # Contoh GIF meracik obat
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(3) # Simulasi proses meracik

        # Pilih obat secara acak berdasarkan peluang
        choices = [med['name'] for med in self.medicines_data]
        weights = [med['chance'] for med in self.medicines_data]
        chosen_medicine_name = random.choices(choices, weights=weights, k=1)[0]
        chosen_medicine = next(med for med in self.medicines_data if med['name'] == chosen_medicine_name)

        result_embed = discord.Embed(title="Medicine Gacha Result", description=f"You got... **{chosen_medicine['name']}**!", color=discord.Color.from_str(chosen_medicine['color']))
        result_embed.add_field(name="Effect", value=chosen_medicine['effect_desc'])
        await msg.edit(embed=result_embed)
        
        # Coba sembuhkan berdasarkan peluang obat
        if random.randint(1, 100) <= chosen_medicine['heal_chance']:
            await asyncio.sleep(2)
            heal_embed = discord.Embed(title="✨ Medicine Worked! ✨", color=discord.Color.green())
            await ctx.author.remove_roles(sick_role) # Hapus role sakit
            if str(ctx.author.id) in self.sick_users_cooldown: 
                del self.sick_users_cooldown[str(ctx.author.id)] # Reset cooldown sakit
            
            if chosen_medicine['heal_chance'] == 100: # Jika obat memberikan perlindungan
                expiry = datetime.utcnow() + timedelta(hours=24)
                self.protected_users[user_id_str] = expiry.isoformat()
                save_json_to_root(self.protected_users, 'data/protected_users.json')
                heal_embed.description = "You are fully recovered! The 'Sick' role has been removed and you received **24 hours of protection** from monster attacks!"
            else:
                heal_embed.description = "You feel much better and are fully recovered! The 'Sick' role has been removed."
            await ctx.send(embed=heal_embed)
        else:
            await asyncio.sleep(2)
            await ctx.send("Unfortunately... the medicine didn't work. You still feel dizzy. Try again next time.")

async def setup(bot):
    """Fungsi setup untuk menambahkan cog ke bot."""
    await bot.add_cog(DuniaHidup(bot))
