import discord
from discord.ext import commands
import json
import uuid

# =================================================================
# Kelas Modal dan View (Sama seperti sebelumnya)
# =================================================================

class TextModal(discord.ui.Modal, title='Masukkan Teks'):
    def __init__(self, key, config, view):
        super().__init__()
        self.key = key
        self.config = config
        self.view = view
        self.text_input = discord.ui.TextInput(
            label=self.get_label(key),
            style=discord.TextStyle.paragraph if key == 'desc' else discord.TextStyle.short,
            default=config.get(key)
        )
        self.add_item(self.text_input)

    def get_label(self, key):
        labels = {
            'author': 'Nama Pengirim',
            'avatar': 'URL Foto Pengirim',
            'title': 'Judul Embed',
            'desc': 'Deskripsi Embed',
            'content': 'Teks Pesan Biasa',
        }
        return labels.get(key, key.capitalize())

    async def on_submit(self, interaction: discord.Interaction):
        self.config[self.key] = self.text_input.value
        await interaction.response.edit_message(embed=self.view.build_embed())

class ButtonsModal(discord.ui.Modal, title='Konfigurasi Tombol'):
    def __init__(self, config, view):
        super().__init__()
        self.config = config
        self.view = view
        self.buttons_input = discord.ui.TextInput(
            label='Data Tombol (JSON)',
            style=discord.TextStyle.paragraph,
            placeholder='[{"label": "Ambil Role", "style": "green", "action": "role", "value": "123456789012345678"}]',
            default=json.dumps(config.get('buttons', []), indent=2)
        )
        self.add_item(self.buttons_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            buttons_data = json.loads(self.buttons_input.value)
            self.config['buttons'] = buttons_data
            await interaction.response.edit_message(embed=self.view.build_embed())
        except json.JSONDecodeError:
            await interaction.response.send_message("Format JSON tidak valid. Periksa sintaks Anda.", ephemeral=True)

class ColorModal(discord.ui.Modal, title='Pilih Warna Embed'):
    def __init__(self, config, view):
        super().__init__()
        self.config = config
        self.view = view
        self.color_input = discord.ui.TextInput(
            label='Kode Warna (Hex, contoh: #2b2d31)',
            style=discord.TextStyle.short,
            placeholder='contoh: #2b2d31',
            default=config.get('color')
        )
        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction):
        color_str = self.color_input.value
        try:
            if not color_str.startswith('#'):
                color_str = '#' + color_str
            int_color = int(color_str.replace('#', ''), 16)
            self.config['color'] = color_str
            await interaction.response.edit_message(embed=self.view.build_embed())
        except ValueError:
            await interaction.response.send_message("Kode warna tidak valid. Gunakan format heksadesimal (e.g., `#2b2d31`).", ephemeral=True)

class WebhookConfigView(discord.ui.View):
    def __init__(self, bot, channel: discord.TextChannel):
        super().__init__(timeout=300)
        self.bot = bot
        self.channel = channel
        self.config = {}

    def build_embed(self):
        embed = discord.Embed(
            title="Konfigurasi Pesan Webhook",
            description="Silakan gunakan tombol di bawah untuk mengatur pesan.",
            color=0x2b2d31
        )
        
        embed.add_field(name="Judul", value=f"`{self.config.get('title', 'Belum diatur')}`", inline=False)
        embed.add_field(name="Deskripsi", value=f"`{self.config.get('desc', 'Belum diatur')}`", inline=False)
        embed.add_field(name="Warna", value=f"`{self.config.get('color', 'Belum diatur')}`", inline=False)
        embed.add_field(name="Pengirim", value=f"`{self.config.get('author', 'Belum diatur')}`", inline=False)
        embed.add_field(name="Foto Pengirim", value=f"`{self.config.get('avatar', 'Belum diatur')}`", inline=False)
        embed.add_field(name="Tombol", value=f"`{len(self.config.get('buttons', []))} tombol`", inline=False)
        embed.add_field(name="Kanal Tujuan", value=self.channel.mention, inline=False)
        
        return embed

    @discord.ui.button(label="Judul & Deskripsi", style=discord.ButtonStyle.blurple)
    async def title_desc_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        class TitleDescModal(discord.ui.Modal, title="Judul & Deskripsi"):
            def __init__(self, config, view):
                super().__init__()
                self.config = config
                self.view = view
                self.title_input = discord.ui.TextInput(label="Judul Embed", default=config.get('title', ''), required=False)
                self.desc_input = discord.ui.TextInput(label="Deskripsi Embed", style=discord.TextStyle.paragraph, default=config.get('desc', ''), required=False)
                self.add_item(self.title_input)
                self.add_item(self.desc_input)
            
            async def on_submit(self, interaction: discord.Interaction):
                self.config['title'] = self.title_input.value or None
                self.config['desc'] = self.desc_input.value or None
                await interaction.response.edit_message(embed=self.view.build_embed())
        
        await interaction.response.send_modal(TitleDescModal(self.config, self))

    @discord.ui.button(label="Warna", style=discord.ButtonStyle.blurple)
    async def color_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ColorModal(self.config, self))

    @discord.ui.button(label="Pengirim", style=discord.ButtonStyle.blurple)
    async def author_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TextModal('author', self.config, self))

    @discord.ui.button(label="Foto Pengirim", style=discord.ButtonStyle.blurple)
    async def avatar_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TextModal('avatar', self.config, self))

    @discord.ui.button(label="Tombol Interaktif", style=discord.ButtonStyle.blurple)
    async def buttons_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ButtonsModal(self.config, self))
        
    @discord.ui.button(label="Pesan Teks Biasa", style=discord.ButtonStyle.blurple)
    async def content_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TextModal('content', self.config, self))

    @discord.ui.button(label="Kirim Webhook", style=discord.ButtonStyle.green, row=1)
    async def send_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        embed = None
        if self.config.get('title') or self.config.get('desc') or self.config.get('color'):
            try:
                color = int(self.config['color'].replace('#', ''), 16) if self.config.get('color') else 0x2b2d31
                embed = discord.Embed(
                    title=self.config.get('title'),
                    description=self.config.get('desc'),
                    color=color
                )
            except (ValueError, TypeError):
                await interaction.followup.send("Format warna tidak valid. Pesan tidak dikirim.", ephemeral=True)
                return

        webhook = discord.utils.get(await self.channel.webhooks(), name="Webhook Bot")
        if not webhook:
            webhook = await self.channel.create_webhook(name="Webhook Bot")

        view = None
        buttons_data = self.config.get('buttons', [])
        if buttons_data:
            # Memetakan data tombol ke custom_id unik
            actions_map = {}
            for btn_data in buttons_data:
                btn_id = str(uuid.uuid4())
                btn_data['id'] = btn_id
                actions_map[btn_id] = {'action': btn_data.get('action'), 'value': btn_data.get('value')}

            # Menyimpan mapping sementara di bot untuk listener
            self.bot.get_cog('WebhookCog').button_actions.update(actions_map)
            
            view = ButtonView(buttons_data)

        try:
            await webhook.send(
                content=self.config.get('content'),
                username=self.config.get('author') or interaction.guild.name,
                avatar_url=self.config.get('avatar') or interaction.guild.icon.url,
                embeds=[embed] if embed else [],
                view=view
            )
            await interaction.followup.send(f"Pesan webhook berhasil dikirim ke {self.channel.mention}!", ephemeral=True)
            await interaction.message.delete()
        except Exception as e:
            await interaction.followup.send(f"Gagal mengirim pesan webhook: {e}", ephemeral=True)
            
    @discord.ui.button(label="Batalkan", style=discord.ButtonStyle.red, row=1)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Operasi dibatalkan.", ephemeral=True)
        await interaction.message.delete()
        self.stop()
        
# =================================================================
# Kelas View untuk Tombol Interaktif di Pesan Final
# =================================================================
class ButtonView(discord.ui.View):
    def __init__(self, buttons_data):
        super().__init__(timeout=None)
        for data in buttons_data:
            self.add_item(self.create_button(data))

    def create_button(self, data):
        label = data.get('label', 'Tombol')
        style_str = data.get('style', 'blurple')
        style_map = {
            'blurple': discord.ButtonStyle.blurple,
            'red': discord.ButtonStyle.red,
            'green': discord.ButtonStyle.green,
            'grey': discord.ButtonStyle.grey,
        }
        style = style_map.get(style_str, discord.ButtonStyle.blurple)
        
        button = discord.ui.Button(label=label, style=style, custom_id=data['id'])
        return button

# =================================================================
# Main Cog
# =================================================================
class WebhookCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Dictionary untuk menyimpan mapping custom_id ke aksi
        self.button_actions = {}

    @commands.command(aliases=['swh'])
    @commands.has_permissions(manage_webhooks=True)
    async def send_webhook(self, ctx, channel: discord.TextChannel):
        """Memulai wizard untuk membuat pesan webhook."""
        view = WebhookConfigView(self.bot, channel)
        await ctx.send(embed=view.build_embed(), view=view)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        # Memeriksa apakah interaksi berasal dari komponen (tombol)
        if not interaction.type == discord.InteractionType.component:
            return
            
        custom_id = interaction.data.get('custom_id')

        # Mencari aksi berdasarkan custom_id yang unik
        action_data = self.button_actions.get(custom_id)
        if not action_data:
            return

        action = action_data.get('action')
        value = action_data.get('value')
        
        # Logika dinamis berdasarkan data dari tombol
        if action == 'role':
            try:
                role_id = int(value)
                role = interaction.guild.get_role(role_id)
                if role:
                    await interaction.user.add_roles(role)
                    await interaction.response.send_message(f"Anda telah mendapatkan role **{role.name}**!", ephemeral=True)
                else:
                    await interaction.response.send_message("Role tidak ditemukan. Mohon hubungi admin.", ephemeral=True)
            except (ValueError, TypeError):
                await interaction.response.send_message("ID role tidak valid. Mohon hubungi admin.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"Terjadi kesalahan saat memberikan role: {e}", ephemeral=True)
        
        # Tambahkan logika untuk aksi lainnya di sini jika diperlukan
        # elif action == 'kirim_dm':
        #     ...

async def setup(bot):
    await bot.add_cog(WebhookCog(bot))
