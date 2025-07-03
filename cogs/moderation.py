import discord
from discord.ext import commands
import json
import os
import re
import asyncio
from typing import Optional
from datetime import datetime, timedelta
import time
import aiohttp
import sys

# =======================================================================================
# UTILITY FUNCTIONS - Fungsi bantuan
# =======================================================================================

def load_data(file_path):
    """Memuat data dari file JSON. Jika file tidak ada, kembalikan dictionary kosong."""
    try:
        if not os.path.exists(file_path):
            print(f"[{datetime.now()}] [DEBUG HELPER] File tidak ditemukan: {file_path}. Mengembalikan data kosong.")
            return {}
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content:
                print(f"[{datetime.now()}] [DEBUG HELPER] File kosong: {file_path}. Mengembalikan data kosong.")
                return {}
            data = json.loads(content)
            print(f"[{datetime.now()}] [DEBUG HELPER] Data berhasil dimuat dari: {file_path}.")
            return data
    except (json.JSONDecodeError, IOError) as e:
        print(f"[{datetime.now()}] [DEBUG HELPER] ERROR memuat {file_path}: {e}. Mengembalikan data kosong.", file=sys.stderr)
        return {}

def save_data(file_path, data):
    """Menyimpan data ke file JSON."""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        print(f"[{datetime.now()}] [DEBUG HELPER] Data berhasil disimpan ke: {file_path}.")
    except Exception as e:
        print(f"[{datetime.now()}] [DEBUG HELPER] ERROR menyimpan {file_path}: {e}.", file=sys.stderr)

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
        self.color_announce = 0x7289DA

        self.settings = load_data(self.settings_file)
        self.filters = load_data(self.filters_file)
        self.warnings = load_data(self.warnings_file)
        print(f"[{datetime.now()}] [DEBUG ADMIN] ServerAdminCog diinisialisasi. Settings: {len(self.settings)} guild, Filters: {len(self.filters)} guild, Warnings: {len(self.warnings)} guild.")

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
            save_data(self.settings_file, self.settings)
            print(f"[{datetime.now()}] [DEBUG ADMIN] Pengaturan default dibuat untuk guild {guild_id}.")
        elif "channel_rules" not in self.settings[guild_id_str]:
            self.settings[guild_id_str]["channel_rules"] = {}
            save_data(self.settings_file, self.settings)
            print(f"[{datetime.now()}] [DEBUG ADMIN] Aturan channel ditambahkan untuk guild {guild_id}.")
        return self.settings[guild_id_str]

    def get_channel_rules(self, guild_id: int, channel_id: int) -> dict:
        guild_settings = self.get_guild_settings(guild_id)
        channel_id_str = str(channel_id)
        if channel_id_str not in guild_settings["channel_rules"]:
            guild_settings["channel_rules"][channel_id_str] = {
                "disallow_bots": False, "disallow_media": False, "disallow_prefix": False,
                "disallow_url": False, "auto_delete_seconds": 0
            }
            save_data(self.settings_file, self.settings)
            print(f"[{datetime.now()}] [DEBUG ADMIN] Aturan default dibuat untuk channel {channel_id} di guild {guild_id}.")
        return guild_settings["channel_rules"][channel_id_str]
        
    def get_guild_filters(self, guild_id: int):
        guild_id_str = str(guild_id)
        if guild_id_str not in self.filters:
            self.filters[guild_id_str] = { "bad_words": [], "link_patterns": [] }
            save_data(self.filters_file, self.filters)
            print(f"[{datetime.now()}] [DEBUG ADMIN] Filter default dibuat untuk guild {guild_id}.")
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
        print(f"[{datetime.now()}] [DEBUG ADMIN] Logging action: {title} di guild {guild.name}.")
        if not (log_channel_id := self.get_guild_settings(guild.id).get("log_channel_id")):
            print(f"[{datetime.now()}] [DEBUG ADMIN] Log channel tidak diatur untuk guild {guild.name}.")
            return
        if (log_channel := guild.get_channel(log_channel_id)) and log_channel.permissions_for(guild.me).send_messages:
            embed = self._create_embed(title=title, color=color)
            for name, value in fields.items():
                embed.add_field(name=name, value=value, inline=False)
            await log_channel.send(embed=embed)
            print(f"[{datetime.now()}] [DEBUG ADMIN] Aksi '{title}' berhasil dilog ke {log_channel.name}.")
        else:
            print(f"[{datetime.now()}] [DEBUG ADMIN] Gagal melog aksi '{title}': Channel tidak ditemukan atau bot tidak memiliki izin mengirim pesan.")

    # =======================================================================================
    # EVENT LISTENERS
    # =======================================================================================

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        print(f"[{datetime.now()}] [DEBUG ADMIN] on_command_error dipicu untuk command '{ctx.command}': {type(error).__name__}.")
        if isinstance(error, commands.MissingPermissions):
            embed = self._create_embed(description=f"❌ Anda tidak memiliki izin `{', '.join(error.missing_permissions)}` untuk menjalankan perintah ini.", color=self.color_error)
            await ctx.send(embed=embed, delete_after=15)
            print(f"[{datetime.now()}] [DEBUG ADMIN] Error: MissingPermissions. Pesan dikirim.")
        elif isinstance(error, commands.CommandNotFound):
            print(f"[{datetime.now()}] [DEBUG ADMIN] Error: CommandNotFound. Diabaikan.")
            pass
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(embed=self._create_embed(description=f"❌ Anggota tidak ditemukan.", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] Error: MemberNotFound. Pesan dikirim.")
        elif isinstance(error, commands.UserNotFound):
            await ctx.send(embed=self._create_embed(description=f"❌ Pengguna tidak ditemukan.", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] Error: UserNotFound. Pesan dikirim.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(embed=self._create_embed(description=f"❌ Argument tidak valid: {error}", color=self.color_error), delete_after=15)
            print(f"[{datetime.now()}] [DEBUG ADMIN] Error: BadArgument. Pesan dikirim.")
        else:
            print(f"[{datetime.now()}] [DEBUG ADMIN] Error tak terduga pada perintah '{ctx.command}': {error}", file=sys.stderr)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        print(f"[{datetime.now()}] [DEBUG ADMIN] on_member_join dipicu untuk {member.display_name} di {member.guild.name}.")
        guild_settings = self.get_guild_settings(member.guild.id)
        if (welcome_channel_id := guild_settings.get("welcome_channel_id")) and (channel := member.guild.get_channel(welcome_channel_id)):
            welcome_message = guild_settings.get("welcome_message", "Selamat datang, {user}!")
            embed = discord.Embed(description=welcome_message.format(user=member.mention, guild_name=member.guild.name), color=self.color_welcome)
            embed.set_author(name=f"SELAMAT DATANG DI {member.guild.name.upper()}", icon_url=member.guild.icon.url if member.guild.icon else None)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Kamu adalah anggota ke-{member.guild.member_count}!")
            await channel.send(embed=embed)
            print(f"[{datetime.now()}] [DEBUG ADMIN] Pesan selamat datang dikirim ke {channel.name} untuk {member.display_name}.")
        if (auto_role_id := guild_settings.get("auto_role_id")) and (role := member.guild.get_role(auto_role_id)):
            try:
                await member.add_roles(role, reason="Auto Role")
                print(f"[{datetime.now()}] [DEBUG ADMIN] Auto-role {role.name} diberikan ke {member.display_name}.")
            except discord.Forbidden:
                print(f"[{datetime.now()}] [DEBUG ADMIN] Bot lacks permissions to assign auto-role {role.name} in {member.guild.name}.", file=sys.stderr)
            
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.id == self.bot.user.id: return
        
        rules = self.get_channel_rules(message.guild.id, message.channel.id)
        log_fields = {"Pengirim": message.author.mention, "Channel": message.channel.mention, "Isi Pesan": f"```{message.content[:1000]}```"}
        
        if (delay := rules.get("auto_delete_seconds", 0)) > 0:
            try:
                await message.delete(delay=delay)
                print(f"[{datetime.now()}] [DEBUG ADMIN] Pesan dari {message.author.display_name} dihapus otomatis setelah {delay} detik.")
            except discord.NotFound:
                print(f"[{datetime.now()}] [DEBUG ADMIN] Gagal hapus pesan {message.id}: Sudah tidak ditemukan.")
                pass

        if rules.get("disallow_bots") and message.author.bot:
            await message.delete()
            await self.log_action(message.guild, "🛡️ Pesan Bot Dihapus", log_fields, self.color_info)
            print(f"[{datetime.now()}] [DEBUG ADMIN] Pesan bot {message.author.display_name} dihapus.")
            return

        if message.author.bot:
            return

        if rules.get("disallow_media") and message.attachments:
            await message.delete()
            await message.channel.send(embed=self._create_embed(description=f"🖼️ {message.author.mention}, dilarang mengirim media/file di channel ini.", color=self.color_warning), delete_after=10)
            await self.log_action(message.guild, "🖼️ Media Dihapus", log_fields, self.color_warning)
            print(f"[{datetime.now()}] [DEBUG ADMIN] Pesan media dari {message.author.display_name} dihapus.")
            try:
                dm_embed = self._create_embed(title="Peringatan Pelanggaran Aturan", color=self.color_warning)
                dm_embed.add_field(name="Server", value=message.guild.name, inline=False)
                dm_embed.add_field(name="Pelanggaran", value="Pesan Anda dihapus karena mengandung **media/file** di channel yang tidak semestinya.", inline=False)
                dm_embed.add_field(name="Saran", value="Silakan kirim media di channel yang telah disediakan. Mohon periksa kembali peraturan server.", inline=False)
                await message.author.send(embed=dm_embed)
            except discord.Forbidden: print(f"[{datetime.now()}] [DEBUG ADMIN] Gagal kirim DM peringatan ke {message.author.display_name} (Forbidden).")
            return
        
        if message.content and message.content.startswith(self.bot.command_prefix):
            command_prefixes = await self.bot.get_prefix(message)
            if not isinstance(command_prefixes, list):
                command_prefixes = [command_prefixes]

            is_actual_command = False
            for prefix in command_prefixes:
                if message.content.startswith(prefix):
                    command_name = message.content[len(prefix):].split(' ')[0]
                    if self.bot.get_command(command_name):
                        is_actual_command = True
                        break
            
            if rules.get("disallow_prefix") and not is_actual_command:
                await message.delete()
                await message.channel.send(embed=self._create_embed(description=f"❗ {message.author.mention}, dilarang menggunakan perintah bot di channel ini.", color=self.color_warning), delete_after=10)
                await self.log_action(message.guild, "❗ Perintah Bot Dihapus", log_fields, self.color_warning)
                print(f"[{datetime.now()}] [DEBUG ADMIN] Pesan dengan prefix dari {message.author.display_name} dihapus (bukan command valid).")
                return

        if rules.get("disallow_url") and self.url_regex.search(message.content):
            await message.delete()
            await message.channel.send(embed=self._create_embed(description=f"🔗 {message.author.mention}, dilarang mengirim link di channel ini.", color=self.color_warning), delete_after=10)
            await self.log_action(message.guild, "🔗 Link Dihapus", log_fields, self.color_warning)
            print(f"[{datetime.now()}] [DEBUG ADMIN] Pesan link dari {message.author.display_name} dihapus.")
            try:
                dm_embed = self._create_embed(title="Peringatan Pelanggaran Aturan", color=self.color_warning)
                dm_embed.add_field(name="Server", value=message.guild.name, inline=False)
                dm_embed.add_field(name="Pelanggaran", value="Pesan Anda dihapus karena mengandung **URL/link** di channel yang tidak semestinya.", inline=False)
                dm_embed.add_field(name="Saran", value="Silakan kirim link di channel yang telah disediakan. Mohon periksa kembali peraturan server.", inline=False)
                await message.author.send(embed=dm_embed)
            except discord.Forbidden: print(f"[{datetime.now()}] [DEBUG ADMIN] Gagal kirim DM peringatan ke {message.author.display_name} (Forbidden).")
            return

        guild_filters = self.get_guild_filters(message.guild.id)
        content_lower = message.content.lower()
        for bad_word in guild_filters.get("bad_words", []):
            if bad_word.lower() in content_lower:
                await message.delete()
                await message.channel.send(embed=self._create_embed(description=f"🤫 Pesan dari {message.author.mention} dihapus karena melanggar aturan.", color=self.color_warning), delete_after=10)
                await self.log_action(message.guild, "🚫 Pesan Disensor (Kata Kasar)", log_fields, self.color_warning)
                print(f"[{datetime.now()}] [DEBUG ADMIN] Pesan kata kasar dari {message.author.display_name} dihapus.")
                return
        for pattern in guild_filters.get("link_patterns", []):
            try:
                if re.search(pattern, message.content):
                    await message.delete()
                    await message.channel.send(embed=self._create_embed(description=f"🚨 {message.author.mention}, jenis link tersebut tidak diizinkan di sini.", color=self.color_warning), delete_after=10)
                    await self.log_action(message.guild, "🔗 Pesan Disensor (Pola Link)", log_fields, self.color_warning)
                    print(f"[{datetime.now()}] [DEBUG ADMIN] Pesan pola link dari {message.author.display_name} dihapus.")
                    return
            except re.error as e:
                print(f"[{datetime.now()}] [DEBUG ADMIN] ERROR: Regex filter pattern '{pattern}' tidak valid: {e}", file=sys.stderr)
        
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None or payload.member is None or payload.member.bot: return
        print(f"[{datetime.now()}] [DEBUG ADMIN] on_raw_reaction_add dipicu oleh {payload.member.display_name} di guild {payload.guild_id}.")

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            print(f"[{datetime.now()}] [DEBUG ADMIN] on_raw_reaction_add: Guild tidak ditemukan untuk payload {payload.guild_id}.")
            return
        
        guild_settings = self.get_guild_settings(payload.guild_id)
        role_map = guild_settings.get("reaction_roles", {}).get(str(payload.message_id))
        
        if role_map and (role_id := role_map.get(str(payload.emoji))):
            if (role := guild.get_role(role_id)):
                try:
                    await payload.member.add_roles(role, reason="Reaction Role")
                    print(f"[{datetime.now()}] [DEBUG ADMIN] Reaction Role: {role.name} diberikan kepada {payload.member.display_name}.")
                except discord.Forbidden:
                    print(f"[{datetime.now()}] [DEBUG ADMIN] Bot lacks permissions to assign reaction role {role.name} to {payload.member.display_name} in {guild.name}.", file=sys.stderr)
                except Exception as e:
                    print(f"[{datetime.now()}] [DEBUG ADMIN] Error assigning reaction role: {e}.", file=sys.stderr)
            else:
                print(f"[{datetime.now()}] [DEBUG ADMIN] Reaction Role: Role dengan ID {role_id} tidak ditemukan di guild {guild.name}.")
        else:
            print(f"[{datetime.now()}] [DEBUG ADMIN] Reaction Role: Tidak ada pengaturan reaction role untuk pesan {payload.message_id} atau emoji {payload.emoji}.")


    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None: return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild or not (member := guild.get_member(payload.user_id)) or member.bot: return
        print(f"[{datetime.now()}] [DEBUG ADMIN] on_raw_reaction_remove dipicu oleh {member.display_name} di guild {payload.guild_id}.")

        guild_settings = self.get_guild_settings(payload.guild_id)
        role_map = guild_settings.get("reaction_roles", {}).get(str(payload.message_id))
        
        if role_map and (role_id := role_map.get(str(payload.emoji))):
            if (role := guild.get_role(role_id)):
                if role in member.roles:
                    try:
                        await member.remove_roles(role, reason="Reaction Role Removed")
                        print(f"[{datetime.now()}] [DEBUG ADMIN] Reaction Role Removed: {role.name} dihapus dari {member.display_name}.")
                    except discord.Forbidden:
                        print(f"[{datetime.now()}] [DEBUG ADMIN] Bot lacks permissions to remove reaction role {role.name} from {member.display_name} in {guild.name}.", file=sys.stderr)
                    except Exception as e:
                        print(f"[{datetime.now()}] [DEBUG ADMIN] Error removing reaction role: {e}.", file=sys.stderr)
                else:
                    print(f"[{datetime.now()}] [DEBUG ADMIN] Reaction Role Removed: {member.display_name} tidak memiliki role {role.name}.")
            else:
                print(f"[{datetime.now()}] [DEBUG ADMIN] Reaction Role Removed: Role dengan ID {role_id} tidak ditemukan di guild {guild.name}.")
        else:
            print(f"[{datetime.now()}] [DEBUG ADMIN] Reaction Role Removed: Tidak ada pengaturan reaction role untuk pesan {payload.message_id} atau emoji {payload.emoji}.")

    # =======================================================================================
    # MODERATION COMMANDS
    # =======================================================================================

    @commands.command(name="kick")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: Optional[str] = "Tidak ada alasan."):
        print(f"[{datetime.now()}] [DEBUG ADMIN] Command !kick dipanggil oleh {ctx.author.display_name} untuk {member.display_name}.")
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengeluarkan anggota dengan role setara atau lebih tinggi.", color=self.color_error)); return
        if member.id == ctx.guild.owner.id:
            await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengeluarkan pemilik server.", color=self.color_error)); return
        if member.id == self.bot.user.id:
            await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengeluarkan bot ini sendiri.", color=self.color_error)); return

        try:
            await member.kick(reason=reason)
            await ctx.send(embed=self._create_embed(description=f"✅ **{member.display_name}** telah dikeluarkan.", color=self.color_success))
            await self.log_action(ctx.guild, "👢 Member Dikeluarkan", {"Member": f"{member} ({member.id})", "Moderator": ctx.author.mention, "Alasan": reason}, self.color_warning)
            print(f"[{datetime.now()}] [DEBUG ADMIN] {member.display_name} berhasil di-kick.")
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin yang cukup untuk mengeluarkan anggota ini. Pastikan role bot lebih tinggi.", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !kick: Bot Forbidden.")
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat mengeluarkan anggota: {e}", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !kick: ERROR: {e}.", file=sys.stderr)


    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: Optional[str] = "Tidak ada alasan."):
        print(f"[{datetime.now()}] [DEBUG ADMIN] Command !ban dipanggil oleh {ctx.author.display_name} untuk {member.display_name}.")
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner: await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa memblokir anggota dengan role setara atau lebih tinggi.", color=self.color_error)); return
        if member.id == ctx.guild.owner.id: await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa memblokir pemilik server.", color=self.color_error)); return
        if member.id == self.bot.user.id: await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa memblokir bot ini sendiri.", color=self.color_error)); return

        try:
            await member.ban(reason=reason)
            await ctx.send(embed=self._create_embed(description=f"✅ **{member.display_name}** telah diblokir.", color=self.color_success))
            await self.log_action(ctx.guild, "🔨 Member Diblokir", {"Member": f"{member} ({member.id})", "Moderator": ctx.author.mention, "Alasan": reason}, self.color_error)
            print(f"[{datetime.now()}] [DEBUG ADMIN] {member.display_name} berhasil di-ban.")
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin yang cukup untuk memblokir anggota ini. Pastikan role bot lebih tinggi.", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !ban: Bot Forbidden.")
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat memblokir anggota: {e}", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !ban: ERROR: {e}.", file=sys.stderr)


    @commands.command(name="unban")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, *, user_identifier: str, reason: Optional[str] = "Tidak ada alasan."):
        print(f"[{datetime.now()}] [DEBUG ADMIN] Command !unban dipanggil oleh {ctx.author.display_name} untuk '{user_identifier}'.")
        user_to_unban = None
        try:
            user_id = int(user_identifier)
            temp_user = await self.bot.fetch_user(user_id)
            user_to_unban = temp_user
            print(f"[{datetime.now()}] [DEBUG ADMIN] !unban: User ditemukan berdasarkan ID: {user_to_unban.display_name}.")
        except ValueError:
            print(f"[{datetime.now()}] [DEBUG ADMIN] !unban: '{user_identifier}' bukan ID, mencari berdasarkan Nama#Tag.")
            for entry in [entry async for entry in ctx.guild.bans()]:
                if str(entry.user).lower() == user_identifier.lower():
                    user_to_unban = entry.user
                    print(f"[{datetime.now()}] [DEBUG ADMIN] !unban: User ditemukan berdasarkan Nama#Tag: {user_to_unban.display_name}.")
                    break
        except discord.NotFound:
            print(f"[{datetime.now()}] [DEBUG ADMIN] !unban: User tidak ditemukan di Discord API.")
            pass

        if user_to_unban is None:
            await ctx.send(embed=self._create_embed(description=f"❌ Pengguna `{user_identifier}` tidak ditemukan dalam daftar blokir atau ID/Nama#Tag tidak valid.", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !unban: Pengguna tidak ditemukan untuk unban.")
            return

        try:
            await ctx.guild.unban(user_to_unban, reason=reason)
            await ctx.send(embed=self._create_embed(description=f"✅ Blokir untuk **{user_to_unban}** telah dibuka.", color=self.color_success))
            await self.log_action(ctx.guild, "🤝 Blokir Dibuka", {"Pengguna": f"{user_to_unban} ({user_to_unban.id})", "Moderator": ctx.author.mention, "Alasan": reason}, self.color_success)
            print(f"[{datetime.now()}] [DEBUG ADMIN] {user_to_unban.display_name} berhasil di-unban.")
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin yang cukup untuk membuka blokir anggota ini. Pastikan role bot lebih tinggi.", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !unban: Bot Forbidden.")
        except discord.NotFound:
            await ctx.send(embed=self._create_embed(description=f"❌ Pengguna `{user_to_unban}` tidak ditemukan dalam daftar blokir.", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !unban: User tidak ada di daftar ban.")
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat membuka blokir: {e}", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !unban: ERROR: {e}.", file=sys.stderr)


    @commands.command(name="warn")
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str):
        print(f"[{datetime.now()}] [DEBUG ADMIN] Command !warn dipanggil oleh {ctx.author.display_name} untuk {member.display_name} dengan alasan: '{reason}'.")
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
        print(f"[{datetime.now()}] [DEBUG ADMIN] Peringatan disimpan untuk {member.display_name}.")

        try:
            dm_embed = self._create_embed(title=f"🚨 Anda Menerima Peringatan di {ctx.guild.name}", color=self.color_warning)
            dm_embed.add_field(name="Alasan Peringatan", value=reason, inline=False)
            dm_embed.set_footer(text=f"Peringatan diberikan oleh {ctx.author.display_name}")
            await member.send(embed=dm_embed)
            dm_sent = True
            print(f"[{datetime.now()}] [DEBUG ADMIN] DM peringatan berhasil dikirim ke {member.display_name}.")
        except discord.Forbidden:
            dm_sent = False
            print(f"[{datetime.now()}] [DEBUG ADMIN] Gagal kirim DM peringatan ke {member.display_name} (Forbidden).")

        confirm_desc = f"✅ **{member.display_name}** telah diperingatkan."
        if not dm_sent:
            confirm_desc += "\n*(Pesan peringatan tidak dapat dikirim ke DM pengguna.)*"
            
        await ctx.send(embed=self._create_embed(description=confirm_desc, color=self.color_success))
        await self.log_action(ctx.guild, "⚠️ Member Diperingatkan", {"Member": f"{member} ({member.id})", "Moderator": ctx.author.mention, "Alasan": reason}, self.color_warning)

    @commands.command(name="unwarn")
    @commands.has_permissions(kick_members=True)
    async def unwarn(self, ctx, member: discord.Member, warning_index: int, *, reason: Optional[str] = "Kesalahan admin."):
        print(f"[{datetime.now()}] [DEBUG ADMIN] Command !unwarn dipanggil oleh {ctx.author.display_name} untuk {member.display_name} (indeks {warning_index}).")
        guild_id_str = str(ctx.guild.id)
        member_id_str = str(member.id)
        
        user_warnings = self.warnings.get(guild_id_str, {}).get(member_id_str, [])
        
        if not user_warnings:
            await ctx.send(embed=self._create_embed(description=f"❌ **{member.display_name}** tidak memiliki peringatan.", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !unwarn: {member.display_name} tidak punya peringatan.")
            return

        if not (0 < warning_index <= len(user_warnings)):
            await ctx.send(embed=self._create_embed(description=f"❌ Indeks peringatan tidak valid. Gunakan `!warnings {member.mention}` untuk melihat daftar peringatan.", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !unwarn: Indeks peringatan tidak valid ({warning_index}).")
            return
        
        removed_warning = self.warnings[guild_id_str][member_id_str].pop(warning_index - 1)
        self.save_warnings()
        print(f"[{datetime.now()}] [DEBUG ADMIN] Peringatan {warning_index} dihapus untuk {member.display_name}.")
        
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
        print(f"[{datetime.now()}] [DEBUG ADMIN] Command !warnings dipanggil oleh {ctx.author.display_name} untuk {member.display_name}.")
        guild_id_str = str(ctx.guild.id)
        member_id_str = str(member.id)
        
        user_warnings = self.warnings.get(guild_id_str, {}).get(member_id_str, [])
        
        if not user_warnings:
            await ctx.send(embed=self._create_embed(description=f"✅ **{member.display_name}** tidak memiliki riwayat peringatan.", color=self.color_success))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !warnings: {member.display_name} tidak punya riwayat peringatan.")
            return

        embed = self._create_embed(title=f"Riwayat Peringatan untuk {member.display_name}", color=self.color_info)
        embed.set_thumbnail(url=member.display_avatar.url)

        for idx, warn_data in enumerate(user_warnings, 1):
            moderator = await self.bot.fetch_user(warn_data.get('moderator_id', 0))
            timestamp = warn_data.get('timestamp', 0)
            reason = warn_data.get('reason', 'N/A')
            field_value = f"**Alasan:** {reason}\n**Moderator:** {moderator.mention if moderator else 'Tidak diketahui'}\n**Tanggal:** <t:{timestamp}:F>"
            embed.add_field(name=f"Peringatan #{idx}", value=field_value, inline=False)
            print(f"[{datetime.now()}] [DEBUG ADMIN] !warnings: Menambahkan peringatan #{idx}.")
            
        await ctx.send(embed=embed)
        print(f"[{datetime.now()}] [DEBUG ADMIN] !warnings: Riwayat peringatan dikirim.")

    @commands.command(name="timeout", aliases=["mute"])
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx, member: discord.Member, duration: str, *, reason: Optional[str] = "Tidak ada alasan."):
        print(f"[{datetime.now()}] [DEBUG ADMIN] Command !timeout dipanggil oleh {ctx.author.display_name} untuk {member.display_name} selama {duration}.")
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa memberikan timeout pada anggota dengan role setara atau lebih tinggi.", color=self.color_error)); return
        if member.id == ctx.guild.owner.id:
            await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa memberikan timeout pada pemilik server.", color=self.color_error)); return
        if member.id == self.bot.user.id:
            await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa memberikan timeout pada bot ini sendiri.", color=self.color_error)); return

        delta = parse_duration(duration)
        if not delta: await ctx.send(embed=self._create_embed(description="❌ Format durasi tidak valid. Gunakan `s` (detik), `m` (menit), `h` (jam), `d` (hari). Contoh: `10m`.", color=self.color_error)); return
        if delta.total_seconds() > 2419200:
            await ctx.send(embed=self._create_embed(description="❌ Durasi timeout tidak bisa lebih dari 28 hari.", color=self.color_error)); return

        try:
            await member.timeout(delta, reason=reason)
            await ctx.send(embed=self._create_embed(description=f"✅ **{member.display_name}** telah diberi timeout selama `{duration}`.", color=self.color_success))
            await self.log_action(ctx.guild, "🤫 Member Timeout", {"Member": f"{member} ({member.id})", "Durasi": duration, "Moderator": ctx.author.mention, "Alasan": reason}, self.color_warning)
            print(f"[{datetime.now()}] [DEBUG ADMIN] {member.display_name} berhasil di-timeout.")
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin yang cukup untuk memberikan timeout pada anggota ini. Pastikan role bot lebih tinggi.", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !timeout: Bot Forbidden.")
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat memberikan timeout: {e}", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !timeout: ERROR: {e}.", file=sys.stderr)


    @commands.command(name="removetimeout", aliases=["unmute"])
    @commands.has_permissions(moderate_members=True)
    async def remove_timeout(self, ctx, member: discord.Member):
        print(f"[{datetime.now()}] [DEBUG ADMIN] Command !removetimeout dipanggil oleh {ctx.author.display_name} untuk {member.display_name}.")
        if member.id == ctx.guild.owner.id: await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa menghapus timeout pemilik server.", color=self.color_error)); return
        if member.id == self.bot.user.id: await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa menghapus timeout bot ini sendiri.", color=self.color_error)); return

        if not member.is_timed_out():
            await ctx.send(embed=self._create_embed(description=f"❌ {member.display_name} tidak sedang dalam timeout.", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !removetimeout: {member.display_name} tidak dalam timeout.")
            return

        try:
            await member.timeout(None, reason=f"Timeout dihapus oleh {ctx.author}")
            await ctx.send(embed=self._create_embed(description=f"✅ Timeout untuk **{member.display_name}** telah dihapus.", color=self.color_success))
            await self.log_action(ctx.guild, "😊 Timeout Dihapus", {"Member": f"{member} ({member.id})", "Moderator": ctx.author.mention}, self.color_success)
            print(f"[{datetime.now()}] [DEBUG ADMIN] Timeout {member.display_name} berhasil dihapus.")
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin yang cukup untuk menghapus timeout anggota ini. Pastikan role bot lebih tinggi.", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !removetimeout: Bot Forbidden.")
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat menghapus timeout: {e}", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !removetimeout: ERROR: {e}.", file=sys.stderr)

        
    @commands.command(name="clear", aliases=["purge"])
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int):
        print(f"[{datetime.now()}] [DEBUG ADMIN] Command !clear dipanggil oleh {ctx.author.display_name} untuk {amount} pesan.")
        if amount <= 0: await ctx.send(embed=self._create_embed(description="❌ Jumlah harus lebih dari 0.", color=self.color_error)); return
        if amount > 100: await ctx.send(embed=self._create_embed(description="❌ Anda hanya bisa menghapus maksimal 100 pesan sekaligus.", color=self.color_error)); return

        try:
            deleted = await ctx.channel.purge(limit=amount + 1)
            embed = self._create_embed(description=f"🗑️ Berhasil menghapus **{len(deleted) - 1}** pesan.", color=self.color_success)
            await ctx.send(embed=embed, delete_after=5)
            await self.log_action(ctx.guild, "🗑️ Pesan Dihapus", {"Channel": ctx.channel.mention, "Jumlah": f"{len(deleted) - 1} pesan", "Moderator": ctx.author.mention}, self.color_info)
            print(f"[{datetime.now()}] [DEBUG ADMIN] {len(deleted) - 1} pesan berhasil dihapus.")
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin `Manage Messages` untuk menghapus pesan.", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !clear: Bot Forbidden.")
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat menghapus pesan: {e}", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !clear: ERROR: {e}.", file=sys.stderr)
        
    @commands.command(name="slowmode")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int):
        print(f"[{datetime.now()}] [DEBUG ADMIN] Command !slowmode dipanggil oleh {ctx.author.display_name} untuk {seconds} detik.")
        if seconds < 0: await ctx.send(embed=self._create_embed(description="❌ Durasi slowmode tidak bisa negatif.", color=self.color_error)); return
        if seconds > 21600: await ctx.send(embed=self._create_embed(description="❌ Durasi slowmode tidak bisa lebih dari 6 jam (21600 detik).", color=self.color_error)); return

        try:
            await ctx.channel.edit(slowmode_delay=seconds)
            status = f"diatur ke `{seconds}` detik" if seconds > 0 else "dinonaktifkan"
            await ctx.send(embed=self._create_embed(description=f"✅ Mode lambat di channel ini telah {status}.", color=self.color_success))
            await self.log_action(ctx.guild, "⏳ Slowmode Diubah", {"Channel": ctx.channel.mention, "Durasi": f"{seconds} detik", "Moderator": ctx.author.mention}, self.color_info)
            print(f"[{datetime.now()}] [DEBUG ADMIN] Slowmode di channel {ctx.channel.name} diatur ke {seconds} detik.")
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin `Manage Channels` untuk mengatur slowmode.", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !slowmode: Bot Forbidden.")
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat mengatur slowmode: {e}", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !slowmode: ERROR: {e}.", file=sys.stderr)


    @commands.command(name="lock")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx, channel: Optional[discord.TextChannel] = None):
        print(f"[{datetime.now()}] [DEBUG ADMIN] Command !lock dipanggil oleh {ctx.author.display_name} untuk channel: {channel.name if channel else ctx.channel.name}.")
        target_channel = channel or ctx.channel
        current_perms = target_channel.permissions_for(ctx.guild.default_role)
        if not current_perms.send_messages is False:
            try:
                await target_channel.set_permissions(ctx.guild.default_role, send_messages=False)
                await ctx.send(embed=self._create_embed(description=f"🔒 Channel {target_channel.mention} telah dikunci.", color=self.color_success))
                await self.log_action(ctx.guild, "🔒 Channel Dikunci", {"Channel": target_channel.mention, "Moderator": ctx.author.mention}, self.color_warning)
                print(f"[{datetime.now()}] [DEBUG ADMIN] Channel {target_channel.name} berhasil dikunci.")
            except discord.Forbidden:
                await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin `Manage Channels` untuk mengunci channel.", color=self.color_error))
                print(f"[{datetime.now()}] [DEBUG ADMIN] !lock: Bot Forbidden.")
            except Exception as e:
                await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat mengunci channel: {e}", color=self.color_error))
                print(f"[{datetime.now()}] [DEBUG ADMIN] !lock: ERROR: {e}.", file=sys.stderr)
        else:
            await ctx.send(embed=self._create_embed(description=f"❌ Channel {target_channel.mention} sudah terkunci.", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !lock: Channel {target_channel.name} sudah terkunci.")


    @commands.command(name="unlock")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx, channel: Optional[discord.TextChannel] = None):
        print(f"[{datetime.now()}] [DEBUG ADMIN] Command !unlock dipanggil oleh {ctx.author.display_name} untuk channel: {channel.name if channel else ctx.channel.name}.")
        target_channel = channel or ctx.channel
        current_perms = target_channel.permissions_for(ctx.guild.default_role)
        if not current_perms.send_messages is True:
            try:
                await target_channel.set_permissions(ctx.guild.default_role, send_messages=None)
                await ctx.send(embed=self._create_embed(description=f"🔓 Kunci channel {target_channel.mention} telah dibuka.", color=self.color_success))
                await self.log_action(ctx.guild, "🔓 Kunci Dibuka", {"Channel": target_channel.mention, "Moderator": ctx.author.mention}, self.color_success)
                print(f"[{datetime.now()}] [DEBUG ADMIN] Channel {target_channel.name} berhasil dibuka kuncinya.")
            except discord.Forbidden:
                await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin `Manage Channels` untuk membuka kunci channel.", color=self.color_error))
                print(f"[{datetime.now()}] [DEBUG ADMIN] !unlock: Bot Forbidden.")
            except Exception as e:
                await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat membuka kunci channel: {e}", color=self.color_error))
                print(f"[{datetime.now()}] [DEBUG ADMIN] !unlock: ERROR: {e}.", file=sys.stderr)
        else:
            await ctx.send(embed=self._create_embed(description=f"❌ Channel {target_channel.mention} sudah tidak terkunci.", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !unlock: Channel {target_channel.name} sudah tidak terkunci.")


    @commands.command(name="addrole")
    @commands.has_permissions(manage_roles=True)
    async def add_role(self, ctx, member: discord.Member, role: discord.Role):
        print(f"[{datetime.now()}] [DEBUG ADMIN] Command !addrole dipanggil oleh {ctx.author.display_name} untuk {member.display_name} role {role.name}.")
        if ctx.author.top_role <= role:
            await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa memberikan role yang lebih tinggi atau setara dengan role Anda.", color=self.color_error))
            return
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengubah role anggota yang posisinya lebih tinggi atau setara.", color=self.color_error))
            return
        if role in member.roles:
            await ctx.send(embed=self._create_embed(description=f"❌ {member.display_name} sudah memiliki role {role.mention}.", color=self.color_error))
            return

        try:
            await member.add_roles(role, reason=f"Diberikan oleh {ctx.author}")
            await ctx.send(embed=self._create_embed(description=f"✅ Role {role.mention} telah diberikan kepada {member.mention}.", color=self.color_success))
            await self.log_action(ctx.guild, "➕ Role Diberikan", {"Member": member.mention, "Role": role.mention, "Moderator": ctx.author.mention}, self.color_info)
            print(f"[{datetime.now()}] [DEBUG ADMIN] Role {role.name} berhasil diberikan ke {member.display_name}.")
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin yang cukup untuk memberikan role ini. Pastikan role bot lebih tinggi dari role yang ingin diberikan.", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !addrole: Bot Forbidden.")
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat memberikan role: {e}", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !addrole: ERROR: {e}.", file=sys.stderr)


    @commands.command(name="removerole")
    @commands.has_permissions(manage_roles=True)
    async def remove_role(self, ctx, member: discord.Member, role: discord.Role):
        print(f"[{datetime.now()}] [DEBUG ADMIN] Command !removerole dipanggil oleh {ctx.author.display_name} untuk {member.display_name} role {role.name}.")
        if ctx.author.top_role <= role:
            await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa menghapus role yang lebih tinggi atau setara dengan role Anda.", color=self.color_error))
            return
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengubah role anggota yang posisinya lebih tinggi atau setara.", color=self.color_error))
            return
        if role not in member.roles:
            await ctx.send(embed=self._create_embed(description=f"❌ {member.display_name} tidak memiliki role {role.mention}.", color=self.color_error))
            return
            
        try:
            await member.remove_roles(role, reason=f"Dihapus oleh {ctx.author}")
            await ctx.send(embed=self._create_embed(description=f"✅ Role {role.mention} telah dihapus dari {member.mention}.", color=self.color_success))
            await self.log_action(ctx.guild, "➖ Role Dihapus", {"Member": member.mention, "Role": role.mention, "Moderator": ctx.author.mention}, self.color_info)
            print(f"[{datetime.now()}] [DEBUG ADMIN] Role {role.name} berhasil dihapus dari {member.display_name}.")
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin yang cukup untuk menghapus role ini. Pastikan role bot lebih tinggi dari role yang ingin dihapus.", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !removerole: Bot Forbidden.")
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat menghapus role: {e}", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !removerole: ERROR: {e}.", file=sys.stderr)


    @commands.command(name="nick")
    @commands.has_permissions(manage_nicknames=True)
    async def nick(self, ctx, member: discord.Member, *, new_nickname: Optional[str] = None):
        print(f"[{datetime.now()}] [DEBUG ADMIN] Command !nick dipanggil oleh {ctx.author.display_name} untuk {member.display_name} dengan nickname baru: '{new_nickname}'.")
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengubah nickname anggota dengan role lebih tinggi atau setara.", color=self.color_error))
            return
        if member.id == ctx.guild.owner.id:
            await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengubah nickname pemilik server.", color=self.color_error)); return
        if member.id == self.bot.user.id:
            await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengubah nickname bot ini sendiri.", color=self.color_error)); return

        old_nickname = member.display_name
        try:
            await member.edit(nick=new_nickname, reason=f"Diubah oleh {ctx.author}")
            if new_nickname:
                await ctx.send(embed=self._create_embed(description=f"✅ Nickname **{old_nickname}** telah diubah menjadi **{new_nickname}**.", color=self.color_success))
                await self.log_action(ctx.guild, "👤 Nickname Diubah", {"Member": member.mention, "Dari": old_nickname, "Menjadi": new_nickname, "Moderator": ctx.author.mention}, self.color_info)
                print(f"[{datetime.now()}] [DEBUG ADMIN] Nickname {member.display_name} diubah ke {new_nickname}.")
            else:
                await ctx.send(embed=self._create_embed(description=f"✅ Nickname untuk **{old_nickname}** telah direset.", color=self.color_success))
                await self.log_action(ctx.guild, "👤 Nickname Direset", {"Member": member.mention, "Moderator": ctx.author.mention}, self.color_info)
                print(f"[{datetime.now()}] [DEBUG ADMIN] Nickname {member.display_name} direset.")
        except discord.Forbidden:
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin yang cukup untuk mengubah nickname ini. Pastikan role bot lebih tinggi dari anggota ini.", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !nick: Bot Forbidden.")
        except Exception as e:
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan saat mengubah nickname: {e}", color=self.color_error))
            print(f"[{datetime.now()}] [DEBUG ADMIN] !nick: ERROR: {e}.", file=sys.stderr)


    # =======================================================================================
    # CHANNEL RULES COMMANDS
    # =======================================================================================
    @commands.command(name="channelrules", aliases=["cr"])
    @commands.has_permissions(manage_channels=True)
    async def channel_rules(self, ctx, channel: Optional[discord.TextChannel] = None):
        print(f"[{datetime.now()}] [DEBUG ADMIN] Command !channelrules dipanggil oleh {ctx.author.display_name} untuk channel: {channel.name if channel else ctx.channel.name}.")
        target_channel = channel or ctx.channel
        class ChannelRuleView(discord.ui.View):
            def __init__(self, cog_instance, author, target_channel):
                super().__init__(timeout=300)
                self.cog, self.author, self.target_channel = cog_instance, author, target_channel
                self.guild_id, self.channel_id = target_channel.guild.id, target_channel.id
                self.message = None
                self.update_buttons()
                print(f"[{datetime.now()}] [DEBUG ADMIN] ChannelRuleView diinisialisasi untuk {target_channel.name}.")

            def update_buttons(self):
                print(f"[{datetime.now()}] [DEBUG ADMIN] ChannelRuleView: update_buttons dipanggil.")
                rules = self.cog.get_channel_rules(self.guild_id, self.channel_id)
                def set_button_state(button, label_text, is_active):
                    button.label = f"{label_text}: {'Aktif' if is_active else 'Nonaktif'}"
                    button.style = discord.ButtonStyle.green if is_active else discord.ButtonStyle.red
                
                self.clear_items()
                
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
                print(f"[{datetime.now()}] [DEBUG ADMIN] ChannelRuleView: Tombol diupdate.")

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                print(f"[{datetime.now()}] [DEBUG ADMIN] ChannelRuleView: interaction_check dipicu oleh {interaction.user.display_name}.")
                if interaction.user != self.author:
                    await interaction.response.send_message("Hanya pengguna yang memulai perintah yang dapat berinteraksi.", ephemeral=True)
                    print(f"[{datetime.now()}] [DEBUG ADMIN] ChannelRuleView: Pengguna bukan pemanggil asli.")
                    return False
                if not interaction.user.guild_permissions.manage_channels:
                    await interaction.response.send_message("Anda tidak memiliki izin `Manage Channels` untuk mengubah aturan ini.", ephemeral=True)
                    print(f"[{datetime.now()}] [DEBUG ADMIN] ChannelRuleView: Pengguna tidak memiliki izin.")
                    return False
                print(f"[{datetime.now()}] [DEBUG ADMIN] ChannelRuleView: Check interaksi lolos.")
                return True

            async def toggle_rule(self, interaction: discord.Interaction, rule_name: str):
                print(f"[{datetime.now()}] [DEBUG ADMIN] ChannelRuleView: toggle_rule '{rule_name}' diklik oleh {interaction.user.display_name}.")
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
                print(f"[{datetime.now()}] [DEBUG ADMIN] ChannelRuleView: Aturan '{rule_name}' diubah ke {rules[rule_name]}.")

            async def set_auto_delete(self, interaction: discord.Interaction):
                print(f"[{datetime.now()}] [DEBUG ADMIN] ChannelRuleView: set_auto_delete diklik oleh {interaction.user.display_name}.")
                class AutoDeleteModal(discord.ui.Modal, title="Atur Hapus Otomatis"):
                    def __init__(self, current_delay, parent_view_instance):
                        super().__init__()
                        self.cog = parent_view_instance.cog
                        self.guild_id = parent_view_instance.guild_id
                        self.channel_id = parent_view_instance.channel_id
                        self.parent_view = parent_view_instance

                        self.delay_input = discord.ui.TextInput(
                            label="Durasi (detik, 0 untuk nonaktif)",
                            placeholder="Contoh: 30 (maks 3600)",
                            default=str(current_delay),
                            max_length=4
                        )
                        self.add_item(self.delay_input)
                        print(f"[{datetime.now()}] [DEBUG ADMIN] AutoDeleteModal diinisialisasi (current_delay: {current_delay}).")

                    async def on_submit(self, modal_interaction: discord.Interaction):
                        print(f"[{datetime.now()}] [DEBUG ADMIN] AutoDeleteModal: on_submit dipanggil oleh {modal_interaction.user.display_name}.")
                        await modal_interaction.response.defer(ephemeral=True)
                        try:
                            delay = int(self.delay_input.value)
                            if not (0 <= delay <= 3600):
                                print(f"[{datetime.now()}] [DEBUG ADMIN] AutoDeleteModal: Durasi tidak valid ({delay}).")
                                await modal_interaction.followup.send(embed=self.cog._create_embed(description="❌ Durasi harus antara 0 dan 3600 detik (1 jam).", color=self.cog.color_error), ephemeral=True)
                                return
                            
                            rules = self.cog.get_channel_rules(self.guild_id, self.channel_id)
                            rules["auto_delete_seconds"] = delay
                            self.cog.save_settings()
                            print(f"[{datetime.now()}] [DEBUG ADMIN] AutoDeleteModal: Durasi auto delete diatur ke {delay}s.")
                            
                            self.parent_view.update_buttons()
                            await modal_interaction.message.edit(view=self.parent_view) # Edit the original message of the modal trigger
                            
                            await self.cog.log_action(
                                self.parent_view.target_channel.guild,
                                "⏳ Hapus Otomatis Diubah",
                                {"Channel": self.parent_view.target_channel.mention, "Durasi": f"{delay} detik" if delay > 0 else "Dinonaktifkan", "Moderator": modal_interaction.user.mention},
                                self.cog.color_info
                            )
                        except ValueError:
                            print(f"[{datetime.now()}] [DEBUG ADMIN] AutoDeleteModal: Input durasi bukan angka.")
                            await modal_interaction.followup.send(embed=self.cog._create_embed(description="❌ Durasi harus berupa angka.", color=self.cog.color_error), ephemeral=True)
                        except Exception as e:
                            print(f"[{datetime.now()}] [DEBUG ADMIN] AutoDeleteModal: ERROR di on_submit: {e}.", file=sys.stderr)
                            await modal_interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan: {e}", color=self.cog.color_error), ephemeral=True)
                
                rules = self.cog.get_channel_rules(self.guild_id, self.channel_id)
                current_delay = rules.get("auto_delete_seconds", 0)
                await interaction.response.send_modal(AutoDeleteModal(current_delay, self))
                print(f"[{datetime.now()}] [DEBUG ADMIN] ChannelRuleView: Modal AutoDeleteModal dikirim.")

        embed = self._create_embed(title=f"🔧 Aturan untuk Channel: #{target_channel.name}", description="Tekan tombol untuk mengaktifkan (hijau) atau menonaktifkan (merah) aturan untuk channel ini. Tekan tombol hapus otomatis untuk mengatur durasi (default 30s).", color=self.color_info)
        initial_msg = await ctx.send(embed=embed, view=ChannelRuleView(self, ctx.author, target_channel))
        # Store the message for later edits by the view
        ChannelRuleView(self, ctx.author, target_channel).message = initial_msg # This line needs to be careful. Better to pass the message object to the view's init or make it a method.
        # Let's adjust this to properly pass the message object
        view_instance = ChannelRuleView(self, ctx.author, target_channel)
        view_instance.message = await ctx.send(embed=embed, view=view_instance)
        print(f"[{datetime.now()}] [DEBUG ADMIN] !channelrules: Pesan ChannelRuleView dikirim.")
        
    # =======================================================================================
    # SETUP COMMANDS
    # =======================================================================================

    @commands.command(name="setwelcomechannel")
    @commands.has_permissions(manage_guild=True)
    async def set_welcome_channel(self, ctx, channel: discord.TextChannel):
        print(f"[{datetime.now()}] [DEBUG ADMIN] Command !setwelcomechannel dipanggil oleh {ctx.author.display_name} untuk channel: {channel.name}.")
        """Mengatur channel untuk pesan selamat datang."""
        guild_settings = self.get_guild_settings(ctx.guild.id)
        guild_settings["welcome_channel_id"] = channel.id
        self.save_settings()
        embed = self._create_embed(
            description=f"✅ Channel selamat datang telah berhasil diatur ke {channel.mention}.",
            color=self.color_success
        )
        await ctx.send(embed=embed)
        print(f"[{datetime.now()}] [DEBUG ADMIN] Welcome channel diatur ke {channel.name}.")

    @commands.command(name="setreactionrole")
    @commands.has_permissions(manage_roles=True)
    async def set_reaction_role(self, ctx, message: discord.Message, emoji: str, role: discord.Role):
        print(f"[{datetime.now()}] [DEBUG ADMIN] Command !setreactionrole dipanggil oleh {ctx.author.display_name} untuk pesan {message.id}, emoji {emoji}, role {role.name}.")
        if ctx.author.top_role <= role:
            print(f"[{datetime.now()}] [DEBUG ADMIN] !setreactionrole: Pemanggil tidak punya izin (role terlalu rendah).")
            return await ctx.send(embed=self._create_embed(description="❌ Anda tidak bisa mengatur reaction role untuk role yang lebih tinggi atau setara dengan role Anda.", color=self.color_error))
        
        guild_settings = self.get_guild_settings(ctx.guild.id)
        message_id_str = str(message.id)
        if message_id_str not in guild_settings["reaction_roles"]: guild_settings["reaction_roles"][message_id_str] = {}
        guild_settings["reaction_roles"][message_id_str][emoji] = role.id
        self.save_settings()
        print(f"[{datetime.now()}] [DEBUG ADMIN] Pengaturan reaction role disimpan.")
        try:
            await message.add_reaction(emoji)
            await ctx.send(embed=self._create_embed(description=f"✅ Role **{role.mention}** akan diberikan untuk reaksi {emoji} pada [pesan itu]({message.jump_url}).", color=self.color_success))
            print(f"[{datetime.now()}] [DEBUG ADMIN] Reaction {emoji} ditambahkan ke pesan {message.id}.")
        except discord.Forbidden:
            print(f"[{datetime.now()}] [DEBUG ADMIN] !setreactionrole: Bot Forbidden menambahkan reaksi atau mengatur role.", file=sys.stderr)
            await ctx.send(embed=self._create_embed(description="❌ Bot tidak memiliki izin untuk menambahkan reaksi atau mengatur role. Pastikan izinnya lengkap.", color=self.color_error))
        except Exception as e:
            print(f"[{datetime.now()}] [DEBUG ADMIN] !setreactionrole: ERROR: {e}.", file=sys.stderr)
            await ctx.send(embed=self._create_embed(description=f"❌ Terjadi kesalahan: {e}", color=self.color_error))


    @commands.command(name="setup")
    @commands.has_permissions(manage_guild=True)
    async def setup(self, ctx):
        print(f"[{datetime.now()}] [DEBUG ADMIN] Command !setup dipanggil oleh {ctx.author.display_name}.")
        class SetupView(discord.ui.View):
            def __init__(self, cog_instance, author, ctx): # Added ctx to init
                super().__init__(timeout=300)
                self.cog = cog_instance
                self.guild_id = ctx.guild.id
                self.author = author
                self.ctx = ctx # Store ctx
                print(f"[{datetime.now()}] [DEBUG ADMIN] SetupView diinisialisasi.")

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                print(f"[{datetime.now()}] [DEBUG ADMIN] SetupView: interaction_check dipicu oleh {interaction.user.display_name}.")
                if interaction.user != self.author:
                    await interaction.response.send_message("Hanya pengguna yang memulai setup yang dapat berinteraksi.", ephemeral=True)
                    print(f"[{datetime.now()}] [DEBUG ADMIN] SetupView: Pengguna bukan pemanggil asli.")
                    return False
                if not interaction.user.guild_permissions.manage_guild:
                    await interaction.response.send_message("Anda tidak memiliki izin `Manage Server` untuk menggunakan setup ini.", ephemeral=True)
                    print(f"[{datetime.now()}] [DEBUG ADMIN] SetupView: Pengguna tidak memiliki izin.")
                    return False
                print(f"[{datetime.now()}] [DEBUG ADMIN] SetupView: Check interaksi lolos.")
                return True

            async def handle_response(self, interaction, prompt, callback):
                print(f"[{datetime.now()}] [DEBUG ADMIN] SetupView: handle_response dipanggil.")
                await interaction.response.send_message(embed=self.cog._create_embed(description=prompt, color=self.cog.color_info), ephemeral=True)
                try:
                    msg = await self.cog.bot.wait_for('message', check=lambda m: m.author == self.author and m.channel == interaction.channel, timeout=120)
                    await callback(msg, interaction)
                    print(f"[{datetime.now()}] [DEBUG ADMIN] SetupView: Respons untuk handle_response diterima.")
                except asyncio.TimeoutError:
                    await interaction.followup.send(embed=self.cog._create_embed(description="❌ Waktu habis.", color=self.cog.color_error), ephemeral=True)
                    print(f"[{datetime.now()}] [DEBUG ADMIN] SetupView: handle_response waktu habis.")
                except Exception as e:
                    await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan: {e}", color=self.cog.color_error), ephemeral=True)
                    print(f"[{datetime.now()}] [DEBUG ADMIN] SetupView: handle_response ERROR: {e}.", file=sys.stderr)

            @discord.ui.button(label="Auto Role", style=discord.ButtonStyle.primary, emoji="👤", row=0)
            async def set_auto_role(self, interaction: discord.Interaction, button: discord.ui.Button):
                print(f"[{datetime.now()}] [DEBUG ADMIN] SetupView: Tombol Auto Role diklik.")
                async def callback(msg, inter):
                    role = msg.role_mentions[0] if msg.role_mentions else self.ctx.guild.get_role(int(msg.content)) if msg.content.isdigit() else None
                    if role:
                        self.cog.get_guild_settings(self.guild_id)['auto_role_id'] = role.id; self.cog.save_settings()
                        await inter.followup.send(embed=self.cog._create_embed(description=f"✅ Auto Role diatur ke **{role.mention}**.", color=self.cog.color_success), ephemeral=True)
                        print(f"[{datetime.now()}] [DEBUG ADMIN] SetupView: Auto Role diatur ke {role.name}.")
                    else:
                        await inter.followup.send(embed=self.cog._create_embed(description="❌ Role tidak ditemukan.", color=self.cog.color_error), ephemeral=True)
                        print(f"[{datetime.now()}] [DEBUG ADMIN] SetupView: Role tidak ditemukan untuk Auto Role.")
                await self.handle_response(interaction, "Sebutkan (mention) atau masukkan ID role untuk pengguna baru:", callback)

            @discord.ui.button(label="Welcome Msg", style=discord.ButtonStyle.primary, emoji="💬", row=0)
            async def set_welcome_message(self, interaction: discord.Interaction, button: discord.ui.Button):
                print(f"[{datetime.now()}] [DEBUG ADMIN] SetupView: Tombol Welcome Msg diklik.")
                async def callback(msg, inter):
                    self.cog.get_guild_settings(self.guild_id)['welcome_message'] = msg.content; self.cog.save_settings()
                    await inter.followup.send(embed=self.cog._create_embed(description="✅ Pesan selamat datang berhasil diatur.", color=self.cog.color_success), ephemeral=True)
                    print(f"[{datetime.now()}] [DEBUG ADMIN] SetupView: Pesan selamat datang diatur.")
                await self.handle_response(interaction, "Ketik pesan selamat datangmu. Gunakan `{user}` dan `{guild_name}`.", callback)

            @discord.ui.button(label="Log Channel", style=discord.ButtonStyle.primary, emoji="📝", row=0)
            async def set_log_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
                print(f"[{datetime.now()}] [DEBUG ADMIN] SetupView: Tombol Log Channel diklik.")
                async def callback(msg, inter):
                    channel = msg.channel_mentions[0] if msg.channel_mentions else self.ctx.guild.get_channel(int(msg.content)) if msg.content.isdigit() else None
                    if channel and isinstance(channel, discord.TextChannel):
                        self.cog.get_guild_settings(self.guild_id)['log_channel_id'] = channel.id; self.cog.save_settings()
                        await inter.followup.send(embed=self.cog._create_embed(description=f"✅ Log Channel diatur ke **{channel.mention}**.", color=self.cog.color_success), ephemeral=True)
                        print(f"[{datetime.now()}] [DEBUG ADMIN] SetupView: Log Channel diatur ke {channel.name}.")
                    else:
                        await inter.followup.send(embed=self.cog._create_embed(description="❌ Channel tidak ditemukan atau bukan channel teks.", color=self.cog.color_error), ephemeral=True)
                        print(f"[{datetime.now()}] [DEBUG ADMIN] SetupView: Channel tidak ditemukan untuk Log Channel.")
                await self.handle_response(interaction, "Sebutkan (mention) atau masukkan ID channel untuk log aktivitas bot:", callback)

            @discord.ui.button(label="Kelola Filter", style=discord.ButtonStyle.secondary, emoji="🛡️", row=1)
            async def manage_filters(self, interaction: discord.Interaction, button: discord.ui.Button):
                print(f"[{datetime.now()}] [DEBUG ADMIN] SetupView: Tombol Kelola Filter diklik.")
                await interaction.response.send_message(view=FilterManageView(self.cog, self.author), ephemeral=True)

            @discord.ui.button(label="Lihat Konfigurasi", style=discord.ButtonStyle.secondary, emoji="📋", row=1)
            async def view_config(self, interaction: discord.Interaction, button: discord.ui.Button):
                print(f"[{datetime.now()}] [DEBUG ADMIN] SetupView: Tombol Lihat Konfigurasi diklik.")
                settings = self.cog.get_guild_settings(self.guild_id); filters = self.cog.get_guild_filters(self.guild_id)
                auto_role = self.ctx.guild.get_role(settings.get('auto_role_id')) if settings.get('auto_role_id') else "Tidak diatur"
                welcome_ch = self.ctx.guild.get_channel(settings.get('welcome_channel_id')) if settings.get('welcome_channel_id') else "Tidak diatur"
                log_ch = self.ctx.guild.get_channel(settings.get('log_channel_id')) if settings.get('log_channel_id') else "Tidak diatur"
                embed = self.cog._create_embed(title=f"Konfigurasi untuk {self.ctx.guild.name}", color=self.cog.color_info)
                embed.add_field(name="Pengaturan Dasar", value=f"**Auto Role**: {auto_role.mention if isinstance(auto_role, discord.Role) else auto_role}\n**Welcome Channel**: {welcome_ch.mention if isinstance(welcome_ch, discord.TextChannel) else welcome_ch}\n**Log Channel**: {log_ch.mention if isinstance(log_ch, discord.TextChannel) else log_ch}", inline=False)
                embed.add_field(name="Pesan Selamat Datang", value=f"```{settings.get('welcome_message')}```", inline=False)
                embed.add_field(name="Filter Kata Kasar", value=f"Total: {len(filters.get('bad_words',[]))} kata", inline=True)
                embed.add_field(name="Filter Link", value=f"Total: {len(filters.get('link_patterns',[]))} pola", inline=True)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                print(f"[{datetime.now()}] [DEBUG ADMIN] SetupView: Konfigurasi dilihat.")

        class AddFilterModal(discord.ui.Modal, title="Tambah Filter"):
            def __init__(self, cog_instance, filter_type):
                super().__init__(); self.cog = cog_instance; self.filter_type = filter_type
                self.item_to_add = discord.ui.TextInput(label=f"Masukkan {('kata' if filter_type == 'bad_words' else 'pola regex')} untuk ditambahkan", style=discord.TextStyle.paragraph)
                self.add_item(self.item_to_add)
                print(f"[{datetime.now()}] [DEBUG ADMIN] AddFilterModal diinisialisasi (tipe: {filter_type}).")
            async def on_submit(self, interaction: discord.Interaction):
                print(f"[{datetime.now()}] [DEBUG ADMIN] AddFilterModal: on_submit dipanggil oleh {interaction.user.display_name}.")
                filters = self.cog.get_guild_filters(interaction.guild_id); item = self.item_to_add.value.lower().strip()
                if item in filters[self.filter_type]:
                    await interaction.response.send_message(embed=self.cog._create_embed(description=f"❌ `{item}` sudah ada di filter.", color=self.cog.color_error), ephemeral=True)
                    print(f"[{datetime.now()}] [DEBUG ADMIN] AddFilterModal: Item sudah ada.")
                else:
                    filters[self.filter_type].append(item); self.cog.save_filters()
                    await interaction.response.send_message(embed=self.cog._create_embed(description=f"✅ `{item}` berhasil ditambahkan ke filter.", color=self.cog.color_success), ephemeral=True)
                    print(f"[{datetime.now()}] [DEBUG ADMIN] AddFilterModal: Item '{item}' ditambahkan.")

        class RemoveFilterModal(discord.ui.Modal, title="Hapus Filter"):
            def __init__(self, cog_instance, filter_type):
                super().__init__(); self.cog = cog_instance; self.filter_type = filter_type
                self.item_to_remove = discord.ui.TextInput(label=f"Masukkan {('kata' if filter_type == 'bad_words' else 'pola')} yang akan dihapus")
                self.add_item(self.item_to_remove)
                print(f"[{datetime.now()}] [DEBUG ADMIN] RemoveFilterModal diinisialisasi (tipe: {filter_type}).")
            async def on_submit(self, interaction: discord.Interaction):
                print(f"[{datetime.now()}] [DEBUG ADMIN] RemoveFilterModal: on_submit dipanggil oleh {interaction.user.display_name}.")
                filters = self.cog.get_guild_filters(interaction.guild_id); item = self.item_to_remove.value.lower().strip()
                if item in filters[self.filter_type]:
                    filters[self.filter_type].remove(item); self.cog.save_filters()
                    await interaction.response.send_message(embed=self.cog._create_embed(description=f"✅ `{item}` berhasil dihapus dari filter.", color=self.cog.color_success), ephemeral=True)
                    print(f"[{datetime.now()}] [DEBUG ADMIN] RemoveFilterModal: Item '{item}' dihapus.")
                else:
                    await interaction.response.send_message(embed=self.cog._create_embed(description=f"❌ `{item}` tidak ditemukan di filter.", color=self.cog.color_error), ephemeral=True)
                    print(f"[{datetime.now()}] [DEBUG ADMIN] RemoveFilterModal: Item tidak ditemukan.")

        class FilterManageView(discord.ui.View):
            def __init__(self, cog_instance, author):
                super().__init__(timeout=180); self.cog = cog_instance; self.author = author
                print(f"[{datetime.now()}] [DEBUG ADMIN] FilterManageView diinisialisasi.")
            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                print(f"[{datetime.now()}] [DEBUG ADMIN] FilterManageView: interaction_check dipicu oleh {interaction.user.display_name}.")
                return interaction.user == self.author
            @discord.ui.button(label="Tambah Kata Kasar", style=discord.ButtonStyle.primary, emoji="🤬")
            async def add_bad_word(self, interaction: discord.Interaction, button: discord.ui.Button):
                print(f"[{datetime.now()}] [DEBUG ADMIN] FilterManageView: Tombol Tambah Kata Kasar diklik.")
                await interaction.response.send_modal(AddFilterModal(self.cog, "bad_words"))
            @discord.ui.button(label="Hapus Kata Kasar", style=discord.ButtonStyle.danger, emoji="🗑️")
            async def remove_bad_word(self, interaction: discord.Interaction, button: discord.ui.Button):
                print(f"[{datetime.now()}] [DEBUG ADMIN] FilterManageView: Tombol Hapus Kata Kasar diklik.")
                await interaction.response.send_modal(RemoveFilterModal(self.cog, "bad_words"))
            @discord.ui.button(label="Tambah Pola Link", style=discord.ButtonStyle.primary, emoji="🔗")
            async def add_link_pattern(self, interaction: discord.Interaction, button: discord.ui.Button):
                print(f"[{datetime.now()}] [DEBUG ADMIN] FilterManageView: Tombol Tambah Pola Link diklik.")
                await interaction.response.send_modal(AddFilterModal(self.cog, "link_patterns"))
            @discord.ui.button(label="Hapus Pola Link", style=discord.ButtonStyle.danger, emoji="🔗")
            async def remove_link_pattern(self, interaction: discord.Interaction, button: discord.ui.Button):
                print(f"[{datetime.now()}] [DEBUG ADMIN] FilterManageView: Tombol Hapus Pola Link diklik.")
                await interaction.response.send_modal(RemoveFilterModal(self.cog, "link_patterns"))
            @discord.ui.button(label="Lihat Semua Filter", style=discord.ButtonStyle.secondary, emoji="📋", row=2)
            async def view_filters(self, interaction: discord.Interaction, button: discord.ui.Button):
                print(f"[{datetime.now()}] [DEBUG ADMIN] FilterManageView: Tombol Lihat Semua Filter diklik.")
                filters = self.cog.get_guild_filters(interaction.guild_id); bad_words = ", ".join(f"`{w}`" for w in filters['bad_words']) or "Kosong"; link_patterns = ", ".join(f"`{p}`" for p in filters['link_patterns']) or "Kosong"
                embed = self.cog._create_embed(title="Daftar Filter Aktif", color=self.cog.color_info)
                embed.add_field(name="🚫 Kata Kasar", value=bad_words[:1024], inline=False); embed.add_field(name="🔗 Pola Link", value=link_patterns[:1024], inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                print(f"[{datetime.now()}] [DEBUG ADMIN] FilterManageView: Filter dilihat.")

        embed = self._create_embed(title="⚙️ Panel Kontrol Server", description="Gunakan tombol di bawah ini untuk mengatur bot. Anda memiliki 5 menit sebelum panel ini nonaktif.", color=self.color_info, author_name=ctx.guild.name, author_icon_url=ctx.guild.icon.url if ctx.guild.icon else "")
        view_instance = SetupView(self, ctx.author, ctx) # Pass ctx here
        await ctx.send(embed=embed, view=view_instance)
        print(f"[{datetime.now()}] [DEBUG ADMIN] !setup: Pesan SetupView dikirim.")


    # =======================================================================================
    # ANNOUNCEMENT FEATURE
    # =======================================================================================

    @commands.command(name="announce", aliases=["pengumuman", "broadcast"])
    @commands.has_permissions(manage_guild=True)
    async def announce(self, ctx, channel_identifier: str):
        """
        Membuat pengumuman kustom dengan form UI ke channel spesifik.
        Channel tujuan dimasukkan via command (mention atau ID).
        Detail lainnya (judul, profil kustom, gambar) diisi via modal.
        Deskripsi diambil dari URL GitHub Raw yang telah ditentukan.
        Format: !announce <#channel_mention_ATAU_channel_ID>
        Contoh: !announce #general
        Contoh: !announce 123456789012345678
        """
        print(f"[{datetime.now()}] [DEBUG ANNOUNCE] Command !announce dipanggil oleh {ctx.author.display_name} untuk channel: '{channel_identifier}'.")
        GITHUB_RAW_DESCRIPTION_URL = "https://raw.githubusercontent.com/Abogoboga04/OpenAI/main/announcement.txt" # Ganti 'main' jika branch Anda berbeda
        print(f"[{datetime.now()}] [DEBUG ANNOUNCE] !announce: Menggunakan GitHub Raw URL: {GITHUB_RAW_DESCRIPTION_URL}.")

        # --- Parsing Channel from Command Argument ---
        target_channel = None
        print(f"[{datetime.now()}] [DEBUG ANNOUNCE] Menganalisis channel_identifier: '{channel_identifier}'")

        if channel_identifier.startswith('<#') and channel_identifier.endswith('>'):
            try:
                channel_id = int(channel_identifier[2:-1])
                target_channel = ctx.guild.get_channel(channel_id)
                if not target_channel:
                    target_channel = self.bot.get_channel(channel_id)
                print(f"[{datetime.now()}] [DEBUG ANNOUNCE] Channel diidentifikasi via mention sebagai ID: {channel_id}, Result: {target_channel.name if target_channel else 'None'}.")
            except ValueError:
                print(f"[{datetime.now()}] [DEBUG ANNOUNCE] Gagal parsing mention channel. Mencoba ID mentah.")
                pass
        
        if not target_channel and channel_identifier.isdigit():
            try:
                channel_id = int(channel_identifier)
                target_channel = ctx.guild.get_channel(channel_id)
                if not target_channel:
                    target_channel = self.bot.get_channel(channel_id)
                print(f"[{datetime.now()}] [DEBUG ANNOUNCE] Channel diidentifikasi via ID: {channel_id}, Result: {target_channel.name if target_channel else 'None'}.")
            except ValueError:
                print(f"[{datetime.now()}] [DEBUG ANNOUNCE] Gagal parsing ID channel mentah.")
                pass

        if not target_channel or not isinstance(target_channel, discord.TextChannel):
            print(f"[{datetime.now()}] [DEBUG ANNOUNCE] Channel target '{channel_identifier}' tidak ditemukan atau bukan channel teks yang valid.")
            await ctx.send(embed=self._create_embed(
                description=f"❌ Channel '{channel_identifier}' tidak ditemukan atau bukan channel teks yang valid. Mohon gunakan mention channel (misal: `#general`) atau ID channel yang benar. Pastikan bot berada di server tersebut.",
                color=self.color_error
            ))
            return
        print(f"[{datetime.now()}] [DEBUG ANNOUNCE] Channel target valid: {target_channel.name} ({target_channel.id}).")
        
        # --- Announcement Modal Class (Definisi kelas di dalam fungsi announce untuk akses ke context) ---
        class AnnouncementModal(discord.ui.Modal, title=f"Buat Pengumuman untuk #{target_channel.name}"):
            announcement_title = discord.ui.TextInput(
                label="Judul Pengumuman (maks 256 karakter)",
                placeholder="Contoh: Pembaruan Server Penting!",
                max_length=256,
                required=True,
                row=0
            )
            custom_username = discord.ui.TextInput(
                label="Username Pengirim Kustom (maks 256 karakter)",
                placeholder="Contoh: Tim Admin / Pengumuman Resmi",
                max_length=256,
                required=True,
                row=1
            )
            custom_profile_url = discord.ui.TextInput(
                label="URL Avatar Pengirim Kustom (Opsional, http/https)",
                placeholder="Contoh: https://example.com/avatar.png",
                max_length=2000,
                required=False,
                row=2
            )
            announcement_image_url = discord.ui.TextInput(
                label="URL Gambar di Akhir Pengumuman (Opsional, http/https)",
                placeholder="Contoh: https://example.com/banner.png",
                max_length=2000,
                required=False,
                row=3
            )

            def __init__(self, cog_instance, original_ctx, target_channel_obj, github_raw_url):
                super().__init__()
                self.cog = cog_instance
                self.original_ctx = original_ctx
                self.target_channel_obj = target_channel_obj
                self.github_raw_url = github_raw_url
                print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModal diinisialisasi.")

            async def on_submit(self, interaction: discord.Interaction):
                print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModal: on_submit dipanggil oleh {interaction.user.display_name}.")
                await interaction.response.defer(ephemeral=True)

                title = self.announcement_title.value.strip()
                username = self.custom_username.value.strip()
                profile_url = self.custom_profile_url.value.strip()
                image_url = self.announcement_image_url.value.strip()

                print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModal: Input diterima - Judul: '{title}', User: '{username}'.")

                # --- Validasi Input ---
                if not username:
                    print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModal: Username kustom kosong.")
                    await interaction.followup.send(embed=self.cog._create_embed(description="❌ Username Pengirim Kustom tidak boleh kosong.", color=self.cog.color_error), ephemeral=True); return
                if profile_url and not (profile_url.startswith("http://") or profile_url.startswith("https://")):
                    print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModal: URL Avatar tidak valid: {profile_url}.")
                    await interaction.followup.send(embed=self.cog._create_embed(description="❌ URL Avatar Pengirim Kustom tidak valid. Harus dimulai dengan `http://` atau `https://`.", color=self.cog.color_error), ephemeral=True); return
                if image_url and not (image_url.startswith("http://") or image_url.startswith("https://")):
                    print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModal: URL Gambar tidak valid: {image_url}.")
                    await interaction.followup.send(embed=self.cog._create_embed(description="❌ URL Gambar Pengumuman tidak valid. Harus dimulai dengan `http://` atau `https://`.", color=self.cog.color_error), ephemeral=True); return
                
                print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModal: Input divalidasi. Mencoba ambil deskripsi dari {self.github_raw_url}.")

                # --- Fetch Description from GitHub Raw URL ---
                full_description = ""
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(self.github_raw_url) as resp:
                            print(f"[{datetime.now()}] [DEBUG ANNOUNCE] GitHub fetch Status: {resp.status}, Content-Type: {resp.headers.get('Content-Type')}.")
                            if resp.status == 200:
                                full_description = await resp.text()
                                print(f"[{datetime.now()}] [DEBUG ANNOUNCE] GitHub fetch: Deskripsi berhasil diambil ({len(full_description)} karakter). Awal deskripsi: '{full_description[:100]}...'")
                            else:
                                print(f"[{datetime.now()}] [DEBUG ANNOUNCE] GitHub fetch: Gagal (HTTP Status {resp.status}).")
                                await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Gagal mengambil deskripsi dari URL GitHub Raw ({self.github_raw_url}): Status HTTP {resp.status}. Pastikan URL valid dan publik.", color=self.cog.color_error), ephemeral=True); return
                except aiohttp.ClientError as e:
                    print(f"[{datetime.now()}] [ERROR ANNOUNCE] GitHub fetch: Kesalahan jaringan: {e}.", file=sys.stderr)
                    await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan jaringan saat mengambil deskripsi dari GitHub: {e}. Pastikan URL GitHub Raw benar.", color=self.cog.color_error), ephemeral=True); return
                except Exception as e:
                    print(f"[{datetime.now()}] [ERROR ANNOUNCE] GitHub fetch: Kesalahan tak terduga: {e}.", file=sys.stderr)
                    await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan tidak terduga saat mengambil deskripsi: {e}", color=self.cog.color_error), ephemeral=True); return

                if not full_description.strip():
                    print(f"[{datetime.now()}] [DEBUG ANNOUNCE] Deskripsi dari GitHub Raw kosong atau hanya spasi.")
                    await interaction.followup.send(embed=self.cog._create_embed(description="❌ Deskripsi pengumuman dari URL GitHub Raw kosong atau hanya berisi spasi. Pastikan file teks memiliki konten.", color=self.cog.color_error), ephemeral=True); return
                
                description_chunks = [full_description[i:i+4096] for i in range(0, len(full_description), 4096)]
                print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModal: Deskripsi dipecah menjadi {len(description_chunks)} bagian.")


                # --- Create and Send Embeds ---
                sent_first_embed = False
                for i, chunk in enumerate(description_chunks):
                    if not chunk.strip(): continue

                    embed = discord.Embed(
                        description=chunk,
                        color=self.cog.color_announce,
                        timestamp=datetime.utcnow() if i == 0 else discord.Embed.Empty
                    )
                    
                    if i == 0:
                        embed.title = title
                        embed.set_author(name=username, icon_url=profile_url if profile_url else discord.Embed.Empty)
                        if image_url: embed.set_image(url=image_url)
                        embed.set_footer(text=f"Pengumuman dari {self.original_ctx.guild.name}", icon_url=self.original_ctx.guild.icon.url if self.original_ctx.guild.icon else None)
                    else:
                        embed.set_footer(text=f"Lanjutan Pengumuman ({i+1}/{len(description_chunks)})")

                    try:
                        perms = self.target_channel_obj.permissions_for(self.target_channel_obj.guild.me)
                        if not perms.send_messages or not perms.embed_links:
                            if not sent_first_embed:
                                print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModal: Bot kekurangan izin kirim pesan/embed di {self.target_channel_obj.name}.")
                                await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Bot tidak memiliki izin untuk mengirim pesan atau menyematkan tautan di {self.target_channel_obj.mention}. Pastikan bot memiliki izin 'Kirim Pesan' dan 'Sematkan Tautan'.", color=self.cog.color_error), ephemeral=True)
                            return
                        
                        await self.target_channel_obj.send(embed=embed)
                        sent_first_embed = True
                        print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModal: Embed #{i+1} berhasil dikirim ke {self.target_channel_obj.name}.")
                    except discord.Forbidden:
                        print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModal: Bot Forbidden kirim pesan ke {self.target_channel_obj.name}.", file=sys.stderr)
                        if not sent_first_embed: await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Bot tidak memiliki izin untuk mengirim pesan di {self.target_channel_obj.mention}. Pastikan bot memiliki izin 'Send Messages' dan 'Embed Links'.", color=self.cog.color_error), ephemeral=True); return
                    except Exception as e:
                        print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModal: Error saat mengirim embed ke {self.target_channel_obj.name}: {e}.", file=sys.stderr)
                        if not sent_first_embed: await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan saat mengirim pengumuman: {e}", color=self.cog.color_error), ephemeral=True); return
                
                if sent_first_embed:
                    await interaction.followup.send(embed=self.cog._create_embed(description=f"✅ Pengumuman berhasil dikirim ke <#{self.target_channel_obj.id}>!", color=self.cog.color_success), ephemeral=True)
                    await self.cog.log_action(self.original_ctx.guild, "📢 Pengumuman Baru Dibuat", {"Pengirim (Eksekutor)": self.original_ctx.author.mention, "Pengirim (Tampilan)": f"{username} ({profile_url if profile_url else 'Default'})", "Channel Target": f"<#{self.target_channel_obj.id}>", "Judul": title, "Deskripsi Sumber": GITHUB_RAW_DESCRIPTION_URL, "Panjang Deskripsi": f"{len(full_description)} karakter"}, self.cog.color_announce)
                    print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModal: Konfirmasi dan log pengumuman selesai.")
                else:
                    print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModal: Tidak ada embed yang berhasil terkirim.")

            async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
                print(f"[{datetime.now()}] [ERROR ANNOUNCE] Error in AnnouncementModal (on_error): {error}", file=sys.stderr)
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan tak terduga saat memproses formulir: {error}", color=self.cog.color_error), ephemeral=True)
                else:
                    await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan tak terduga saat memproses formulir: {error}", color=self.cog.color_error), ephemeral=True)

        # Initial message with the button
        # Perbaikan untuk AnnounceButtonView: Simpan pesan awal agar bisa diedit saat timeout
        view_instance = AnnounceButtonView(self.bot, self, ctx, target_channel, GITHUB_RAW_DESCRIPTION_URL)
        initial_msg = await ctx.send(embed=self._create_embed(
            title="🔔 Siap Membuat Pengumuman?",
            description=f"Anda akan membuat pengumuman di channel {target_channel.mention}. Tekan tombol di bawah untuk mengisi detail lainnya. Deskripsi pengumuman akan diambil otomatis dari file teks di GitHub (`{GITHUB_RAW_DESCRIPTION_URL}`). Anda memiliki **60 detik** untuk mengisi formulir.",
            color=self.color_info),
            view=view_instance
        )
        view_instance.message = initial_msg # Menyimpan objek pesan untuk view
        print(f"[{datetime.now()}] [DEBUG ANNOUNCE] !announce: Pesan pemicu modal dikirim.")

# View untuk tombol pemicu modal
class AnnounceButtonView(discord.ui.View):
    def __init__(self, bot_instance, cog_instance, original_ctx, target_channel_obj, github_raw_url):
        super().__init__(timeout=60)
        self.bot = bot_instance
        self.cog = cog_instance
        self.original_ctx = original_ctx
        self.target_channel_obj = target_channel_obj
        self.github_raw_url = github_raw_url
        self.message = None # Ini akan diisi setelah pesan awal dikirim di command !announce
        print(f"[{datetime.now()}] [DEBUG ADMIN] AnnounceButtonView diinisialisasi.")

    @discord.ui.button(label="Buka Formulir Pengumuman", style=discord.ButtonStyle.primary, emoji="📣")
    async def open_announcement_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"[{datetime.now()}] [DEBUG ADMIN] Tombol 'Buka Formulir Pengumuman' diklik oleh {interaction.user.display_name}.")
        if interaction.user.id != self.original_ctx.author.id:
            print(f"[{datetime.now()}] [DEBUG ADMIN] AnnounceButtonView: Pengguna bukan pemanggil asli, blokir.")
            return await interaction.response.send_message("Hanya orang yang memulai perintah yang dapat membuat pengumuman ini.", ephemeral=True)
        
        if not self.original_ctx.author.guild_permissions.manage_guild:
            print(f"[{datetime.now()}] [DEBUG ADMIN] AnnounceButtonView: Pemanggil asli kekurangan izin 'Manage Server', blokir.")
            return await interaction.response.send_message("Anda tidak memiliki izin `Manage Server` untuk membuat pengumuman.", ephemeral=True)
        
        # Perbaiki agar AnnouncementModal bisa diakses (diimport atau didefinisikan di luar)
        # Untuk tujuan kode lengkap ini, saya akan mengasumsikan AnnouncementModal didefinisikan secara lokal di `announce`
        # atau Anda memindahkannya ke luar (misalnya ke level file ini).
        # Jika Anda tetap menginginkan nested class seperti di kode asli, ini bisa jadi tricky.
        # Solusi terbaik adalah definisi Modal di global scope file ini.
        # UNTUK KODE LENGKAP INI, SAYA ASUMSIKAN AnnouncementModal DI DEFINISIKAN DALAM FUNGSI ANNOUNCE ITU SENDIRI
        # DAN KITA MEMANGGILNYA DARI SANA SEPERTI INI. Ini hanya berfungsi jika modal didefinisikan global.
        # Karena modal didefinisikan di dalam `announce`, kita perlu memanggil modal dari `announce` command.
        # Button view harus dikirimkan dari dalam `announce` command itu sendiri, bukan di luar.
        # Ini berarti struktur kode Anda yang asli untuk `AnnounceButtonView` (didefinisikan di luar Cog)
        # dan `AnnouncementModal` (didefinisikan di dalam command `announce`) saling bertentangan.
        # Mari kita sesuaikan agar `AnnouncementModal` juga bisa diakses dari `AnnounceButtonView`.
        # CARA PALING MUDAH: DEFINISIKAN AnnouncementModal DI LUAR `ServerAdminCog` atau di Global Scope file ini.

        # --- RE-DEFINISI ULANG AnnouncementModal DI GLOBAL SCOPE (ini perubahan besar) ---
        # (Saya akan menempatkannya di bawah `AnnounceButtonView` agar kode tetap teratur)
        # Karena ini adalah kode lengkap, saya akan masukkan semua definisi di satu file.
        # Ini akan membuat `AnnouncementModal` dapat diakses dari mana saja di file ini.
        
        # Karena AnnouncementModal sekarang di global scope, dia tidak memiliki akses langsung ke `self.cog` dari `ServerAdminCog`.
        # Kita harus meneruskan `cog_instance` ke modal saat inisialisasi.
        modal = AnnouncementModalGlobal(self.cog, self.original_ctx, self.target_channel_obj, self.github_raw_url)
        try:
            await interaction.response.send_modal(modal)
            print(f"[{datetime.now()}] [DEBUG ADMIN] AnnounceButtonView: Modal pengumuman berhasil dikirim.")
        except discord.Forbidden:
            print(f"[{datetime.now()}] [DEBUG ADMIN] AnnounceButtonView: Bot Forbidden mengirim modal. Pastikan bot bisa DM user atau izin lainnya.", file=sys.stderr)
            await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Bot tidak memiliki izin untuk mengirim modal (pop-up form). Ini mungkin karena bot tidak bisa mengirim DM ke Anda atau ada masalah izin di server.", color=self.cog.color_error), ephemeral=True)
        except Exception as e:
            print(f"[{datetime.now()}] [DEBUG ADMIN] AnnounceButtonView: Error saat menampilkan modal pengumuman: {e}.", file=sys.stderr)
            await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan saat menampilkan formulir: {e}", color=self.cog.color_error), ephemeral=True)

    async def on_timeout(self) -> None:
        print(f"[{datetime.now()}] [DEBUG ADMIN] AnnounceButtonView: View timeout.")
        for item in self.children:
            item.disabled = True
        try:
            if self.message: # Hanya edit jika self.message sudah ada
                await self.message.edit(view=self)
                print(f"[{datetime.now()}] [DEBUG ADMIN] AnnounceButtonView: Pesan view dinonaktifkan.")
            else:
                print(f"[{datetime.now()}] [DEBUG ADMIN] AnnounceButtonView: Pesan view tidak ditemukan saat timeout (belum diatur).")
        except discord.NotFound:
            print(f"[{datetime.now()}] [DEBUG ADMIN] AnnounceButtonView: Pesan view tidak ditemukan saat timeout.")
            pass
        except Exception as e:
            print(f"[{datetime.now()}] [DEBUG ADMIN] AnnounceButtonView: ERROR saat menonaktifkan tombol pada timeout: {e}.", file=sys.stderr)


# =======================================================================================
# GLOBAL MODAL CLASS FOR ANNOUNCEMENT (DIPINDAHKAN KE SINI AGAR BISA DIAKSES DARI VIEWS)
# =======================================================================================
class AnnouncementModalGlobal(discord.ui.Modal, title="Buat Pengumuman"): # Nama diubah sedikit
    announcement_title = discord.ui.TextInput(
        label="Judul Pengumuman (maks 256 karakter)",
        placeholder="Contoh: Pembaruan Server Penting!",
        max_length=256,
        required=True,
        row=0
    )
    custom_username = discord.ui.TextInput(
        label="Username Pengirim Kustom (maks 256 karakter)",
        placeholder="Contoh: Tim Admin / Pengumuman Resmi",
        max_length=256,
        required=True,
        row=1
    )
    custom_profile_url = discord.ui.TextInput(
        label="URL Avatar Pengirim Kustom (Opsional, http/https)",
        placeholder="Contoh: https://example.com/avatar.png",
        max_length=2000,
        required=False,
        row=2
    )
    announcement_image_url = discord.ui.TextInput(
        label="URL Gambar di Akhir Pengumuman (Opsional, http/https)",
        placeholder="Contoh: https://example.com/banner.png",
        max_length=2000,
        required=False,
        row=3
    )

    def __init__(self, cog_instance, original_ctx, target_channel_obj, github_raw_url):
        super().__init__()
        self.cog = cog_instance
        self.original_ctx = original_ctx
        self.target_channel_obj = target_channel_obj
        self.github_raw_url = github_raw_url
        # Update title based on target channel
        self.title = f"Buat Pengumuman untuk #{target_channel_obj.name}"
        print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModalGlobal diinisialisasi.")

    async def on_submit(self, interaction: discord.Interaction):
        print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModalGlobal: on_submit dipanggil oleh {interaction.user.display_name}.")
        await interaction.response.defer(ephemeral=True)

        title = self.announcement_title.value.strip()
        username = self.custom_username.value.strip()
        profile_url = self.custom_profile_url.value.strip()
        image_url = self.announcement_image_url.value.strip()

        print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModalGlobal: Input diterima - Judul: '{title}', User: '{username}'.")

        if not username:
            print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModalGlobal: Username kustom kosong.")
            await interaction.followup.send(embed=self.cog._create_embed(description="❌ Username Pengirim Kustom tidak boleh kosong.", color=self.cog.color_error), ephemeral=True); return
        if profile_url and not (profile_url.startswith("http://") or profile_url.startswith("https://")):
            print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModalGlobal: URL Avatar tidak valid: {profile_url}.")
            await interaction.followup.send(embed=self.cog._create_embed(description="❌ URL Avatar Pengirim Kustom tidak valid. Harus dimulai dengan `http://` atau `https://`.", color=self.cog.color_error), ephemeral=True); return
        if image_url and not (image_url.startswith("http://") or image_url.startswith("https://")):
            print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModalGlobal: URL Gambar tidak valid: {image_url}.")
            await interaction.followup.send(embed=self.cog._create_embed(description="❌ URL Gambar Pengumuman tidak valid. Harus dimulai dengan `http://` atau `https://`.", color=self.cog.color_error), ephemeral=True); return
        
        print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModalGlobal: Input divalidasi. Mencoba ambil deskripsi dari {self.github_raw_url}.")

        full_description = ""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.github_raw_url) as resp:
                    print(f"[{datetime.now()}] [DEBUG ANNOUNCE] GitHub fetch Status: {resp.status}, Content-Type: {resp.headers.get('Content-Type')}.")
                    if resp.status == 200:
                        full_description = await resp.text()
                        print(f"[{datetime.now()}] [DEBUG ANNOUNCE] GitHub fetch: Deskripsi berhasil diambil ({len(full_description)} karakter). Awal deskripsi: '{full_description[:100]}...'")
                    else:
                        print(f"[{datetime.now()}] [DEBUG ANNOUNCE] GitHub fetch: Gagal (HTTP Status {resp.status}).")
                        await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Gagal mengambil deskripsi dari URL GitHub Raw ({self.github_raw_url}): Status HTTP {resp.status}. Pastikan URL valid dan publik.", color=self.cog.color_error), ephemeral=True); return
        except aiohttp.ClientError as e:
            print(f"[{datetime.now()}] [ERROR ANNOUNCE] GitHub fetch: Kesalahan jaringan: {e}.", file=sys.stderr)
            await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan jaringan saat mengambil deskripsi dari GitHub: {e}. Pastikan URL GitHub Raw benar.", color=self.cog.color_error), ephemeral=True); return
        except Exception as e:
            print(f"[{datetime.now()}] [ERROR ANNOUNCE] GitHub fetch: Kesalahan tak terduga: {e}.", file=sys.stderr)
            await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan tidak terduga saat mengambil deskripsi: {e}", color=self.cog.color_error), ephemeral=True); return

        if not full_description.strip():
            print(f"[{datetime.now()}] [DEBUG ANNOUNCE] Deskripsi dari GitHub Raw kosong atau hanya spasi.")
            await interaction.followup.send(embed=self.cog._create_embed(description="❌ Deskripsi pengumuman dari URL GitHub Raw kosong atau hanya berisi spasi. Pastikan file teks memiliki konten.", color=self.cog.color_error), ephemeral=True); return
        
        description_chunks = [full_description[i:i+4096] for i in range(0, len(full_description), 4096)]
        print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModalGlobal: Deskripsi dipecah menjadi {len(description_chunks)} bagian.")

        sent_first_embed = False
        for i, chunk in enumerate(description_chunks):
            if not chunk.strip(): continue

            embed = discord.Embed(
                description=chunk,
                color=self.cog.color_announce,
                timestamp=datetime.utcnow() if i == 0 else discord.Embed.Empty
            )
            
            if i == 0:
                embed.title = title
                embed.set_author(name=username, icon_url=profile_url if profile_url else discord.Embed.Empty)
                if image_url: embed.set_image(url=image_url)
                embed.set_footer(text=f"Pengumuman dari {self.original_ctx.guild.name}", icon_url=self.original_ctx.guild.icon.url if self.original_ctx.guild.icon else None)
            else:
                embed.set_footer(text=f"Lanjutan Pengumuman ({i+1}/{len(description_chunks)})")

            try:
                perms = self.target_channel_obj.permissions_for(self.target_channel_obj.guild.me)
                if not perms.send_messages or not perms.embed_links:
                    if not sent_first_embed:
                        print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModalGlobal: Bot kekurangan izin kirim pesan/embed di {self.target_channel_obj.name}.")
                        await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Bot tidak memiliki izin untuk mengirim pesan atau menyematkan tautan di {self.target_channel_obj.mention}. Pastikan bot memiliki izin 'Kirim Pesan' dan 'Sematkan Tautan'.", color=self.cog.color_error), ephemeral=True)
                    return
                
                await self.target_channel_obj.send(embed=embed)
                sent_first_embed = True
                print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModalGlobal: Embed #{i+1} berhasil dikirim ke {self.target_channel_obj.name}.")
            except discord.Forbidden:
                print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModalGlobal: Bot Forbidden kirim pesan ke {self.target_channel_obj.name}.", file=sys.stderr)
                if not sent_first_embed: await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Bot tidak memiliki izin untuk mengirim pesan di {self.target_channel_obj.mention}. Pastikan bot memiliki izin 'Send Messages' dan 'Embed Links'.", color=self.cog.color_error), ephemeral=True); return
            except Exception as e:
                print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModalGlobal: Error saat mengirim embed ke {self.target_channel_obj.name}: {e}.", file=sys.stderr)
                if not sent_first_embed: await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan saat mengirim pengumuman: {e}", color=self.cog.color_error), ephemeral=True); return
            
        if sent_first_embed:
            await interaction.followup.send(embed=self.cog._create_embed(description=f"✅ Pengumuman berhasil dikirim ke <#{self.target_channel_obj.id}>!", color=self.cog.color_success), ephemeral=True)
            await self.cog.log_action(self.original_ctx.guild, "📢 Pengumuman Baru Dibuat", {"Pengirim (Eksekutor)": self.original_ctx.author.mention, "Pengirim (Tampilan)": f"{username} ({profile_url if profile_url else 'Default'})", "Channel Target": f"<#{self.target_channel_obj.id}>", "Judul": title, "Deskripsi Sumber": GITHUB_RAW_DESCRIPTION_URL, "Panjang Deskripsi": f"{len(full_description)} karakter"}, self.cog.color_announce)
            print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModalGlobal: Konfirmasi dan log pengumuman selesai.")
        else:
            print(f"[{datetime.now()}] [DEBUG ANNOUNCE] AnnouncementModalGlobal: Tidak ada embed yang berhasil terkirim.")

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        print(f"[{datetime.now()}] [ERROR ANNOUNCE] Error in AnnouncementModalGlobal (on_error): {error}", file=sys.stderr)
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan tak terduga saat memproses formulir: {error}", color=self.cog.color_error), ephemeral=True)
        else:
            await interaction.followup.send(embed=self.cog._create_embed(description=f"❌ Terjadi kesalahan tak terduga saat memproses formulir: {error}", color=self.cog.color_error), ephemeral=True)

# Function to setup the cog in your main bot file
async def setup(bot):
    await bot.add_cog(ServerAdminCog(bot))
