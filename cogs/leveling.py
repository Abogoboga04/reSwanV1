import discord
from discord.ext import commands, tasks
import json
import os
import random
import logging
import asyncio
from datetime import datetime
from PIL import Image, ImageDraw
import requests
from io import BytesIO
import aiohttp


# ========== KONFIGURASI UTAMA ==========
DATA_FILE = "data/level_data.json"
BANK_FILE = "data/bank_data.json"
SHOP_FILE = "data/shop_items.json"
QUESTS_FILE = "data/quests.json"
WEEKLY_RESET_DAY = 0  # Senin (0 = Senin, 6 = Minggu)

LEVEL_ROLES = {
    1: 1255275460926111775,
    2: 1255275460926111775,
    3: 1255275460926111775,
    4: 1255275460926111775,
    5: 1380825351235571743,
    6: 1380825351235571743,
    7: 1381011171309785230,
    8: 1381011171309785230,
    9: 1381011171309785230,
    10: 1380827670220247152,
    11: 1380827670220247152,
    12: 1380827670220247152,
    13: 1380828063058628669,
    14: 1380828063058628669,
    15: 1380828063058628669,
    16: 1380828063058628669,
    17: 1381009806722338927,
    18: 1381009806722338927,
    19: 1381009806722338927,
    20: 1380828272019111946,
    21: 1380828272019111946,
    22: 1380828272019111946,
    23: 1380828272019111946,
    24: 1380828272019111946,
    25: 1381011504324935783,
}

LEVEL_BADGES = {
    5: "🥉",
    10: "🥈",
    15: "🥇",
}

LEVEL_ANNOUNCE_CHANNEL_ID = 7651403001460896  # Ganti dengan ID channel pengumuman

LEVEL_DATA_PATH = "data/level_data.json"

def load_data(guild_id):
    if not os.path.exists(LEVEL_DATA_PATH):
        return {}
    with open(LEVEL_DATA_PATH, "r") as f:
        all_data = json.load(f)
    return all_data.get(guild_id, {})

def save_data(guild_id, data):
    if os.path.exists(LEVEL_DATA_PATH):
        with open(LEVEL_DATA_PATH, "r") as f:
            all_data = json.load(f)
    else:
        all_data = {}

    all_data[guild_id] = data

    with open(LEVEL_DATA_PATH, "w") as f:
        json.dump(all_data, f, indent=2)
# ========== FUNGSI UTILITAS ==========
def calculate_level(exp):
    return exp // 3200

def load_data(guild_id):
    # Implementasi untuk memuat data dari file JSON
    pass

def save_data(guild_id, data):
    # Implementasi untuk menyimpan data ke file JSON
    pass

async def crop_avatar_to_circle(user: discord.User):
    async with aiohttp.ClientSession() as session:
        async with session.get(user.display_avatar.url) as resp:
            avatar_bytes = await resp.read()

    with Image.open(BytesIO(avatar_bytes)).convert("RGBA") as img:
        size = (256, 256)
        img = img.resize(size)

        mask = Image.new("L", size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0) + size, fill=255)

        output = Image.new("RGBA", size)
        output.paste(img, (0, 0), mask)

        buffer = BytesIO()
        output.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer  # <--- ini penting: kembalikan buffe
    

def ensure_data_files():
    os.makedirs("data", exist_ok=True)
    for file in [DATA_FILE, BANK_FILE, SHOP_FILE, QUESTS_FILE]:
        if not os.path.exists(file):
            with open(file, "w") as f:
                if file == SHOP_FILE or file == QUESTS_FILE:
                    json.dump({"items": {}, "quests": {}}, f)
                else:
                    json.dump({}, f)

# ========== FUNGSI UNTUK MENGATUR DATA ==========
def load_data(guild_id):
    ensure_data_files()
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get(guild_id, {})
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_data(guild_id, data):
    ensure_data_files()
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            all_data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        all_data = {}

    all_data[guild_id] = data
    with open(DATA_FILE, "w") as f:
        json.dump(all_data, f, indent=4)

def load_bank_data():
    ensure_data_files()
    try:
        with open(BANK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_bank_data(data):
    ensure_data_files()
    with open(BANK_FILE, "w") as f:
        json.dump(data, f, indent=4)

def load_shop_items(self):
    """Load shop items from a JSON file."""
    try:
        with open('shop_items.json', 'r') as f:
            data = json.load(f)
            return data.get('shop', {})  # Ambil item dari JSON
    except FileNotFoundError:
        return {}  # Kembali ke dictionary kosong jika file tidak ditemukan

def save_shop_items(self):
    """Simpan item ke file JSON."""
    with open('shop_items.json', 'w') as f:
        json.dump({"shop": self.shop_items}, f, indent=4)

def load_quests_data():
    ensure_data_files()
    try:
        with open(QUESTS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"quests": {}}

def save_quests_data(data):
    ensure_data_files()
    with open(QUESTS_FILE, "w") as f:
        json.dump(data, f, indent=4)

class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.EXP_PER_MINUTE_VC = 5  # EXP per menit di voice channel
        self.RSWN_PER_MINUTE_VC = 10  # RSWN per menit di voice channel
        self.EXP_PER_MESSAGE = 10  # EXP per pesan
        self.RSWN_PER_MESSAGE = 1  # RSWN per pesan
        self.voice_task = self.create_voice_task()
        self.daily_quest_task = self.daily_quest_task.start()
        self.voice_task.start()

        logging.basicConfig(level=logging.INFO)

    def create_voice_task(self):
        @tasks.loop(minutes=1)
        async def voice_task():
            try:
                now = datetime.utcnow()
                for guild in self.bot.guilds:
                    guild_id = str(guild.id)
                    data = load_data(guild_id)

                    # Inisialisasi bank_data di luar loop
                    bank_data = load_bank_data()

                    for vc in guild.voice_channels:
                        for member in vc.members:
                            if member.bot:
                                continue

                            user_id = str(member.id)
                            if user_id not in data:
                                data[user_id] = {
                                    "exp": 0,
                                    "weekly_exp": 0,
                                    "level": 0,
                                    "badges": []
                                }

                            # Tambah EXP
                            data[user_id]["exp"] += self.EXP_PER_MINUTE_VC
                            data[user_id]["weekly_exp"] += self.EXP_PER_MINUTE_VC

                            if user_id not in bank_data:
                                bank_data[user_id] = {"balance": 0, "debt": 0}

                            bank_data[user_id]["balance"] += self.RSWN_PER_MINUTE_VC


                            # Cek level baru
                            new_level = calculate_level(data[user_id]["exp"])
                            if new_level > data[user_id]["level"]:
                                data[user_id]["level"] = new_level
                                await self.level_up(member, guild, vc, new_level, data)

                    save_data(guild_id, data)
                    save_bank_data(bank_data)  # Simpan data bank setelah menambahkan RSWN

                    if now.weekday() == WEEKLY_RESET_DAY and now.date() != self.last_reset.date():
                        for user_data in data.values():
                            user_data["weekly_exp"] = 0
                        self.last_reset = now
                        save_data(guild_id, data)
            except Exception as e:
                print(f"Error in voice task: {e}")

        return voice_task
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if message.content.startswith(self.bot.command_prefix):
            logging.info(f"Pesan adalah perintah: {message.content}")
            return

        user_id = str(message.author.id)
        guild_id = str(message.guild.id)
        data = load_data(guild_id)

        if user_id not in data:
            data[user_id] = {
                "exp": 0,
                "weekly_exp": 0,
                "level": 0,
                "badges": [],
                "last_active": None,
                "booster": {}
            }

        booster = data[user_id].get("booster", {})
        multiplier = 1
        expires = booster.get("expires_at")

        # Memeriksa apakah booster aktif
        expires = booster.get("expires_at")
        print(f"User ID: {user_id}, Expires At: {expires}")  # Debugging expires_at

        if expires:
            try:
                # Cek apakah booster belum expired
                if datetime.utcnow() < datetime.fromisoformat(expires):
                    multiplier = booster.get("exp_multiplier", 1)
                    print(f"Booster aktif! Multiplier: {multiplier}")  # Debugging multiplier
                else:
                    print("Booster sudah expired!")  # Debugging expired
                    data[user_id]["booster"] = {}  # Reset booster jika sudah expired
            except Exception as e:
                print(f"[BOOSTER ERROR] Gagal parsing expires_at: {e}")
                data[user_id]["booster"] = {}  # Reset jika ada kesalahan parsing

        exp_gain = int(self.EXP_PER_MESSAGE * multiplier)
        data[user_id]["exp"] += exp_gain
        print(f"User ID: {user_id}, EXP yang didapat: {exp_gain}, Total EXP: {data[user_id]['exp']}")  # Debugging EXP
        # Hitung RSWN
        rswn_gain = int(self.RSWN_PER_MESSAGE * multiplier)  # Hitung RSWN dengan multiplier
        bank_data = load_bank_data()
        if user_id not in bank_data:
            bank_data[user_id] = {"balance": 0, "debt": 0}

        bank_data[user_id]["balance"] += rswn_gain  # Tambahkan RSWN ke saldo
        print(f"User ID: {user_id}, RSWN yang didapat: {rswn_gain}, Total Saldo: {bank_data[user_id]['balance']}")  # Debugging RSWN


        data[user_id]["exp"] += exp_gain
        data[user_id]["weekly_exp"] += exp_gain
        data[user_id]["last_active"] = datetime.utcnow().isoformat()
           # Simpan gold ke bank
        bank_data = load_bank_data()
        if user_id not in bank_data:
            bank_data[user_id] = {"balance": 0, "debt": 0}
        bank_data[user_id]["balance"] += rswn_gain

         # Logging console
        print(f"[ACTIVITY] {message.author} dapat +{exp_gain} EXP & +{rswn_gain} RSWN (x{multiplier} booster)")

        # Cek level baru
        new_level = calculate_level(data[user_id]["exp"])
        if new_level > data[user_id]["level"]:
            data[user_id]["level"] = new_level
            await self.level_up(message.author, message.guild, message.channel, new_level, data)
        save_data(guild_id, data)
        save_bank_data(bank_data)

    @tasks.loop(hours=24)
    async def daily_quest_task(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            quests_data = load_quests_data()
            quests = list(quests_data.get("quests", {}).values())
            if quests:
                random_quest = random.choice(quests)

                # Simpan quest yang dipilih untuk hari ini
                with open(f"data/daily_quest_{guild.id}.json", "w") as f:
                    json.dump(random_quest, f)

                # Kirim pesan ke channel pengumuman
                announce_channel = guild.get_channel(LEVEL_ANNOUNCE_CHANNEL_ID)
                if announce_channel:
                    await announce_channel.send(f"🎉 Quest Harian Baru! {random_quest['description']} (Reward: {random_quest['reward_exp']} EXP, {random_quest['reward_coins']} 🪙RSWN)")

    async def level_up(self, member, guild, channel, new_level, data):
        try:
            role_id = LEVEL_ROLES.get(new_level)
            if role_id:
                role = guild.get_role(role_id)
                if role:
                    await member.add_roles(role)

            badge = LEVEL_BADGES.get(new_level)
            if badge and badge not in data[str(member.id)]["badges"]:
                data[str(member.id)]["badges"].append(badge)
                save_data(str(guild.id), data)

            announce_channel = guild.get_channel(LEVEL_ANNOUNCE_CHANNEL_ID)
            if announce_channel:
                embed = discord.Embed(
                    title="🎉 Level Up!",
                    description=f"{member.mention} telah mencapai level **{new_level}**!",
                    color=discord.Color.green()
                )
                await announce_channel.send(embed=embed)
        except Exception as e:
            print(f"Error in level_up: {e}")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def add_quest(self, ctx, description: str, reward_exp: int, reward_coins: int):
        """Menambahkan quest baru (Admin only)"""
        if reward_exp < 0 or reward_coins < 0:
            return await ctx.send("❌ Reward harus bernilai positif!")

        quests_data = load_quests_data()
        new_id = str(len(quests_data.get("quests", {})) + 1)

        quests_data.setdefault("quests", {})[new_id] = {
            "description": description,
            "reward_exp": reward_exp,
            "reward_coins": reward_coins
        }

        save_quests_data(quests_data)
        await ctx.send(f"✅ Quest baru berhasil ditambahkan dengan ID `{new_id}`!")

    @commands.command()
    async def daily_quest(self, ctx):
        """Ambil quest harian"""
        guild_id = str(ctx.guild.id)
        try:
            with open(f"data/daily_quest_{guild_id}.json", "r", encoding="utf-8") as f:
                daily_quest = json.load(f)
            await ctx.send(f"🎯 Quest Harian: {daily_quest['description']}")
        except FileNotFoundError:
            await ctx.send("❌ Belum ada quest harian yang ditentukan!")


    @commands.command()
    async def complete_quest(self, ctx):
        """Selesaikan quest harian dan dapatkan reward"""
        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)

        try:
            with open(f"data/daily_quest_{guild_id}.json", "r") as f:
                daily_quest = json.load(f)

            # Load user data
            data = load_data(guild_id)
            if user_id not in data:
                data[user_id] = {
                    "exp": 0,
                    "level": 0,
                    "weekly_exp": 0,
                    "badges": [],
                    "last_completed_quest": None  # Tambahkan field baru
                }

            # Cek apakah pengguna sudah menyelesaikan quest hari ini
            last_completed = data[user_id].get("last_completed_quest")
            if last_completed:
                last_completed_date = datetime.fromisoformat(last_completed)
                if last_completed_date.date() == datetime.utcnow().date():
                    return await ctx.send("❌ Kamu sudah menyelesaikan quest harian hari ini!")

            # Tambahkan reward ke pengguna
            data[user_id]["exp"] += daily_quest["reward_exp"]
            data[user_id]["last_completed_quest"] = datetime.utcnow().isoformat()  # Update timestamp
            save_data(guild_id, data)

            # Tambahkan coins (RSWN) ke pengguna
            bank_data = load_bank_data()
            if user_id not in bank_data:
                bank_data[user_id] = {"balance": 0, "debt": 0}

            bank_data[user_id]["balance"] += daily_quest["reward_coins"]
            save_bank_data(bank_data)

            await ctx.send(f"✅ Kamu telah menyelesaikan quest harian! Reward: {daily_quest['reward_exp']} EXP dan {daily_quest['reward_coins']} 🪙RSWN.")
        except FileNotFoundError:
            await ctx.send("❌ Belum ada quest harian yang ditentukan!")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def giveexp(self, ctx, member: discord.Member, amount: int):
        """Memberikan EXP kepada pengguna"""
        if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            await ctx.message.delete()

        guild_id = str(ctx.guild.id)
        data = load_data(guild_id)
        user_id = str(member.id)
        now = datetime.utcnow().isoformat()

        if user_id not in data:
            data[user_id] = {
                "exp": 0,
                "level": 0,
                "last_active": now,
                "weekly_exp": 0,
                "badges": []
            }

        # Tambah EXP dan update waktu aktif
        data[user_id]["exp"] += amount
        data[user_id]["weekly_exp"] += amount
        data[user_id]["last_active"] = now

        # Cek apakah naik level
        current_exp = data[user_id]["exp"]
        old_level = data[user_id]["level"]
        new_level = calculate_level(current_exp)

        if new_level > old_level:
            data[user_id]["level"] = new_level
            save_data(guild_id, data)
            await self.level_up(member, ctx.guild, ctx.channel, new_level, data)
        else:
            save_data(guild_id, data)

        # Kirim pesan ke user yang diberi EXP
        try:
            await member.send(
                f"🎁 Kamu telah menerima **{amount} EXP gratis** dari {ctx.author.mention}!"
            )
        except discord.Forbidden:
            await ctx.send("❌ Gagal mengirim pesan ke user (DM tertutup).")

        # Kirim DM ke admin yang memberi EXP
        await ctx.author.send(
            f"✅ Kamu telah memberikan **{amount} EXP** ke {member.mention} secara rahasia."
        )

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def givecoins(self, ctx, member: discord.Member, amount: int):
        """Memberikan RSWN gratis kepada pengguna tanpa mengurangi saldo admin"""
        if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            await ctx.message.delete()

        bank_data = load_bank_data()
        user_id = str(member.id)

        if user_id not in bank_data:
            bank_data[user_id] = {"balance": 0, "debt": 0}

        bank_data[user_id]["balance"] += amount
        save_bank_data(bank_data)

        # Kirim DM ke penerima
        try:
            await member.send(
                f"🎉 Kamu telah menerima **{amount} 🪙RSWN gratis** dari admin {ctx.author.mention}!"
            )
        except discord.Forbidden:
            await ctx.send("❌ Gagal mengirim pesan ke user (DM tertutup).")

        # Kirim konfirmasi DM ke admin
        await ctx.author.send(
            f"✅ Kamu telah memberikan **{amount} 🪙RSWN gratis** ke {member.mention}."
        )

    @commands.command()
    async def transfercoins(self, ctx, member: discord.Member, amount: int):
        """Memberikan RSWN kepada pengguna lain"""
        if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            await ctx.message.delete()

        bank_data = load_bank_data()
        sender_id = str(ctx.author.id)
        receiver_id = str(member.id)

        if sender_id not in bank_data:
            bank_data[sender_id] = {"balance": 0, "debt": 0}

        if bank_data[sender_id]["balance"] < amount:
            return await ctx.send("❌ Saldo tidak cukup!")

        if receiver_id not in bank_data:
            bank_data[receiver_id] = {"balance": 0, "debt": 0}

        # Kurangi saldo dari pengirim dan tambahkan ke penerima
        bank_data[sender_id]["balance"] -= amount
        bank_data[receiver_id]["balance"] += amount
        save_bank_data(bank_data)

        # Kirim DM ke penerima
        try:
            await member.send(
                f"🎉 Kamu telah menerima **{amount} 🪙RSWN** dari {ctx.author.mention}!"
            )
        except discord.Forbidden:
            await ctx.send("❌ Gagal mengirim pesan ke user (DM tertutup).")

        # Kirim konfirmasi DM ke pengirim
        await ctx.author.send(
            f"✅ Kamu telah memberikan **{amount} 🪙RSWN** ke {member.mention}."
        )

    @commands.command()
    async def buyexp(self, ctx, amount: int, member: commands.MemberConverter = None):
        """Beli EXP menggunakan RSWN. Gunakan: !buyexp <amount> [@user]"""
        if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            await ctx.message.delete()

        bank_data = load_bank_data()
        user_id = str(ctx.author.id)

        if user_id not in bank_data:
            bank_data[user_id] = {"balance": 0, "debt": 0}

        cost = amount * 1  # Misalnya, 1 RSWN per EXP

        if bank_data[user_id]["balance"] < cost:
            return await ctx.send("❌ Saldo tidak cukup untuk membeli EXP.")

        # Jika member tidak disebutkan, gunakan pengirim pesan
        if member is None:
            member = ctx.author

        # Ambil data dari guild
        guild_id = str(ctx.guild.id)
        data = load_data(guild_id)

        # Periksa apakah pengguna yang dituju ada dalam data
        target_user_id = str(member.id)
        if target_user_id not in data:
            data[target_user_id] = {
                "exp": 0,
                "level": 0,
                "weekly_exp": 0,
                "badges": []
            }

        # Tambah EXP ke pengguna yang dituju
        data[target_user_id]["exp"] += amount
        data[target_user_id]["weekly_exp"] += amount
        bank_data[user_id]["balance"] -= cost

        save_data(guild_id, data)
        save_bank_data(bank_data)

        await ctx.send(f"✅ Kamu telah membeli {amount} EXP untuk {member.mention} dengan harga {cost} 💰 RSWN!")

        # Kirim DM ke pengguna yang dituju
        try:
            await member.send(
                f"📩 {ctx.author.mention} telah membeli {amount} EXP untukmu!"
            )
        except discord.Forbidden:
            await ctx.send("❌ Gagal mengirim pesan ke user (DM tertutup).")

    @commands.command()
    async def coins(self, ctx):

        """Tampilkan saldo RSWN pengguna"""
        user_id = str(ctx.author.id)
        bank_data = load_bank_data()

        if user_id not in bank_data:
            bank_data[user_id] = {"balance": 0, "debt": 0}

        balance = bank_data[user_id]["balance"]
        await ctx.send(f"💰 Saldo kamu: {balance} 🪙RSWN")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setlevel(self, ctx, member: discord.Member, level: int):
        """Set level pengguna (Admin only)"""
        guild_id = str(ctx.guild.id)
        data = load_data(guild_id)
        user_id = str(member.id)

        if user_id not in data:
            data[user_id] = {
                "exp": 0,
                "level": 0,
                "weekly_exp": 0,
                "badges": []
            }

        data[user_id]["level"] = level
        save_data(guild_id, data)

        await ctx.send(f"✅ Level {member.mention} telah diset menjadi {level}!")
    async def give_role(self, member, role_name):
        """Memberikan role kepada pengguna."""
        role = discord.utils.get(member.guild.roles, name=role_name)
        if role:
            await member.add_roles(role)
            print(f"Role {role_name} diberikan kepada {member.name}.")
        else:
            print(f"Role {role_name} tidak ditemukan.")

    async def check_level_up(self, member):
        """Cek apakah pengguna naik level dan berikan role jika perlu."""
        user_id = member.id
        user_level = self.levels.get(user_id, 0)  # Ambil level pengguna
        user_xp = self.get_user_xp(user_id)  # Fungsi untuk mendapatkan XP pengguna

        # Misalkan setiap level membutuhkan 100 XP (ubah sesuai kebutuhan)
        required_xp = (user_level + 1) * 750

        if user_xp >= required_xp:
            self.levels[user_id] += 1  # Naik level
            await self.give_role(member, f"Level {self.levels[user_id]}")  # Berikan role baru

    @commands.command()
    async def leaderboard(self, ctx):
        """Tampilkan leaderboard pengguna berdasarkan EXP"""
        guild_id = str(ctx.guild.id)
        data = load_data(guild_id)
        sorted_users = sorted(data.items(), key=lambda x: x[1]['exp'], reverse=True)

        embed = discord.Embed(title="🏆 Leaderboard EXP", color=discord.Color.gold())
        embed.set_thumbnail(url=ctx.guild.icon.url)  # Set thumbnail dengan foto profil server
        for idx, (user_id, user_data) in enumerate(sorted_users[:10], start=1):
            user = ctx.guild.get_member(int(user_id))
            badges = " ".join(user_data["badges"]) if user_data.get("badges") else "Tidak ada"
            embed.add_field(name=f"{idx}. {user.mention} ({user.display_name})", 
                            value=f"EXP: {user_data['exp']}\n💰 Saldo: {load_bank_data().get(user_id, {}).get('balance', 0)} 🪙RSWN\n🏅 Badges: {badges}", 
                            inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    async def weekly(self, ctx):
        """Tampilkan leaderboard mingguan berdasarkan EXP"""
        guild_id = str(ctx.guild.id)
        data = load_data(guild_id)
        sorted_users = sorted(data.items(), key=lambda x: x[1]['weekly_exp'], reverse=True)

        embed = discord.Embed(title="🏅 Weekly Leaderboard", color=discord.Color.blue())
        embed.set_thumbnail(url=ctx.guild.icon.url)  # Set thumbnail dengan foto profil server
        for idx, (user_id, user_data) in enumerate(sorted_users[:10], start=1):
            user = ctx.guild.get_member(int(user_id))
            badges = " ".join(user_data["badges"]) if user_data.get("badges") else "Tidak ada"
            embed.add_field(name=f"{idx}. {user.mention} ({user.display_name})", 
                            value=f"Weekly EXP: {user_data['weekly_exp']}\n💰 Saldo: {load_bank_data().get(user_id, {}).get('balance', 0)} 🪙RSWN\n🏅 Badges: {badges}", 
                            inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    async def rank(self, ctx):
        """Tampilkan rank pengguna saat ini"""
        user_id = str(ctx.author.id)
        guild_id = str(ctx.guild.id)

        # Load data level dengan penanganan kesalahan
        try:
            if not os.path.exists("data/level_data.json"):
                with open("data/level_data.json", "w") as f:
                    json.dump({}, f)

            with open("data/level_data.json", "r") as f:
                data = json.load(f)

            guild_data = data.setdefault(guild_id, {})
            user_data = guild_data.setdefault(user_id, {
                "exp": 0,
                "level": 0,
                "weekly_exp": 0,
                "badges": [],
                "image_url": None
            })

            # Save data setelah setdefault
            with open("data/level_data.json", "w") as f:
                json.dump(data, f, indent=2)

        except json.JSONDecodeError:
            await ctx.send("Terjadi kesalahan saat memuat data level. File mungkin rusak.")
            return
        except Exception as e:
            await ctx.send(f"Terjadi kesalahan: {str(e)}")
            return

        # Mengambil dan menyaring badge
        badge_list = user_data.get("badges", [])
        badge_display = [badge for badge in badge_list if badge is not None and not str(badge).startswith("http")]
        badges = " ".join(badge_display) or "Tidak ada"

        # Mengambil URL gambar
        custom_image_url = user_data.get("image_url") or str(ctx.author.avatar.url)

        # Cek validitas URL gambar
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(custom_image_url) as resp:
                    if resp.status != 200:
                        custom_image_url = str(ctx.author.avatar.url)
                    image_data = BytesIO(await resp.read())
        except Exception:
            custom_image_url = str(ctx.author.avatar.url)
            async with aiohttp.ClientSession() as session:
                async with session.get(custom_image_url) as resp:
                    image_data = BytesIO(await resp.read())

        # Membuat embed untuk menampilkan informasi
        embed = discord.Embed(title=f"📊 Rank {ctx.author.display_name}", color=discord.Color.purple())
        embed.set_thumbnail(url="attachment://avatar.png")
        embed.add_field(name="Level", value=user_data["level"], inline=True)
        embed.add_field(name="Saldo", value=f"{load_bank_data().get(user_id, {}).get('balance', 0)} 🪙RSWN", inline=True)
        embed.add_field(name="EXP", value=user_data["exp"], inline=True)

        await ctx.send(file=discord.File(image_data, "avatar.png"), embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def resetall(self, ctx):
        """Reset semua data pengguna di server ini"""
        ensure_data_files()
        guild_id = str(ctx.guild.id)
        data = load_data(guild_id)

        # Hapus data EXP tetapi simpan data bank
        for user_id in data.keys():
            data[user_id]["exp"] = 0
            data[user_id]["weekly_exp"] = 0
            data[user_id]["level"] = 0
            data[user_id]["badges"] = 0

        save_data(guild_id, data)
        await ctx.send("✅ Semua data EXP pengguna di server ini telah direset!")

async def setup(bot):
    await bot.add_cog(Leveling(bot))
