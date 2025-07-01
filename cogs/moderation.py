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
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading {file_path}: {e}")
        return {}

def save_data(file_path, data):
    """Menyimpan data ke file JSON."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
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
        # Pastikan path ke folder data sudah benar relatif terhadap main bot script
        self.settings_file = "data/settings.json"
        self.filters_file = "data/filters.json"
        self.warnings_file = "data/warnings.json"
        
        self.common_prefixes = ('!', '.', '?', '-', '$', '%', '&', '#', '+', '=')
        self.url_regex = re.compile(r'https?://[^\s/$.?#].[^\s]*')
        
        # Palet Warna untuk Embeds
        self.color_success = 0x2ECC71
        self.color_error = 0xE74C3C
        self.color_info = 0x3498DB
        self.color_warning = 0xF1C40F
        self.color_log = 0x95A5A6
        self.color_welcome = 0x9B59B6
        self.color_announce = 0x7289DA # Warna baru untuk announcement
        
        self.settings = load_data(self.settings_file)
        self.filters = load_data(self.filters_file)
        self.warnings = load_data(self.warnings_file)

    # --- Helper Methods for Data Management ---
    def get_guild_settings(self, guild_id: int):
        guild_id_str = str(guild_id)
        if guild_id_str not in self.settings:
            self.settings[guild_id_str] = {
                "auto_role_id": None, "welcome_channel_id": None,
                "welcome_message": "Selamat datang di **{guild_name}**, {user}! 🎉",
                "log_channel_id": None, "reaction_roles": {},
                "channel_rules": {}
            }
            self.save_settings()
        elif "channel_rules" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["channel_rules"] = {}
            self.save_settings()
        return self.settings[guild_id_str]

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
    def save_warnings(self): save_data(self.warnings_file, self.warnings)

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
        elif isinstance(error, commands.BadArgument):
            await ctx.send(embed=self._create_embed(description=f"❌ Argument tidak valid: {error}", color=self.color_error), delete_after=15)
        else:
            print(f"Error pada perintah '{ctx.command}': {error}")


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
            try:
                await member.add_roles(role, reason="Auto Role")
            except discord.Forbidden:
                print(f"Bot lacks permissions to assign auto-role {role.name} in {member.guild.name}.")
            
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.id == self.bot.user.id: return

        rules = self.get_channel_rules(message.guild.id, message.channel.id)
        log_fields = {"Pengirim": message.author.mention, "Channel": message.channel.mention, "Isi Pesan": f"```{message.content[:1000]}```"}
        
        if (delay := rules.get("auto_delete_seconds", 0)) > 0:
            try: await message.delete(delay=delay)
            except discord.NotFound: pass

        if rules.get("disallow_bots") and message.author.bot:
            await message.delete()
            await self.log_action(message.guild, "🛡️ Pesan Bot Dihapus", log_fields, self.color_info)
            return

        if message.author.bot:
             return

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
            command_prefix = await self.bot.get_prefix(message)
            if message.content.startswith(command_prefix):
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
            try:
                await payload.member.add_roles(role, reason="Reaction Role")
            except discord.Forbidden:
                print(f"Bot lacks permissions to assign reaction role {role.name} in {guild.name}.")


    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None: return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild or not (member := guild.get_member(payload.user_id)) or member.bot: return
        guild_settings = self.get_guild_settings(payload.guild_id)
        if (role_map := guild_settings.get("reaction_roles", {}).get(str(payload.message_id))) and \
           (role_id := role_map.get(str(payload.emoji))) and \
           (role := guild.get_role(role_id)) and role in member.roles:
            try:
                await member.remove_roles(role, reason="Reaction Role Removed")
            except discord.Forbidden:
                print(f"Bot lacks permissions to remove reaction role {role.name} from {member.display_name} in {guild.name}.")


    # =======================================================================================
    # MODERATION COMMANDS
    # =======================================================================================

    @commands.command(name="kick")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: Optional[str] = "Tidak ada alasan."):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner: await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengeluarkan anggota dengan role setara atau lebih tinggi.", color=self.color_error)); return
        if member.id == ctx.guild.owner.id: await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengeluarkan pemilik server.", color=self.color_error)); return
        if member.id == self.bot.user.id: await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengeluarkan bot ini sendiri.", color=self.color_error)); return

        try:
            await member.kick(reason=reason)
            await ctx.send(embed=self._create_embed(description=f"✅ **{member.display_name}** telah dikeluarkan.", color=self.color_success))
            await self.log_action(ctx.guild, "👢 Member Dikeluarkan", {"Member": f"{member} ({member.id})", "Moderator": ctx.author.mention, "Alasan": reason}, self.color_warning)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin yang cukup untuk mengeluarkan anggota ini. Pastikan role bot lebih tinggi.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat mengeluarkan anggota: {e}", color=self.color_error))


    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: Optional[str] = "Tidak ada alasan."):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner: await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa memblokir anggota dengan role setara atau lebih tinggi.", color=self.color_error)); return
        if member.id == ctx.guild.owner.id: await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa memblokir pemilik server.", color=self.color_error)); return
        if member.id == self.bot.user.id: await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa memblokir bot ini sendiri.", color=self.color_error)); return

        try:
            await member.ban(reason=reason)
            await ctx.send(embed=self._create_embed(description=f"✅ **{member.display_name}** telah diblokir.", color=self.color_success))
            await self.log_action(ctx.guild, "🔨 Member Diblokir", {"Member": f"{member} ({member.id})", "Moderator": ctx.author.mention, "Alasan": reason}, self.color_error)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin yang cukup untuk memblokir anggota ini. Pastikan role bot lebih tinggi.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat memblokir anggota: {e}", color=self.color_error))


    @commands.command(name="unban")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, *, user_identifier: str, reason: Optional[str] = "Tidak ada alasan."):
        """Membuka blokir pengguna berdasarkan Nama#Tag atau ID."""
        user_to_unban = None
        try:
            user_id = int(user_identifier)
            temp_user = await self.bot.fetch_user(user_id)
            user_to_unban = temp_user
        except ValueError:
            for entry in [entry async for entry in ctx.guild.bans()]:
                if str(entry.user).lower() == user_identifier.lower():
                    user_to_unban = entry.user
                    break
        except discord.NotFound:
            pass

        if user_to_unban is None:
            await ctx.send(embed=self._create_embed(description=f"❌ Pengguna `{user_identifier}` tidak ditemukan dalam daftar blokir atau ID/Nama#Tag tidak valid.", color=self.color_error))
            return

        try:
            await ctx.guild.unban(user_to_unban, reason=reason)
            await ctx.send(embed=self._create_embed(description=f"✅ Blokir untuk **{user_to_unban}** telah dibuka.", color=self.color_success))
            await self.log_action(ctx.guild, "🤝 Blokir Dibuka", {"Pengguna": f"{user_to_unban} ({user_to_unban.id})", "Moderator": ctx.author.mention, "Alasan": reason}, self.color_success)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin yang cukup untuk membuka blokir anggota ini. Pastikan role bot lebih tinggi.", color=self.color_error))
        except discord.NotFound:
            await ctx.send(embed=self._create_embed(description=f"❌ Pengguna `{user_to_unban}` tidak ditemukan dalam daftar blokir.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat membuka blokir: {e}", color=self.color_error))


    @commands.command(name="warn")
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str):
        """Memberi peringatan kepada anggota."""
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa memberi peringatan kepada anggota dengan role setara atau lebih tinggi.", color=self.color_error))
            return
        if member.bot:
            await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa memberi peringatan kepada bot.", color=self.color_error)); return
        if member.id == ctx.guild.owner.id:
            await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa memperingatkan pemilik server.", color=self.color_error)); return

        timestamp = int(time.time())
        warning_data = {
            "moderator_id": ctx.author.id,
            "timestamp": timestamp,
            "reason": reason
        }
        guild_id_str = str(ctx.guild.id)
        member_id_str = str(member.id)
        
        self.warnings.setdefault(guild_id_str, {}).setdefault(member_id_str, []).append(warning_data)
        self.save_warnings()

        try:
            dm_embed = self._create_embed(title=f"🚨 Anda Menerima Peringatan di {ctx.guild.name}", color=self.color_warning)
            dm_embed.add_field(name="Alasan Peringatan", value=reason, inline=False)
            dm_embed.set_footer(text=f"Peringatan diberikan oleh {ctx.author.display_name}")
            await member.send(embed=dm_embed)
            dm_sent = True
        except discord.Forbidden:
            dm_sent = False

        confirm_desc = f"✅ **{member.display_name}** telah diperingatkan."
        if not dm_sent:
            confirm_desc += "\n*(Pesan peringatan tidak dapat dikirim ke DM pengguna.)*"
            
        await ctx.send(embed=self._create_embed(description=confirm_desc, color=self.color_success))
        await self.log_action(ctx.guild, "⚠️ Member Diperingatkan", {"Member": f"{member} ({member.id})", "Moderator": ctx.author.mention, "Alasan": reason}, self.color_warning)

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
        if member.id == ctx.guild.owner.id: await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa memberikan timeout pada pemilik server.", color=self.color_error)); return
        if member.id == self.bot.user.id: await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa memberikan timeout pada bot ini sendiri.", color=self.color_error)); return

        delta = parse_duration(duration)
        if not delta: await ctx.send(embed=self._create_embed(description="❌ Format durasi tidak valid. Gunakan `s` (detik), `m` (menit), `h` (jam), `d` (hari). Contoh: `10m`.", color=self.color_error)); return
        if delta.total_seconds() > 2419200:
            await ctx.send(embed=self._create_embed(description="❌ Durasi timeout tidak bisa lebih dari 28 hari.", color=self.color_error)); return

        try:
            await member.timeout(delta, reason=reason)
            await ctx.send(embed=self._create_embed(description=f"✅ **{member.display_name}** telah diberi timeout selama `{duration}`.", color=self.color_success))
            await self.log_action(ctx.guild, "🤫 Member Timeout", {"Member": f"{member} ({member.id})", "Durasi": duration, "Moderator": ctx.author.mention, "Alasan": reason}, self.color_warning)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin yang cukup untuk memberikan timeout pada anggota ini. Pastikan role bot lebih tinggi.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat memberikan timeout: {e}", color=self.color_error))


    @commands.command(name="removetimeout", aliases=["unmute"])
    @commands.has_permissions(moderate_members=True)
    async def remove_timeout(self, ctx, member: discord.Member):
        if member.id == ctx.guild.owner.id: await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa menghapus timeout pemilik server.", color=self.color_error)); return
        if member.id == self.bot.user.id: await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa menghapus timeout bot ini sendiri.", color=self.color_error)); return

        if not member.is_timed_out():
            return await ctx.send(embed=self._create_embed(description=f"❌ {member.display_name} tidak sedang dalam timeout.", color=self.color_error))

        try:
            await member.timeout(None, reason=f"Timeout dihapus oleh {ctx.author}")
            await ctx.send(embed=self._create_embed(description=f"✅ Timeout untuk **{member.display_name}** telah dihapus.", color=self.color_success))
            await self.log_action(ctx.guild, "😊 Timeout Dihapus", {"Member": f"{member} ({member.id})", "Moderator": ctx.author.mention}, self.color_success)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin yang cukup untuk menghapus timeout anggota ini. Pastikan role bot lebih tinggi.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat menghapus timeout: {e}", color=self.color_error))

        
    @commands.command(name="clear", aliases=["purge"])
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int):
        if amount <= 0: await ctx.send(embed=self._create_embed(description="❌ Jumlah harus lebih dari 0.", color=self.color_error)); return
        if amount > 100: await ctx.send(embed=self._create_embed(description="❌ Anda hanya bisa menghapus maksimal 100 pesan sekaligus.", color=self.color_error)); return

        try:
            deleted = await ctx.channel.purge(limit=amount + 1)
            embed = self._create_embed(description=f"🗑️ Berhasil menghapus **{len(deleted) - 1}** pesan.", color=self.color_success)
            await ctx.send(embed=embed, delete_after=5)
            await self.log_action(ctx.guild, "🗑️ Pesan Dihapus", {"Channel": ctx.channel.mention, "Jumlah": f"{len(deleted) - 1} pesan", "Moderator": ctx.author.mention}, self.color_info)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin `Manage Messages` untuk menghapus pesan.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat menghapus pesan: {e}", color=self.color_error))
        
    @commands.command(name="slowmode")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int):
        if seconds < 0: await ctx.send(embed=self._create_embed(description="❌ Durasi slowmode tidak bisa negatif.", color=self.color_error)); return
        if seconds > 21600: await ctx.send(embed=self._create_embed(description="❌ Durasi slowmode tidak bisa lebih dari 6 jam (21600 detik).", color=self.color_error)); return

        try:
            await ctx.channel.edit(slowmode_delay=seconds)
            status = f"diatur ke `{seconds}` detik" if seconds > 0 else "dinonaktifkan"
            await ctx.send(embed=self._create_embed(description=f"✅ Mode lambat di channel ini telah {status}.", color=self.color_success))
            await self.log_action(ctx.guild, "⏳ Slowmode Diubah", {"Channel": ctx.channel.mention, "Durasi": f"{seconds} detik", "Moderator": ctx.author.mention}, self.color_info)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin `Manage Channels` untuk mengatur slowmode.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat mengatur slowmode: {e}", color=self.color_error))


    @commands.command(name="lock")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx, channel: Optional[discord.TextChannel] = None):
        target_channel = channel or ctx.channel
        current_perms = target_channel.permissions_for(ctx.guild.default_role)
        if not current_perms.send_messages is False:
            try:
                await target_channel.set_permissions(ctx.guild.default_role, send_messages=False)
                await ctx.send(embed=self._create_embed(description=f"🔒 Channel {target_channel.mention} telah dikunci.", color=self.color_success))
                await self.log_action(ctx.guild, "🔒 Channel Dikunci", {"Channel": target_channel.mention, "Moderator": ctx.author.mention}, self.color_warning)
            except discord.Forbidden:
                await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin `Manage Channels` untuk mengunci channel.", color=self.color_error))
            except Exception as e:
                await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat mengunci channel: {e}", color=self.color_error))
        else:
            await ctx.send(embed=self._create_embed(description=f"❌ Channel {target_channel.mention} sudah terkunci.", color=self.color_error))


    @commands.command(name="unlock")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx, channel: Optional[discord.TextChannel] = None):
        target_channel = channel or ctx.channel
        current_perms = target_channel.permissions_for(ctx.guild.default_role)
        if not current_perms.send_messages is True:
            try:
                await target_channel.set_permissions(ctx.guild.default_role, send_messages=None)
                await ctx.send(embed=self._create_embed(description=f"🔓 Kunci channel {target_channel.mention} telah dibuka.", color=self.color_success))
                await self.log_action(ctx.guild, "🔓 Kunci Dibuka", {"Channel": target_channel.mention, "Moderator": ctx.author.mention}, self.color_success)
            except discord.Forbidden:
                await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin `Manage Channels` untuk membuka kunci channel.", color=self.color_error))
            except Exception as e:
                await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat membuka kunci channel: {e}", color=self.color_error))
        else:
            await ctx.send(embed=self._create_embed(description=f"❌ Channel {target_channel.mention} sudah tidak terkunci.", color=self.color_error))


    @commands.command(name="addrole")
    @commands.has_permissions(manage_roles=True)
    async def add_role(self, ctx, member: discord.Member, role: discord.Role):
        """Memberikan role kepada seorang anggota."""
        if ctx.author.top_role <= role:
            return await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa memberikan role yang lebih tinggi atau setara dengan role Anda.", color=self.color_error))
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengubah role anggota yang posisinya lebih tinggi atau setara.", color=self.color_error))
        if role in member.roles:
            return await ctx.send(embed=self._create_embed(description=f"❌ {member.display_name} sudah memiliki role {role.mention}.", color=self.color_error))

        try:
            await member.add_roles(role, reason=f"Diberikan oleh {ctx.author}")
            await ctx.send(embed=self._create_embed(description=f"✅ Role {role.mention} telah diberikan kepada {member.mention}.", color=self.color_success))
            await self.log_action(ctx.guild, "➕ Role Diberikan", {"Member": member.mention, "Role": role.mention, "Moderator": ctx.author.mention}, self.color_info)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin yang cukup untuk memberikan role ini. Pastikan role bot lebih tinggi dari role yang ingin diberikan.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat memberikan role: {e}", color=self.color_error))


    @commands.command(name="removerole")
    @commands.has_permissions(manage_roles=True)
    async def remove_role(self, ctx, member: discord.Member, role: discord.Role):
        """Menghapus role dari seorang anggota."""
        if ctx.author.top_role <= role:
            return await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa menghapus role yang lebih tinggi atau setara dengan role Anda.", color=self.color_error))
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengubah role anggota yang posisinya lebih tinggi atau setara.", color=self.color_error))
        if role not in member.roles:
            return await ctx.send(embed=self._create_embed(description=f"❌ {member.display_name} tidak memiliki role {role.mention}.", color=self.color_error))
            
        try:
            await member.remove_roles(role, reason=f"Dihapus oleh {ctx.author}")
            await ctx.send(embed=self._create_embed(description=f"✅ Role {role.mention} telah dihapus dari {member.mention}.", color=self.color_success))
            await self.log_action(ctx.guild, "➖ Role Dihapus", {"Member": member.mention, "Role": role.mention, "Moderator": ctx.author.mention}, self.color_info)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin yang cukup untuk menghapus role ini. Pastikan role bot lebih tinggi dari role yang ingin dihapus.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat menghapus role: {e}", color=self.color_error))


    @commands.command(name="nick")
    @commands.has_permissions(manage_nicknames=True)
    async def nick(self, ctx, member: discord.Member, *, new_nickname: Optional[str] = None):
        """Mengubah atau mereset nickname seorang anggota."""
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengubah nickname anggota dengan role lebih tinggi atau setara.", color=self.color_error))
        if member.id == ctx.guild.owner.id:
            return await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengubah nickname pemilik server.", color=self.color_error)); return
        if member.id == self.bot.user.id:
            return await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengubah nickname bot ini sendiri.", color=self.color_error)); return

        old_nickname = member.display_name
        try:
            await member.edit(nick=new_nickname, reason=f"Diubah oleh {ctx.author}")
            if new_nickname:
                await ctx.send(embed=self._create_embed(description=f"✅ Nickname **{old_nickname}** telah diubah menjadi **{new_nickname}**.", color=self.color_success))
                await self.log_action(ctx.guild, "👤 Nickname Diubah", {"Member": member.mention, "Dari": old_nickname, "Menjadi": new_nickname, "Moderator": ctx.author.mention}, self.color_info)
            else:
                await ctx.send(embed=self._create_embed(description=f"✅ Nickname untuk **{old_nickname}** telah direset.", color=self.color_success))
                await self.log_action(ctx.guild, "👤 Nickname Direset", {"Member": member.mention, "Moderator": ctx.author.mention}, self.color_info)
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin yang cukup untuk mengubah nickname ini. Pastikan role bot lebih tinggi dari anggota ini.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat mengubah nickname: {e}", color=self.color_error))


    # =======================================================================================
    # CHANNEL RULES COMMANDS
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
                
                self.clear_items() # Clear existing items before adding updated ones
                
                # Re-create and add buttons with updated states
                self.toggle_bots = discord.ui.Button(emoji="🛡️", row=0)
                self.toggle_bots.callback = lambda i: self.toggle_rule(i, "disallow_bots")
                set_button_state(self.toggle_bots, "Dilarang Bot", rules.get("disallow_bots", False))
                self.add_item(self.toggle_bots)

                self.toggle_media = discord.ui.Button(emoji="🖼️", row=0)
                self.toggle_media.callback = lambda i: self.toggle_rule(i, "disallow_media")
                set_button_state(self.toggle_media, "Dilarang Media", rules.get("disallow_media", False))
                self.add_item(self.toggle_media)

                self.toggle_prefix = discord.ui.Button(emoji="❗", row=0)
                self.toggle_prefix.callback = lambda i: self.toggle_rule(i, "disallow_prefix")
                set_button_state(self.toggle_prefix, "Dilarang Prefix", rules.get("disallow_prefix", False))
                self.add_item(self.toggle_prefix)

                self.toggle_url = discord.ui.Button(emoji="🔗", row=1)
                self.toggle_url.callback = lambda i: self.toggle_rule(i, "disallow_url")
                set_button_state(self.toggle_url, "Dilarang URL", rules.get("disallow_url", False))
                self.add_item(self.toggle_url)
                
                self.toggle_auto_delete = discord.ui.Button(emoji="⏳", row=1)
                self.toggle_auto_delete.callback = lambda i: self.set_auto_delete(i)
                delay = rules.get("auto_delete_seconds", 0)
                self.toggle_auto_delete.label = f"Hapus Otomatis: {delay}s" if delay > 0 else "Hapus Otomatis: Nonaktif"
                self.toggle_auto_delete.style = discord.ButtonStyle.green if delay > 0 else discord.ButtonStyle.red
                self.add_item(self.toggle_auto_delete)

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                if interaction.user != self.author: await interaction.response.send_message("Hanya pengguna yang memulai perintah yang dapat berinteraksi.", ephemeral=True); return False
                if not interaction.user.guild_permissions.manage_channels:
                    await interaction.response.send_message("Anda tidak memiliki izin `Manage Channels` untuk mengubah aturan ini.", ephemeral=True)
                    return False
                return True

            async def toggle_rule(self, interaction: discord.Interaction, rule_name: str):
                rules = self.cog.get_channel_rules(self.guild_id, self.channel_id)
                rules[rule_name] = not rules.get(rule_name, False)
                self.cog.save_settings()
                self.update_buttons()
                await interaction.response.edit_message(view=self)
                await self.cog.log_action(
                    self.target_channel.guild, 
                    "🔧 Aturan Channel Diubah", 
                    {"Channel": self.target_channel.mention, f"Aturan '{rule_name}'": "Diaktifkan" if rules[rule_name] else "Dinonaktifkan", "Moderator": interaction.user.mention}, 
                    self.cog.color_info
                )

            async def set_auto_delete(self, interaction: discord.Interaction):
                class AutoDeleteModal(discord.ui.Modal, title="Atur Hapus Otomatis"):
                    def __init__(self, current_delay):
                        super().__init__()
                        self.delay_input = discord.ui.TextInput(
                            label="Durasi (detik, 0 untuk nonaktif)",
                            placeholder="Contoh: 30 (maks 3600)",
                            default=str(current_delay),
                            max_length=4
                        )
                        self.add_item(self.delay_input)

                    async def on_submit(self, modal_interaction: discord.Interaction):
                        try:
                            delay = int(self.delay_input.value)
                            if not (0 <= delay <= 3600):
                                await modal_interaction.response.send_message(embed=self.cog._create_embed(description="❌ Durasi harus antara 0 dan 3600 detik (1 jam).", color=self.cog.color_error), ephemeral=True)
                                return
                            
                            rules = self.cog.get_channel_rules(self.guild_id, self.channel_id)
                            rules["auto_delete_seconds"] = delay
                            self.cog.save_settings()
                            self.update_buttons()
                            await modal_interaction.response.edit_message(view=self)
                            
                            await self.cog.log_action(
                                self.target_channel.guild, 
                                "⏳ Hapus Otomatis Diubah", 
                                {"Channel": self.target_channel.mention, "Durasi": f"{delay} detik" if delay > 0 else "Dinonaktifkan", "Moderator": modal_interaction.user.mention}, 
                                self.cog.color_info
                            )
                        except ValueError:
                            await modal_interaction.response.send_message(embed=self.cog._create_embed(description="❌ Durasi harus berupa angka.", color=self.cog.color_error), ephemeral=True)
                        except Exception as e:
                            await modal_interaction.response.send_message(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan: {e}", color=self.cog.color_error), ephemeral=True)
                
                rules = self.cog.get_channel_rules(self.guild_id, self.channel_id)
                current_delay = rules.get("auto_delete_seconds", 0)
                await interaction.response.send_modal(AutoDeleteModal(current_delay))

        embed = self._create_embed(title=f"🔧 Aturan untuk Channel: #{target_channel.name}", description="Tekan tombol untuk mengaktifkan (hijau) atau menonaktifkan (merah) aturan untuk channel ini. Tekan tombol hapus otomatis untuk mengatur durasi (default 30s).", color=self.color_info)
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
        if ctx.author.top_role <= role:
            return await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengatur reaction role untuk role yang lebih tinggi atau setara dengan role Anda.", color=self.color_error))
        
        guild_settings = self.get_guild_settings(ctx.guild.id)
        message_id_str = str(message.id)
        if message_id_str not in guild_settings["reaction_roles"]: guild_settings["reaction_roles"][message_id_str] = {}
        guild_settings["reaction_roles"][message_id_str][emoji] = role.id
        self.save_settings()
        try:
            await message.add_reaction(emoji)
            await ctx.send(embed=self._create_embed(description=f"✅ Role **{role.mention}** akan diberikan untuk reaksi {emoji} pada [pesan itu]({message.jump_url}).", color=self.color_success))
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin untuk menambahkan reaksi atau mengatur role. Pastikan izinnya lengkap.", color=self.color_error))
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan: {e}", color=self.color_error))


    @commands.command(name="setup")
    @commands.has_permissions(manage_guild=True)
    async def setup(self, ctx):
        class SetupView(discord.ui.View):
            def __init__(self, cog_instance):
                super().__init__(timeout=300)
                self.cog = cog_instance; self.guild_id = ctx.guild.id; self.author = ctx.author
            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                if interaction.user != self.author: await interaction.response.send_message("Hanya pengguna yang memulai setup yang dapat berinteraksi.", ephemeral=True); return False
                if not interaction.user.guild_permissions.manage_guild:
                    await interaction.response.send_message("Anda tidak memiliki izin `Manage Server` untuk menggunakan setup ini.", ephemeral=True)
                    return False
                return True

            async def handle_response(self, interaction, prompt, callback):
                await interaction.response.send_message(embed=self.cog._create_embed(description=prompt, color=self.cog.color_info), ephemeral=True)
                try:
                    msg = await self.cog.bot.wait_for('message', check=lambda m: m.author == self.author and m.channel == interaction.channel, timeout=120)
                    await callback(msg, interaction)
                except asyncio.TimeoutError: await interaction.followup.send(embed=self.cog._create_embed(description="❌ Waktu habis.", color=self.cog.color_error), ephemeral=True)
                except Exception as e:
                    await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan: {e}", color=self.cog.color_error), ephemeral=True)

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
            @discord.ui.button(label="Log Channel", style=discord.ButtonStyle.primary, emoji="📝", row=0)
            async def set_log_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
                async def callback(msg, inter):
                    channel = msg.channel_mentions[0] if msg.channel_mentions else ctx.guild.get_channel(int(msg.content)) if msg.content.isdigit() else None
                    if channel and isinstance(channel, discord.TextChannel):
                        self.cog.get_guild_settings(self.guild_id)['log_channel_id'] = channel.id; self.cog.save_settings()
                        await inter.followup.send(embed=self.cog._create_embed(description=f"✅ Log Channel diatur ke **{channel.mention}**.", color=self.cog.color_success), ephemeral=True)
                    else: await inter.followup.send(embed=self.cog._create_embed(description="❌ Channel tidak ditemukan atau bukan channel teks.", color=self.cog.color_error), ephemeral=True)
                await self.handle_response(interaction, "Sebutkan (mention) atau masukkan ID channel untuk log aktivitas bot:", callback)
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
        class AddFilterModal(discord.ui.Modal, title="Tambah Filter"):
            def __init__(self, cog_instance, filter_type):
                super().__init__(); self.cog = cog_instance; self.filter_type = filter_type
                self.item_to_add = discord.ui.TextInput(label=f"Masukkan {('kata' if filter_type == 'bad_words' else 'pola regex')} untuk ditambahkan", style=discord.TextStyle.paragraph)
                self.add_item(self.item_to_add)
            async def on_submit(self, interaction: discord.Interaction):
                filters = self.cog.get_guild_filters(interaction.guild_id); item = self.item_to_add.value.lower().strip()
                if item in filters[self.filter_type]:
                    await interaction.response.send_message(embed=self.cog._create_embed(description=f"❌ `{item}` sudah ada di filter.", color=self.cog.color_error), ephemeral=True)
                else:
                    filters[self.filter_type].append(item); self.cog.save_filters()
                    await interaction.response.send_message(embed=self.cog._create_embed(description=f"✅ `{item}` berhasil ditambahkan ke filter.", color=self.cog.color_success), ephemeral=True)

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
            async def add_bad_word(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_modal(AddFilterModal(self.cog, "bad_words"))
            @discord.ui.button(label="Hapus Kata Kasar", style=discord.ButtonStyle.danger, emoji="🗑️")
            async def remove_bad_word(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_modal(RemoveFilterModal(self.cog, "bad_words"))
            @discord.ui.button(label="Tambah Pola Link", style=discord.ButtonStyle.primary, emoji="🔗")
            async def add_link_pattern(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_modal(AddFilterModal(self.cog, "link_patterns"))
            @discord.ui.button(label="Hapus Pola Link", style=discord.ButtonStyle.danger, emoji="🔗")
            async def remove_link_pattern(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_modal(RemoveFilterModal(self.cog, "link_patterns"))
            @discord.ui.button(label="Lihat Semua Filter", style=discord.ButtonStyle.secondary, emoji="📋", row=2)
            async def view_filters(self, interaction: discord.Interaction, button: discord.ui.Button):
                filters = self.cog.get_guild_filters(interaction.guild_id); bad_words = ", ".join(f"`{w}`" for w in filters['bad_words']) or "Kosong"; link_patterns = ", ".join(f"`{p}`" for p in filters['link_patterns']) or "Kosong"
                embed = self.cog._create_embed(title="Daftar Filter Aktif", color=self.cog.color_info)
                embed.add_field(name="🚫 Kata Kasar", value=bad_words[:1024], inline=False); embed.add_field(name="🔗 Pola Link", value=link_patterns[:1024], inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        embed = self._create_embed(title="⚙️ Panel Kontrol Server", description="Gunakan tombol di bawah ini untuk mengatur bot. Anda memiliki 5 menit sebelum panel ini nonaktif.", color=self.color_info, author_name=ctx.guild.name, author_icon_url=ctx.guild.icon.url if ctx.guild.icon else "")
        await ctx.send(embed=embed, view=SetupView(self))


    # =======================================================================================
    # ANNOUNCEMENT FEATURE - DITAMBAHKAN DAN DIOPTIMALKAN
    # =======================================================================================

    @commands.command(name="announce", aliases=["pengumuman", "broadcast"])
    @commands.has_permissions(manage_guild=True)
    async def announce(self, ctx, channel: Optional[discord.TextChannel] = None):
        """
        Membuat pengumuman kustom dengan tampilan modern.
        Pengguna akan mengisi detail melalui pop-up form (Modal UI).
        Pengumuman akan dikirim ke channel yang ditentukan atau channel saat ini.
        """
        target_channel = channel or ctx.channel

        class AnnouncementModal(discord.ui.Modal, title="Buat Pengumuman Baru"):
            # Input fields
            announcement_title = discord.ui.TextInput(
                label="Judul Pengumuman",
                placeholder="Contoh: Pembaruan Server!",
                max_length=256,
                required=True,
                row=0
            )
            announcement_description = discord.ui.TextInput(
                label="Deskripsi Pengumuman (Maks 4000 karakter)",
                placeholder="Tuliskan detail pengumumanmu di sini. Mendukung Discord Markdown.",
                style=discord.TextStyle.paragraph,
                max_length=4000,
                required=True,
                row=1
            )
            sender_name = discord.ui.TextInput(
                label="Nama Pengirim (Opsional, default: Anda)",
                placeholder=ctx.author.display_name, # Placeholder shows current user's name
                default=ctx.author.display_name,      # Pre-fill with current user's name
                max_length=256,
                required=False,
                row=2
            )
            sender_avatar_url = discord.ui.TextInput(
                label="URL Avatar Pengirim (Opsional, default: Avatar Anda)",
                placeholder="Contoh: https://example.com/avatar.png", # Generic placeholder
                default=str(ctx.author.display_avatar.url),      # Pre-fill with current user's avatar
                max_length=2000,
                required=False,
                row=3
            )
            announcement_image_url = discord.ui.TextInput(
                label="URL Gambar di Akhir Pengumuman (Opsional)",
                placeholder="Contoh: https://example.com/banner.png",
                max_length=2000,
                required=False,
                row=4
            )

            def __init__(self, cog_instance, original_ctx):
                super().__init__()
                self.cog = cog_instance
                self.original_ctx = original_ctx
                # The TextInput instances are already defined as class attributes above.
                # When super().__init__() is called, it automatically adds these class attributes
                # that are instances of discord.ui.InputText (or TextInput) to the modal's items.
                # So, no need for self.add_item() here, unless you want to dynamically create them.

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer(ephemeral=False) 

                title = self.announcement_title.value
                description = self.announcement_description.value
                
                # Retrieve values from modal inputs. .strip() to remove leading/trailing whitespace.
                # If optional fields are empty, use default values (original ctx.author's info).
                author_name = self.sender_name.value.strip() if self.sender_name.value else self.original_ctx.author.display_name
                author_icon = self.sender_avatar_url.value.strip() if self.sender_avatar_url.value else str(self.original_ctx.author.display_avatar.url)
                image_url = self.announcement_image_url.value.strip()
                
                # Basic URL validation
                if author_icon and not (author_icon.startswith("http://") or author_icon.startswith("https://")):
                    await interaction.followup.send(embed=self.cog._create_embed(
                        description="❌ URL Avatar Pengirim tidak valid. Harus dimulai dengan `http://` atau `https://`.", 
                        color=self.cog.color_error
                    ), ephemeral=True)
                    return
                if image_url and not (image_url.startswith("http://") or image_url.startswith("https://")):
                    await interaction.followup.send(embed=self.cog._create_embed(
                        description="❌ URL Gambar Pengumuman tidak valid. Harus dimulai dengan `http://` atau `https://`.", 
                        color=self.cog.color_error
                    ), ephemeral=True)
                    return

                # Create the announcement embed
                announce_embed = discord.Embed(
                    title=title,
                    description=description,
                    color=self.cog.color_announce,
                    timestamp=datetime.utcnow() # Use UTC for consistency
                )
                announce_embed.set_author(name=author_name, icon_url=author_icon)
                if image_url:
                    announce_embed.set_image(url=image_url)
                
                # Footer tetap dengan informasi bot atau server
                announce_embed.set_footer(text=f"Pengumuman dari {self.original_ctx.guild.name}", icon_url=self.original_ctx.guild.icon.url if self.original_ctx.guild.icon else None)

                try:
                    # Check bot's permissions in the target channel before sending
                    perms = target_channel.permissions_for(target_channel.guild.me)
                    if not perms.send_messages or not perms.embed_links:
                        await interaction.followup.send(embed=self.cog._create_embed(
                            description=f"❌ Bot tidak memiliki izin untuk mengirim pesan atau menyematkan tautan di {target_channel.mention}. Pastikan bot memiliki izin 'Kirim Pesan' dan 'Sematkan Tautan'.", 
                            color=self.cog.color_error
                        ), ephemeral=True)
                        return

                    await target_channel.send(embed=announce_embed)
                    await interaction.followup.send(embed=self.cog._create_embed(
                        description=f"✅ Pengumuman berhasil dikirim ke {target_channel.mention}!", 
                        color=self.cog.color_success
                    ), ephemeral=True)
                    # Log the announcement creation
                    await self.cog.log_action(
                        self.original_ctx.guild, 
                        "📢 Pengumuman Baru Dibuat", 
                        {
                            "Pengirim": self.original_ctx.author.mention, 
                            "Channel Target": target_channel.mention, 
                            "Judul": title, 
                            "Deskripsi (Awal)": description[:1024] + "..." if len(description) > 1024 else description
                        }, 
                        self.cog.color_announce
                    )
                except discord.Forbidden:
                    await interaction.followup.send(embed=self.cog._create_embed(
                        description=f"❌ Bot tidak memiliki izin untuk mengirim pesan di {target_channel.mention}. Pastikan bot memiliki izin 'Send Messages' dan 'Embed Links'.", 
                        color=self.cog.color_error
                    ), ephemeral=True)
                except Exception as e:
                    print(f"Error saat mengirim pengumuman di channel {target_channel.id}: {e}")
                    await interaction.followup.send(embed=self.cog._create_embed(
                        description=f"❌ Terjadi kesalahan saat mengirim pengumuman: {e}", 
                        color=self.cog.color_error
                    ), ephemeral=True)

            async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
                print(f"Error in AnnouncementModal (on_error): {error}")
                await interaction.followup.send(embed=self.cog._create_embed(
                    description=f"❌ Terjadi kesalahan tak terduga saat memproses formulir: {error}",
                    color=self.cog.color_error
                ), ephemeral=True)

        class AnnounceButtonView(discord.ui.View):
            def __init__(self, cog_instance, original_ctx, target_channel):
                super().__init__(timeout=60)
                self.cog = cog_instance
                self.original_ctx = original_ctx
                self.target_channel = target_channel

            @discord.ui.button(label="Buat Pengumuman", style=discord.ButtonStyle.primary, emoji="📣")
            async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user != self.original_ctx.author:
                    return await interaction.response.send_message("Hanya orang yang memulai perintah yang dapat membuat pengumuman.", ephemeral=True)
                if not interaction.user.guild_permissions.manage_guild:
                    return await interaction.response.send_message("Anda tidak memiliki izin `Manage Server`.", ephemeral=True)
                
                modal = AnnouncementModal(self.cog, self.original_ctx)
                try:
                    await interaction.response.send_modal(modal)
                except discord.Forbidden:
                    await interaction.followup.send(embed=self.cog._create_embed(
                        description=f"❌ Bot tidak memiliki izin untuk mengirim modal. Ini bisa terjadi jika bot tidak bisa mengirim DM ke Anda atau ada masalah izin.",
                        color=self.cog.color_error
                    ), ephemeral=True)
                except Exception as e:
                    print(f"Error saat menampilkan modal pengumuman: {e}")
                    await interaction.followup.send(embed=self.cog._create_embed(
                        description=f"❌ Terjadi kesalahan saat menampilkan formulir: {e}",
                        color=self.cog.color_error
                    ), ephemeral=True)


            async def on_timeout(self) -> None:
                for item in self.children:
                    item.disabled = True
                try:
                    await self.original_ctx.edit_original_response(view=self)
                except discord.NotFound:
                    pass

        # Send the initial message with the button
        await ctx.send(embed=self._create_embed(
            title="🔔 Siap Membuat Pengumuman?", 
            description=f"Tekan tombol di bawah untuk membuka formulir pengumuman yang akan dikirim ke channel {target_channel.mention}. Anda memiliki **60 detik**.", 
            color=self.color_info), 
            view=AnnounceButtonView(self, ctx, target_channel)
        )

async def setup(bot):
    await bot.add_cog(ServerAdminCog(bot))

