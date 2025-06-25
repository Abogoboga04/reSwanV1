import discord
from discord.ext import commands
import json
import os
import re
import asyncio

class AutoSetup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.settings_file = "settings.json"
        self.filters_file = "filters.json"
        self.load_settings()
        self.load_filters()

    def load_settings(self):
        if not os.path.exists(self.settings_file):
            self.settings = {
                "auto_role": None,
                "welcome_channel": None,
                "welcome_message": "Selamat datang di server kami, {user}!",
                "reaction_roles": {},
                "channel_configs": {},
                "mute_status": False,
                "hide_status": False
            }
            self.save_settings()
        else:
            with open(self.settings_file, "r") as f:
                self.settings = json.load(f)

    def save_settings(self):
        with open(self.settings_file, "w") as f:
            json.dump(self.settings, f, indent=2)

    def load_filters(self):
        if not os.path.exists(self.filters_file):
            self.filters = {
                "bad_words": [],
                "link_patterns": []
            }
            self.save_filters()
        else:
            with open(self.filters_file, "r") as f:
                self.filters = json.load(f)

    def save_filters(self):
        with open(self.filters_file, "w") as f:
            json.dump(self.filters, f, indent=2)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.guild_id is None:
            return

        guild_id = str(payload.guild_id)
        message_id = str(payload.message_id)
        emoji = str(payload.emoji)

        # CEK apakah guild_id ada
        if guild_id not in self.settings:
            return

        # CEK apakah ada reaction_roles di guild ini
        if "reaction_roles" not in self.settings[guild_id]:
            return

        # CEK apakah message ID cocok
        if message_id not in self.settings[guild_id]["reaction_roles"]:
            return

        # Ambil role_id dari emoji
        role_id = self.settings[guild_id]["reaction_roles"][message_id].get(emoji)
        if not role_id:
            print(f"[SKIP] Emoji {emoji} gak cocok di msg {message_id}")
            return

        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)

        if not member or member.bot:
            return

        role = discord.utils.get(guild.roles, id=role_id)
        if role:
            try:
                await member.add_roles(role, reason="Reaction role")
                print(f"[✅] Berhasil kasih role '{role.name}' ke {member.name}")
            except discord.Forbidden:
                print(f"[❌] Gagal kasih role '{role.name}' ke {member.name} (cek permission)")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        role_name = self.settings.get("auto_role")
        if role_name:
            role = discord.utils.get(member.guild.roles, name=role_name)
            if role:
                await member.add_roles(role)

    @commands.command(name="setreactionrole", help="Atur role berdasarkan reaksi pada pesan tertentu.")
    @commands.has_permissions(manage_roles=True)
    async def set_reaction_role(self, ctx, message_id: int, emoji: str, role: discord.Role):
        guild_id = str(ctx.guild.id)
        message_id = str(message_id)

        if guild_id not in self.settings:
            self.settings[guild_id] = {}

        if "reaction_roles" not in self.settings[guild_id]:
            self.settings[guild_id]["reaction_roles"] = {}

        if message_id not in self.settings[guild_id]["reaction_roles"]:
            self.settings[guild_id]["reaction_roles"][message_id] = {}

        self.settings[guild_id]["reaction_roles"][message_id][emoji] = role.id
        self.save_settings()

        await ctx.send(f"✅ Role **{role.name}** akan diberikan saat react {emoji} di pesan ID `{message_id}`.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return

        channel_settings = self.get_channel_settings(message.channel.id)

        # Cek filter untuk kata kasar
        for bad_word in self.filters["bad_words"]:
            if bad_word.lower() in message.content.lower():
                await message.delete()
                return

        # Cek filter untuk link
        for pattern in self.filters["link_patterns"]:
            if re.search(pattern, message.content):
                await message.delete()
                # Mengirimkan pesan peringatan
                await message.channel.send(
                    f"🚨 Hey {message.author.mention}, "
                    "sepertinya kamu sedang mencoba membagikan sesuatu yang tidak diinginkan. "
                    "Apakah kamu yakin itu bukan spam? Kita tidak suka spam di sini! 😏"
                )
                return

        # Cek aturan untuk prefix
        if channel_settings["disallow_prefix"]:
            prefix = "!"  # Ganti dengan prefix yang Anda gunakan
            if message.content.startswith(prefix):
                await message.delete()
                # Mengirimkan pesan peringatan di channel yang sama
                await message.channel.send(
                    f"🚨 Hey {message.author.mention}, jika kamu mau gunakan bot maka silahkan pergi ke channel command bot.",
                    delete_after=10  # Menghapus pesan setelah 10 detik
                )
                return

    def get_channel_settings(self, channel_id):
        if str(channel_id) not in self.settings:
            self.settings[str(channel_id)] = {
                "disallow_bot": False,
                "disallow_links": False,
                "disallow_media": False,
                "disallow_prefix": False
            }
            self.save_settings()
        return self.settings[str(channel_id)]

    @commands.command(name="setup", help="Mengatur semua fitur dalam satu perintah.")
    @commands.has_permissions(manage_roles=True)
    async def setup(self, ctx):
        # Menampilkan semua role untuk debug
        roles = ctx.guild.roles
        print("Daftar Role di Server:")
        for role in roles:
            print(f"- {role.name} (ID: {role.id})")

        # Tombol untuk mengatur auto role
        auto_role_button = discord.ui.Button(label="Set Auto Role", style=discord.ButtonStyle.primary)

        async def set_auto_role_callback(interaction):
            if not interaction.user.guild_permissions.manage_roles:
                await interaction.response.send_message("🚫 Anda tidak memiliki izin untuk melakukan ini.", ephemeral=True)
                return

            await interaction.response.send_message("Silakan masukkan ID role yang ingin diberikan kepada pengguna baru:")
            try:
                msg = await self.bot.wait_for('message', check=lambda m: m.author == interaction.user, timeout=30)
                role_id = int(msg.content)
                role = ctx.guild.get_role(role_id)
                if role:
                    self.settings["auto_role"] = role.name
                    self.save_settings()
                    await interaction.followup.send(f"Auto role telah diatur ke: {role.name}")
                else:
                    await interaction.followup.send("Role tidak ditemukan. Pastikan ID yang dimasukkan benar.")
            except ValueError:
                await interaction.followup.send("ID role harus berupa angka. Silakan coba lagi.")
            except asyncio.TimeoutError:
                await interaction.followup.send("Waktu habis! Silakan coba lagi.")

        auto_role_button.callback = set_auto_role_callback

        # Tombol untuk mute/unmute
        mute_button = discord.ui.Button(label="Mute", style=discord.ButtonStyle.red)
        unmute_button = discord.ui.Button(label="Unmute", style=discord.ButtonStyle.green)

        async def mute_callback(interaction):
            if not interaction.user.guild_permissions.manage_roles:
                await interaction.response.send_message("🚫 Anda tidak memiliki izin untuk melakukan ini.", ephemeral=True)
                return

            self.settings["mute_status"] = True
            await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
            await interaction.response.send_message(f"{ctx.channel.mention} telah dimute.", ephemeral=True)

        async def unmute_callback(interaction):
            if not interaction.user.guild_permissions.manage_roles:
                await interaction.response.send_message("🚫 Anda tidak memiliki izin untuk melakukan ini.", ephemeral=True)
                return

            self.settings["mute_status"] = False
            await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
            await interaction.response.send_message(f"{ctx.channel.mention} telah diunmute.", ephemeral=True)

        mute_button.callback = mute_callback
        unmute_button.callback = unmute_callback

        # Tombol untuk hide/unhide
        hide_button = discord.ui.Button(label="Hide", style=discord.ButtonStyle.gray)
        unhide_button = discord.ui.Button(label="Unhide", style=discord.ButtonStyle.green)

        async def hide_callback(interaction):
            if not interaction.user.guild_permissions.manage_roles:
                await interaction.response.send_message("🚫 Anda tidak memiliki izin untuk melakukan ini.", ephemeral=True)
                return

            self.settings["hide_status"] = True
            await ctx.channel.set_permissions(ctx.guild.default_role, read_messages=False)
            await interaction.response.send_message(f"{ctx.channel.mention} telah disembunyikan.", ephemeral=True)

        async def unhide_callback(interaction):
            if not interaction.user.guild_permissions.manage_roles:
                await interaction.response.send_message("🚫 Anda tidak memiliki izin untuk melakukan ini.", ephemeral=True)
                return

            self.settings["hide_status"] = False
            await ctx.channel.set_permissions(ctx.guild.default_role, read_messages=True)
            await interaction.response.send_message(f"{ctx.channel.mention} telah ditampilkan.", ephemeral=True)

        hide_button.callback = hide_callback
        unhide_button.callback = unhide_callback

        # Tombol untuk mengatur pesan sambutan
        set_welcome_button = discord.ui.Button(label="Set Welcome Msg", style=discord.ButtonStyle.primary)

        async def set_welcome_callback(interaction):
            if not interaction.user.guild_permissions.manage_roles:
                await interaction.response.send_message("🚫 Anda tidak memiliki izin untuk melakukan ini.", ephemeral=True)
                return

            await interaction.response.send_message("Silakan masukkan pesan sambutan (gunakan {user} untuk menyebut pengguna baru):", ephemeral=True)
            msg = await self.bot.wait_for('message', check=lambda m: m.author == interaction.user)
            self.settings["welcome_message"] = msg.content[:200]  # Batasi panjang pesan sambutan
            self.save_settings()
            await interaction.followup.send(f"Pesan sambutan diatur ke: {msg.content}", ephemeral=True)

        set_welcome_button.callback = set_welcome_callback

        # Tombol untuk menambahkan kata kasar
        add_bad_word_button = discord.ui.Button(label="Add Bad Word", style=discord.ButtonStyle.primary)

        async def add_bad_word_callback(interaction):
            if not interaction.user.guild_permissions.manage_roles:
                await interaction.response.send_message("🚫 Anda tidak memiliki izin untuk melakukan ini.", ephemeral=True)
                return

            await interaction.response.send_message("Silakan masukkan kata kasar yang ingin ditambahkan:", ephemeral=True)
            msg = await self.bot.wait_for('message', check=lambda m: m.author == interaction.user)
            if 1 <= len(msg.content) <= 25:  # Validasi panjang kata kasar
                self.filters["bad_words"].append(msg.content)
                self.save_filters()
                await interaction.followup.send(f"Kata kasar '{msg.content}' telah ditambahkan.", ephemeral=True)
            else:
                await interaction.followup.send("Kata kasar harus antara 1 dan 25 karakter.", ephemeral=True)

        add_bad_word_button.callback = add_bad_word_callback

        # Tombol untuk menambahkan regex link
        add_link_pattern_button = discord.ui.Button(label="Add Link Regex", style=discord.ButtonStyle.primary)

        async def add_link_pattern_callback(interaction):
            if not interaction.user.guild_permissions.manage_roles:
                await interaction.response.send_message("🚫 Anda tidak memiliki izin untuk melakukan ini.", ephemeral=True)
                return

            await interaction.response.send_message("Silakan masukkan pola regex untuk link yang ingin ditambahkan:", ephemeral=True)
            msg = await self.bot.wait_for('message', check=lambda m: m.author == interaction.user)
            if len(msg.content) > 0:  # Pastikan pola regex tidak kosong
                self.filters["link_patterns"].append(msg.content)
                self.save_filters()
                await interaction.followup.send(f"Pola regex '{msg.content}' telah ditambahkan.", ephemeral=True)
            else:
                await interaction.followup.send("Pola regex tidak boleh kosong.", ephemeral=True)

        add_link_pattern_button.callback = add_link_pattern_callback

        # Tombol untuk mengatur pengaturan channel
        channel_settings_button = discord.ui.Button(label="Set Channel Settings", style=discord.ButtonStyle.secondary)

        async def set_channel_settings_callback(interaction):
            if not interaction.user.guild_permissions.manage_roles:
                await interaction.response.send_message("🚫 Anda tidak memiliki izin untuk melakukan ini.", ephemeral=True)
                return

            channel_settings = self.get_channel_settings(ctx.channel.id)

            # Dropdown untuk mengatur setiap aturan
            options = [
                discord.SelectOption(label="Larangan Bot", value="disallow_bot", description="Aktifkan atau nonaktifkan larangan bot."),
                discord.SelectOption(label="Larangan Link", value="disallow_links", description="Aktifkan atau nonaktifkan larangan link."),
                discord.SelectOption(label="Larangan Media", value="disallow_media", description="Aktifkan atau nonaktifkan larangan media."),
                discord.SelectOption(label="Larangan Prefix", value="disallow_prefix", description="Aktifkan atau nonaktifkan larangan prefix.")
            ]

            select = discord.ui.Select(placeholder="Pilih aturan untuk diatur...", options=options)

            async def select_callback(interaction):
                selected_option = select.values[0]
                current_status = channel_settings[selected_option]
                channel_settings[selected_option] = not current_status  # Toggle status
                self.save_settings()
                status_message = "diaktifkan" if not current_status else "dinonaktifkan"
                await interaction.response.send_message(f"Aturan '{selected_option}' telah {status_message}.", ephemeral=True)

            select.callback = select_callback

            view = discord.ui.View()
            view.add_item(select)

            await interaction.response.defer()
            await interaction.followup.send("Silakan pilih aturan yang ingin diatur:", view=view)

        channel_settings_button.callback = set_channel_settings_callback

        # Menampilkan semua UI
        view = discord.ui.View()
        view.add_item(auto_role_button)
        view.add_item(mute_button)
        view.add_item(unmute_button)
        view.add_item(hide_button)
        view.add_item(unhide_button)
        view.add_item(set_welcome_button)
        view.add_item(add_bad_word_button)
        view.add_item(add_link_pattern_button)
        view.add_item(channel_settings_button)

        await ctx.send("Silakan atur fitur-fitur berikut:", view=view)

async def setup(bot):
    await bot.add_cog(AutoSetup(bot))
