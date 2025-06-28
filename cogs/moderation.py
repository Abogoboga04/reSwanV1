import discord
from discord.ext import commands
import json
import os
import re
import asyncio
from typing import Optional
from datetime import datetime, timedelta
import time

# =======================================================================================
# UTILITY FUNCTIONS - Fungsi bantuan
# =======================================================================================

def load_data(file_path):
    """Memuat data dari file JSON. Jika file tidak ada, kembalikan dictionary kosong."""
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content: return {}
            return json.loads(content)
    except (json.JSONDecodeError, IOError):
        return {} # Kembalikan dict kosong jika file rusak atau tidak bisa dibaca

def save_data(file_path, data):
    """Menyimpan data ke file JSON."""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def parse_duration(duration_str: str) -> Optional[timedelta]:
    """Mengubah string durasi (e.g., 10s, 5m, 1h, 1d) menjadi timedelta."""
    match = re.match(r"(\d+)([smhd])", duration_str.lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    if unit == 's': return timedelta(seconds=value)
    if unit == 'm': return timedelta(minutes=value)
    if unit == 'h': return timedelta(hours=value)
    if unit == 'd': return timedelta(days=value)
    return None

# =======================================================================================
# MAIN COG CLASS - Kelas utama untuk semua fungsionalitas bot
# =======================================================================================

class ServerAdminCog(commands.Cog, name="👑 Administrasi"):
    """
    Cog ini berisi semua perintah untuk administrasi dan moderasi server.
    Semua perintah di sini memerlukan izin administrator atau moderator.
    """
    def __init__(self, bot):
        self.bot = bot
        self.settings_file = "settings.json"
        self.filters_file = "filters.json"
        self.warnings_file = "warnings.json" # ---> DITAMBAHKAN: File baru untuk data peringatan
        
        # ---> DITAMBAHKAN: Regex dan prefix untuk aturan channel
        self.common_prefixes = ('!', '.', '?', '-', '$', '%', '&', '#', '+', '=')
        self.url_regex = re.compile(r'https?://[^\s/$.?#].[^\s]*')
        
        # Palet Warna untuk Embeds
        self.color_success = 0x2ECC71; self.color_error = 0xE74C3C
        self.color_info = 0x3498DB; self.color_warning = 0xF1C40F
        self.color_log = 0x95A5A6; self.color_welcome = 0x9B59B6
        
        self.settings = load_data(self.settings_file)
        self.filters = load_data(self.filters_file)
        self.warnings = load_data(self.warnings_file) # ---> DITAMBAHKAN: Memuat data peringatan saat bot mulai

    # --- Helper Methods for Data Management ---
    def get_guild_settings(self, guild_id: int):
        guild_id_str = str(guild_id)
        if guild_id_str not in self.settings:
            self.settings[guild_id_str] = {
                "auto_role_id": None, "welcome_channel_id": None,
                "welcome_message": "Selamat datang di **{guild_name}**, {user}! 🎉",
                "log_channel_id": None, "reaction_roles": {},
                # ---> DITAMBAHKAN: Struktur dasar untuk aturan channel
                "channel_rules": {}
            }
            self.save_settings()
        # ---> DITAMBAHKAN: Pengecekan untuk kompatibilitas data lama
        elif "channel_rules" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["channel_rules"] = {}
            self.save_settings()
        return self.settings[guild_id_str]

    # ---> DITAMBAHKAN: Fungsi baru untuk mengelola aturan per-channel
    def get_channel_rules(self, guild_id: int, channel_id: int) -> dict:
        guild_settings = self.get_guild_settings(guild_id)
        channel_id_str = str(channel_id)
        if channel_id_str not in guild_settings["channel_rules"]:
            guild_settings["channel_rules"][channel_id_str] = {
                "disallow_bots": False, "disallow_media": False, "disallow_prefix": False,
                "disallow_url": False, "auto_delete_seconds": 0
            }
            self.save_settings()
        return guild_settings["channel_rules"][channel_id_str]

    def get_guild_filters(self, guild_id: int):
        guild_id_str = str(guild_id)
        if guild_id_str not in self.filters:
            self.filters[guild_id_str] = { "bad_words": [], "link_patterns": [] }
            self.save_filters()
        return self.filters[guild_id_str]
        
    def save_settings(self): save_data(self.settings_file, self.settings)
    def save_filters(self): save_data(self.filters_file, self.filters)
    def save_warnings(self): save_data(self.warnings_file, self.warnings) # ---> DITAMBAHKAN: Fungsi untuk menyimpan peringatan

    # --- Helper Methods for UI & Logging ---
    def _create_embed(self, title: str = "", description: str = "", color: int = 0, author_name: str = "", author_icon_url: str = ""):
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now())
        if author_name: embed.set_author(name=author_name, icon_url=author_icon_url)
        embed.set_footer(text=f"Dijalankan oleh {self.bot.user.name}", icon_url=self.bot.user.display_avatar.url)
        return embed

    async def log_action(self, guild: discord.Guild, title: str, fields: dict, color: int):
        if not (log_channel_id := self.get_guild_settings(guild.id).get("log_channel_id")): return
        if (log_channel := guild.get_channel(log_channel_id)) and log_channel.permissions_for(guild.me).send_messages:
            embed = self._create_embed(title=title, color=color)
            for name, value in fields.items():
                embed.add_field(name=name, value=value, inline=False)
            await log_channel.send(embed=embed)

    # =======================================================================================
    # EVENT LISTENERS
    # =======================================================================================

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            embed = self._create_embed(description=f"❌ Anda tidak memiliki izin `{', '.join(error.missing_permissions)}` untuk menjalankan perintah ini.", color=self.color_error)
            await ctx.send(embed=embed, delete_after=15)
        elif isinstance(error, commands.CommandNotFound): pass
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(embed=self._create_embed(description=f"❌ Anggota tidak ditemukan.", color=self.color_error))
        elif isinstance(error, commands.UserNotFound):
            await ctx.send(embed=self._create_embed(description=f"❌ Pengguna tidak ditemukan.", color=self.color_error))
        else: print(f"Error pada perintah '{ctx.command}': {error}")


    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild_settings = self.get_guild_settings(member.guild.id)
        if (welcome_channel_id := guild_settings.get("welcome_channel_id")) and (channel := member.guild.get_channel(welcome_channel_id)):
            welcome_message = guild_settings.get("welcome_message", "Selamat datang, {user}!")
            embed = discord.Embed(description=welcome_message.format(user=member.mention, guild_name=member.guild.name), color=self.color_welcome)
            embed.set_author(name=f"SELAMAT DATANG DI {member.guild.name.upper()}", icon_url=member.guild.icon.url if member.guild.icon else None)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Kamu adalah anggota ke-{member.guild.member_count}!")
            await channel.send(embed=embed)
        if (auto_role_id := guild_settings.get("auto_role_id")) and (role := member.guild.get_role(auto_role_id)):
            await member.add_roles(role, reason="Auto Role")
            
    # ---> DITAMBAHKAN: Logika baru untuk on_message yang memprioritaskan aturan channel
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.id == self.bot.user.id: return

        # 1. Penegakan Aturan Spesifik per-Channel
        rules = self.get_channel_rules(message.guild.id, message.channel.id)
        log_fields = {"Pengirim": message.author.mention, "Channel": message.channel.mention, "Isi Pesan": f"```{message.content[:1000]}```"}
        
        if (delay := rules.get("auto_delete_seconds", 0)) > 0:
            try: await message.delete(delay=delay)
            except discord.NotFound: pass

        if rules.get("disallow_bots") and message.author.bot:
            await message.delete()
            await self.log_action(message.guild, "🛡️ Pesan Bot Dihapus", log_fields, self.color_info)
            return

        if message.author.bot: return

        if rules.get("disallow_media") and message.attachments:
            await message.delete()
            await message.channel.send(embed=self._create_embed(description=f"🖼️ {message.author.mention}, dilarang mengirim media/file di channel ini.", color=self.color_warning), delete_after=10)
            await self.log_action(message.guild, "🖼️ Media Dihapus", log_fields, self.color_warning)
            try:
                dm_embed = self._create_embed(title="Peringatan Pelanggaran Aturan", color=self.color_warning)
                dm_embed.add_field(name="Server", value=message.guild.name, inline=False)
                dm_embed.add_field(name="Pelanggaran", value="Pesan Anda dihapus karena mengandung **media/file** di channel yang tidak semestinya.", inline=False)
                dm_embed.add_field(name="Saran", value="Silakan kirim media di channel yang telah disediakan. Mohon periksa kembali peraturan server.", inline=False)
                await message.author.send(embed=dm_embed)
            except discord.Forbidden: pass
            return
        
        if rules.get("disallow_prefix") and message.content.startswith(self.common_prefixes):
            await message.delete()
            await message.channel.send(embed=self._create_embed(description=f"❗ {message.author.mention}, dilarang menggunakan perintah bot di channel ini.", color=self.color_warning), delete_after=10)
            await self.log_action(message.guild, "❗ Perintah Bot Dihapus", log_fields, self.color_warning)
            return

        if rules.get("disallow_url") and self.url_regex.search(message.content):
            await message.delete()
            await message.channel.send(embed=self._create_embed(description=f"🔗 {message.author.mention}, dilarang mengirim link di channel ini.", color=self.color_warning), delete_after=10)
            await self.log_action(message.guild, "🔗 Link Dihapus", log_fields, self.color_warning)
            try:
                dm_embed = self._create_embed(title="Peringatan Pelanggaran Aturan", color=self.color_warning)
                dm_embed.add_field(name="Server", value=message.guild.name, inline=False)
                dm_embed.add_field(name="Pelanggaran", value="Pesan Anda dihapus karena mengandung **URL/link** di channel yang tidak semestinya.", inline=False)
                dm_embed.add_field(name="Saran", value="Silakan kirim link di channel yang telah disediakan. Mohon periksa kembali peraturan server.", inline=False)
                await message.author.send(embed=dm_embed)
            except discord.Forbidden: pass
            return

        # 2. Filter Global se-Server (berjalan jika tidak ada aturan channel yang dilanggar)
        guild_filters = self.get_guild_filters(message.guild.id)
        content_lower = message.content.lower()
        for bad_word in guild_filters.get("bad_words", []):
            if bad_word.lower() in content_lower:
                await message.delete()
                await message.channel.send(embed=self._create_embed(description=f"🤫 Pesan dari {message.author.mention} dihapus karena melanggar aturan.", color=self.color_warning), delete_after=10)
                await self.log_action(message.guild, "🚫 Pesan Disensor (Kata Kasar)", log_fields, self.color_warning)
                return 
        for pattern in guild_filters.get("link_patterns", []):
            if re.search(pattern, message.content):
                await message.delete()
                await message.channel.send(embed=self._create_embed(description=f"🚨 {message.author.mention}, jenis link tersebut tidak diizinkan di sini.", color=self.color_warning), delete_after=10)
                await self.log_action(message.guild, "🔗 Pesan Disensor (Pola Link)", log_fields, self.color_warning)
                return

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None or payload.member.bot: return
        guild_settings = self.get_guild_settings(payload.guild_id)
        if (role_map := guild_settings.get("reaction_roles", {}).get(str(payload.message_id))) and \
           (role_id := role_map.get(str(payload.emoji))) and \
           (guild := self.bot.get_guild(payload.guild_id)) and \
           (role := guild.get_role(role_id)):
            await payload.member.add_roles(role, reason="Reaction Role")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None: return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild or not (member := guild.get_member(payload.user_id)) or member.bot: return
        guild_settings = self.get_guild_settings(payload.guild_id)
        if (role_map := guild_settings.get("reaction_roles", {}).get(str(payload.message_id))) and \
           (role_id := role_map.get(str(payload.emoji))) and \
           (role := guild.get_role(role_id)) and role in member.roles:
            await member.remove_roles(role, reason="Reaction Role Removed")

    # =======================================================================================
    # MODERATION COMMANDS
    # =======================================================================================

    @commands.command(name="kick")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: Optional[str] = "Tidak ada alasan."):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner: await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengeluarkan anggota dengan role setara atau lebih tinggi.", color=self.color_error)); return
        await member.kick(reason=reason)
        await ctx.send(embed=self._create_embed(description=f"✅ **{member.display_name}** telah dikeluarkan.", color=self.color_success))
        await self.log_action(ctx.guild, "👢 Member Dikeluarkan", {"Member": f"{member} ({member.id})", "Moderator": ctx.author.mention, "Alasan": reason}, self.color_warning)

    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: Optional[str] = "Tidak ada alasan."):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner: await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa memblokir anggota dengan role setara atau lebih tinggi.", color=self.color_error)); return
        await member.ban(reason=reason)
        await ctx.send(embed=self._create_embed(description=f"✅ **{member.display_name}** telah diblokir.", color=self.color_success))
        await self.log_action(ctx.guild, "🔨 Member Diblokir", {"Member": f"{member} ({member.id})", "Moderator": ctx.author.mention, "Alasan": reason}, self.color_error)

    # ---> PERINTAH BARU: UNBAN <---
    @commands.command(name="unban")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, *, user_identifier: str, reason: Optional[str] = "Tidak ada alasan."):
        """Membuka blokir pengguna berdasarkan Nama#Tag atau ID."""
        ban_entries = [entry async for entry in ctx.guild.bans()]
        banned_user_entry = None

        try:
            # Coba cari berdasarkan ID dulu, ini cara paling akurat
            user_id = int(user_identifier)
            target_user = await self.bot.fetch_user(user_id)
            banned_user_entry = await ctx.guild.fetch_ban(target_user)
        except ValueError:
            # Jika bukan ID, cari berdasarkan Nama#Tag
            for entry in ban_entries:
                if str(entry.user) == user_identifier:
                    banned_user_entry = entry
                    break
        except discord.NotFound:
             await ctx.send(embed=self._create_embed(description=f"❌ Pengguna dengan ID `{user_identifier}` tidak ditemukan dalam daftar blokir.", color=self.color_error))
             return


        if banned_user_entry is None:
            await ctx.send(embed=self._create_embed(description=f"❌ Pengguna `{user_identifier}` tidak ditemukan dalam daftar blokir. Coba gunakan ID pengguna.", color=self.color_error))
            return

        user_to_unban = banned_user_entry.user
        await ctx.guild.unban(user_to_unban, reason=reason)
        await ctx.send(embed=self._create_embed(description=f"✅ Blokir untuk **{user_to_unban}** telah dibuka.", color=self.color_success))
        await self.log_action(ctx.guild, "🤝 Blokir Dibuka", {"Pengguna": f"{user_to_unban} ({user_to_unban.id})", "Moderator": ctx.author.mention, "Alasan": reason}, self.color_success)

    @commands.command(name="warn")
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str):
        """Memberi peringatan kepada anggota."""
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa memberi peringatan kepada anggota dengan role setara atau lebih tinggi.", color=self.color_error))
            return
        if member.bot:
            await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa memberi peringatan kepada bot.", color=self.color_error))
            return

        # ---> DITAMBAHKAN: Logika untuk menyimpan peringatan <---
        timestamp = int(time.time())
        warning_data = {
            "moderator_id": ctx.author.id,
            "timestamp": timestamp,
            "reason": reason
        }
        guild_id_str = str(ctx.guild.id)
        member_id_str = str(member.id)
        if guild_id_str not in self.warnings:
            self.warnings[guild_id_str] = {}
        if member_id_str not in self.warnings[guild_id_str]:
            self.warnings[guild_id_str][member_id_str] = []
        
        self.warnings[guild_id_str][member_id_str].append(warning_data)
        self.save_warnings()
        # ---> Akhir dari logika penyimpanan <---

        # Kirim DM ke pengguna
        try:
            dm_embed = self._create_embed(title=f"🚨 Anda Menerima Peringatan di {ctx.guild.name}", color=self.color_warning)
            dm_embed.add_field(name="Alasan Peringatan", value=reason, inline=False)
            dm_embed.set_footer(text=f"Peringatan diberikan oleh {ctx.author.display_name}")
            await member.send(embed=dm_embed)
            dm_sent = True
        except discord.Forbidden:
            dm_sent = False

        # Kirim konfirmasi di channel & log
        confirm_desc = f"✅ **{member.display_name}** telah diperingatkan."
        if not dm_sent:
            confirm_desc += "\n*(Pesan peringatan tidak dapat dikirim ke DM pengguna.)*"
            
        await ctx.send(embed=self._create_embed(description=confirm_desc, color=self.color_success))
        await self.log_action(ctx.guild, "⚠️ Member Diperingatkan", {"Member": f"{member} ({member.id})", "Moderator": ctx.author.mention, "Alasan": reason}, self.color_warning)

    # ---> PERINTAH BARU: UNWARN <---
    @commands.command(name="unwarn")
    @commands.has_permissions(kick_members=True)
    async def unwarn(self, ctx, member: discord.Member, warning_index: int, *, reason: Optional[str] = "Kesalahan admin."):
        """Menghapus peringatan spesifik dari anggota."""
        guild_id_str = str(ctx.guild.id)
        member_id_str = str(member.id)
        
        user_warnings = self.warnings.get(guild_id_str, {}).get(member_id_str, [])
        
        if not user_warnings:
            return await ctx.send(embed=self._create_embed(description=f"❌ **{member.display_name}** tidak memiliki peringatan.", color=self.color_error))

        if not (0 < warning_index <= len(user_warnings)):
            return await ctx.send(embed=self._create_embed(description=f"❌ Indeks peringatan tidak valid. Gunakan `!warnings {member.mention}` untuk melihat daftar peringatan.", color=self.color_error))
        
        removed_warning = self.warnings[guild_id_str][member_id_str].pop(warning_index - 1)
        self.save_warnings()
        
        await ctx.send(embed=self._create_embed(description=f"✅ Peringatan ke-{warning_index} untuk **{member.display_name}** telah dihapus.", color=self.color_success))
        
        log_fields = {
            "Member": f"{member} ({member.id})", 
            "Moderator": ctx.author.mention, 
            "Alasan Hapus": reason,
            "Peringatan yang Dihapus": f"`{removed_warning['reason']}`"
        }
        await self.log_action(ctx.guild, "👍 Peringatan Dihapus", log_fields, self.color_success)

    # ---> PERINTAH BARU: WARNINGS <---
    @commands.command(name="warnings", aliases=["history"])
    @commands.has_permissions(kick_members=True)
    async def warnings(self, ctx, member: discord.Member):
        """Melihat riwayat peringatan seorang anggota."""
        guild_id_str = str(ctx.guild.id)
        member_id_str = str(member.id)
        
        user_warnings = self.warnings.get(guild_id_str, {}).get(member_id_str, [])
        
        if not user_warnings:
            return await ctx.send(embed=self._create_embed(description=f"✅ **{member.display_name}** tidak memiliki riwayat peringatan.", color=self.color_success))

        embed = self._create_embed(title=f"Riwayat Peringatan untuk {member.display_name}", color=self.color_info)
        embed.set_thumbnail(url=member.display_avatar.url)

        for idx, warn_data in enumerate(user_warnings, 1):
            moderator = await self.bot.fetch_user(warn_data.get('moderator_id', 0))
            timestamp = warn_data.get('timestamp', 0)
            reason = warn_data.get('reason', 'N/A')
            field_value = f"**Alasan:** {reason}\n**Moderator:** {moderator.mention if moderator else 'Tidak diketahui'}\n**Tanggal:** <t:{timestamp}:F>"
            embed.add_field(name=f"Peringatan #{idx}", value=field_value, inline=False)
            
        await ctx.send(embed=embed)

    @commands.command(name="timeout", aliases=["mute"])
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx, member: discord.Member, duration: str, *, reason: Optional[str] = "Tidak ada alasan."):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner: await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa memberikan timeout pada anggota dengan role setara atau lebih tinggi.", color=self.color_error)); return
        delta = parse_duration(duration)
        if not delta: await ctx.send(embed=self._create_embed(description="❌ Format durasi tidak valid. Gunakan `s` (detik), `m` (menit), `h` (jam), `d` (hari). Contoh: `10m`.", color=self.color_error)); return
        await member.timeout(delta, reason=reason)
        await ctx.send(embed=self._create_embed(description=f"✅ **{member.display_name}** telah diberi timeout selama `{duration}`.", color=self.color_success))
        await self.log_action(ctx.guild, "🤫 Member Timeout", {"Member": f"{member} ({member.id})", "Durasi": duration, "Moderator": ctx.author.mention, "Alasan": reason}, self.color_warning)

    @commands.command(name="removetimeout", aliases=["unmute"])
    @commands.has_permissions(moderate_members=True)
    async def remove_timeout(self, ctx, member: discord.Member):
        await member.timeout(None, reason=f"Timeout dihapus oleh {ctx.author}")
        await ctx.send(embed=self._create_embed(description=f"✅ Timeout untuk **{member.display_name}** telah dihapus.", color=self.color_success))
        await self.log_action(ctx.guild, "😊 Timeout Dihapus", {"Member": f"{member} ({member.id})", "Moderator": ctx.author.mention}, self.color_success)
        
    @commands.command(name="clear", aliases=["purge"])
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int):
        if amount <= 0: await ctx.send(embed=self._create_embed(description="❌ Jumlah harus lebih dari 0.", color=self.color_error)); return
        deleted = await ctx.channel.purge(limit=amount + 1)
        embed = self._create_embed(description=f"🗑️ Berhasil menghapus **{len(deleted) - 1}** pesan.", color=self.color_success)
        await ctx.send(embed=embed, delete_after=5)
        await self.log_action(ctx.guild, "🗑️ Pesan Dihapus", {"Channel": ctx.channel.mention, "Jumlah": f"{len(deleted) - 1} pesan", "Moderator": ctx.author.mention}, self.color_info)
        
    @commands.command(name="slowmode")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int):
        await ctx.channel.edit(slowmode_delay=seconds)
        status = f"diatur ke `{seconds}` detik" if seconds > 0 else "dinonaktifkan"
        await ctx.send(embed=self._create_embed(description=f"✅ Mode lambat di channel ini telah {status}.", color=self.color_success))
        await self.log_action(ctx.guild, "⏳ Slowmode Diubah", {"Channel": ctx.channel.mention, "Durasi": f"{seconds} detik", "Moderator": ctx.author.mention}, self.color_info)

    @commands.command(name="lock")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx, channel: Optional[discord.TextChannel] = None):
        target_channel = channel or ctx.channel
        await target_channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.send(embed=self._create_embed(description=f"🔒 Channel {target_channel.mention} telah dikunci.", color=self.color_success))
        await self.log_action(ctx.guild, "🔒 Channel Dikunci", {"Channel": target_channel.mention, "Moderator": ctx.author.mention}, self.color_warning)

    @commands.command(name="unlock")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx, channel: Optional[discord.TextChannel] = None):
        target_channel = channel or ctx.channel
        await target_channel.set_permissions(ctx.guild.default_role, send_messages=None)
        await ctx.send(embed=self._create_embed(description=f"🔓 Kunci channel {target_channel.mention} telah dibuka.", color=self.color_success))
        await self.log_action(ctx.guild, "🔓 Kunci Dibuka", {"Channel": target_channel.mention, "Moderator": ctx.author.mention}, self.color_success)

    # ---> PERINTAH BARU: ADDROLE & REMOVEROLE <---
    @commands.command(name="addrole")
    @commands.has_permissions(manage_roles=True)
    async def add_role(self, ctx, member: discord.Member, role: discord.Role):
        """Memberikan role kepada seorang anggota."""
        if ctx.author.top_role <= role:
            return await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa memberikan role yang lebih tinggi atau setara dengan role Anda.", color=self.color_error))
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengubah role anggota yang posisinya lebih tinggi atau setara.", color=self.color_error))

        await member.add_roles(role, reason=f"Diberikan oleh {ctx.author}")
        await ctx.send(embed=self._create_embed(description=f"✅ Role {role.mention} telah diberikan kepada {member.mention}.", color=self.color_success))
        await self.log_action(ctx.guild, "➕ Role Diberikan", {"Member": member.mention, "Role": role.mention, "Moderator": ctx.author.mention}, self.color_info)

    @commands.command(name="removerole")
    @commands.has_permissions(manage_roles=True)
    async def remove_role(self, ctx, member: discord.Member, role: discord.Role):
        """Menghapus role dari seorang anggota."""
        if ctx.author.top_role <= role:
            return await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa menghapus role yang lebih tinggi atau setara dengan role Anda.", color=self.color_error))
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengubah role anggota yang posisinya lebih tinggi atau setara.", color=self.color_error))
            
        await member.remove_roles(role, reason=f"Dihapus oleh {ctx.author}")
        await ctx.send(embed=self._create_embed(description=f"✅ Role {role.mention} telah dihapus dari {member.mention}.", color=self.color_success))
        await self.log_action(ctx.guild, "➖ Role Dihapus", {"Member": member.mention, "Role": role.mention, "Moderator": ctx.author.mention}, self.color_info)

    # ---> PERINTAH BARU: NICK <---
    @commands.command(name="nick")
    @commands.has_permissions(manage_nicknames=True)
    async def nick(self, ctx, member: discord.Member, *, new_nickname: Optional[str] = None):
        """Mengubah atau mereset nickname seorang anggota."""
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengubah nickname anggota dengan role lebih tinggi atau setara.", color=self.color_error))

        old_nickname = member.display_name
        await member.edit(nick=new_nickname, reason=f"Diubah oleh {ctx.author}")
        
        if new_nickname:
            await ctx.send(embed=self._create_embed(description=f"✅ Nickname **{old_nickname}** telah diubah menjadi **{new_nickname}**.", color=self.color_success))
            await self.log_action(ctx.guild, "👤 Nickname Diubah", {"Member": member.mention, "Dari": old_nickname, "Menjadi": new_nickname, "Moderator": ctx.author.mention}, self.color_info)
        else:
            await ctx.send(embed=self._create_embed(description=f"✅ Nickname untuk **{old_nickname}** telah direset.", color=self.color_success))
            await self.log_action(ctx.guild, "👤 Nickname Direset", {"Member": member.mention, "Moderator": ctx.author.mention}, self.color_info)


    # =======================================================================================
    # ---> DITAMBAHKAN: Perintah dan UI untuk `channelrules`
    # =======================================================================================
    @commands.command(name="channelrules", aliases=["cr"])
    @commands.has_permissions(manage_channels=True)
    async def channel_rules(self, ctx, channel: Optional[discord.TextChannel] = None):
        target_channel = channel or ctx.channel
        class ChannelRuleView(discord.ui.View):
            def __init__(self, cog_instance, author, target_channel):
                super().__init__(timeout=300)
                self.cog, self.author, self.target_channel = cog_instance, author, target_channel
                self.guild_id, self.channel_id = target_channel.guild.id, target_channel.id
                self.update_buttons()
            def update_buttons(self):
                rules = self.cog.get_channel_rules(self.guild_id, self.channel_id)
                def set_button_state(button, label_text, is_active):
                    button.label = f"{label_text}: {'Aktif' if is_active else 'Nonaktif'}"
                    button.style = discord.ButtonStyle.green if is_active else discord.ButtonStyle.red
                set_button_state(self.toggle_bots, "Dilarang Bot", rules.get("disallow_bots", False))
                set_button_state(self.toggle_media, "Dilarang Media", rules.get("disallow_media", False))
                set_button_state(self.toggle_prefix, "Dilarang Prefix", rules.get("disallow_prefix", False))
                set_button_state(self.toggle_url, "Dilarang URL", rules.get("disallow_url", False))
                delay = rules.get("auto_delete_seconds", 0)
                self.toggle_auto_delete.label = f"Hapus Otomatis: {delay}s" if delay > 0 else "Hapus Otomatis: Nonaktif"
                self.toggle_auto_delete.style = discord.ButtonStyle.green if delay > 0 else discord.ButtonStyle.red
            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                if interaction.user != self.author: await interaction.response.send_message("Hanya pengguna yang memulai perintah yang dapat berinteraksi.", ephemeral=True); return False
                return True
            async def toggle_rule(self, interaction: discord.Interaction, rule_name: str):
                rules = self.cog.get_channel_rules(self.guild_id, self.channel_id); rules[rule_name] = not rules.get(rule_name, False); self.cog.save_settings(); self.update_buttons(); await interaction.response.edit_message(view=self)
            @discord.ui.button(emoji="🛡️", row=0)
            async def toggle_bots(self, interaction: discord.Interaction, button: discord.ui.Button): await self.toggle_rule(interaction, "disallow_bots")
            @discord.ui.button(emoji="🖼️", row=0)
            async def toggle_media(self, interaction: discord.Interaction, button: discord.ui.Button): await self.toggle_rule(interaction, "disallow_media")
            @discord.ui.button(emoji="❗", row=0)
            async def toggle_prefix(self, interaction: discord.Interaction, button: discord.ui.Button): await self.toggle_rule(interaction, "disallow_prefix")
            @discord.ui.button(emoji="🔗", row=1)
            async def toggle_url(self, interaction: discord.Interaction, button: discord.ui.Button): await self.toggle_rule(interaction, "disallow_url")
            @discord.ui.button(emoji="⏳", row=1)
            async def toggle_auto_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
                rules = self.cog.get_channel_rules(self.guild_id, self.channel_id); rules["auto_delete_seconds"] = 0 if rules.get("auto_delete_seconds", 0) > 0 else 30; self.cog.save_settings(); self.update_buttons(); await interaction.response.edit_message(view=self)
        embed = self._create_embed(title=f"🔧 Aturan untuk Channel: #{target_channel.name}", description="Tekan tombol untuk mengaktifkan (hijau) atau menonaktifkan (merah) aturan untuk channel ini.", color=self.color_info)
        await ctx.send(embed=embed, view=ChannelRuleView(self, ctx.author, target_channel))
        
    # =======================================================================================
    # SETUP COMMANDS
    # =======================================================================================

    @commands.command(name="setwelcomechannel")
    @commands.has_permissions(manage_guild=True)
    async def set_welcome_channel(self, ctx, channel: discord.TextChannel):
        """Mengatur channel untuk pesan selamat datang."""
        guild_settings = self.get_guild_settings(ctx.guild.id)
        guild_settings["welcome_channel_id"] = channel.id
        self.save_settings()
        embed = self._create_embed(
            description=f"✅ Channel selamat datang telah berhasil diatur ke {channel.mention}.",
            color=self.color_success
        )
        await ctx.send(embed=embed)

    @commands.command(name="setreactionrole")
    @commands.has_permissions(manage_roles=True)
    async def set_reaction_role(self, ctx, message: discord.Message, emoji: str, role: discord.Role):
        guild_settings = self.get_guild_settings(ctx.guild.id)
        message_id_str = str(message.id)
        if message_id_str not in guild_settings["reaction_roles"]: guild_settings["reaction_roles"][message_id_str] = {}
        guild_settings["reaction_roles"][message_id_str][emoji] = role.id
        self.save_settings()
        await message.add_reaction(emoji)
        await ctx.send(embed=self._create_embed(description=f"✅ Role **{role.mention}** akan diberikan untuk reaksi {emoji} pada [pesan itu]({message.jump_url}).", color=self.color_success))

    @commands.command(name="setup")
    @commands.has_permissions(manage_guild=True)
    async def setup(self, ctx):
        class SetupView(discord.ui.View):
            def __init__(self, cog_instance):
                super().__init__(timeout=300)
                self.cog = cog_instance; self.guild_id = ctx.guild.id; self.author = ctx.author
            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                if interaction.user != self.author: await interaction.response.send_message("Hanya pengguna yang memulai setup yang dapat berinteraksi.", ephemeral=True); return False
                return True
            async def handle_response(self, interaction, prompt, callback):
                await interaction.response.send_message(embed=self.cog._create_embed(description=prompt, color=self.cog.color_info), ephemeral=True)
                try:
                    msg = await self.cog.bot.wait_for('message', check=lambda m: m.author == self.author and m.channel == interaction.channel, timeout=120)
                    await msg.delete(); await callback(msg, interaction)
                except asyncio.TimeoutError: await interaction.followup.send(embed=self.cog._create_embed(description="❌ Waktu habis.", color=self.cog.color_error), ephemeral=True)
            @discord.ui.button(label="Auto Role", style=discord.ButtonStyle.primary, emoji="👤", row=0)
            async def set_auto_role(self, interaction: discord.Interaction, button: discord.ui.Button):
                async def callback(msg, inter):
                    role = msg.role_mentions[0] if msg.role_mentions else ctx.guild.get_role(int(msg.content)) if msg.content.isdigit() else None
                    if role:
                        self.cog.get_guild_settings(self.guild_id)['auto_role_id'] = role.id; self.cog.save_settings()
                        await inter.followup.send(embed=self.cog._create_embed(description=f"✅ Auto Role diatur ke **{role.mention}**.", color=self.cog.color_success), ephemeral=True)
                    else: await inter.followup.send(embed=self.cog._create_embed(description="❌ Role tidak ditemukan.", color=self.cog.color_error), ephemeral=True)
                await self.handle_response(interaction, "Sebutkan (mention) atau masukkan ID role untuk pengguna baru:", callback)
            @discord.ui.button(label="Welcome Msg", style=discord.ButtonStyle.primary, emoji="💬", row=0)
            async def set_welcome_message(self, interaction: discord.Interaction, button: discord.ui.Button):
                async def callback(msg, inter):
                    self.cog.get_guild_settings(self.guild_id)['welcome_message'] = msg.content; self.cog.save_settings()
                    await inter.followup.send(embed=self.cog._create_embed(description="✅ Pesan selamat datang berhasil diatur.", color=self.cog.color_success), ephemeral=True)
                await self.handle_response(interaction, "Ketik pesan selamat datangmu. Gunakan `{user}` dan `{guild_name}`.", callback)
            @discord.ui.button(label="Kelola Filter", style=discord.ButtonStyle.secondary, emoji="🛡️", row=1)
            async def manage_filters(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_message(view=FilterManageView(self.cog, self.author), ephemeral=True)
            @discord.ui.button(label="Lihat Konfigurasi", style=discord.ButtonStyle.secondary, emoji="📋", row=1)
            async def view_config(self, interaction: discord.Interaction, button: discord.ui.Button):
                settings = self.cog.get_guild_settings(self.guild_id); filters = self.cog.get_guild_filters(self.guild_id)
                auto_role = ctx.guild.get_role(settings.get('auto_role_id')) if settings.get('auto_role_id') else "Tidak diatur"
                welcome_ch = ctx.guild.get_channel(settings.get('welcome_channel_id')) if settings.get('welcome_channel_id') else "Tidak diatur"
                log_ch = ctx.guild.get_channel(settings.get('log_channel_id')) if settings.get('log_channel_id') else "Tidak diatur"
                embed = self.cog._create_embed(title=f"Konfigurasi untuk {ctx.guild.name}", color=self.cog.color_info)
                embed.add_field(name="Pengaturan Dasar", value=f"**Auto Role**: {auto_role.mention if isinstance(auto_role, discord.Role) else auto_role}\n**Welcome Channel**: {welcome_ch.mention if isinstance(welcome_ch, discord.TextChannel) else welcome_ch}\n**Log Channel**: {log_ch.mention if isinstance(log_ch, discord.TextChannel) else log_ch}", inline=False)
                embed.add_field(name="Pesan Selamat Datang", value=f"```{settings.get('welcome_message')}```", inline=False)
                embed.add_field(name="Filter Kata Kasar", value=f"Total: {len(filters.get('bad_words',[]))} kata", inline=True)
                embed.add_field(name="Filter Link", value=f"Total: {len(filters.get('link_patterns',[]))} pola", inline=True)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        class RemoveFilterModal(discord.ui.Modal, title="Hapus Filter"):
            def __init__(self, cog_instance, filter_type):
                super().__init__(); self.cog = cog_instance; self.filter_type = filter_type
                self.item_to_remove = discord.ui.TextInput(label=f"Masukkan {('kata' if filter_type == 'bad_words' else 'pola')} yang akan dihapus")
                self.add_item(self.item_to_remove)
            async def on_submit(self, interaction: discord.Interaction):
                filters = self.cog.get_guild_filters(interaction.guild_id); item = self.item_to_remove.value.lower().strip()
                if item in filters[self.filter_type]:
                    filters[self.filter_type].remove(item); self.cog.save_filters()
                    await interaction.response.send_message(embed=self.cog._create_embed(description=f"✅ `{item}` berhasil dihapus dari filter.", color=self.cog.color_success), ephemeral=True)
                else: await interaction.response.send_message(embed=self.cog._create_embed(description=f"❌ `{item}` tidak ditemukan di filter.", color=self.cog.color_error), ephemeral=True)
        class FilterManageView(discord.ui.View):
            def __init__(self, cog_instance, author):
                super().__init__(timeout=180); self.cog = cog_instance; self.author = author
            async def interaction_check(self, interaction: discord.Interaction) -> bool: return interaction.user == self.author
            @discord.ui.button(label="Tambah Kata Kasar", style=discord.ButtonStyle.primary, emoji="🤬")
            async def add_bad_word(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_message("Fitur ini belum diimplementasikan di sini.", ephemeral=True)
            @discord.ui.button(label="Hapus Kata Kasar", style=discord.ButtonStyle.danger, emoji="🗑️")
            async def remove_bad_word(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_modal(RemoveFilterModal(self.cog, "bad_words"))
            @discord.ui.button(label="Lihat Semua Filter", style=discord.ButtonStyle.secondary, emoji="📋")
            async def view_filters(self, interaction: discord.Interaction, button: discord.ui.Button):
                filters = self.cog.get_guild_filters(interaction.guild_id); bad_words = ", ".join(f"`{w}`" for w in filters['bad_words']) or "Kosong"; link_patterns = ", ".join(f"`{p}`" for p in filters['link_patterns']) or "Kosong"
                embed = self.cog._create_embed(title="Daftar Filter Aktif", color=self.cog.color_info)
                embed.add_field(name="🚫 Kata Kasar", value=bad_words[:1024], inline=False); embed.add_field(name="🔗 Pola Link", value=link_patterns[:1024], inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        embed = self._create_embed(title="⚙️ Panel Kontrol Server", description="Gunakan tombol di bawah ini untuk mengatur bot. Anda memiliki 5 menit sebelum panel ini nonaktif.", color=self.color_info, author_name=ctx.guild.name, author_icon_url=ctx.guild.icon.url if ctx.guild.icon else "")
        await ctx.send(embed=embed, view=SetupView(self))

async def setup(bot):
    await bot.add_cog(ServerAdminCog(bot))

