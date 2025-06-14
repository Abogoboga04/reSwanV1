import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
import json
import re
import asyncio
import random
import os
import shutil
from datetime import datetime, timedelta

DEFAULT_RULES = {
    "detect_links": False,
    "detect_images": False,
    "detect_bot_messages": False,
    "detect_bad_words": False
}

CONFIG_PATH = 'config/channel_rules.json'
PATTERNS_PATH = 'config/suspicious_patterns.json'
WELCOME_MESSAGE_PATH = 'config/welcome_message.json'
BADWORDS_PATH = 'config/badwords.json'
SUSPICIOUS_LINKS_PATH = 'config/suspicious_links.json'

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.load_channel_rules()
        self.load_suspicious_links()
        self.load_suspicious_messages()
        self.suspicious_patterns = self.load_suspicious_patterns()
        self.pending_reviews = {}
        self.cleanup_suspicious_messages.start()

    def load_channel_rules(self):
        try:
            with open(CONFIG_PATH) as f:
                self.channel_rules = json.load(f)
        except FileNotFoundError:
            self.channel_rules = {}

    def save_channel_rules(self):
        with open(CONFIG_PATH, 'w') as f:
            json.dump(self.channel_rules, f, indent=4)

    def load_suspicious_links(self):
        try:
            with open(SUSPICIOUS_LINKS_PATH) as f:
                self.suspicious_links = json.load(f)
        except FileNotFoundError:
            self.suspicious_links = []

    def save_suspicious_links(self):
        with open(SUSPICIOUS_LINKS_PATH, 'w') as f:
            json.dump(self.suspicious_links, f, indent=4)

    def load_suspicious_messages(self):
        try:
            with open('config/suspicious_messages.json') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self.suspicious_messages = data.get("messages", [])
                elif isinstance(data, list):
                    self.suspicious_messages = data
                else:
                    self.suspicious_messages = []
        except:
            self.suspicious_messages = []

        if not self.suspicious_messages:
            self.suspicious_messages = ["Pesan mencurigakan terdeteksi."]

    def load_suspicious_patterns(self):
        try:
            with open(PATTERNS_PATH, 'r') as f:
                data = json.load(f)
                return data.get("patterns", [])
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    @tasks.loop(minutes=1)
    async def cleanup_suspicious_messages(self):
        now = datetime.utcnow()
        to_delete = []
        for msg_id, data in list(self.pending_reviews.items()):
            if now >= data['expires_at']:
                try:
                    await data['message'].delete()
                except:
                    pass
                to_delete.append(msg_id)
        for msg_id in to_delete:
            del self.pending_reviews[msg_id]

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        try:
            with open(WELCOME_MESSAGE_PATH) as f:
                welcome_message = json.load(f).get("message", "Selamat datang!")
            content = welcome_message.replace("{user}", member.display_name)
            await member.send(content)
        except:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        channel_id = str(message.channel.id)
        rules = self.channel_rules.get(channel_id, DEFAULT_RULES.copy())

        # Deteksi menggunakan pola dari file JSON
        for pattern in self.suspicious_patterns:
            if re.search(pattern, message.content):
                await self.handle_suspicious_message(message)
                return

        # Memeriksa aturan secara independen
        if rules.get("detect_links") and re.search(r"https?://", message.content):
            await message.reply("⚠️ Link tidak diizinkan.")
            await message.delete()
            self.add_link_to_json(message.content)
            return

        if rules.get("detect_bot_messages") and message.author.bot:
            await message.reply("⚠️ Pesan dari bot tidak diperbolehkan.")
            await message.delete()
            return

        if rules.get("detect_images") and message.attachments:
            await message.reply("⚠️ Gambar tidak diperbolehkan.")
            await message.delete()
            return

        if rules.get("detect_bad_words"):
            try:
                with open(BADWORDS_PATH) as f:
                    badwords = json.load(f)
            except:
                badwords = ["kasar", "bodoh"]
            for bw in badwords:
                if bw.lower() in message.content.lower():
                    await message.reply("⚠️ Kata kasar terdeteksi.")
                    await message.delete()
                    return

    async def handle_suspicious_message(self, message):
        warning_text = random.choice(self.suspicious_messages)
        view = SuspiciousActionView(self, message)
        sent = await message.channel.send(f"⚠️ {warning_text}", view=view)

        self.pending_reviews[str(message.id)] = {
            "message": sent,
            "original": message,
            "expires_at": datetime.utcnow() + timedelta(hours=5)
        }

    def add_link_to_json(self, link):
        # Membaca data yang sudah ada
        if os.path.exists(SUSPICIOUS_LINKS_PATH):
            with open(SUSPICIOUS_LINKS_PATH, 'r') as f:
                data = json.load(f)
        else:
            data = {"links": []}  # Inisialisasi jika file tidak ada

        # Menambahkan link baru
        if link not in data["links"]:
            data["links"].append(link)

        # Menyimpan kembali data ke file JSON
        with open(SUSPICIOUS_LINKS_PATH, 'w') as f:
            json.dump(data, f, indent=4)

        print(f"Link '{link}' telah ditambahkan ke dalam JSON.")

    @commands.command(name="add_pattern", help="Tambahkan pola regex ke dalam suspicious patterns.")
    @commands.has_permissions(administrator=True)
    async def add_pattern(self, ctx, *, pattern: str):
        # Membaca data yang sudah ada
        if os.path.exists(PATTERNS_PATH):
            with open(PATTERNS_PATH, 'r') as f:
                data = json.load(f)
        else:
            data = {"patterns": []}  # Inisialisasi jika file tidak ada

        # Menambahkan pola baru
        if pattern not in data["patterns"]:
            data["patterns"].append(pattern)

        # Menyimpan kembali data ke file JSON
        with open(PATTERNS_PATH, 'w') as f:
            json.dump(data, f, indent=4)

        await ctx.send(f"✅ Pola '{pattern}' telah ditambahkan ke dalam suspicious patterns.")

    @commands.command(name="setup_channel", help="Atur pengaturan channel dengan berbagai pilihan.")
    @commands.has_permissions(administrator=True)
    async def setup_channel(self, ctx):
        await ctx.send(
            "⚙️ Pilih pengaturan yang ingin diterapkan pada channel ini:",
            view=ChannelSetupView(ctx.channel.id),
            ephemeral=True
        )

    @commands.command(name="clear_rules", help="Hapus semua rules di channel ini")
    @commands.has_permissions(administrator=True)
    async def clear_rules(self, ctx):
        channel_id = str(ctx.channel.id)
        if channel_id in self.channel_rules:
            del self.channel_rules[channel_id]
            self.save_channel_rules()
            await ctx.send("✅ Semua aturan dihapus untuk channel ini.")
        else:
            await ctx.send("⚠️ Tidak ada aturan yang aktif di channel ini.")

    @commands.command(name="list_rules", help="Lihat rules aktif di channel ini")
    async def list_rules(self, ctx):
        channel_id = str(ctx.channel.id)
        rules = self.channel_rules.get(channel_id)
        if not rules:
            await ctx.send("Tidak ada rules yang aktif di channel ini.")
            return

        active = [name.replace("_", " ").title() for name, val in rules.items() if val]
        await ctx.send("✅ Rules aktif: " + ", ".join(active))

    @commands.command(name="backup_data", help="Backup semua data ke file.")
    @commands.has_permissions(administrator=True)
    async def backup_data(self, ctx):
        backup_dir = 'backup/'
        os.makedirs(backup_dir, exist_ok=True)

        for filename in os.listdir('config'):
            if filename.endswith('.json'):
                shutil.copy(os.path.join('config', filename), os.path.join(backup_dir, filename))

        await ctx.send("✅ Semua data berhasil dibackup.")

    @commands.command(name="restore_data", help="Restore data dari backup file.")
    @commands.has_permissions(administrator=True)
    async def restore_data(self, ctx):
        backup_dir = 'backup/'

        if not os.path.exists(backup_dir):
            await ctx.send("⚠️ Tidak ada file backup yang ditemukan.")
            return

        for filename in os.listdir(backup_dir):
            if filename.endswith('.json'):
                shutil.copy(os.path.join(backup_dir, filename), os.path.join('config', filename))

        await ctx.send("✅ Semua data berhasil di-restore.")

class ChannelSetupView(ui.View):
    def __init__(self, channel_id: int):
        super().__init__(timeout=120)
        self.channel_id = channel_id
        self.add_item(ChannelSetupSelect(self.channel_id))

class ChannelSetupSelect(ui.Select):
    def __init__(self, channel_id: str):
        self.channel_id = channel_id
        options = [
            discord.SelectOption(label="Mute Channel", value="mute_channel"),
            discord.SelectOption(label="Unmute Channel", value="unmute_channel"),
            discord.SelectOption(label="Hide Channel", value="hide_channel"),
            discord.SelectOption(label="Unhide Channel", value="unhide_channel"),
            discord.SelectOption(label="Allow Only Admins to Send Messages", value="admin_only"),
            discord.SelectOption(label="Allow All Users to Send Messages", value="allow_all_users"),
            discord.SelectOption(label="Set Timeout for Violators", value="set_timeout"),
            discord.SelectOption(label="Backup Data", value="backup_data"),
            discord.SelectOption(label="Restore Data", value="restore_data"),
        ]

        super().__init__(
            placeholder="Pilih pengaturan channel",
            min_values=1,
            max_values=len(options),
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        channel = interaction.guild.get_channel(int(self.channel_id))

        if choice == "mute_channel":
            await channel.set_permissions(interaction.guild.default_role, send_messages=False)
            await interaction.response.send_message("✅ Channel ini telah dimute. Hanya admin yang dapat mengirim pesan.", ephemeral=True)

        elif choice == "unmute_channel":
            await channel.set_permissions(interaction.guild.default_role, send_messages=True)
            await interaction.response.send_message("✅ Channel ini telah di-unmute. Semua pengguna dapat mengirim pesan.", ephemeral=True)

        elif choice == "hide_channel":
            await channel.set_permissions(interaction.guild.default_role, view_channel=False)
            await interaction.response.send_message("✅ Channel ini telah disembunyikan dari anggota.", ephemeral=True)

        elif choice == "unhide_channel":
            await channel.set_permissions(interaction.guild.default_role, view_channel=True)
            await interaction.response.send_message("✅ Channel ini telah ditampilkan untuk anggota.", ephemeral=True)

        elif choice == "admin_only":
            await channel.set_permissions(interaction.guild.default_role, send_messages=False)
            admin_role = discord.utils.get(interaction.guild.roles, name="Admin")
            if admin_role:
                await channel.set_permissions(admin_role, send_messages=True)
            await interaction.response.send_message("✅ Hanya admin yang dapat mengirim pesan di channel ini.", ephemeral=True)

        elif choice == "allow_all_users":
            await channel.set_permissions(interaction.guild.default_role, send_messages=True)
            await interaction.response.send_message("✅ Semua pengguna dapat mengirim pesan di channel ini.", ephemeral=True)

        elif choice == "set_timeout":
            # Implementasi timeout (tambahkan logika untuk mengatur timeout)
            await interaction.response.send_message("⏳ Fitur timeout belum diimplementasikan.", ephemeral=True)

        elif choice == "backup_data":
            await self.bot.get_command('backup_data').callback(interaction)

        elif choice == "restore_data":
            await self.bot.get_command('restore_data').callback(interaction)

async def setup(bot):
    await bot.add_cog(Moderation(bot))
