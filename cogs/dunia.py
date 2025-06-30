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
        
        embed = discord.Embed(title=f"⚔️ Melawan {self.monster['name']} ⚔️", description=status_text, color=discord.Color.red())
        embed.set_thumbnail(url=self.monster['image_url'])
        embed.add_field(name="❤️ Sisa HP Monster", value=f"`[{hp_bar}]`\n**{self.monster['current_hp']:,} / {self.monster['max_hp']:,}**", inline=False)
        party_status = "\n".join([f"**{p.display_name}**" for p in self.party])
        embed.add_field(name="👥 Party Penyerang", value=party_status, inline=True)
        log_text = "\n".join([f"> {log}" for log in self.battle_log[-5:]]) # Hanya menampilkan 5 log terakhir
        embed.add_field(name="📜 Log Pertarungan", value=log_text, inline=False)
        return embed

    async def update_view(self, interaction: discord.Interaction):
        """Memperbarui pesan interaksi dengan embed dan view terbaru."""
        if self.monster['current_hp'] <= 0:
            embed = self.create_battle_embed(f"🎉 **MONSTER DIKALAHKAN!** 🎉")
            embed.color = discord.Color.gold()
            for item in self.children: item.disabled = True # Menonaktifkan semua tombol
            await interaction.message.edit(embed=embed, view=self)
            self.stop() # Menghentikan view
            await self.cog.handle_monster_defeat(interaction.channel, self.party) # Mengubah dari self.monster_attackers ke self.party
        else:
            embed = self.create_battle_embed(f"Giliran: **{self.get_current_player().display_name}**")
            await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Serang ⚔️", style=discord.ButtonStyle.danger)
    async def attack(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Tombol serangan untuk pertarungan monster."""
        current_player = self.get_current_player()
        if interaction.user != current_player:
            return await interaction.response.send_message("Bukan giliranmu!", ephemeral=True)

        await interaction.response.defer() # Defer respons agar bot tidak timeout

        # Ambil level pengguna dari data level
        level_data = load_json_from_root('data/level_data.json').get(str(interaction.guild.id), {})
        user_level = level_data.get(str(interaction.user.id), {}).get('level', 1)
        
        # Hitung damage berdasarkan level pengguna
        damage = random.randint(50, 150) + (user_level * 20)
        self.monster['current_hp'] -= damage
        self.cog.monster_attackers.add(interaction.user.id) # Menambahkan penyerang ke set

        self.battle_log.append(f"{interaction.user.display_name} menyerang, memberikan **{damage}** damage!")
        
        if self.monster['current_hp'] > 0:
            monster_damage = random.randint(100, 300)
            self.battle_log.append(f"{self.monster['name']} menyerang balik, memberikan **{monster_damage}** damage pada {interaction.user.display_name}!")
        
        # Pindah ke giliran pemain berikutnya
        self.turn_index = (self.turn_index + 1) % len(self.party)
        await self.update_view(interaction)

class DuniaHidup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = set() # Tidak jelas digunakan untuk apa, bisa dihapus jika tidak terpakai
        self.current_monster = None
        self.monster_attack_queue = []
        self.monster_attackers = set() # Set ini digunakan untuk melacak penyerang monster utama
        self.active_anomaly = None
        self.anomaly_end_time = None
        self.sick_users_cooldown = {}
        self.protected_users = load_json_from_root('data/protected_users.json') 
        self.dropped_codes = {}
        self.attacked_users_log = [] # New: Untuk melacak user yang diserang monster
        self.last_event_type = None # New: Untuk melacak jenis event terakhir

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
        self.last_event_type = event_type # Simpan jenis event terakhir
        if event_type == 'monster' and self.monsters_data.get('monsters'): 
            self.attacked_users_log.clear() # Reset log serangan saat monster baru muncul
            await self.spawn_monster()
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

        # --- Peningkatan Tampilan Kemunculan Monster ---
        embed = discord.Embed(
            title=f"🚨 ANCAMAN BARU MUNCUL! 🚨\n**{self.current_monster['name']}**", 
            description=f"___{self.current_monster['story']}___", # Menambahkan underscore untuk italic
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=self.current_monster['image_url'])
        embed.add_field(name="❤️ HP", value=f"**{self.current_monster['current_hp']:,}/{self.current_monster['max_hp']:,}**", inline=True)
        embed.add_field(name="⚔️ Tipe", value=self.current_monster['type'], inline=True)
        # Menambahkan field lokasi jika ada di data monster
        if self.current_monster.get('location'):
            embed.add_field(name="Lokasi Terlihat", value=self.current_monster['location'], inline=True)
        embed.set_footer(text="Gunakan !serangmonster untuk membentuk party dan melawannya!")
        
        await channel.send(f"**Peringatan, para penduduk! Sebuah bayangan menakutkan telah terlihat!**")
        await channel.send(embed=embed)
        await self.schedule_monster_attacks(channel.guild)

    async def schedule_monster_attacks(self, guild):
        """
        Menjadwalkan serangan monster terhadap pengguna yang paling banyak
        mengoleksi EXP + RSWN (top 15).
        """
        level_data = load_json_from_root(f'data/level_data.json').get(str(guild.id), {})
        bank_data = load_json_from_root('data/bank_data.json')

        user_scores = []
        for user_id, user_exp_data in level_data.items():
            member = guild.get_member(int(user_id))
            if not member: # Lewati jika member tidak ditemukan di guild (mungkin sudah keluar)
                continue
            
            exp = user_exp_data.get('exp', 0)
            balance = bank_data.get(user_id, {}).get('balance', 0)
            total_score = exp + balance
            
            # Hanya sertakan user yang memiliki setidaknya EXP atau RSWN
            if total_score > 0:
                user_scores.append((total_score, user_id))

        # Urutkan berdasarkan total score tertinggi
        user_scores.sort(key=lambda x: x[0], reverse=True)
        
        # Ambil hingga 15 pengguna teratas yang memiliki EXP/RSWN
        top_users_ids = [uid for score, uid in user_scores[:15]]

        if not top_users_ids:
            print("No suitable users found to schedule monster attacks (top 15 with EXP/RSWN).")
            return
        
        # Pilih 3 target acak dari top_users_ids (atau kurang jika kurang dari 3 pengguna di daftar)
        num_targets = min(len(top_users_ids), 3)
        targets = random.sample(top_users_ids, num_targets)
        
        now = datetime.utcnow()
        # Jadwalkan serangan dengan waktu yang berbeda untuk setiap target
        self.monster_attack_queue = [
            {'user_id': uid, 'attack_time': (now + timedelta(hours=random.randint(i*4+1, (i+1)*4))).isoformat()} 
            for i, uid in enumerate(targets)
        ]
        print(f"Scheduled monster attacks for: {[guild.get_member(int(uid)).display_name for uid in targets if guild.get_member(int(uid))]}")


    @tasks.loop(minutes=10)
    async def monster_attack_processor(self):
        """Memproses serangan monster yang terjadwal."""
        # Jika tidak ada antrean serangan atau tidak ada monster yang aktif, keluar
        if not self.monster_attack_queue or not self.current_monster: return 
        
        now = datetime.utcnow()
        # Periksa apakah sudah waktunya serangan pertama dalam antrean
        if now < datetime.fromisoformat(self.monster_attack_queue[0]['attack_time']): return
        
        attack = self.monster_attack_queue.pop(0) # Ambil serangan pertama dari antrean
        user_id_to_attack = attack['user_id']

        # Lewati serangan jika pengguna dilindungi
        if str(user_id_to_attack) in self.protected_users: 
            print(f"Skipping monster attack on {user_id_to_attack} (protected).")
            return

        # Dapatkan objek guild dan member
        guild = self.bot.guilds[0] # Asumsi bot hanya di satu guild. Jika tidak, Anda mungkin perlu logika untuk memilih guild yang benar.
        member = guild.get_member(int(user_id_to_attack))
        if not member: 
            print(f"Skipping monster attack: Member {user_id_to_attack} not found in guild.")
            return # Lewati jika member tidak ditemukan di guild

        # Tentukan jumlah EXP dan RSWN yang hilang secara acak
        exp_loss, rswn_loss = random.randint(250, 500), random.randint(250, 500)
        
        # Muat data EXP dan Bank
        level_data = load_json_from_root('data/level_data.json')
        bank_data = load_json_from_root('data/bank_data.json')

        guild_id_str = str(guild.id)
        user_id_str = str(user_id_to_attack)

        # Simpan EXP dan RSWN asli sebelum dikurangi untuk log
        original_exp = level_data.get(guild_id_str, {}).get(user_id_str, {}).get('exp', 0)
        original_rswn = bank_data.get(user_id_str, {}).get('balance', 0)

        # Kurangi EXP pengguna, pastikan tidak kurang dari 0
        level_data.setdefault(guild_id_str, {}).setdefault(user_id_str, {})['exp'] = max(0, original_exp - exp_loss)
        
        # Kurangi RSWN pengguna, pastikan tidak kurang dari 0
        bank_data.setdefault(user_id_str, {})['balance'] = max(0, original_rswn - rswn_loss)
        
        # Simpan perubahan data
        save_json_to_root(level_data, 'data/level_data.json')
        save_json_to_root(bank_data, 'data/bank_data.json')
        
        # Tambahkan ke log serangan
        self.attacked_users_log.append({
            "user_id": user_id_to_attack,
            "display_name": member.display_name,
            "exp_lost": original_exp - level_data[guild_id_str][user_id_str]['exp'], # Actual lost
            "rswn_lost": original_rswn - bank_data[user_id_str]['balance'] # Actual lost
        })

        # Kirim pemberitahuan serangan ke channel yang ditentukan
        channel = self.bot.get_channel(self.event_channel_id)
        if channel:
            # --- Peningkatan Tampilan Serangan Individu ---
            attack_phrases = [
                f"Tiba-tiba, {self.current_monster['name']} melesat keluar dari bayangan dan menerkam!",
                f"Suara gemuruh! {self.current_monster['name']} melancarkan serangan kejutan yang brutal!",
                f"Udara bergetar saat {self.current_monster['name']} melesatkan jurus mematikan!",
                f"Sebuah raungan mengerikan! {self.current_monster['name']} menerkam tanpa ampun!",
                f"Kengerian menyelimuti saat {self.current_monster['name']} menyerang dari balik kegelapan!"
            ]
            chosen_phrase = random.choice(attack_phrases)

            embed = discord.Embed(
                title="⚡ SERANGAN MENDADAK! ⚡", 
                description=f"{chosen_phrase}\n\n**{member.display_name}** ({member.mention}) adalah korbannya!", 
                color=discord.Color.dark_red()
            )
            embed.set_thumbnail(url="https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/An1.jpg") # Thumbnail default untuk serangan monster
            embed.add_field(name="Kerugian", value=f"Kamu kehilangan **{exp_loss} EXP** dan **{rswn_loss} RSWN**!", inline=False)
            embed.set_footer(text="Pertarungan ini belum berakhir...")
            await channel.send(embed=embed)
            print(f"Monster attacked {member.display_name} ({member.id})")

    @commands.command(name="serangmonster")
    async def serangmonster(self, ctx):
        """Memulai sesi pembentukan party untuk menyerang monster."""
        if not self.current_monster: 
            return await ctx.send("There is no monster to attack currently.", delete_after=10)
        
        view = discord.ui.View(timeout=60.0) # View akan nonaktif setelah 60 detik
        party = {ctx.author} # Inisialisasi party dengan pembuat perintah

        embed = discord.Embed(
            title="⚔️ MEMBENTUK PARTY PENYERANG! ⚔️", 
            description=f"**{ctx.author.display_name}** memulai penyerangan terhadap **{self.current_monster['name']}**!\n\nPara pejuang, klik 'Gabung Pertarungan' untuk ikut serta! Waktu 60 detik.", 
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Semakin banyak pejuang, semakin besar peluang kemenangan!")
        
        async def join_callback(interaction: discord.Interaction):
            """Callback untuk tombol 'Gabung Pertarungan'."""
            if interaction.user not in party:
                party.add(interaction.user)
                await interaction.response.send_message(f"{interaction.user.mention} telah bergabung dalam party!", ephemeral=True)
            else:
                await interaction.response.send_message("Kamu sudah bergabung.", ephemeral=True)

        join_button = discord.ui.Button(label="Gabung Pertarungan", style=discord.ButtonStyle.success, emoji="🤝")
        join_button.callback = join_callback
        view.add_item(join_button)
        
        msg = await ctx.send(embed=embed, view=view)
        await asyncio.sleep(60) # Tunggu 60 detik untuk pemain bergabung
        
        try: 
            await msg.delete() # Hapus pesan pembentukan party setelah waktu habis
        except discord.NotFound: 
            pass # Pesan mungkin sudah dihapus secara manual

        if not party: 
            return await ctx.send("Tidak ada yang bergabung dalam party. Monster terus berkeliaran bebas...", delete_after=10)
        
        # Mulai pertarungan dengan party yang terbentuk
        battle_view = MonsterBattleView(self, self.current_monster, party)
        initial_embed = battle_view.create_battle_embed(f"Giliran: **{battle_view.get_current_player().display_name}**")
        await ctx.send(embed=initial_embed, view=battle_view)

    async def handle_monster_defeat(self, channel, party_members): # Mengubah attackers_set menjadi party_members
        """
        Menangani logika setelah monster dikalahkan, termasuk pesan rincian
        dan ancaman event berikutnya.
        """
        reward_rswn, reward_exp = 5000, 5000
        
        bank_data = load_json_from_root('data/bank_data.json')
        level_data = load_json_from_root('data/level_data.json')

        guild_id_str = str(channel.guild.id)
        
        # Distribusikan hadiah kepada para penyerang
        for member in party_members: # Iterasi langsung melalui objek Member di party_members
            user_id_str = str(member.id)
            # Pastikan data ada sebelum menambahkan, jika tidak, setel default
            bank_data.setdefault(user_id_str, {'balance': 0})['balance'] += reward_rswn
            level_data.setdefault(guild_id_str, {}).setdefault(user_id_str, {'exp': 0})['exp'] += reward_exp
        
        save_json_to_root(bank_data, 'data/bank_data.json')
        save_json_to_root(level_data, 'data/level_data.json')
        
        # --- Peningkatan: Pesan Kemenangan (Menggunakan Embed) ---
        win_embed = discord.Embed(
            title=f"🎉 MONSTER DIKALAHKAN! 🎉\n**{self.current_monster['name']}** Telah Tumbang!",
            description=(
                f"Seluruh pejuang telah bersatu dan menunjukkan kekuatan sejati! "
                f"Berkat keberanian **{len(party_members)} pejuang** yang ikut serta, "
                f"ancaman {self.current_monster['name']} berhasil dihentikan!"
            ),
            color=discord.Color.gold()
        )
        win_embed.add_field(
            name="Imbalan Kemenangan", 
            value=f"Setiap pejuang mendapatkan:\n**{reward_exp:,} EXP** 🌟\n**{reward_rswn:,} RSWN** ðŸª™", 
            inline=False
        )
        win_embed.set_thumbnail(url=self.current_monster['image_url']) # Thumbnail monster yang dikalahkan
        win_embed.set_footer(text="Kemenangan ini akan tercatat dalam sejarah!")
        await channel.send(embed=win_embed)


        # --- Peningkatan: Laporan Kerugian (Embed yang Lebih Dramatis) ---
        await asyncio.sleep(3) # Jeda singkat untuk efek dramatis

        if self.attacked_users_log:
            attack_details_list = []
            for log in self.attacked_users_log:
                # Pastikan user masih ada di cache bot
                user_obj = self.bot.get_user(int(log['user_id']))
                user_mention = user_obj.mention if user_obj else log['display_name'] + " (User Tidak Ditemukan)"
                attack_details_list.append(
                    f"**{log['display_name']}** ({user_mention}) "
                    f"kehilangan {log['exp_lost']} EXP dan {log['rswn_lost']} RSWN."
                )
            
            attack_summary_embed = discord.Embed(
                title=f"☠️ LAPORAN KERUGIAN DARI {self.current_monster['name'].upper()} ☠️",
                description=(
                    f"Meskipun monster telah dikalahkan, jejak kehancurannya masih terasa. "
                    f"Beberapa penduduk mengalami kerugian selama serangannya:\n\n"
                    f"{'```diff\n' + '\\n'.join(attack_details_list) + '\\n```'}"
                ),
                color=discord.Color.dark_grey()
            )
            attack_summary_embed.set_thumbnail(url="https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/An2.jpg") # Ilustrasi kerugian/dampak
            attack_summary_embed.set_footer(text="Kerugian ini akan menjadi pengingat untuk selalu waspada.")
            await channel.send(embed=attack_summary_embed)
        else:
            await channel.send("Untungnya, tidak ada penduduk yang diserang oleh monster ini kali ini! Keberuntungan ada di pihak kita.")

        # --- Peningkatan: Pesan Ancaman Berikutnya (Embed yang Lebih Serius) ---
        await asyncio.sleep(5) # Jeda sebentar sebelum pesan ancaman

        threat_messages = [
            {"title": "🌘 ENERGI GELAP BERGELORA! 🌘",
             "description": "Kemenangan ini hanyalah selingan. Kekuatan kuno di balik bayang-bayang mulai bergerak. Udara terasa berat, dan bisikan-bisikan jahat menembus kegelapan. Sesuatu yang tak terbayangkan akan segera terungkap...",
             "image": "https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/An3.jpg", # Contoh gambar ancaman gelap
             "color": discord.Color.darker_grey()},
            {"title": "🌪️ GERBANG REALITAS RETAK! 🌪️",
             "description": "Retakan di dimensi mulai melebar. Monster-monster dari alam lain, yang lebih kejam dan kuat, mengendus dunia kita. Siapkan diri, para pejuang, realitas akan segera berputar di luar kendali!",
             "image": "https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/An4.jpg", # Contoh gambar anomali/retakan
             "color": discord.Color.blurple()},
            {"title": "💀 KUTUKAN KUNO TERBANGUN! 💀",
             "description": "Darah monster yang tumpah telah membangunkan kutukan yang telah lama tertidur. Energi negatif menyebar, menginfeksi tanah dan jiwa. Wabah, keputusasaan, dan monster-monster mengerikan baru akan menyelimuti dunia. Tidak ada tempat untuk bersembunyi!",
             "image": "https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/An5.jpg", # Contoh gambar kutukan/wabah
             "color": discord.Color.dark_purple()}
        ]
        
        # Pilih satu ancaman secara acak
        next_threat_event = random.choice(threat_messages)

        threat_embed = discord.Embed(
            title=next_threat_event['title'],
            description=next_threat_event['description'] + "\n\n**Bersiaplah. Event berikutnya akan segera datang...**",
            color=next_threat_event['color']
        )
        threat_embed.set_thumbnail(url=next_threat_event['image'])
        threat_embed.set_footer(text="Waspadalah! Takdir dunia ada di tanganmu.")
        await channel.send(embed=threat_embed)


        # Reset status monster dan antrean serangan serta log serangan
        self.current_monster = None
        self.monster_attack_queue = []
        self.monster_attackers = set()
        self.attacked_users_log = [] # Pastikan log serangan direset setelah cerita
        self.last_event_type = None # Reset jenis event terakhir

    async def trigger_anomaly(self):
        """Memicu event anomali dunia."""
        anomaly = random.choice(self.anomalies_data)
        self.active_anomaly = anomaly
        self.anomaly_end_time = datetime.utcnow() + timedelta(seconds=anomaly['duration_seconds'])
        
        channel = self.bot.get_channel(self.event_channel_id)
        if not channel: return
        
        embed = discord.Embed(title=f"{anomaly['emoji']} ANOMALI: {anomaly['name']} {anomaly['emoji']}", description=anomaly['description'], color=discord.Color.from_str(anomaly['color']))
        embed.set_thumbnail(url=anomaly['thumbnail_url'])
        await channel.send(embed=embed)
        
        if anomaly['type'] == 'code_drop': 
            self.bot.loop.create_task(self.code_dropper(anomaly['duration_seconds']))
        elif anomaly['type'] == 'sickness_plague': 
            await self.start_sickness_plague(channel.guild)

        # Tunggu sampai anomali berakhir
        await asyncio.sleep(anomaly['duration_seconds'])
        await channel.send(f"Anomali **{anomaly['name']}** telah berakhir.")
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
                await channel.send(f"☄️ **HUJAN METEOR!** Sebuah kode jatuh! Ketik `!klaim {code}` untuk hadiah!")
            
            self.bot.loop.create_task(self.expire_code(code)) # Jadwalkan penghapusan kode

    async def expire_code(self, code):
        """Menghapus kode yang dijatuhkan setelah waktu tertentu."""
        await asyncio.sleep(120) # Kode akan kadaluarsa dalam 2 menit
        if code in self.dropped_codes: 
            del self.dropped_codes[code]
            channel = self.bot.get_channel(self.event_channel_id)
            if channel:
                # Opsi: Beri tahu bahwa kode telah kadaluarsa di channel
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
        
        embed = discord.Embed(title=f"❓ TANTANGAN DARI {quiz_monster['name'].upper()} ❓", description=quiz_monster['intro'], color=discord.Color.dark_purple())
        embed.set_thumbnail(url=quiz_monster['image_url'])
        embed.add_field(name="Riddle:", value=f"**{quiz_monster['riddle']}**\n\n_Hint: {quiz_monster['hint']}_")
        embed.set_footer(text="Answer in this channel! 5 minutes remaining.")
        await channel.send(embed=embed)

        def check(m): 
            # Pastikan pesan berasal dari channel yang sama, bukan bot, dan jawaban cocok
            return m.channel == channel and not m.author.bot and m.content.lower() == quiz_monster['answer'].lower()

        try:
            winner_msg = await self.bot.wait_for('message', timeout=300.0, check=check) # Tunggu 5 menit untuk jawaban
            await channel.send(f"🧠 **Jenius!** {winner_msg.author.mention} answered correctly and saved the server from the curse! You received a great reward!")
            
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
            # Anda bisa menambahkan efek negatif di sini jika tidak ada yang menjawab
            # Contoh: Mengurangi sejumlah kecil EXP dari beberapa pengguna acak di server
        
        self.active_anomaly = None # Reset anomali setelah kuis selesai

    async def start_sickness_plague(self, guild):
        """Menyebarkan wabah penyakit ke pengguna aktif."""
        level_data = load_json_from_root('data/level_data.json').get(str(guild.id), {})
        # Filter pengguna yang aktif dalam 3 hari terakhir dan masih ada di guild
        active_users = [
            uid for uid, data in level_data.items() 
            if 'last_active' in data and datetime.utcnow() - datetime.fromisoformat(data['last_active']) < timedelta(days=3)
            and guild.get_member(int(uid)) # Pastikan member masih ada di guild
        ]
        
        num_to_infect = min(len(active_users), random.randint(3, 7)) # Infeksi antara 3 hingga 7 pengguna
        if num_to_infect == 0: return # Tidak ada yang bisa diinfeksi

        infected_users_ids = random.sample(active_users, num_to_infect)
        
        role = guild.get_role(self.sick_role_id)
        if not role: 
            print(f"Warning: Sick role with ID {self.sick_role_id} not found in guild {guild.name}.")
            return # Tidak ada role sakit

        infected_mentions = []
        for user_id in infected_users_ids:
            member = guild.get_member(int(user_id))
            if member:
                await member.add_roles(role)
                infected_mentions.append(member.mention)
        
        channel = self.bot.get_channel(self.event_channel_id)
        if channel and infected_mentions:
            await channel.send(f"😷 **WABAH MENYEBAR!** {', '.join(infected_mentions)} telah jatuh sakit. Interaksi mereka akan terbatas. Cepat cari obat di `!shop`!")

    @commands.Cog.listener()
    async def on_message(self, message):
        """
        Listener untuk setiap pesan. Digunakan untuk logika cooldown pesan bagi pengguna yang sakit.
        PENTING: Listener ini TIDAK memanggil `bot.process_commands(message)`
        karena sudah ditangani secara sentral di `on_message` global di `main.py`.
        """
        # Abaikan pesan dari bot itu sendiri atau pesan di luar guild (misalnya DM)
        if message.author.bot or not message.guild:
            return
        
        user_id = message.author.id
        sick_role = message.guild.get_role(self.sick_role_id)

        # Logika untuk role "sakit" dan cooldown pesan
        if sick_role and sick_role in message.author.roles:
            now = datetime.utcnow()
            last_message_time = self.sick_users_cooldown.get(user_id)
            if last_message_time:
                cooldown = timedelta(minutes=self.sickness_cooldown_minutes)
                # Jika waktu sejak pesan terakhir kurang dari cooldown
                if now - last_message_time < cooldown:
                    time_left = cooldown - (now - last_message_time)
                    try:
                        # Hapus pesan pengguna dan kirim DM peringatan
                        await message.delete()
                        await message.author.send(
                            f"You are sick and still weak... You need to rest for **{int(time_left.total_seconds())} seconds** before you can speak again.", 
                            delete_after=60 # DM akan terhapus sendiri setelah 60 detik
                        )
                    except (discord.Forbidden, discord.NotFound): 
                        # Abaikan jika bot tidak bisa menghapus pesan (izin) atau mengirim DM (privasi user)
                        pass 
                    return # Hentikan pemrosesan pesan lebih lanjut jika user dalam cooldown
            self.sick_users_cooldown[user_id] = now # Update waktu pesan terakhir pengguna

        # Tidak ada `await self.bot.process_commands(message)` di sini!

    @commands.command(name="minumobat")
    async def minumobat(self, ctx):
        """Menggunakan 'Kotak Obat Misterius' untuk mencoba menyembuhkan penyakit."""
        user_id_str = str(ctx.author.id)
        sick_role = ctx.guild.get_role(self.sick_role_id)
        
        if not sick_role or sick_role not in ctx.author.roles:
            return await ctx.send("You are not sick, no need to drink medicine.")
        
        inventory_data = load_json_from_root('data/inventory.json')
        user_inventory = inventory_data.setdefault(user_id_str, [])
        
        # Cari Kotak Obat Misterius di inventaris pengguna
        medicine_box = next((item for item in user_inventory if item.get('type') == 'gacha_medicine_box'), None)
        if not medicine_box: 
            return await ctx.send("You don't have a Mysterious Medicine Box. Buy one from `!shop` first.")
        
        # Hapus satu Kotak Obat Misterius dari inventaris
        user_inventory.remove(medicine_box)
        save_json_to_root(inventory_data, 'data/inventory.json')
        
        embed = discord.Embed(title="💊 Meracik Obat...", description="Kamu membuka Kotak Obat Misterius dan mulai mengocoknya...", color=discord.Color.light_grey())
        # Placeholder GIF, Anda bisa ganti dengan URL GIF yang Anda buat
        embed.set_thumbnail(url="https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/gif.gif") 
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(3) # Simulasi proses meracik

        # Piligifbat secara acak berdasarkan peluang
        choices = [med['name'] for med in self.medicines_data]
        weights = [med['chance'] for med in self.medicines_data]
        chosen_medicine_name = random.choices(choices, weights=weights, k=1)[0]
        chosen_medicine = next(med for med in self.medicines_data if med['name'] == chosen_medicine_name)

        result_embed = discord.Embed(title="Hasil Gacha Obat", description=f"Kamu mendapatkan... **{chosen_medicine['name']}**!", color=discord.Color.from_str(chosen_medicine['color']))
        result_embed.add_field(name="Efek", value=chosen_medicine['effect_desc'])
        await msg.edit(embed=result_embed)
        
        # Coba sembuhkan berdasarkan peluang obat
        if random.randint(1, 100) <= chosen_medicine['heal_chance']:
            await asyncio.sleep(2)
            heal_embed = discord.Embed(title="✨ Obat Bekerja! ✨", color=discord.Color.green())
            await ctx.author.remove_roles(sick_role) # Hapus role sakit dari pengguna
            if str(ctx.author.id) in self.sick_users_cooldown: 
                del self.sick_users_cooldown[str(ctx.author.id)] # Reset cooldown sakit
            
            if chosen_medicine['heal_chance'] == 100: # Jika obat memberikan perlindungan penuh
                expiry = datetime.utcnow() + timedelta(hours=24)
                self.protected_users[user_id_str] = expiry.isoformat()
                save_json_to_root(self.protected_users, 'data/protected_users.json')
                heal_embed.description = "Kamu sembuh total! Role 'Sakit' telah dilepas dan kamu mendapat **perlindungan 24 jam** dari serangan monster!"
            else:
                heal_embed.description = "Kamu merasa jauh lebih baik dan sembuh total! Role 'Sakit' telah dilepas."
            await ctx.send(embed=heal_embed)
        else:
            await asyncio.sleep(2)
            await ctx.send("Sayang sekali... obatnya tidak bekerja. Kamu masih merasa pusing. Coba lagi lain kali.")

async def setup(bot):
    """Fungsi setup untuk menambahkan cog ke bot."""
    await bot.add_cog(DuniaHidup(bot))
