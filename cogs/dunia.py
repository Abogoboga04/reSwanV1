import discord
from discord.ext import commands, tasks
import json
import random
import asyncio
import os
from datetime import datetime, timedelta
import string

# --- Helper Functions (Wajib ada di awal) ---
def load_json_from_root(file_path):
    """Memuat data JSON dari direktori utama bot dengan aman."""
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        full_path = os.path.join(base_dir, file_path)
        with open(full_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Jika file tidak ada atau rusak, kembalikan struktur data kosong yang sesuai
        if 'users' in file_path or 'inventory' in file_path:
            return {}
        elif 'monsters' in file_path or 'anomalies' in file_path or 'medicines' in file_path:
            return {os.path.basename(file_path).replace('.json', ''): []}
        return {}

def save_json_to_root(data, file_path):
    """Menyimpan data ke file JSON di direktori utama bot."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    full_path = os.path.join(base_dir, file_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

# --- UI View untuk Pertarungan Monster ---
class MonsterBattleView(discord.ui.View):
    def __init__(self, bot_cog, monster, party):
        super().__init__(timeout=600)  # Pertarungan berlangsung maksimal 10 menit
        self.cog = bot_cog
        self.monster = monster
        self.party = list(party) # Ubah ke list agar bisa diindeks
        self.turn_index = 0
        self.battle_log = ["Pertarungan dimulai!"]
        
    def get_current_player(self):
        """Mendapatkan pemain yang sedang giliran."""
        return self.party[self.turn_index]

    def create_battle_embed(self, status_text):
        """Membuat dan memperbarui embed pertarungan."""
        hp_percentage = self.monster['current_hp'] / self.monster['max_hp']
        # Pastikan bar tidak negatif
        bar_filled = max(0, int(hp_percentage * 20))
        bar_empty = 20 - bar_filled
        hp_bar = "█" * bar_filled + "─" * bar_empty
        
        embed = discord.Embed(
            title=f"⚔️ Melawan {self.monster['name']} ⚔️",
            description=status_text,
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=self.monster['image_url'])
        embed.add_field(
            name="❤️ Sisa HP Monster",
            value=f"`[{hp_bar}]`\n**{self.monster['current_hp']:,} / {self.monster['max_hp']:,}**",
            inline=False
        )
        party_status = "\n".join([f"**{p.display_name}**" for p in self.party])
        embed.add_field(name="👥 Party Penyerang", value=party_status, inline=True)
        log_text = "\n".join([f"> {log}" for log in self.battle_log[-5:]]) # Tampilkan 5 log terakhir
        embed.add_field(name="📜 Log Pertarungan", value=log_text, inline=False)
        return embed

    async def update_view(self, interaction: discord.Interaction):
        """Memperbarui tampilan setelah setiap aksi."""
        if self.monster['current_hp'] <= 0:
            embed = self.create_battle_embed(f"🎉 **MONSTER DIKALAHKAN!** 🎉")
            embed.color = discord.Color.gold()
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(embed=embed, view=self)
            self.stop()
            await self.cog.handle_monster_defeat(interaction.channel)
        else:
            embed = self.create_battle_embed(f"Giliran: **{self.get_current_player().display_name}**")
            await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Serang ⚔️", style=discord.ButtonStyle.danger)
    async def attack(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_player = self.get_current_player()
        if interaction.user != current_player:
            return await interaction.response.send_message("Bukan giliranmu!", ephemeral=True)

        await interaction.response.defer()
        
        # Aksi Pemain
        level_data = load_json_from_root('data/level_data.json').get(str(interaction.guild.id), {})
        user_level = level_data.get(str(interaction.user.id), {}).get('level', 1)
        damage = random.randint(50, 150) + (user_level * 20)
        self.monster['current_hp'] -= damage
        self.battle_log.append(f"{interaction.user.display_name} menyerang, memberikan **{damage}** damage!")
        
        # Aksi Balasan Monster (jika belum mati)
        if self.monster['current_hp'] > 0:
            monster_damage = random.randint(100, 300)
            self.battle_log.append(f"{self.monster['name']} menyerang balik, memberikan **{monster_damage}** damage pada {interaction.user.display_name}!")
        
        # Pindah Giliran
        self.turn_index = (self.turn_index + 1) % len(self.party)
        await self.update_view(interaction)

class DuniaHidup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # --- State Management ---
        self.active_games = set()
        self.current_monster = None
        self.monster_attack_queue = []
        self.monster_attackers = set()
        
        self.active_anomaly = None
        self.anomaly_end_time = None
        
        self.sick_users_cooldown = {} # {user_id: last_message_datetime}
        
        self.protected_users = load_json_from_root('data/protected_users.json') 
        self.dropped_codes = {}

        # --- Konfigurasi (WAJIB DIUBAH) ---
        self.event_channel_id = 765140300145360896 # GANTI dengan ID channel pengumuman event
        self.sick_role_id = 123456789012345678 # GANTI dengan ID role 'Sakit' yang sudah dibuat
        self.sickness_cooldown_minutes = 1.5 # Cooldown 1.5 menit (90 detik)
        
        # --- Data Loading ---
        self.monsters_data = load_json_from_root('data/monsters.json')
        self.anomalies_data = load_json_from_root('data/world_anomalies.json').get('anomalies', [])
        self.medicines_data = load_json_from_root('data/medicines.json').get('medicines', [])
        
        # --- Memulai Dunia ---
        self.world_event_loop.start()
        self.monster_attack_processor.start()
        self.protection_cleaner.start()

    def cog_unload(self):
        self.world_event_loop.cancel()
        self.monster_attack_processor.cancel()
        self.protection_cleaner.cancel()

    # --- Bagian Loop Dunia & Event ---
    @tasks.loop(hours=random.randint(3, 6))
    async def world_event_loop(self):
        await self.bot.wait_until_ready()
        if self.current_monster or self.active_anomaly:
            print("[DUNIA HIDUP] Event sedang berlangsung, loop diskip.")
            return

        event_type = random.choice(['monster', 'anomaly', 'monster_quiz'])
        
        if event_type == 'monster' and self.monsters_data.get('monsters'):
            await self.spawn_monster()
        elif event_type == 'anomaly' and self.anomalies_data:
            await self.trigger_anomaly()
        elif event_type == 'monster_quiz' and self.monsters_data.get('monster_quiz'):
            await self.trigger_monster_quiz()

    @tasks.loop(minutes=30)
    async def protection_cleaner(self):
        now = datetime.utcnow()
        expired_users = [uid for uid, expiry in self.protected_users.items() if now >= datetime.fromisoformat(expiry)]
        for uid in expired_users:
            del self.protected_users[uid]
        if expired_users:
            save_json_to_root(self.protected_users, 'data/protected_users.json')
    
    # --- Bagian Sistem Monster ---
    async def spawn_monster(self):
        self.current_monster = random.choice(self.monsters_data['monsters']).copy()
        self.current_monster['current_hp'] = self.current_monster['max_hp']
        self.monster_attackers.clear()
        channel = self.bot.get_channel(self.event_channel_id)
        if not channel: return

        embed = discord.Embed(title=f"🚨 ANCAMAN BARU MUNCUL! 🚨\n{self.current_monster['name']}", description=f"_{self.current_monster['story']}_", color=discord.Color.red())
        embed.set_thumbnail(url=self.current_monster['image_url'])
        embed.add_field(name="❤️ HP", value=f"**{self.current_monster['current_hp']:,}/{self.current_monster['max_hp']:,}**", inline=True)
        embed.add_field(name="⚔️ Tipe", value=self.current_monster['type'], inline=True)
        embed.set_footer(text="Gunakan !serangmonster untuk membentuk party dan melawannya!")
        await channel.send(embed=embed)
        await self.schedule_monster_attacks(channel.guild)

    async def schedule_monster_attacks(self, guild):
        level_data = load_json_from_root('data/level_data.json').get(str(guild.id), {})
        if not level_data: return
        sorted_users = sorted(level_data.items(), key=lambda x: x[1].get('exp', 0), reverse=True)
        top_10 = [uid for uid, data in sorted_users[:10]]
        if len(top_10) < 3: targets = top_10
        else: targets = random.sample(top_10, 3)
        if not targets: return
        now = datetime.utcnow()
        self.monster_attack_queue = [{'user_id': uid, 'attack_time': (now + timedelta(hours=random.randint(i*4+1, (i+1)*4))).isoformat()} for i, uid in enumerate(targets)]

    @tasks.loop(minutes=10)
    async def monster_attack_processor(self):
        now = datetime.utcnow()
        if not self.monster_attack_queue or not self.current_monster: return
        
        attack = self.monster_attack_queue[0]
        if now < datetime.fromisoformat(attack['attack_time']): return

        user_id_to_attack = attack['user_id']
        if user_id_to_attack in self.protected_users:
            self.monster_attack_queue.pop(0)
            return

        guild = self.bot.guilds[0]
        member = guild.get_member(int(user_id_to_attack))
        if not member:
            self.monster_attack_queue.pop(0)
            return

        exp_loss, rswn_loss = random.randint(250, 500), random.randint(250, 500)
        
        level_data = load_json_from_root('data/level_data.json')
        bank_data = load_json_from_root('data/bank_data.json')
        if str(guild.id) in level_data and user_id_to_attack in level_data[str(guild.id)]:
            level_data[str(guild.id)][user_id_to_attack]['exp'] = max(0, level_data[str(guild.id)][user_id_to_attack]['exp'] - exp_loss)
        if user_id_to_attack in bank_data:
            bank_data[user_id_to_attack]['balance'] = max(0, bank_data[user_id_to_attack]['balance'] - rswn_loss)
        save_json_to_root(level_data, 'data/level_data.json')
        save_json_to_root(bank_data, 'data/bank_data.json')
        
        channel = self.bot.get_channel(self.event_channel_id)
        if channel: await channel.send(f"⚔️ **SERANGAN MONSTER!** {self.current_monster['name']} menyerang {member.mention}! Kamu kehilangan **{exp_loss} EXP** dan **{rswn_loss} RSWN**!")
        
        self.monster_attack_queue.pop(0)

    @commands.command(name="serangmonster")
    async def serangmonster(self, ctx):
        if not self.current_monster: return await ctx.send("Tidak ada monster untuk diserang saat ini.", delete_after=10)
        
        view = discord.ui.View(timeout=60.0)
        party = {ctx.author}

        embed = discord.Embed(title="⚔️ Membentuk Party Penyerang!", description=f"**{ctx.author.display_name}** memulai penyerangan terhadap **{self.current_monster['name']}**!\n\nPemain lain, klik 'Gabung' untuk ikut serta! Waktu 60 detik.", color=discord.Color.blurple())
        
        async def join_callback(interaction: discord.Interaction):
            if interaction.user not in party:
                party.add(interaction.user)
                await interaction.response.send_message(f"{interaction.user.mention} telah bergabung!", ephemeral=True)
            else:
                await interaction.response.send_message("Kamu sudah bergabung.", ephemeral=True)
        
        join_button = discord.ui.Button(label="Gabung Pertarungan", style=discord.ButtonStyle.success, emoji="🤝")
        join_button.callback = join_callback
        view.add_item(join_button)
        
        await ctx.send(embed=embed, view=view)
        await asyncio.sleep(60)

        if not party: return
            
        battle_view = MonsterBattleView(self, self.current_monster, party)
        initial_embed = battle_view.create_battle_embed(f"Giliran: **{battle_view.get_current_player().display_name}**")
        await ctx.send(embed=initial_embed, view=battle_view)

    async def handle_monster_defeat(self, channel):
        await channel.send(f"🎉 **SELAMAT!** Kalian telah mengalahkan **{self.current_monster['name']}**! Semua **{len(self.monster_attackers)} pejuang** yang berpartisipasi mendapatkan hadiah!")
        for user_id in self.monster_attackers:
            member = channel.guild.get_member(user_id)
            if member:
                # Logika pemberian hadiah
                bank_data = load_json_from_root('data/bank_data.json')
                level_data = load_json_from_root('data/level_data.json')
                reward_rswn, reward_exp = 5000, 5000 # Contoh hadiah besar
                bank_data.setdefault(str(user_id), {'balance': 0, 'debt': 0})['balance'] += reward_rswn
                level_data.setdefault(str(channel.guild.id), {}).setdefault(str(user_id), {'exp': 0})['exp'] += reward_exp
                save_json_to_root(bank_data, 'data/bank_data.json')
                save_json_to_root(level_data, 'data/level_data.json')
        self.current_monster = None

    # --- Bagian Sistem Anomali & Event ---
    async def trigger_anomaly(self):
        anomaly = random.choice(self.anomalies_data)
        self.active_anomaly = anomaly
        self.anomaly_end_time = datetime.utcnow() + timedelta(seconds=anomaly['duration_seconds'])
        channel = self.bot.get_channel(self.event_channel_id)
        if not channel: return
        
        embed = discord.Embed(title=f"🌀 ANOMALI TERDETEKSI: {anomaly['name']} 🌀", description=anomaly['description'], color=discord.Color.from_str(anomaly['color']))
        await channel.send(embed=embed)
        
        if anomaly['type'] == 'code_drop': self.bot.loop.create_task(self.code_dropper(anomaly['duration_seconds']))
        elif anomaly['type'] == 'sickness_plague': await self.start_sickness_plague(channel.guild)

        await asyncio.sleep(anomaly['duration_seconds'])
        await channel.send(f"Anomali **{anomaly['name']}** telah berakhir.")
        self.active_anomaly = None
        self.anomaly_end_time = None

    async def code_dropper(self, duration):
        end_time = datetime.utcnow() + timedelta(seconds=duration)
        while datetime.utcnow() < end_time:
            await asyncio.sleep(random.randint(300, 900))
            if not self.active_anomaly: break
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            self.dropped_codes[code] = {"rswn": random.randint(500, 2000), "exp": random.randint(500, 2000)}
            channel = self.bot.get_channel(self.event_channel_id)
            if channel: await channel.send(f"☄️ **HUJAN METEOR!** Sebuah kode jatuh! Ketik `!klaim {code}` untuk hadiah!")
            self.bot.loop.create_task(self.expire_code(code))

    async def expire_code(self, code):
        await asyncio.sleep(120)
        if code in self.dropped_codes: del self.dropped_codes[code]

    @commands.command(name="klaim")
    async def klaim(self, ctx, code: str):
        if code in self.dropped_codes:
            reward = self.dropped_codes[code]
            # ... (logika pemberian hadiah seperti di respons sebelumnya) ...
            await ctx.send(f"🎉 Selamat {ctx.author.mention}! Kamu berhasil mengklaim hadiah **{reward['rswn']} RSWN** dan **{reward['exp']} EXP**!")
            del self.dropped_codes[code]
        else:
            await ctx.send("Kode tidak valid atau sudah hangus.", delete_after=10)

    # --- Bagian Sistem Penyakit ---
    async def start_sickness_plague(self, guild):
        level_data = load_json_from_root('data/level_data.json').get(str(guild.id), {})
        active_users = [uid for uid, data in level_data.items() if 'last_active' in data and datetime.utcnow() - datetime.fromisoformat(data['last_active']) < timedelta(days=3)]
        num_to_infect = min(len(active_users), random.randint(3, 7))
        infected_users_ids = random.sample(active_users, num_to_infect)
        
        role = guild.get_role(self.sick_role_id)
        if not role: return

        infected_mentions = []
        for user_id in infected_users_ids:
            member = guild.get_member(int(user_id))
            if member:
                await member.add_roles(role)
                infected_mentions.append(member.mention)
        
        channel = self.bot.get_channel(self.event_channel_id)
        if channel and infected_mentions:
            await channel.send(f"😷 **WABAH MENYEBAR!** {', '.join(infected_mentions)} telah jatuh sakit. Interaksi mereka akan terbatas. Cepat cari obat di `!toko`!")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            if not message.author.bot: await self.bot.process_commands(message)
            return
        
        user_id = message.author.id
        sick_role = message.guild.get_role(self.sick_role_id)

        if sick_role and sick_role in message.author.roles:
            now = datetime.utcnow()
            last_message_time = self.sick_users_cooldown.get(user_id)
            if last_message_time:
                cooldown = timedelta(minutes=self.sickness_cooldown_minutes)
                if now - last_message_time < cooldown:
                    time_left = cooldown - (now - last_message_time)
                    try:
                        await message.delete()
                        await message.author.send(f"Kamu sedang sakit dan masih lemas... Kamu butuh istirahat **{int(time_left.total_seconds())} detik** lagi sebelum bisa berbicara.", delete_after=60)
                    except (discord.Forbidden, discord.NotFound): pass
                    return
            self.sick_users_cooldown[user_id] = now
        
        await self.bot.process_commands(message)

    @commands.command(name="minumobat")
    async def minumobat(self, ctx):
        user_id_str = str(ctx.author.id)
        sick_role = ctx.guild.get_role(self.sick_role_id)
        if not sick_role or sick_role not in ctx.author.roles:
            return await ctx.send("Kamu tidak sedang sakit, tidak perlu minum obat.")
        
        inventory_data = load_json_from_root('data/inventory.json')
        user_inventory = inventory_data.setdefault(user_id_str, [])
        medicine_box = next((item for item in user_inventory if item.get('type') == 'gacha_medicine_box'), None)
        if not medicine_box: return await ctx.send("Kamu tidak punya Kotak Obat Misterius. Beli dulu di `!toko`.")
        
        user_inventory.remove(medicine_box)
        save_json_to_root(inventory_data, 'data/inventory.json')
        
        embed = discord.Embed(title="💊 Meracik Obat...", description="Kamu membuka Kotak Obat Misterius dan mulai mengocoknya...", color=discord.Color.light_grey())
        embed.set_thumbnail(url="https://i.imgur.com/gL9pA8v.gif")
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(3)

        choices = [med['name'] for med in self.medicines_data]
        weights = [med['chance'] for med in self.medicines_data]
        chosen_medicine_name = random.choices(choices, weights=weights, k=1)[0]
        chosen_medicine = next(med for med in self.medicines_data if med['name'] == chosen_medicine_name)

        result_embed = discord.Embed(title="Hasil Gacha Obat", description=f"Kamu mendapatkan... **{chosen_medicine['name']}**!", color=discord.Color.from_str(chosen_medicine['color']))
        result_embed.add_field(name="Efek", value=chosen_medicine['effect_desc'])
        await msg.edit(embed=result_embed)
        
        if random.randint(1, 100) <= chosen_medicine['heal_chance']:
            await asyncio.sleep(2)
            heal_embed = discord.Embed(title="✨ Obat Bekerja! ✨", color=discord.Color.green())
            await ctx.author.remove_roles(sick_role)
            if ctx.author.id in self.sick_users_cooldown: del self.sick_users_cooldown[ctx.author.id]
            
            if chosen_medicine['heal_chance'] == 100:
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
    await bot.add_cog(DuniaHidup(bot))

