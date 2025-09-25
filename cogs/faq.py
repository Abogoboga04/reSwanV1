import discord
from discord.ext import commands
import json
import re
import os
import asyncio
import urllib.parse
import yt_dlp
import functools
import uuid # Untuk menghasilkan ID Jalur Unik

# --- UTILITY FUNCTION: YOUTUBE METADATA EXTRACTION ---

def _get_youtube_video_id(url):
    youtube_regex = r'(?:youtu\.be\/|youtube\.com\/(?:embed\/|v\/|watch\?v=|watch\?.*&v=))([a-zA-Z0-9_-]{11})'
    match = re.search(youtube_regex, url)
    return match.group(1) if match else None

def _extract_youtube_info(url):
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'force_generic_extractor': True,
        'no_warnings': True,
        'extractor_args': {'youtube': {'skip': ['dash']}},
        'format': 'best'
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title')
            description = info.get('description', '')
            thumbnail_url = None
            
            thumbnails = info.get('thumbnails', [])
            priority_ids = ['maxres', 'standard', 'high']
            for id_ in priority_ids:
                for t in thumbnails:
                    if t.get('id') == id_:
                        thumbnail_url = t.get('url')
                        break
                if thumbnail_url: break
            if not thumbnail_url and thumbnails: thumbnail_url = thumbnails[-1].get('url')

            return title, description, thumbnail_url
            
    except Exception:
        video_id = _get_youtube_video_id(url)
        if video_id:
            fallback_thumbnail = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
            return None, None, fallback_thumbnail
            
        return None, None, None

def get_path_config(cog, path_id, type_key, field_key=None):
    path_data = cog.config["notification_paths"].get(path_id)
    if not path_data: return None
    
    path = path_data["custom_messages"][type_key]
    return path.get(field_key, "") if field_key else path

# --- MODALS ---

class TextModal(discord.ui.Modal):
    def __init__(self, title, label, default_value, parent_view, type_key, field_key, path_id):
        super().__init__(title=title)
        self.parent_view = parent_view
        self.type_key = type_key
        self.field_key = field_key
        self.path_id = path_id
        self.text_input = discord.ui.TextInput(
            label=label,
            style=discord.TextStyle.paragraph if field_key == 'description' else discord.TextStyle.short,
            default=default_value,
            required=False,
            max_length=4000 if field_key == 'description' else (256 if field_key == 'title' else 2000)
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.parent_view.cog.config["notification_paths"][self.path_id]["custom_messages"][self.type_key][self.field_key] = self.text_input.value
        self.parent_view.cog.save_config()
        await interaction.response.edit_message(embed=self.parent_view.build_embed(), view=self.parent_view)

class ButtonLabelModal(discord.ui.Modal, title="Atur Tombol Notifikasi"):
    def __init__(self, parent_view, type_key, path_id):
        super().__init__()
        self.parent_view = parent_view
        self.type_key = type_key
        self.path_id = path_id
        current_label = get_path_config(parent_view.cog, path_id, type_key, "button_label")
        self.label_input = discord.ui.TextInput(
            label="Label Tombol (Max 80 karater)",
            default=current_label,
            style=discord.TextStyle.short,
            max_length=80
        )
        self.add_item(self.label_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.parent_view.cog.config["notification_paths"][self.path_id]["custom_messages"][self.type_key]["button_label"] = self.label_input.value
        self.parent_view.cog.save_config()
        await interaction.response.edit_message(embed=self.parent_view.build_embed(), view=self.parent_view.build_color_view())

class EmbedConfigModal(discord.ui.Modal, title="Pengaturan Embed & Thumbnail"):
    def __init__(self, parent_view, type_key, path_id):
        super().__init__()
        self.parent_view = parent_view
        self.type_key = type_key
        self.path_id = path_id
        config_msg = get_path_config(parent_view.cog, path_id, type_key)

        self.input_embed = discord.ui.TextInput(
            label=f"Gunakan Embed? (True/False)",
            default=str(config_msg.get('use_embed', True)),
            style=discord.TextStyle.short,
            required=True,
            max_length=5,
            row=0
        )
        self.add_item(self.input_embed)
        
        self.input_thumbnail = discord.ui.TextInput(
            label=f"Gunakan Thumbnail? (True/False)",
            default=str(config_msg.get('embed_thumbnail', True)),
            style=discord.TextStyle.short,
            required=True,
            max_length=5,
            row=1
        )
        self.add_item(self.input_thumbnail)

    async def on_submit(self, interaction: discord.Interaction):
        config_msg = self.parent_view.cog.config["notification_paths"][self.path_id]["custom_messages"][self.type_key]
        
        new_use_embed = self.input_embed.value.lower() == 'true'
        new_use_thumb = self.input_thumbnail.value.lower() == 'true'

        config_msg["use_embed"] = new_use_embed
        config_msg["embed_thumbnail"] = new_use_thumb
        self.parent_view.cog.save_config()
        
        await interaction.response.edit_message(embed=self.parent_view.build_embed(), view=self.parent_view)

# --- VIEWS UTAMA ---

class ButtonColorView(discord.ui.View):
    def __init__(self, parent_view, type_key, path_id):
        super().__init__(timeout=180)
        self.parent_view = parent_view
        self.type_key = type_key
        self.path_id = path_id
        self._create_buttons()

    def _create_buttons(self):
        buttons_data = [
            ("Biru (Primary/Blurple)", discord.ButtonStyle.primary, "#5865f2"),
            ("Abu-abu (Secondary/Grey)", discord.ButtonStyle.secondary, "#95a5a6"),
            ("Hijau (Success/Green)", discord.ButtonStyle.success, "#57f287"),
            ("Merah (Danger/Red)", discord.ButtonStyle.danger, "#ed4245")
        ]
        
        for label, style, hex_color in buttons_data:
            button = discord.ui.Button(label=label, style=style)
            
            async def callback(interaction: discord.Interaction, btn_style_value=style.value, embed_hex=hex_color):
                config_msg = self.parent_view.cog.config["notification_paths"][self.path_id]["custom_messages"][self.type_key]
                
                config_msg["button_style"] = btn_style_value
                config_msg["embed_color"] = hex_color
                self.parent_view.cog.save_config()
                
                await interaction.response.edit_message(embed=self.parent_view.build_embed(), view=self.parent_view)
                self.stop()
            
            button.callback = lambda i, s=style, h=hex_color: callback(i, s.value, h)
            self.add_item(button)
            
    @discord.ui.button(label="Batalkan", style=discord.ButtonStyle.red, row=1)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=self.parent_view.build_embed(), view=self.parent_view)
        self.stop()

class MessageConfigView(discord.ui.View):
    def __init__(self, cog, type_key, path_id):
        super().__init__(timeout=180)
        self.cog = cog
        self.type_key = type_key
        self.path_id = path_id

    def build_embed(self):
        path_data = self.cog.config["notification_paths"][self.path_id]
        config_msg = path_data["custom_messages"][self.type_key]
        
        embed_color_hex = config_msg.get('embed_color', '#3498db') 
        try:
            color_int = int(embed_color_hex.strip("#"), 16)
            embed_color = discord.Color(color_int)
        except:
            embed_color = discord.Color.blue()
            embed_color_hex = "#3498db"

        source_id = path_data["source_id"]
        target_id = path_data["target_id"]
        
        # Ambil info channel untuk display yang jelas
        source_channel = self.cog.bot.get_channel(source_id)
        target_channel = self.cog.bot.get_channel(target_id)
        
        source_info = f"#{source_channel.name} ({source_channel.guild.name})" if source_channel and source_channel.guild else f"ID: {source_id}"
        target_info = f"#{target_channel.name} ({target_channel.guild.name})" if target_channel and target_channel.guild else f"ID: {target_id}"

        embed = discord.Embed(
            title=f"Pengaturan Pesan: {self.type_key.upper()}",
            description=f"**Jalur:** {source_info} $\rightarrow$ {target_info}\n**ID Jalur:** `{self.path_id}`",
            color=embed_color
        )
        
        embed.add_field(name="Isi Pesan Biasa", value=f"`{config_msg.get('content') or 'Belum diatur'}`", inline=False)
        embed.add_field(name="Judul Embed", value=f"`{config_msg.get('title') or 'Belum diatur'}` (Gunakan: {{judul}})", inline=False)
        embed.add_field(name="Deskripsi Embed", value=f"`{config_msg.get('description') or 'Belum diatur'}` (Gunakan: {{deskripsi}})", inline=False)
        embed.add_field(name="Label Tombol", value=f"`{config_msg.get('button_label') or 'Belum diatur'}`", inline=False)
        
        button_style_value = config_msg.get('button_style', discord.ButtonStyle.primary.value)
        try:
            button_style_name = discord.ButtonStyle(button_style_value).name.capitalize().replace('_', ' ')
        except ValueError:
            button_style_name = "Tidak Diketahui (Default: Primary)"
        
        use_embed = config_msg.get('use_embed', True)
        embed_thumb = config_msg.get('embed_thumbnail', True)

        embed.add_field(name="Warna Tombol", value=f"`{button_style_name}`", inline=True)
        embed.add_field(name="Warna Samping Embed", value=f"`{embed_color_hex}`", inline=True)
        embed.add_field(name="Status Embed", value=f"`{'Aktif' if use_embed else 'Mati'}`", inline=True)
        embed.add_field(name="Status Thumbnail", value=f"`{'Aktif' if embed_thumb else 'Mati'}`", inline=True)
        
        return embed

    def build_color_view(self):
        return ButtonColorView(self, self.type_key, self.path_id)

    @discord.ui.button(label="Atur Pesan Biasa", style=discord.ButtonStyle.secondary)
    async def set_content_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_value = get_path_config(self.cog, self.path_id, self.type_key, "content")
        await interaction.response.send_modal(TextModal("Atur Pesan Teks Biasa", "Isi Pesan", current_value, self, self.type_key, "content", self.path_id))

    @discord.ui.button(label="Atur Judul Embed", style=discord.ButtonStyle.secondary)
    async def set_title_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_value = get_path_config(self.cog, self.path_id, self.type_key, "title")
        await interaction.response.send_modal(TextModal("Atur Judul Embed", "Judul Embed", current_value, self, self.type_key, "title", self.path_id))

    @discord.ui.button(label="Atur Deskripsi Embed", style=discord.ButtonStyle.secondary)
    async def set_desc_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_value = get_path_config(self.cog, self.path_id, self.type_key, "description")
        await interaction.response.send_modal(TextModal("Atur Deskripsi Embed", "Deskripsi Embed", current_value, self, self.type_key, "description", self.path_id))
        
    @discord.ui.button(label="Atur Tombol & Warna", style=discord.ButtonStyle.secondary, row=1)
    async def set_button_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ButtonLabelModal(self, self.type_key, self.path_id))
        
    @discord.ui.button(label="Atur Embed/Thumbnail", style=discord.ButtonStyle.secondary, row=1)
    async def set_embed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedConfigModal(self, self.type_key, self.path_id))
        
    @discord.ui.button(label="Selesai", style=discord.ButtonStyle.green, row=2)
    async def finish_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("✅ Pengaturan pesan berhasil disimpan!", ephemeral=True)
        self.stop()

# --- VIEWS INTERAKTIF BARU ---

class PathSelectView(discord.ui.View):
    def __init__(self, cog, guild_id):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self._add_path_select()

    def _get_path_options(self):
        options = []
        for path_id, data in self.cog.config["notification_paths"].items():
            source_id = data['source_id']
            target_id = data['target_id']

            source_channel = self.cog.bot.get_channel(source_id)
            target_channel = self.cog.bot.get_channel(target_id)

            source_name = f"#{source_channel.name}" if source_channel else f"ID {source_id}"
            target_name = f"#{target_channel.name}" if target_channel else f"ID {target_id}"

            label = f"{source_name} → {target_name}"
            options.append(discord.SelectOption(label=label[:100], value=path_id))

        return options

    def _add_path_select(self):
        options = self._get_path_options()
        
        if not options:
            self.add_item(discord.ui.Button(label="❌ Tidak ada Jalur Notifikasi terdaftar", style=discord.ButtonStyle.red, disabled=True))
            return

        path_select = discord.ui.Select(
            placeholder="Pilih Jalur Notifikasi yang akan dikonfigurasi...",
            options=options,
            custom_id="path_select_menu"
        )

        async def callback(interaction: discord.Interaction):
            selected_path_id = path_select.values[0]
            
            type_select_view = TypeSelectView(self.cog, self.guild_id, selected_path_id)
            
            await interaction.response.edit_message(content=f"🛠️ Jalur dipilih: `{selected_path_id}`. Pilih Tipe Pesan:", view=type_select_view)
            self.stop()
            
        path_select.callback = callback
        self.add_item(path_select)

class TypeSelectView(discord.ui.View):
    def __init__(self, cog, guild_id, path_id):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.path_id = path_id
        
        options = []
        for key in self.cog.default_messages.keys():
            options.append(discord.SelectOption(label=key.capitalize(), value=key))
            
        type_select = discord.ui.Select(
            placeholder="Pilih Tipe Pesan...",
            options=options,
            custom_id="type_select_menu"
        )
        
        async def callback(interaction: discord.Interaction):
            selected_type_key = type_select.values[0]
            
            message_config_view = MessageConfigView(self.cog, selected_type_key, self.path_id)
            await interaction.response.edit_message(embed=message_config_view.build_embed(), view=message_config_view)
            self.stop()
        
        type_select.callback = callback
        self.add_item(type_select)
        
        @discord.ui.button(label="← Ganti Jalur", style=discord.ButtonStyle.secondary, row=1)
        async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
             await interaction.response.edit_message(content="Pilih Jalur Notifikasi yang akan dikonfigurasi:", view=PathSelectView(self.cog, self.guild_id))
             self.stop()

# --- COG UTAMA ---

class Notif(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config_file = "data/notif.json"
        self.default_messages = self._get_default_messages() 
        
        # Perubahan Struktur Konfigurasi: Hanya satu notification_paths global
        self.config = self._load_config()

    def _get_link_from_url(self, message):
        youtube_regex = r'(?:https?:\/\/)?(?:www\.)?(?:youtu\.be\/|youtube\.com\/(?:embed\/|v\/|watch\?v=|watch\?.*&v=))([a-zA-Z0-9_-]{11})'
        tiktok_regex = r'(?:https?:\/\/)?(?:www\.)?(?:tiktok\.com\/.*\/video\/(\d+))'

        message_content = message.content
        
        url_pattern = re.compile(r'\[.*?\]\((https?://[^\s)]+)\)')
        urls_from_markdown = url_pattern.findall(message_content)
        link_for_send = urls_from_markdown[0] if urls_from_markdown else None

        if not link_for_send:
            match_youtube = re.search(youtube_regex, message_content)
            match_tiktok = re.search(tiktok_regex, message_content)
            
            if match_youtube:
                link_for_send = match_youtube.group(0)
            elif match_tiktok:
                link_for_send = match_tiktok.group(0)

        if not link_for_send:
            return None, None
            
        if re.search(youtube_regex, link_for_send):
            if "premier" in message_content.lower():
                link_type = "premier"
            elif "live" in message_content.lower():
                link_type = "live"
            else:
                link_type = "upload"
        
        elif re.search(tiktok_regex, link_for_send):
            link_type = "default"
        
        else:
            return None, None

        if link_type == "default":
            parsed_url = urllib.parse.urlparse(link_for_send)
            if not parsed_url.scheme:
                link_for_send = f"https://{link_for_send}"

        return link_type, link_for_send
    
    def _get_default_messages(self):
        return {
            "live": {
                "title": "🔴 {judul}",
                "description": "Yuk gabung di live stream ini!",
                "content": "@everyone Live stream dimulai!",
                "button_label": "Tonton Live",
                "button_style": discord.ButtonStyle.danger.value,
                "embed_color": "#e74c3c",
                "use_embed": True,
                "embed_thumbnail": True
            },
            "upload": {
                "title": "✨ {judul}",
                "description": "Video baru diupload, jangan sampai ketinggalan!",
                "content": "Ada video baru nih, cekidot!",
                "button_label": "Tonton Video",
                "button_style": discord.ButtonStyle.secondary.value,
                "embed_color": "#95a5a6",
                "use_embed": True,
                "embed_thumbnail": True
            },
            "premier": {
                "title": "🎬 Premiere Segera: {judul}",
                "description": "Video premiere akan segera tayang!",
                "content": "Ada video premiere!",
                "button_label": "Tonton Premiere",
                "button_style": discord.ButtonStyle.success.value,
                "embed_color": "#2ecc71",
                "use_embed": True,
                "embed_thumbnail": True
            },
            "default": {
                "title": None,
                "description": None,
                "content": None,
                "button_label": "Tonton Konten",
                "button_style": discord.ButtonStyle.primary.value,
                "embed_color": "#3498db",
                "use_embed": False,
                "embed_thumbnail": False
            }
        }

    def _load_config(self):
        default_config = {
            "mirrored_users": [],
            "notification_paths": {}, # Struktur Global Baru
            "recent_links": []
        }
        
        config = {}
        try:
            with open(self.config_file, "r") as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print("File konfigurasi tidak ditemukan atau tidak valid, membuat yang baru.")
        
        final_config = {**default_config, **config}
        
        if "notification_paths" not in final_config:
            final_config["notification_paths"] = {}

        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with open(self.config_file, "w") as f:
            json.dump(final_config, f, indent=4)
            
        return final_config

    def save_config(self):
        with open(self.config_file, "w") as f:
            json.dump(self.config, f, indent=4)
            
    # --- COMMANDS UTAMA ---

    @commands.command(name="adduser")
    @commands.has_permissions(administrator=True)
    async def add_user(self, ctx, user_id: str):
        if user_id in self.config["mirrored_users"]:
            await ctx.send(f"User dengan ID `{user_id}` sudah ada di daftar.")
            return
        
        self.config["mirrored_users"].append(user_id)
        self.save_config()
        await ctx.send(f"✅ User dengan ID `{user_id}` berhasil ditambahkan.")

    @commands.command(name="removeuser")
    @commands.has_permissions(administrator=True)
    async def remove_user(self, ctx, user_id: str):
        if user_id not in self.config["mirrored_users"]:
            await ctx.send(f"❌ User dengan ID `{user_id}` tidak ditemukan.")
            return
        
        self.config["mirrored_users"].remove(user_id)
        self.save_config()
        await ctx.send(f"✅ User dengan ID `{user_id}` berhasil dihapus.")
            
    @commands.command(name="resetlinks")
    @commands.has_permissions(administrator=True)
    async def reset_links(self, ctx):
        self.config["recent_links"] = []
        self.save_config()
        await ctx.send("✅ Riwayat link yang baru saja diposting berhasil **dibersihkan**.")

    @commands.command(name="addpath")
    @commands.has_permissions(administrator=True)
    async def add_notification_path(self, ctx, source_channel_id: int, target_channel_id: int):
        if not ctx.guild:
            await ctx.send("Perintah ini hanya dapat digunakan di dalam server.")
            return
        
        source_id = source_channel_id
        target_id = target_channel_id

        # Cek apakah jalur sudah ada
        for path_id, data in self.config["notification_paths"].items():
            if data["source_id"] == source_id and data["target_id"] == target_id:
                source_channel = self.bot.get_channel(source_id)
                target_channel = self.bot.get_channel(target_id)
                source_info = f"#{source_channel.name}" if source_channel else f"ID: {source_id}"
                target_info = f"#{target_channel.name}" if target_channel else f"ID: {target_id}"
                return await ctx.send(f"ℹ️ Jalur notifikasi dari {source_info} $\rightarrow$ {target_info} sudah ada dengan ID Jalur `{path_id}`.")
        
        # Buat Jalur Baru
        new_path_id = str(uuid.uuid4())
        
        self.config["notification_paths"][new_path_id] = {
            "source_id": source_id,
            "target_id": target_id,
            "custom_messages": self._get_default_messages()
        }
        
        # Ambil info channel untuk display yang jelas
        source_channel = self.bot.get_channel(source_id)
        target_channel = self.bot.get_channel(target_id)
        
        source_info = f"#{source_channel.name} ({source_channel.guild.name})" if source_channel and source_channel.guild else f"ID: {source_id}"
        target_info = f"#{target_channel.name} ({target_channel.guild.name})" if target_channel and target_channel.guild else f"ID: {target_id}"
        
        self.save_config()
        
        msg = f"✅ Jalur notifikasi baru berhasil dibuat!\n"
        msg += f"Sumber: **{source_info}**\n"
        msg += f"Tujuan: **{target_info}**\n"
        msg += f"ID Jalur (Wajib untuk setmessage): **`{new_path_id}`**"
        
        await ctx.send(msg)

    @commands.command(name="removepath")
    @commands.has_permissions(administrator=True)
    async def remove_notification_path(self, ctx, path_id: str):
        if path_id in self.config["notification_paths"]:
            del self.config["notification_paths"][path_id]
            self.save_config()
            await ctx.send(f"✅ Jalur notifikasi dengan ID Jalur `{path_id}` berhasil dihapus.")
        else:
            await ctx.send(f"❌ Jalur notifikasi dengan ID Jalur `{path_id}` tidak ditemukan.")


    @commands.command(name="setmessage")
    @commands.has_permissions(administrator=True)
    async def set_message(self, ctx, path_id: str, type_key: str = None):
        if not ctx.guild:
            return await ctx.send("Perintah ini hanya dapat digunakan di dalam server.")
        
        if path_id not in self.config["notification_paths"]:
            return await ctx.send(f"❌ ID Jalur `{path_id}` tidak ditemukan. Gunakan `!addpath` untuk membuat jalur.")
            
        if type_key is None or type_key not in self.default_messages:
            types = "|".join(self.default_messages.keys())
            return await ctx.send(f"Gunakan: `!setmessage <path_id> <{types}>`")
            
        # Kirim path_id ke View
        view = MessageConfigView(self, type_key, path_id)
        await ctx.send(embed=view.build_embed(), view=view)
        
    @commands.command(name="config")
    @commands.has_permissions(administrator=True)
    async def start_config(self, ctx):
        if not ctx.guild:
            return await ctx.send("Perintah ini hanya dapat digunakan di dalam server.")
        
        view = PathSelectView(self, ctx.guild.id)
        await ctx.send("Pilih Jalur Notifikasi yang akan dikonfigurasi:", view=view)


    # --- COG LISTENER ---
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.id == self.bot.user.id or not message.guild:
            return
            
        source_channel_id = message.channel.id
        
        # 1. Cek apakah pengguna terdaftar
        if str(message.author.id) not in self.config["mirrored_users"]:
            return

        link_type, link_for_send = self._get_link_from_url(message)
        
        if not link_type or message.content in self.config["recent_links"]:
            return
            
        # 2. Ambil semua Jalur yang memiliki Source Channel ID ini
        paths_to_send = [
            data for data in self.config["notification_paths"].values() 
            if data["source_id"] == source_channel_id
        ]
        
        if not paths_to_send:
            return
            
        # 3. Pre-processing & Cleanup
        self.config["recent_links"].append(message.content)
        if len(self.config["recent_links"]) > 50:
            self.config["recent_links"].pop(0)
        self.save_config()
        
        try:
            await message.delete()
        except Exception:
            pass

        # 4. Ambil Metadata YT sekali saja (di luar loop path)
        youtube_title, youtube_description, youtube_thumbnail = None, None, None
        if link_type in ["live", "upload", "premier"]: 
            loop = self.bot.loop
            youtube_title, youtube_description, youtube_thumbnail = await loop.run_in_executor(
                None, functools.partial(_extract_youtube_info, link_for_send)
            )

        # 5. Loop melalui setiap Jalur (Setiap Target)
        for path_data in paths_to_send:
            target_channel_id = path_data["target_id"]
            config_msg = path_data["custom_messages"].get(link_type, self.default_messages.get(link_type))
            if not config_msg: continue

            try:
                target_channel = self.bot.get_channel(target_channel_id)
                if not target_channel: continue 

                content = config_msg.get('content')
                custom_title = config_msg.get('title')
                custom_description = config_msg.get('description')
                
                # Pemrosesan Judul
                final_title = custom_title
                if final_title and youtube_title:
                    final_title = final_title.replace("{judul}", youtube_title)
                elif not final_title and youtube_title:
                    final_title = youtube_title
                elif final_title and final_title.find("{judul}") != -1:
                    final_title = final_title.replace("{judul}", "")
                elif not final_title:
                    final_title = None

                # Pemrosesan Deskripsi
                final_description = custom_description
                if final_description and youtube_description:
                    desc_sub = youtube_description[:1900] + ('...' if len(youtube_description) > 1900 else '')
                    final_description = final_description.replace("{deskripsi}", desc_sub)
                elif final_description and final_description.find("{deskripsi}") != -1:
                    final_description = final_description.replace("{deskripsi}", "")
                elif not final_description:
                    final_description = ""
                
                use_embed = config_msg.get('use_embed', self.default_messages[link_type]['use_embed'])
                embed_thumbnail_enabled = config_msg.get('embed_thumbnail', self.default_messages[link_type]['embed_thumbnail'])
                
                if not final_title and use_embed: final_title = "Konten Baru!" 
                
                final_content = f"{content} {link_for_send}" if content else link_for_send

                # Pengambilan Button Style
                button_label = config_msg.get('button_label', 'Tonton Konten')
                button_style_value = config_msg.get('button_style', self.default_messages[link_type]['button_style'])
                try: button_style = discord.ButtonStyle(button_style_value)
                except ValueError: button_style = discord.ButtonStyle.primary

                embed_color_hex = config_msg.get('embed_color', self.default_messages[link_type]['embed_color'])
                try: embed_color = discord.Color(int(embed_color_hex.strip("#"), 16))
                except: embed_color = discord.Color.blue()

                # Pembuatan Embed dan Pengiriman
                embed = None
                if use_embed and (final_title or final_description):
                    embed = discord.Embed(
                        title=final_title if final_title else "Konten Baru!",
                        description=final_description,
                        color=embed_color
                    )
                    
                    if embed_thumbnail_enabled and youtube_thumbnail:
                        embed.set_image(url=youtube_thumbnail)

                view = discord.ui.View()
                view.add_item(discord.ui.Button(label=button_label, style=button_style, url=link_for_send))

                await target_channel.send(content=final_content, embed=embed, view=view)
                
            except Exception as e:
                print(f"Gagal mengirim pesan di jalur {path_data}: {e}")

async def setup(bot):
    os.makedirs('data', exist_ok=True)
    await bot.add_cog(Notif(bot))
