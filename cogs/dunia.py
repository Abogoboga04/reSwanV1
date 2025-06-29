import discord
from discord.ext import commands, tasks
import json
import random
import asyncio
import os
from datetime import datetime, timedelta
import string

# --- Helper Functions (Wajib ada) ---
def load_json_from_root(file_path):
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        full_path = os.path.join(base_dir, file_path)
        with open(full_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return {}

def save_json_to_root(data, file_path):
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    full_path = os.path.join(base_dir, file_path)
    with open(full_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

class DuniaHidup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # --- Game State ---
        self.current_monster = None
        self.monster_attack_queue = []
        self.monster_attackers = set()
        
        self.active_anomaly = None
        self.anomaly_end_time = None
        
        self.sick_users = load_json_from_root('data/sick_users.json') # {user_id: {"role_id": int, "message_count": 0, "last_message_time": iso}}
        self.protected_users = load_json_from_root('data/protected_users.json') # {user_id: expiry_iso_string}
        self.dropped_codes = {} # {code: {"rswn": int, "exp": int}}

        # --- Config ---
        self.event_channel_id = 765140300145360896 # GANTI DENGAN ID CHANNEL PENGUMUMAN EVENT
        self.sick_role_id = 123456789012345678 # GANTI DENGAN ID ROLE 'Sakit' YANG SUDAH DIBUAT
        
        # --- Data ---
        self.monsters_data = load_json_from_root('data/monsters.json').get('monsters', [])
        self.anomalies_data = load_json_from_root('data/world_anomalies.json').get('anomalies', [])
        self.medicines_data = load_json_from_root('data/medicines.json').get('medicines', [])
        
        # --- Start The World ---
        self.world_event_loop.start()
        self.monster_attack_processor.start()
        self.protection_cleaner.start()

    def cog_unload(self):
        self.world_event_loop.cancel()
        self.monster_attack_processor.cancel()
        self.protection_cleaner.cancel()

    # --- CORE WORLD & EVENT LOOPS ---
    @tasks.loop(hours=random.randint(3, 6))
    async def world_event_loop(self):
        await self.bot.wait_until_ready()
        
        if self.current_monster or self.active_anomaly:
            print("[DUNIA HIDUP] Event sedang berlangsung, loop diskip.")
            return

        event_type = random.choice(['monster', 'anomaly', 'monster_quiz'])
        
        if event_type == 'monster' and self.monsters_data:
            await self.spawn_monster()
        elif event_type == 'anomaly' and self.anomalies_data:
            await self.trigger_anomaly()
        elif event_type == 'monster_quiz' and self.monsters_data:
            await self.trigger_monster_quiz()

    @tasks.loop(minutes=30)
    async def protection_cleaner(self):
        now = datetime.utcnow()
        expired_users = [uid for uid, expiry in self.protected_users.items() if now >= datetime.fromisoformat(expiry)]
        for uid in expired_users:
            del self.protected_users[uid]
        if expired_users:
            save_json_to_root(self.protected_users, 'data/protected_users.json')

    # --- MONSTER SYSTEM ---
    async def spawn_monster(self):
        self.current_monster = random.choice(self.monsters_data).copy()
        self.current_monster['current_hp'] = self.current_monster['max_hp']
        self.monster_attackers.clear()

        channel = self.bot.get_channel(self.event_channel_id)
        if not channel: return

        embed = discord.Embed(title=f"🚨 ANCAMAN BARU MUNCUL! 🚨\n{self.current_monster['name']}", description=f"_{self.current_monster['story']}_", color=discord.Color.red())
        embed.set_thumbnail(url=self.current_monster['image_url'])
        embed.add_field(name="❤️ HP", value=f"**{self.current_monster['current_hp']:,}/{self.current_monster['max_hp']:,}**", inline=True)
        embed.add_field(name="⚔️ Tipe", value=self.current_monster['type'], inline=True)
        embed.set_footer(text="Gunakan !serangmonster untuk melawan! Hati-hati, monster ini akan menyerang pemain aktif!")
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
        self.monster_attack_queue = [{'user_id': uid, 'attack_time': now + timedelta(hours=random.randint(i*4+1, (i+1)*4))} for i, uid in enumerate(targets)]

    @tasks.loop(minutes=15)
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
        
        # ... (Kode untuk mengurangi EXP dan RSWN) ...
        
        channel = self.bot.get_channel(self.event_channel_id)
        if channel:
            await channel.send(f"⚔️ **SERANGAN MONSTER!** {self.current_monster['name']} menyerang {member.mention}! Kamu kehilangan **{exp_loss} EXP** dan **{rswn_loss} RSWN**!")
        
        self.monster_attack_queue.pop(0)

    @commands.command(name="serangmonster")
    async def serangmonster(self, ctx, *mentioned_members: discord.Member):
        # ... (Kode serangan monster dari respons sebelumnya, tidak ada perubahan) ...
        pass
    
    # --- ANOMALY & EVENT SYSTEM ---
    async def trigger_anomaly(self):
        anomaly = random.choice(self.anomalies_data)
        self.active_anomaly = anomaly
        self.anomaly_end_time = datetime.utcnow() + timedelta(seconds=anomaly['duration_seconds'])
        
        channel = self.bot.get_channel(self.event_channel_id)
        if not channel: return
        
        embed = discord.Embed(title=f"🌀 ANOMALI TERDETEKSI: {anomaly['name']} 🌀", description=anomaly['description'], color=discord.Color.from_str(anomaly['color']))
        await channel.send(embed=embed)
        
        if anomaly['type'] == 'exp_boost':
            # Logika untuk boost EXP bisa ditangani di on_message di leveling.py
            # dengan mengecek self.bot.get_cog('DuniaHidup').active_anomaly
            pass
        elif anomaly['type'] == 'sickness_plague':
            await self.start_sickness_plague(channel.guild)
        elif anomaly['type'] == 'code_drop':
            self.bot.loop.create_task(self.code_dropper(anomaly['duration_seconds']))
            
        await asyncio.sleep(anomaly['duration_seconds'])
        
        await channel.send(f"Anomali **{anomaly['name']}** telah berakhir.")
        self.active_anomaly = None
        self.anomaly_end_time = None

    async def code_dropper(self, duration):
        end_time = datetime.utcnow() + timedelta(seconds=duration)
        while datetime.utcnow() < end_time:
            await asyncio.sleep(random.randint(300, 900)) # Drop setiap 5-15 menit
            if not self.active_anomaly: break
            
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            reward = {"rswn": random.randint(500, 2000), "exp": random.randint(500, 2000)}
            self.dropped_codes[code] = reward
            
            channel = self.bot.get_channel(self.event_channel_id)
            if channel:
                await channel.send(f"☄️ **HUJAN METEOR!** Sebuah kode rahasia jatuh! Ketik `!klaim {code}` untuk hadiah!")
            
            self.bot.loop.create_task(self.expire_code(code))

    async def expire_code(self, code):
        await asyncio.sleep(120) # Kode hangus dalam 2 menit
        if code in self.dropped_codes:
            del self.dropped_codes[code]

    @commands.command(name="klaim")
    async def klaim(self, ctx, code: str):
        if code in self.dropped_codes:
            reward = self.dropped_codes[code]
            # Beri hadiah RSWN
            bank_data = load_json_from_root('data/bank_data.json')
            bank_data.setdefault(str(ctx.author.id), {'balance': 0, 'debt': 0})['balance'] += reward['rswn']
            save_json_to_root(bank_data, 'data/bank_data.json')
            # Beri hadiah EXP
            level_data = load_json_from_root('data/level_data.json')
            guild_data = level_data.setdefault(str(ctx.guild.id), {})
            user_data = guild_data.setdefault(str(ctx.author.id), {'exp': 0, 'level': 0})
            user_data['exp'] += reward['exp']
            save_json_to_root(level_data, 'data/level_data.json')

            await ctx.send(f"🎉 Selamat {ctx.author.mention}! Kamu berhasil mengklaim hadiah **{reward['rswn']} RSWN** dan **{reward['exp']} EXP**!")
            del self.dropped_codes[code]
        else:
            await ctx.send("Kode tidak valid atau sudah hangus.", delete_after=10)

    # --- SICKNESS SYSTEM ---
    async def start_sickness_plague(self, guild):
        level_data = load_json_from_root('data/level_data.json').get(str(guild.id), {})
        active_users = [uid for uid, data in level_data.items() if 'last_active' in data and datetime.utcnow() - datetime.fromisoformat(data['last_active']) < timedelta(days=3)]
        
        num_to_infect = min(len(active_users), random.randint(3, 7))
        infected_users = random.sample(active_users, num_to_infect)
        
        role = guild.get_role(self.sick_role_id)
        if not role: return
        
        for user_id in infected_users:
            member = guild.get_member(int(user_id))
            if member:
                await member.add_roles(role)
                self.sick_users[user_id] = {"message_count": 0, "last_message_time": datetime.utcnow().isoformat()}
        
        save_json_to_root(self.sick_users, 'data/sick_users.json')
        channel = self.bot.get_channel(self.event_channel_id)
        if channel:
            await channel.send(f"😷 **WABAH MENYEBAR!** {num_to_infect} anggota telah jatuh sakit. Interaksi mereka akan terbatas. Cepat cari obat di `!toko`!")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild: return
        
        user_id_str = str(message.author.id)
        if user_id_str in self.sick_users:
            sick_info = self.sick_users[user_id_str]
            now = datetime.utcnow()
            last_msg_time = datetime.fromisoformat(sick_info.get("last_message_time", "2000-01-01T00:00:00"))
            
            if now - last_msg_time < timedelta(seconds=60):
                sick_info["message_count"] += 1
                if sick_info["message_count"] > 3: # Hanya 3 pesan per menit
                    try:
                        await message.delete()
                        await message.author.send("Kamu sedang sakit dan terlalu lemah untuk banyak bicara. Istirahatlah sejenak.", delete_after=60)
                    except discord.Forbidden: pass
                    return
            else:
                sick_info["message_count"] = 1
            sick_info["last_message_time"] = now.isoformat()
            save_json_to_root(self.sick_users, 'data/sick_users.json')
        
        # Penting agar command lain tetap berjalan
        await self.bot.process_commands(message)

    @commands.command(name="minumobat")
    async def minumobat(self, ctx):
        user_id_str = str(ctx.author.id)
        inventory_data = load_json_from_root('data/inventory.json')
        user_inventory = inventory_data.get(user_id_str, [])

        # Cari kotak obat di inventory
        medicine_box = next((item for item in user_inventory if item.get('type') == 'medicine_box'), None)
        
        if not medicine_box:
            return await ctx.send("Kamu tidak punya Kotak Obat Misterius. Beli dulu di `!toko`.")
        
        # Hapus 1 kotak obat dari inventory
        user_inventory.remove(medicine_box)
        save_json_to_root(inventory_data, 'data/inventory.json')
        
        # Logika Gacha Obat
        await ctx.send("Membuka Kotak Obat Misterius...")
        await asyncio.sleep(2)
        
        # Ambil probabilitas dan kocok
        choices = [med['name'] for med in self.medicines_data]
        weights = [med['chance'] for med in self.medicines_data]
        chosen_medicine_name = random.choices(choices, weights=weights, k=1)[0]
        chosen_medicine = next(med for med in self.medicines_data if med['name'] == chosen_medicine_name)

        embed = discord.Embed(title="Hasil Gacha Obat", description=f"Kamu mendapatkan... **{chosen_medicine['name']}**!", color=discord.Color.from_str(chosen_medicine['color']))
        embed.add_field(name="Efek", value=chosen_medicine['effect_desc'])
        await ctx.send(embed=embed)
        
        # Terapkan efek
        if user_id_str in self.sick_users:
            heal_roll = random.randint(1, 100)
            if heal_roll <= chosen_medicine['heal_chance']:
                embed_result = discord.Embed(title="Obat Bekerja!", color=discord.Color.green())
                # Sembuh Total
                role = ctx.guild.get_role(self.sick_role_id)
                if role: await ctx.author.remove_roles(role)
                del self.sick_users[user_id_str]
                save_json_to_root(self.sick_users, 'data/sick_users.json')
                
                # Beri perlindungan jika obat mujarab
                if chosen_medicine['heal_chance'] == 100:
                    expiry = datetime.utcnow() + timedelta(hours=24)
                    self.protected_users[user_id_str] = expiry.isoformat()
                    save_json_to_root(self.protected_users, 'data/protected_users.json')
                    embed_result.description = "Kamu sembuh total! Role 'Sakit' telah dilepas dan kamu mendapat perlindungan dari serangan monster selama 24 jam!"
                else:
                    embed_result.description = "Kamu merasa jauh lebih baik dan sembuh total! Role 'Sakit' telah dilepas."
                
                await ctx.send(embed=embed_result)
            else:
                await ctx.send("Sayang sekali... obatnya tidak bekerja. Kamu masih sakit. Coba lagi lain kali.")
        else:
            await ctx.send("Kamu meminum obatnya, tapi karena kamu tidak sakit, tidak ada efek apa-apa.")

async def setup(bot):
    await bot.add_cog(DuniaHidup(bot))

