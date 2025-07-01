import discord
from discord.ext import commands, tasks
import json
import random
import asyncio
import os
from datetime import datetime, timedelta, time
import string
import pytz # Import pytz untuk zona waktu

# --- Helper Functions (Wajib ada di awal) ---
def load_json_from_root(file_path):
    """Memuat data JSON dari file yang berada di root direktori proyek."""
    try:
        # Mengambil direktori dasar (root) dari bot
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        full_path = os.path.join(base_dir, file_path)
        # Pastikan direktori ada sebelum mencoba membaca
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Critical Warning: Failed to load or corrupted file -> {file_path}")
        # Mengembalikan struktur data default tergantung jenis file
        if 'users' in file_path or 'inventory' in file_path or 'protected_users' in file_path or 'sick_users_cooldown' in file_path: 
            return {}
        elif any(k in file_path for k in ['monsters', 'anomalies', "medicines"]): 
            # Untuk file seperti monsters.json, anomalies.json, medicines.json yang berisi daftar
            return {'monsters': [], 'anomalies': [], 'medicines': []}.get(os.path.basename(file_path).replace('.json', ''), []) # Modified to return empty list or specific dict structure
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
        self.battle_log = ["Pertarungan dimulai! Darah akan tertumpah!"]

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
        
        embed = discord.Embed(title=f"⚔️ MELAWAN {self.monster['name'].upper()} YANG MENGERIKAN! ⚔️", description=status_text, color=discord.Color.red())
        embed.set_thumbnail(url=self.monster['image_url'])
        embed.add_field(name="❤️ Sisa Kehidupan Monster", value=f"`[{hp_bar}]`\n**{self.monster['current_hp']:,} / {self.monster['max_hp']:,}**", inline=False)
        party_status = "\n".join([f"**{p.display_name}**" for p in self.party])
        embed.add_field(name="👥 Pasukan Nekat", value=party_status, inline=True)
        log_text = "\n".join([f"> {log}" for log in self.battle_log[-5:]]) # Hanya menampilkan 5 log terakhir
        embed.add_field(name="📜 Bisikan Pertarungan", value=log_text, inline=False)
        return embed

    async def update_view(self, interaction: discord.Interaction):
        """Memperbarui pesan interaksi dengan embed dan view terbaru."""
        if self.monster['current_hp'] <= 0:
            embed = self.create_battle_embed(f"🎉 **MONSTER INI TELAH TIADA!** 🎉")
            embed.color = discord.Color.gold()
            for item in self.children: item.disabled = True # Menonaktifkan semua tombol
            await interaction.message.edit(embed=embed, view=self)
            self.stop() # Menghentikan view
            await self.cog.handle_monster_defeat(interaction.channel, self.party) # Mengubah dari self.monster_attackers ke self.party
        else:
            embed = self.create_battle_embed(f"Saatnya {self.get_current_player().display_name} menghadapi kengerian ini!")
            await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Serang ⚔️", style=discord.ButtonStyle.danger)
    async def attack(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Tombol serangan untuk pertarungan monster."""
        current_player = self.get_current_player()
        if interaction.user != current_player:
            return await interaction.response.send_message("Bukan giliranmu, nyawa lain sedang dipertaruhkan!", ephemeral=True)

        await interaction.response.defer() # Defer respons agar bot tidak timeout

        # Ambil level pengguna dari data level
        level_data = load_json_from_root('data/level_data.json').get(str(interaction.guild.id), {})
        user_level = level_data.get(str(interaction.user.id), {}).get('level', 1)
        
        # Hitung damage berdasarkan level pengguna
        damage = random.randint(50, 150) + (user_level * 20)
        self.monster['current_hp'] -= damage
        self.cog.monster_attackers.add(interaction.user.id) # Menambahkan penyerang ke set

        self.battle_log.append(f"{interaction.user.display_name} mengayunkan serangan maut, menimbulkan **{damage}** luka!")
        
        if self.monster['current_hp'] > 0:
            monster_damage = random.randint(100, 300)
            self.battle_log.append(f"Raungan mengerikan! {self.monster['name']} membalas, menghantam {interaction.user.display_name} sebesar **{monster_damage}** kerusakan!")
        
        # Pindah ke giliran pemain berikutnya
        self.turn_index = (self.turn_index + 1) % len(self.party)
        await self.update_view(interaction)

# ---
## DuniaHidup Cog
# ---

class DuniaHidup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = set()
        self.current_monster = None
        self.monster_attack_queue = []
        self.monster_attackers = set()
        self.active_anomaly = None
        self.anomaly_end_time = None
        self.sick_users_cooldown = load_json_from_root('data/sick_users_cooldown.json') 
        self.protected_users = load_json_from_root('data/protected_users.json') 
        self.dropped_codes = {}
        self.attacked_users_log = []
        self.last_event_type = None

        # Tambahkan flag untuk hukuman quiz
        self.quiz_punishment_active = False
        self.quiz_punishment_details = {}

        # Ganti dengan ID channel pengumuman di server Discord Anda
        self.event_channel_id = 765140300145360896 
        # Ganti dengan ID role 'Sakit' di server Discord Anda
        self.sick_role_id = 1388744189063200860 
        self.sickness_cooldown_minutes = 1 # Cooldown pesan normal
        self.sickness_duration_minutes = 60 # Durasi sakit default 60 menit (untuk anomali wabah normal)
        self.sickness_duration_minutes_quiz = 300 # Durasi sakit akibat kuis (5 jam = 300 menit)

        # --- PENTING: SET ID GUILD UTAMA ANDA DI SINI ---
        self.main_guild_id = 765138959625486357 # ID Server Utama Anda

        # Memuat data dari file JSON
        # Menyesuaikan inisialisasi agar sesuai dengan load_json_from_root yang diperbarui
        self.monsters_data = load_json_from_root('data/monsters.json')
        if isinstance(self.monsters_data, dict) and 'monsters' in self.monsters_data:
             self.monsters_data = self.monsters_data # Keep if it's already structured correctly
        else:
            print("Warning: monsters.json might be malformed, defaulting to empty list.")
            self.monsters_data = {'monsters': [], 'monster_quiz': []} # Default to a dict with empty lists
            
        self.anomalies_data = load_json_from_root('data/world_anomalies.json')
        if isinstance(self.anomalies_data, dict) and 'anomalies' in self.anomalies_data:
            self.anomalies_data = self.anomalies_data.get('anomalies', [])
        else:
            print("Warning: world_anomalies.json might be malformed, defaulting to empty list.")
            self.anomalies_data = []

        self.medicines_data = load_json_from_root('data/medicines.json')
        if isinstance(self.medicines_data, dict) and 'medicines' in self.medicines_data:
            self.medicines_data = self.medicines_data.get('medicines', [])
        else:
            print("Warning: medicines.json might be malformed, defaulting to empty list.")
            self.medicines_data = []

        # Memulai tasks loop
        self.world_event_loop.start()
        self.monster_attack_processor.start()
        self.protection_cleaner.start()
        self.sick_status_cleaner.start() 


    def cog_unload(self):
        """Dipanggil saat cog dibongkar."""
        self.world_event_loop.cancel()
        self.monster_attack_processor.cancel()
        self.protection_cleaner.cancel()
        self.sick_status_cleaner.cancel()

    @tasks.loop(minutes=30)
    async def sick_status_cleaner(self):
        """Membersihkan status 'sakit' dari pengguna yang sudah melewati durasinya."""
        now = datetime.utcnow()
        
        await self.bot.wait_until_ready()

        # --- Menggunakan self.main_guild_id untuk mendapatkan guild ---
        guild = self.bot.get_guild(self.main_guild_id) 
        if not guild:
            print(f"sick_status_cleaner: Guild dengan ID {self.main_guild_id} tidak ditemukan. Melewatkan pembersihan status sakit.")
            return

        sick_role = guild.get_role(self.sick_role_id)
        if not sick_role: 
            print(f"sick_status_cleaner: Role 'Sakit' dengan ID {self.sick_role_id} tidak ditemukan di guild {guild.name}.")
            return

        users_to_check = list(self.sick_users_cooldown.keys()) 
        
        for user_id_str in users_to_check:
            user_data = self.sick_users_cooldown.get(user_id_str)
            if not user_data: continue

            if not isinstance(user_data.get('sickness_end_time'), str):
                print(f"Warning: 'sickness_end_time' for user {user_id_str} is not a string. Skipping cleanup for this user.")
                continue

            sickness_end_time = datetime.fromisoformat(user_data['sickness_end_time'])
            
            if now >= sickness_end_time:
                member = guild.get_member(int(user_id_str))
                if member and sick_role in member.roles:
                    try:
                        await member.remove_roles(sick_role)
                        channel = self.bot.get_channel(self.event_channel_id)
                        if channel:
                            await channel.send(f"🎉 **{member.display_name}** ({member.mention}) telah pulih dari wabah penyakit!")
                        print(f"{member.display_name} sembuh dari sakit.")
                    except discord.Forbidden:
                        print(f"Bot tidak memiliki izin untuk menghapus role 'Sakit' dari {member.display_name}.")
                    except Exception as e:
                        print(f"Error saat membersihkan role sakit dari {member.display_name}: {e}")
                
                del self.sick_users_cooldown[user_id_str]
        
        save_json_to_root(self.sick_users_cooldown, 'data/sick_users_cooldown.json')


    @tasks.loop(hours=random.randint(3, 6)) # Event dunia terjadi setiap 3-6 jam
    async def world_event_loop(self):
        """Memulai event dunia secara berkala."""
        await self.bot.wait_until_ready()
        
        guild = self.bot.get_guild(self.main_guild_id)
        if not guild:
            print(f"world_event_loop: Guild dengan ID {self.main_guild_id} tidak ditemukan. Melewatkan event dunia.")
            return

        if self.current_monster or self.active_anomaly: return

        event_type = random.choice(['monster', 'anomaly', 'monster_quiz'])
        self.last_event_type = event_type
        # Pastikan monsters_data diinisialisasi sebagai dict dengan key 'monsters' dan 'monster_quiz'
        if event_type == 'monster' and self.monsters_data and self.monsters_data.get('monsters'): 
            self.attacked_users_log.clear()
            await self.spawn_monster()
        elif event_type == 'anomaly' and self.anomalies_data: await self.trigger_anomaly()
        elif event_type == 'monster_quiz' and self.monsters_data and self.monsters_data.get('monster_quiz'): await self.trigger_monster_quiz()
        else:
            print(f"Warning: Not enough data for event type {event_type} or data is malformed.")


    @tasks.loop(minutes=30)
    async def protection_cleaner(self):
        """Membersihkan perlindungan pengguna yang sudah kadaluarsa."""
        now = datetime.utcnow()
        # Membersihkan perlindungan normal
        expired_users = [uid for uid, expiry in list(self.protected_users.items()) if now >= datetime.fromisoformat(expiry)]
        for uid in expired_users:
            del self.protected_users[uid]
        if expired_users: save_json_to_root(self.protected_users, 'data/protected_users.json')

        # Membersihkan hukuman kuis jika sudah kadaluarsa
        if self.quiz_punishment_active and self.quiz_punishment_details.get('end_time'):
            if now >= datetime.fromisoformat(self.quiz_punishment_details['end_time']):
                self.quiz_punishment_active = False
                self.quiz_punishment_details = {}
                channel = self.bot.get_channel(self.event_channel_id)
                if channel:
                    await channel.send("✅ **Dampak kegagalan kuis telah berakhir.** Server kembali ke keadaan normal. Untuk sementara...")
                print("Hukuman kuis telah berakhir.")


    async def spawn_monster(self):
        """Memunculkan monster baru di channel event."""
        # Ensure 'monsters' key exists and is a list
        if not self.monsters_data or not self.monsters_data.get('monsters'):
            print("No monster data available to spawn.")
            return

        self.current_monster = random.choice(self.monsters_data['monsters']).copy()
        self.current_monster['current_hp'] = self.current_monster['max_hp']
        self.monster_attackers.clear()
        channel = self.bot.get_channel(self.event_channel_id)
        if not channel: return

        embed = discord.Embed(
            title=f"🚨 KABAR BURUK! SESUATU MUNCUL! 🚨\n**{self.current_monster['name'].upper()}**", 
            description=f"___{self.current_monster['story']}___",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=self.current_monster['image_url'])
        embed.add_field(name="❤️ NYAWA", value=f"**{self.current_monster['current_hp']:,}/{self.current_monster['max_hp']:,}**", inline=True)
        embed.add_field(name="⚔️ WUJUD", value=self.current_monster['type'], inline=True)
        if self.current_monster.get('location'):
            embed.add_field(name="Teror Terlihat di", value=self.current_monster['location'], inline=True)
        embed.set_footer(text="Gunakan !serangmonster untuk berani mati dan melawannya!")
        
        await channel.send(f"**PERINGATAN, PARA PENDUDUK YANG MALANG! BAYANGAN KEMATIAN MENGHAMPIRI!**")
        await channel.send(embed=embed)
        guild = self.bot.get_guild(self.main_guild_id)
        if guild:
            await self.schedule_monster_attacks(guild)
        else:
            print(f"Warning: Could not find main guild {self.main_guild_id} to schedule monster attacks.")


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
            if not member:
                continue
            
            exp = user_exp_data.get('exp', 0)
            balance = bank_data.get(user_id, {}).get('balance', 0)
            total_score = exp + balance
            
            if total_score > 0:
                user_scores.append((total_score, user_id))

        user_scores.sort(key=lambda x: x[0], reverse=True)
        
        num_targets_base = 3
        if self.quiz_punishment_active and self.quiz_punishment_details.get('type') == 'increased_attack':
            num_targets = min(len(user_scores), num_targets_base + self.quiz_punishment_details.get('extra_targets', 5))
        else:
            num_targets = min(len(user_scores), num_targets_base)
        
        top_users_ids = [uid for score, uid in user_scores[:num_targets]]
        
        if not top_users_ids:
            print("Tidak ada target layak untuk serangan monster (top EXP/RSWN). Dunia ini terlalu aman...")
            return
        
        targets = random.sample(top_users_ids, min(len(top_users_ids), num_targets))
        
        now = datetime.utcnow()
        self.monster_attack_queue = [
            {'user_id': uid, 'attack_time': (now + timedelta(hours=random.randint(i*4+1, (i+1)*4))).isoformat()} 
            for i, uid in enumerate(targets)
        ]
        print(f"Serangan monster dijadwalkan untuk: {[guild.get_member(int(uid)).display_name for uid in targets if guild.get_member(int(uid))]}")


    @tasks.loop(minutes=10)
    async def monster_attack_processor(self):
        """Memproses serangan monster yang terjadwal."""
        if not self.monster_attack_queue or not self.current_monster: return 
        
        now = datetime.utcnow()
        if self.monster_attack_queue and now < datetime.fromisoformat(self.monster_attack_queue[0]['attack_time']): return
        
        if not self.monster_attack_queue: # Add check for empty queue after popping
            return

        attack = self.monster_attack_queue.pop(0)
        user_id_to_attack = attack['user_id']

        if str(user_id_to_attack) in self.protected_users: 
            print(f"Melewatkan serangan monster pada {user_id_to_attack} (dilindungi).")
            return

        guild = self.bot.get_guild(self.main_guild_id)
        if not guild:
            print(f"monster_attack_processor: Guild dengan ID {self.main_guild_id} tidak ditemukan. Melewatkan serangan monster.")
            return

        member = guild.get_member(int(user_id_to_attack))
        if not member: 
            print(f"Melewatkan serangan monster: Anggota {user_id_to_attack} tidak ditemukan di guild.")
            return

        loss_multiplier = 1
        if self.quiz_punishment_active and self.quiz_punishment_details.get('type') == 'increased_attack':
            loss_multiplier = self.quiz_punishment_details.get('loss_multiplier', 2)

        exp_loss = random.randint(250, 500) * loss_multiplier
        rswn_loss = random.randint(250, 500) * loss_multiplier
        
        level_data = load_json_from_root('data/level_data.json')
        bank_data = load_json_from_root('data/bank_data.json')

        guild_id_str = str(guild.id)
        user_id_str = str(user_id_to_attack)

        original_exp = level_data.get(guild_id_str, {}).get(user_id_str, {}).get('exp', 0)
        original_rswn = bank_data.get(user_id_str, {}).get('balance', 0)

        level_data.setdefault(guild_id_str, {}).setdefault(user_id_str, {})['exp'] = max(0, original_exp - exp_loss)
        bank_data.setdefault(user_id_str, {})['balance'] = max(0, original_rswn - rswn_loss)
        
        save_json_to_root(level_data, 'data/level_data.json')
        save_json_to_root(bank_data, 'data/bank_data.json')
        
        self.attacked_users_log.append({
            "user_id": user_id_to_attack,
            "display_name": member.display_name,
            "exp_lost": original_exp - level_data[guild_id_str][user_id_str]['exp'],
            "rswn_lost": original_rswn - bank_data[user_id_str]['balance']
        })

        channel = self.bot.get_channel(self.event_channel_id)
        if channel:
            attack_phrases = [
                f"Tiba-tiba, {self.current_monster['name']} melesat keluar dari bayangan dan menerkam!",
                f"Suara gemuruh memekakkan telinga! {self.current_monster['name']} melancarkan serangan kejutan yang brutal dan mematikan!",
                f"Udara bergetar, jiwa-jiwa berteriak saat {self.current_monster['name']} melesatkan jurus mematikan tak terhentikan!",
                f"Sebuah raungan mengerikan menggema! {self.current_monster['name']} menerkam tanpa ampun, tanpa belas kasihan!",
                f"Kengerian menyelimuti saat {self.current_monster['name']} menyerang dari balik kegelapan, merenggut semua harapan!"
            ]
            chosen_phrase = random.choice(attack_phrases)

            embed = discord.Embed(
                title="⚡ SERANGAN BIADAB! ⚡", 
                description=f"{chosen_phrase}\n\n**{member.display_name}** ({member.mention}) ADALAH KORBANNYA! RASAKAN KESENGSARAANNYA!", 
                color=discord.Color.dark_red()
            )
            embed.set_thumbnail(url="https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/An1.jpg")
            embed.add_field(name="KERUGIAN HARTA DAN JIWA", value=f"Kamu kehilangan **{exp_loss} EXP** dan **{rswn_loss} RSWN**! Merana dalam penyesalan!", inline=False)
            embed.set_footer(text="Pertarungan ini belum berakhir... Ini baru permulaan dari kehancuranmu!")
            await channel.send(embed=embed)
            print(f"Monster menyerang {member.display_name} ({member.id})")

    @commands.command(name="serangmonster")
    async def serangmonster(self, ctx):
        """Memulai sesi pembentukan party untuk menyerang monster."""
        if not self.current_monster: 
            return await ctx.send("Tidak ada monster yang mengintai saat ini. Nikmati ketenanganmu selagi bisa...", delete_after=10)
        
        view = discord.ui.View(timeout=60.0)
        party = {ctx.author}

        embed = discord.Embed(
            title="⚔️ AJAK KAWANMU MENGHADAPI TEROR! ⚔️",
            description=f"**{ctx.author.display_name}** dengan berani mengajakmu menghadapi **{self.current_monster['name']}**!\n\nPara pemberani, klik 'Gabung Pertarungan' untuk ikut serta! Waktu 60 detik untuk memutuskan takdirmu!\n\n**Gunakan perintah:** `!serangmonster`",
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Semakin banyak yang berjuang, semakin besar peluang peluang kemenanganmu... atau kematianmu bersama!")
        
        async def join_callback(interaction: discord.Interaction):
            if interaction.user not in party:
                party.add(interaction.user)
                await interaction.response.send_message(f"{interaction.user.mention} telah melangkah menuju takdirnya!", ephemeral=True)
            else:
                await interaction.response.send_message("Kau sudah di sini, siap mati.", ephemeral=True)

        join_button = discord.ui.Button(label="Gabung Pertarungan", style=discord.ButtonStyle.success, emoji="🤝")
        join_button.callback = join_callback
        view.add_item(join_button)
        
        msg = await ctx.send(embed=embed, view=view)
        await asyncio.sleep(60)
        
        try: 
            await msg.delete()
        except discord.NotFound: 
            pass

        if not party: 
            return await ctx.send("Tidak ada yang berani maju. Monster terus berkeliaran bebas, menebar teror...", delete_after=10)
        
        battle_view = MonsterBattleView(self, self.current_monster, party)
        initial_embed = battle_view.create_battle_embed(f"Saatnya {battle_view.get_current_player().display_name} menghadapi kengerian ini!")
        await ctx.send(embed=initial_embed, view=battle_view)

    async def handle_monster_defeat(self, channel, party_members):
        """
        Menangani logika setelah monster dikalahkan, termasuk pesan rincian
        dan ancaman event berikutnya.
        """
        reward_rswn, reward_exp = 5000, 5000
        
        bank_data = load_json_from_root('data/bank_data.json')
        level_data = load_json_from_root('data/level_data.json')

        guild_id_str = str(channel.guild.id)
        
        for member in party_members:
            user_id_str = str(member.id)
            bank_data.setdefault(user_id_str, {'balance': 0})['balance'] += reward_rswn
            level_data.setdefault(guild_id_str, {}).setdefault(user_id_str, {'exp': 0})['exp'] += reward_exp
        
        save_json_to_root(bank_data, 'data/bank_data.json')
        save_json_to_root(level_data, 'data/level_data.json')
        
        win_embed = discord.Embed(
            title=f"🎉 TEROR BERAKHIR! 🎉\n**{self.current_monster['name'].upper()}** TELAH TUMBANG!",
            description=(
                f"Kengerian ini telah usai! Para pecundang bersatu dan menunjukkan kekuatan yang tak terduga! "
                f"Berkat keberanian **{len(party_members)} jiwa yang putus asa**, "
                f"ancaman {self.current_monster['name']} berhasil dihentikan, untuk sementara waktu!"
            ),
            color=discord.Color.gold()
        )
        win_embed.add_field(
            name="IMBALAN ATAS PENGORBANANMU", 
            value=f"Setiap yang selamat mendapatkan:\n**{reward_exp:,} EXP** 🌟\n**{reward_rswn:,} RSWN** ðŸª™", 
            inline=False
        )
        win_embed.set_thumbnail(url=self.current_monster['image_url'])
        win_embed.set_footer(text="Kemenangan ini hanya menunda kehancuran total...")
        await channel.send(embed=win_embed)


        await asyncio.sleep(3)

        if self.attacked_users_log:
            attack_details_list = []
            for log in self.attacked_users_log:
                user_obj = self.bot.get_user(int(log['user_id']))
                user_mention = user_obj.mention if user_obj else log['display_name'] + " (Jiwa yang Hilang)"
                attack_details_list.append(
                    f"**{log['display_name']}** ({user_mention}) "
                    f"kehilangan {log['exp_lost']} EXP dan {log['rswn_lost']} RSWN. Mereka tidak akan melupakan rasa sakit ini."
                )
            
            attack_summary_embed = discord.Embed(
                title=f"☠️ LAPORAN PENDERITAAN DARI {self.current_monster['name'].upper()} ☠️",
                description=(
                    f"Meskipun monster telah dikalahkan, jejak kehancurannya masih terasa. "
                    f"Beberapa penduduk mengalami kerugian yang tak terbayangkan selama serangannya:\n\n"
                    f"{'```diff\n' + '\\n'.join(attack_details_list) + '\\n```'}"
                ),
                color=discord.Color.dark_grey()
            )
            attack_summary_embed.set_thumbnail(url="https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/An2.jpg")
            attack_summary_embed.set_footer(text="Dunia ini tidak akan pernah sama lagi. Bersiaplah untuk yang terburuk.")
            await channel.send(embed=attack_summary_embed)
        else:
            await channel.send("Entah somehow, monster ini gagal menimbulkan kerusakan fatal! Keberuntungan sesaat ada di pihak kita, tapi jangan lengah!")

        await asyncio.sleep(5)

        threat_messages = [
            {"title": "🌘 ENERGI GELAP BERGELORA! 🌘",
             "description": "Kemenangan ini hanyalah selingan. Kekuatan kuno di balik bayang-bayang mulai bergerak. Udara terasa berat, dan bisikan-bisikan jahat menembus kegelapan. Sesuatu yang tak terbayangkan akan segera terungkap, menyeretmu ke dalam jurang kehampaan...",
             "image": "https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/An3.jpg",
             "color": discord.Color.darker_grey()},
            {"title": "🌪️ GERBANG REALITAS RETAK! 🌪️",
             "description": "Retakan di dimensi mulai melebar. Monster-monster dari alam lain, yang lebih kejam dan kuat, mengendus dunia kita. Siapkan diri, para pejuang, realitas akan segera berputar di luar kendali, menarikmu ke dalam kekosongan!",
             "image": "https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/An4.jpg",
             "color": discord.Color.blurple()},
            {"title": "💀 KUTUKAN KUNO TERBANGUN! 💀",
             "description": "Darah monster yang tumpah telah membangunkan kutukan yang telah lama tertidur. Energi negatif menyebar, menginfeksi tanah dan jiwa. Wabah, keputusasaan, dan monster-monster mengerikan baru akan menyelimuti dunia. Tidak ada tempat untuk bersembunyi dari takdirmu!",
             "image": "https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/An5.jpg",
             "color": discord.Color.dark_purple()}
        ]
        
        next_threat_event = random.choice(threat_messages)

        threat_embed = discord.Embed(
            title=next_threat_event['title'],
            description=next_threat_event['description'] + "\n\n**Bersiaplah. Event berikutnya akan segera datang... Mungkin ini adalah akhir dari segalanya.**",
            color=next_threat_event['color']
        )
        threat_embed.set_thumbnail(url=next_threat_event['image'])
        threat_embed.set_footer(text="Waspadalah! Takdir dunia ada di tanganmu, atau kehancuranmu.")
        await channel.send(embed=threat_embed)

        self.current_monster = None
        self.monster_attack_queue = []
        self.monster_attackers = set()
        self.attacked_users_log = []
        self.last_event_type = None

    async def trigger_anomaly(self):
        """Memicu event anomali dunia."""
        # Ensure anomalies_data is a list
        if not self.anomalies_data:
            print("No anomaly data available to trigger.")
            return

        anomaly = random.choice(self.anomalies_data)
        self.active_anomaly = anomaly
        self.anomaly_end_time = datetime.utcnow() + timedelta(seconds=anomaly['duration_seconds'])
        
        channel = self.bot.get_channel(self.event_channel_id)
        if not channel: return
        
        embed = discord.Embed(title=f"{anomaly['emoji']} ANOMALI: {anomaly['name'].upper()} {anomaly['emoji']}", description=anomaly['description'], color=discord.Color.from_str(anomaly['color']))
        embed.set_thumbnail(url=anomaly['thumbnail_url'])
        await channel.send(embed=embed)
        
        if anomaly['type'] == 'code_drop': 
            self.bot.loop.create_task(self.code_dropper(anomaly['duration_seconds']))
        elif anomaly['type'] == 'sickness_plague': 
            guild = self.bot.get_guild(self.main_guild_id)
            if guild:
                await self.start_sickness_plague(guild)
            else:
                print(f"Warning: Could not find main guild {self.main_guild_id} to start sickness plague.")

        await asyncio.sleep(anomaly['duration_seconds'])
        await channel.send(f"Anomali **{anomaly['name']}** yang mengerikan telah usai, untuk saat ini...")
        self.active_anomaly, self.anomaly_end_time = None, None

    async def code_dropper(self, duration):
        """Menjatuhkan kode secara berkala selama anomali 'code_drop'."""
        end_time = datetime.utcnow() + timedelta(seconds=duration)
        while datetime.utcnow() < end_time:
            await asyncio.sleep(random.randint(300, 900))
            if not self.active_anomaly or self.active_anomaly.get('type') != 'code_drop': break
            
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            self.dropped_codes[code] = {"rswn": random.randint(500, 2000), "exp": random.randint(500, 2000)}
            
            channel = self.bot.get_channel(self.event_channel_id)
            if channel: 
                await channel.send(f"☄️ **HUJAN KEHANCURAN!** Sebuah kode misterius jatuh! Ketik `!klaim {code}` untuk mendapatkan remah-remah harapan!")
            
            self.bot.loop.create_task(self.expire_code(code))

    async def expire_code(self, code):
        """Menghapus kode yang dijatuhkan setelah waktu tertentu."""
        await asyncio.sleep(120)
        if code in self.dropped_codes: 
            del self.dropped_codes[code]
            channel = self.bot.get_channel(self.event_channel_id)
            if channel:
                pass

    @commands.command(name="klaim")
    async def klaim(self, ctx, code: str):
        """Mengklaim hadiah dari kode yang dijatuhkan."""
        if code in self.dropped_codes:
            reward = self.dropped_codes.pop(code)
            
            bank_data = load_json_from_root('data/bank_data.json')
            level_data = load_json_from_root('data/level_data.json')

            user_id_str = str(ctx.author.id)
            guild_id_str = str(ctx.guild.id)

            bank_data.setdefault(user_id_str, {'balance': 0})['balance'] += reward['rswn']
            level_data.setdefault(guild_id_str, {}).setdefault(user_id_str, {'exp': 0})['exp'] += reward['exp']
            
            save_json_to_root(bank_data, 'data/bank_data.json')
            save_json_to_root(level_data, 'data/level_data.json')
            
            await ctx.send(f"🎉 Selamat, {ctx.author.mention}! Kamu berhasil meraih **{reward['rswn']} RSWN** dan **{reward['exp']} EXP** dari kehampaan!")
        else:
            await ctx.send("Kode ini palsu, atau harapanmu telah kadaluarsa.", delete_after=10)

    async def trigger_monster_quiz(self):
        """Memicu event kuis monster."""
        channel = self.bot.get_channel(self.event_channel_id)
        # Ensure 'monster_quiz' key exists and is a list
        if not channel or not self.monsters_data or not self.monsters_data.get('monster_quiz'): 
            print("No monster quiz data available or channel not found.")
            return
        
        quiz_monster = random.choice(self.monsters_data['monster_quiz'])
        self.active_anomaly = quiz_monster
        
        embed = discord.Embed(title=f"❓ TEKA-TEKI DARI {quiz_monster['name'].upper()} YANG MENGGILA! ❓", description=quiz_monster['intro'], color=discord.Color.dark_purple())
        embed.set_thumbnail(url=quiz_monster['image_url'])
        embed.add_field(name="MISTERI GELAP:", value=f"**{quiz_monster['riddle']}**\n\n_Petunjuk: {quiz_monster['hint']}_")
        embed.set_footer(text="Jawab di channel ini! Waktu tersisa 5 menit sebelum kutukan menimpamu.")
        await channel.send(embed=embed)

        def check(m): 
            return m.channel == channel and not m.author.bot and m.content.lower() == quiz_monster['answer'].lower()

        try:
            winner_msg = await self.bot.wait_for('message', timeout=300.0, check=check)
            await channel.send(f"🧠 **KEJENIUSAN YANG MENYERAMKAN!** {winner_msg.author.mention} berhasil menjawab dengan benar dan menyelamatkan server dari kutukan! Kamu menerima imbalan yang besar dari kegelapan!")
            
            reward_rswn_quiz, reward_exp_quiz = 7500, 7500
            bank_data = load_json_from_root('data/bank_data.json')
            level_data = load_json_from_root('data/level_data.json')
            
            winner_id_str = str(winner_msg.author.id)
            guild_id_str = str(winner_msg.guild.id)

            bank_data.setdefault(winner_id_str, {'balance': 0})['balance'] += reward_rswn_quiz
            level_data.setdefault(guild_id_str, {}).setdefault(winner_id_str, {'exp': 0})['exp'] += reward_exp_quiz
            
            save_json_to_root(bank_data, 'data/bank_data.json')
            save_json_to_root(level_data, 'data/level_data.json')

            self.quiz_punishment_active = False
            self.quiz_punishment_details = {}

        except asyncio.TimeoutError:
            guild = channel.guild 
            
            self.quiz_punishment_active = True
            self.quiz_punishment_details = {
                'type': 'combined_punishment',
                'extra_targets': 5,
                'loss_multiplier': 2,
                'infect_users': True,
                'end_time': (datetime.utcnow() + timedelta(hours=3)).isoformat()
            }

            await channel.send(f"Waktu habis! Tidak ada yang bisa menjawab. Jawaban yang benar adalah: **{quiz_monster['answer']}**.")
            
            teror_embed = discord.Embed(
                title="☠️ KUTUKAN TAK TERHINDARKAN! KEGAGALANMU TELAH MEMBAWA BENCANA! ☠️",
                description=(
                    f"**Seluruh server akan merasakan akibat dari kebodohanmu!** "
                    f"Bayangan monster akan menyerang **lebih banyak penduduk** dengan **kerugian harta dan jiwa 2x lipat**!\n\n"
                    f"Dan sebagai sentuhan akhir dari keputusasaan, **wabah penyakit akan menyebar!** "
                    f"Bersiaplah untuk penderitaan yang tak terelakkan selama **{self.sickness_duration_minutes_quiz // 60} jam** ke depan! Tidak ada yang aman!"
                ),
                color=discord.Color.dark_red()
            )
            teror_embed.set_thumbnail(url="https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/An5.jpg")
            teror_embed.set_footer(text="Penyesalan kini menghantuimu. Rasakan teror yang telah kau ciptakan!")
            await channel.send(embed=teror_embed)
            
            print("Hukuman kuis: Peningkatan serangan monster, kerugian 2x lipat, dan wabah penyakit diaktifkan.")

            await self.start_sickness_plague(guild, is_quiz_punishment=True, custom_duration=self.sickness_duration_minutes_quiz) 

            self.active_anomaly = None

    async def start_sickness_plague(self, guild, is_quiz_punishment=False, custom_duration=None):
        """Menyebarkan wabah penyakit ke pengguna aktif."""
        channel = self.bot.get_channel(self.event_channel_id)
        if not channel: return

        sick_role = guild.get_role(self.sick_role_id)
        if not sick_role:
            print(f"Peringatan: Role 'Sakit' dengan ID {self.sick_role_id} tidak ditemukan di guild {guild.name}.")
            if channel: await channel.send("⚠️ Peringatan: Role 'Sakit' tidak ditemukan, wabah tidak dapat menyebar sepenuhnya.")
            return

        level_data = load_json_from_root('data/level_data.json').get(str(guild.id), {})
        bank_data = load_json_from_root('data/bank_data.json')
        inventory_data = load_json_from_root('data/inventory.json')

        users_eligible_for_infection = []
        for user_id_str, user_exp_data in level_data.items():
            member = guild.get_member(int(user_id_str))
            if (member and sick_role not in member.roles and 
                'last_active' in user_exp_data and isinstance(user_exp_data.get('last_active'), str) and 
                datetime.utcnow() - datetime.fromisoformat(user_exp_data['last_active']) < timedelta(days=3)):
                
                exp = user_exp_data.get('exp', 0)
                balance = bank_data.get(user_id_str, {}).get('balance', 0)
                total_score = exp + balance
                users_eligible_for_infection.append((total_score, user_id_str, member))

        infected_mentions_for_log_and_embed = []
        infected_count = 0
        
        if is_quiz_punishment:
            users_eligible_for_infection.sort(key=lambda x: x[0], reverse=True)
            
            num_to_infect = min(len(users_eligible_for_infection), 30) 
            duration = custom_duration if custom_duration else self.sickness_duration_minutes_quiz

            targets_to_infect = users_eligible_for_infection[:num_to_infect]

            if not targets_to_infect:
                await channel.send("Wabah telah menyebar, namun entah somehow tidak ada yang terinfeksi kali ini... Mungkin nasib sedang berpihak, untuk sementara. (Tidak ada user yang memenuhi syarat untuk diinfeksi.)")
                return

            for score, user_id_str, member in targets_to_infect:
                try:
                    await member.add_roles(sick_role)
                    self.sick_users_cooldown[str(member.id)] = {
                        'last_message_time': datetime.utcnow().isoformat(),
                        'sickness_end_time': (datetime.utcnow() + timedelta(minutes=duration)).isoformat(),
                        'duration_minutes': duration,
                        'has_free_medicine': True
                    }
                    
                    user_inventory = inventory_data.setdefault(user_id_str, [])
                    user_inventory.append({"name": "Kotak Obat Misterius", "type": "gacha_medicine_box"})
                    
                    infected_mentions_for_log_and_embed.append(f"**{member.display_name}** ({member.mention})")
                    infected_count += 1
                except discord.Forbidden:
                    print(f"Bot tidak memiliki izin untuk menambahkan role 'Sakit' ke {member.display_name}.")
                except Exception as e:
                    print(f"Error saat menginfeksi {member.display_name}: {e}")
        
        else:
            num_to_infect = min(len(users_eligible_for_infection), random.randint(3, 7))
            duration = self.sickness_duration_minutes
            
            if num_to_infect == 0:
                if channel: await channel.send("Udara terasa bersih, tidak ada yang jatuh sakit kali ini. Sebuah keajaiban...")
                return

            random_targets = random.sample(users_eligible_for_infection, num_to_infect)
            for score, user_id_str, member in random_targets:
                 try:
                    await member.add_roles(sick_role)
                    self.sick_users_cooldown[str(member.id)] = {
                        'last_message_time': datetime.utcnow().isoformat(),
                        'sickness_end_time': (datetime.utcnow() + timedelta(minutes=duration)).isoformat(),
                        'duration_minutes': duration,
                        'has_free_medicine': False
                    }
                    infected_mentions_for_log_and_embed.append(f"**{member.display_name}** ({member.mention})")
                    infected_count += 1
                 except discord.Forbidden:
                    print(f"Bot tidak memiliki izin untuk menambahkan role 'Sakit' ke {member.display_name}.")
                 except Exception as e:
                    print(f"Error saat menginfeksi {member.display_name}: {e}")

        save_json_to_root(self.sick_users_cooldown, 'data/sick_users_cooldown.json')
        save_json_to_root(inventory_data, 'data/inventory.json')
        
        if channel and infected_mentions_for_log_and_embed:
            embed_title = "😷 WABAH KEJI MENYEBAR! 😷"
            embed_description = (
                f"Beberapa penduduk telah jatuh sakit dan akan merasakan penderitaan selama **{duration} menit**!\n\n"
                f"**Korban Wabah:**\n"
                f"{', '.join(infected_mentions_for_log_and_embed)}\n\n"
                f"Mereka akan kesulitan berinteraksi. Cepat cari obat di `!shop` sebelum terlambat!"
            )
            embed_color = discord.Color.red()
            embed_thumbnail = "https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/An5.jpg"

            if is_quiz_punishment:
                embed_title = "☠️ KUTUKAN WABAH DARI KEGAGALAN KUIS! ☠️"
                embed_description = (
                    f"Akibat kegagalan kuis, wabah penyakit telah menyebar lebih luas dan parah!\n"
                    f"Para korban akan menderita selama **{duration // 60} jam**!\n\n"
                    f"**Korban Wabah:**\n"
                    f"{', '.join(infected_mentions_for_log_and_embed)}\n\n"
                    f"Setiap korban telah mendapatkan **1 Kotak Obat Misterius GRATIS** (`!minumobat`)! Namun, tidak ada yang aman dari malapetaka ini! Biarkan mereka menderita!"
                )
                embed_color = discord.Color.dark_red()
                embed_thumbnail = "https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/An6.jpg"

            embed = discord.Embed(
                title=embed_title,
                description=embed_description,
                color=embed_color
            )
            embed.set_thumbnail(url=embed_thumbnail)
            embed.set_footer(text="Waspadalah! Penyakit ini tidak mengenal belas kasihan.")
            await channel.send(embed=embed)
        elif channel and infected_count == 0 and is_quiz_punishment:
             await channel.send("Wabah telah menyebar, namun entah somehow tidak ada yang terinfeksi kali ini... Mungkin nasib sedang berpihak, untuk sementara. (Tidak ada user yang memenuhi syarat untuk diinfeksi atau bot tidak memiliki izin untuk menambahkan role.)")

    @commands.Cog.listener()
    async def on_message(self, message):
        """
        Listener untuk setiap pesan. Digunakan untuk logika cooldown pesan bagi pengguna yang sakit.
        """
        if message.author.bot or not message.guild:
            return
        
        user_id_str = str(message.author.id)
        sick_role = message.guild.get_role(self.sick_role_id)

        if sick_role and sick_role in message.author.roles:
            now = datetime.utcnow()
            user_sickness_data = self.sick_users_cooldown.get(user_id_str)
            
            if user_sickness_data and 'last_message_time' in user_sickness_data:
                last_message_time = datetime.fromisoformat(user_sickness_data['last_message_time'])
                cooldown = timedelta(minutes=self.sickness_cooldown_minutes)
                
                if now - last_message_time < cooldown:
                    time_left_cooldown = cooldown - (now - last_message_time)
                    
                    sickness_end_time = datetime.fromisoformat(user_sickness_data['sickness_end_time'])
                    time_left_sickness = sickness_end_time - now
                    
                    total_seconds_sickness = max(0, int(time_left_sickness.total_seconds()))
                    hours_sickness = total_seconds_sickness // 3600
                    minutes_sickness = (total_seconds_sickness % 3600) // 60
                    seconds_sickness = total_seconds_sickness % 60
                    
                    sickness_time_str = []
                    if hours_sickness > 0: sickness_time_str.append(f"{hours_sickness} jam")
                    if minutes_sickness > 0: sickness_time_str.append(f"{minutes} menit") # Changed to minutes_sickness
                    if seconds_sickness > 0 or (not hours_sickness and not minutes_sickness): sickness_time_str.append(f"{seconds_sickness} detik")
                    
                    if not sickness_time_str: sickness_time_str.append("segera pulih")

                    try:
                        await message.delete()
                        await message.author.send(
                            f"Kamu sakit parah dan tubuhmu lemah... Kamu harus beristirahat selama **{int(time_left_cooldown.total_seconds())} detik** sebelum bisa bicara lagi. Jangan coba melawan takdirmu! (Sisa sakit: {' '.join(sickness_time_str)})",
                            delete_after=60
                        )
                    except (discord.Forbidden, discord.NotFound): 
                        pass 
                    return
            
            self.sick_users_cooldown.setdefault(user_id_str, {})['last_message_time'] = now.isoformat()
            save_json_to_root(self.sick_users_cooldown, 'data/sick_users_cooldown.json')

    @commands.command(name="minumobat")
    async def minumobat(self, ctx):
        """Menggunakan 'Kotak Obat Misterius' untuk mencoba menyembuhkan penyakit."""
        user_id_str = str(ctx.author.id)
        sick_role = ctx.guild.get_role(self.sick_role_id)
        
        if not sick_role or sick_role not in ctx.author.roles:
            return await ctx.send("Kamu tidak sakit. Jangan mencari masalah yang tidak perlu.")
        
        inventory_data = load_json_from_root('data/inventory.json')
        user_inventory = inventory_data.setdefault(user_id_str, [])
        user_sickness_data = self.sick_users_cooldown.get(user_id_str, {})

        has_free_medicine = user_sickness_data.get('has_free_medicine', False)
        if has_free_medicine:
            medicine_box = {"name": "Kotak Obat Misterius", "type": "gacha_medicine_box"}
            self.sick_users_cooldown[user_id_str]['has_free_medicine'] = False
            save_json_to_root(self.sick_users_cooldown, 'data/sick_users_cooldown.json')
            await ctx.send("Kamu menggunakan Kotak Obat Misterius GRATIS yang kamu dapatkan dari kutukan kuis!", ephemeral=True)
        else:
            medicine_box = next((item for item in user_inventory if item.get('type') == 'gacha_medicine_box'), None)
            if not medicine_box: 
                return await ctx.send("Kamu tidak punya Kotak Obat Misterius. Beli satu dari `!shop` jika kau ingin bertahan hidup.")
            
            user_inventory.remove(medicine_box)
            save_json_to_root(inventory_data, 'data/inventory.json')
            await ctx.send("Kamu menggunakan Kotak Obat Misterius dari inventaris.", ephemeral=True)

        embed = discord.Embed(title="💊 MERACIK RAMUAN KESEMBUHAN, ATAU KEMATIAN?...", description="Kamu membuka Kotak Obat Misterius, merasakan energi aneh mengalir saat kau mengocoknya...", color=discord.Color.light_grey())
        embed.set_thumbnail(url="https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/gif.gif") 
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(3)

        choices = [med['name'] for med in self.medicines_data]
        weights = [med['chance'] for med in self.medicines_data]
        chosen_medicine_name = random.choices(choices, weights=weights, k=1)[0]
        chosen_medicine = next(med for med in self.medicines_data if med['name'] == chosen_medicine_name)

        result_embed = discord.Embed(title="HASIL TARUHAN NYAWA!", description=f"Kamu mendapatkan... **{chosen_medicine['name']}**! Semoga ini bukan racun...", color=discord.Color.from_str(chosen_medicine['color']))
        result_embed.add_field(name="EFEK", value=chosen_medicine['effect_desc'])
        await msg.edit(embed=result_embed)
        
        if random.randint(1, 100) <= chosen_medicine['heal_chance']:
            await asyncio.sleep(2)
            heal_embed = discord.Embed(title="✨ KEAJAIBAN! ATAU HANYA PENUNDAAN?! ✨", color=discord.Color.green())
            await ctx.author.remove_roles(sick_role)
            if str(ctx.author.id) in self.sick_users_cooldown: 
                del self.sick_users_cooldown[str(ctx.author.id)]
            save_json_to_root(self.sick_users_cooldown, 'data/sick_users_cooldown.json')

            if chosen_medicine['heal_chance'] == 100:
                expiry = datetime.utcnow() + timedelta(hours=24)
                self.protected_users[user_id_str] = expiry.isoformat()
                save_json_to_root(self.protected_users, 'data/protected_users.json')
                heal_embed.description = "Kamu sembuh total dari penderitaanmu! Role 'Sakit' telah dilepas dan kamu mendapat **perlindungan 24 jam** dari serangan monster! Nikmati kelegaan sesaat ini..."
            else:
                heal_embed.description = "Kamu merasa jauh lebih baik dan sembuh total! Role 'Sakit' telah dilepas. Tapi ingat, bahaya selalu mengintai."
            await ctx.send(embed=heal_embed)
        else:
            await asyncio.sleep(2)
            await ctx.send("Sayang sekali... obatnya tidak bekerja. Kamu masih merasa pusing, mual, dan tak berdaya. Coba lagi lain kali, jika kau masih hidup.")

    @commands.command(name="sembuhkan")
    @commands.has_permissions(administrator=True)
    async def sembuhkan(self, ctx, member: discord.Member):
        """
        [ADMIN ONLY] Menyembuhkan pengguna secara instan dari status 'Sakit'
        dan menghilangkan cooldown pesan mereka.
        """
        sick_role = ctx.guild.get_role(self.sick_role_id)

        if not sick_role:
            return await ctx.send("⚠️ Error: Role 'Sakit' tidak ditemukan di server ini. Pastikan ID role sudah benar.", ephemeral=True)

        if sick_role not in member.roles:
            return await ctx.send(f"{member.display_name} ({member.mention}) tidak sedang sakit.", ephemeral=True)

        try:
            await member.remove_roles(sick_role)
            if str(member.id) in self.sick_users_cooldown:
                del self.sick_users_cooldown[str(member.id)]
                save_json_to_root(self.sick_users_cooldown, 'data/sick_users_cooldown.json')
            
            await ctx.send(f"✨ **Kekuatan admin telah menyembuhkan!** {member.display_name} ({member.mention}) telah pulih dari sakitnya!")
            print(f"Admin {ctx.author.display_name} menyembuhkan {member.display_name}.")

        except discord.Forbidden:
            await ctx.send("❌ Aku tidak punya izin untuk menghapus role dari pengguna ini. Pastikan role bot di atas role 'Sakit'.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ Terjadi kesalahan saat mencoba menyembuhkan {member.display_name}: {e}", ephemeral=True)

    @commands.command(name="daftar_sakit")
    @commands.has_permissions(administrator=True)
    async def daftar_sakit(self, ctx):
        """
        [ADMIN ONLY] Menampilkan daftar pengguna yang saat ini terkena wabah penyakit
        beserta sisa durasi sakit mereka.
        """
        sick_role = ctx.guild.get_role(self.sick_role_id)
        if not sick_role:
            return await ctx.send("⚠️ Error: Role 'Sakit' tidak ditemukan di server ini.", ephemeral=True)

        now = datetime.utcnow()
        sick_list = []

        for user_id_str, user_data in list(self.sick_users_cooldown.items()):
            if 'sickness_end_time' not in user_data or not isinstance(user_data.get('sickness_end_time'), str):
                continue

            sickness_end_time = datetime.fromisoformat(user_data['sickness_end_time'])
            
            if now < sickness_end_time:
                member = ctx.guild.get_member(int(user_id_str))
                if member and sick_role in member.roles:
                    time_left = sickness_end_time - now
                    total_seconds = int(time_left.total_seconds())
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    seconds = total_seconds % 60
                    
                    time_str = []
                    if hours > 0: time_str.append(f"{hours} jam")
                    if minutes > 0: time_str.append(f"{minutes} menit")
                    if seconds > 0 or (not hours and not minutes): time_str.append(f"{seconds} detik") # Corrected logic for seconds display
                    
                    sick_list.append(f"- **{member.display_name}** ({member.mention}): Sisa **{' '.join(time_str)}**")
            else:
                pass
        
        if not sick_list:
            embed = discord.Embed(
                title="✅ DAFTAR PENGGUNA SAKIT",
                description="Sejauh ini, tidak ada penduduk yang terinfeksi wabah penyakit. Tetap waspada!",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="😷 DAFTAR PENGGUNA SAKIT SAAT INI 😷",
                description="Berikut adalah mereka yang terinfeksi wabah penyakit dan sedang dalam penderitaan:",
                color=discord.Color.red()
            )
            embed.add_field(name="Korban Wabah", value="\n".join(sick_list), inline=False)
        
        embed.set_footer(text=f"Diperbarui pada: {datetime.now(pytz.timezone('Asia/Jakarta')).strftime('%H:%M:%S WIB')}")
        await ctx.send(embed=embed)


async def setup(bot):
    """Fungsi setup untuk menambahkan cog ke bot."""
    await bot.add_cog(DuniaHidup(bot))
