import discord
from discord.ext import commands
import json
import uuid
import asyncio
import os
from datetime import datetime, timedelta
import logging
import pytz

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

class TextMediaModal(discord.ui.Modal, title='Teks dan Media URL'):
    def __init__(self, config, view):
        super().__init__()
        self.config = config
        self.view = view
        self.content_input = discord.ui.TextInput(
            label='Teks Pesan Biasa',
            style=discord.TextStyle.paragraph,
            default=config.get('content', ''),
            required=False
        )
        self.media_input = discord.ui.TextInput(
            label='Direct Link Media (URL Gambar/Video)',
            style=discord.TextStyle.short,
            default=config.get('media_url', ''),
            placeholder='https://example.com/image.png',
            required=False
        )
        self.add_item(self.content_input)
        self.add_item(self.media_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.config['content'] = self.content_input.value or None
        self.config['media_url'] = self.media_input.value or None
        await interaction.response.edit_message(embed=self.view.build_embed())

class AuthorModal(discord.ui.Modal, title='Pengirim Webhook'):
    def __init__(self, config, view):
        super().__init__()
        self.config = config
        self.view = view
        self.name_input = discord.ui.TextInput(
            label='Nama Pengirim',
            style=discord.TextStyle.short,
            default=config.get('author', ''),
            required=False
        )
        self.avatar_input = discord.ui.TextInput(
            label='URL Foto Pengirim',
            style=discord.TextStyle.short,
            default=config.get('avatar', ''),
            required=False
        )
        self.add_item(self.name_input)
        self.add_item(self.avatar_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.config['author'] = self.name_input.value or None
        self.config['avatar'] = self.avatar_input.value or None
        await interaction.response.edit_message(embed=self.view.build_embed())

class ButtonsModal(discord.ui.Modal, title='Konfigurasi Tombol'):
    def __init__(self, config, view):
        super().__init__()
        self.config = config
        self.view = view
        self.buttons_input = discord.ui.TextInput(
            label='Data Tombol (JSON)',
            style=discord.TextStyle.paragraph,
            placeholder='[{"label": "Ambil Role", "style": "green", "action": "role", "value": "123"}]',
            default=json.dumps(config.get('buttons', []), indent=2)
        )
        self.add_item(self.buttons_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            buttons_data = json.loads(self.buttons_input.value)
            self.config['buttons'] = buttons_data
            await interaction.response.edit_message(embed=self.view.build_embed())
        except json.JSONDecodeError:
            await interaction.response.send_message("Format JSON tidak valid.", ephemeral=True)

class ColorModal(discord.ui.Modal, title='Pilih Warna Kustom'):
    def __init__(self, config, view, color_message):
        super().__init__()
        self.config = config
        self.view = view
        self.color_message = color_message
        self.color_input = discord.ui.TextInput(
            label='Kode Hex:',
            style=discord.TextStyle.short,
            placeholder='#2b2d31',
            default=config.get('color', '')
        )
        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction):
        color_str = self.color_input.value
        try:
            if not color_str.startswith('#') and color_str:
                color_str = '#' + color_str
            if color_str:
                int(color_str.replace('#', ''), 16)
            self.config['color'] = color_str or None
            await interaction.response.edit_message(embed=self.view.build_embed())
            await self.color_message.delete()
        except ValueError:
            await interaction.response.send_message("Kode warna tidak valid.", ephemeral=True)

class ColorView(discord.ui.View):
    def __init__(self, config, parent_view):
        super().__init__(timeout=60)
        self.config = config
        self.parent_view = parent_view
        colors = [("Biru", "#3498DB"), ("Merah", "#E74C3C"), ("Hijau", "#2ECC71"), ("Emas", "#F1C40F"), ("Ungu", "#9B59B6"), ("Oranye", "#E67E22"), ("Abu-abu", "#95A5A6"), ("Biru Tua", "#0000FF"), ("Cyan", "#00FFFF"), ("Merah Tua", "#8B0000"), ("Hijau Tua", "#006400"), ("Coklat", "#A52A2A")]
        for label, hex_val in colors:
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary)
            btn.callback = self.make_callback(hex_val)
            self.add_item(btn)

    def make_callback(self, hex_val):
        async def callback(interaction: discord.Interaction):
            self.config['color'] = hex_val
            await interaction.response.edit_message(embed=self.parent_view.build_embed(), view=self.parent_view)
            self.stop()
        return callback
        
    @discord.ui.button(label="Pilih Kustom", style=discord.ButtonStyle.primary)
    async def custom_color_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ColorModal(self.config, self.parent_view, interaction.message))
        self.stop()

    async def on_timeout(self):
        if self.message:
            await self.message.delete()

class ScheduleTimeModal(discord.ui.Modal, title='Tentukan Jadwal'):
    def __init__(self, config, view):
        super().__init__()
        self.config = config
        self.view = view
        self.date_input = discord.ui.TextInput(
            label='Tanggal (YYYY-MM-DD)',
            placeholder=datetime.now().strftime('%Y-%m-%d'),
            style=discord.TextStyle.short,
            required=True
        )
        self.time_input = discord.ui.TextInput(
            label='Waktu (HH:MM WIB)',
            placeholder='15:30',
            style=discord.TextStyle.short,
            required=True
        )
        self.add_item(self.date_input)
        self.add_item(self.time_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            scheduled_time_str = f"{self.date_input.value} {self.time_input.value}"
            wib_timezone = pytz.timezone('Asia/Jakarta')
            scheduled_datetime_wib = wib_timezone.localize(datetime.strptime(scheduled_time_str, "%Y-%m-%d %H:%M"))
            now_wib = datetime.now(wib_timezone)
            
            if scheduled_datetime_wib < now_wib - timedelta(minutes=5):
                await interaction.response.send_message("Waktu harus di masa mendatang.", ephemeral=True)
                return
            
            self.config['scheduled_time'] = scheduled_datetime_wib.isoformat()
            await interaction.response.edit_message(embed=self.view.build_embed())
        except ValueError:
            await interaction.response.send_message("Format tanggal/waktu tidak valid.", ephemeral=True)

class SaveConfigModal(discord.ui.Modal, title='Simpan Konfigurasi'):
    def __init__(self, config, cog, target_channel):
        super().__init__()
        self.config = config
        self.cog = cog
        self.target_channel = target_channel
        self.name_input = discord.ui.TextInput(
            label='Nama Konfigurasi',
            required=True
        )
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        config_name = self.name_input.value
        self.cog.save_config_to_file(self.target_channel.guild.id, self.target_channel.id, config_name, self.config)
        await interaction.response.send_message(f"Konfigurasi '{config_name}' tersimpan!", ephemeral=True)

class WebhookButtonView(discord.ui.View):
    def __init__(self, buttons_data):
        super().__init__(timeout=None)
        for data in buttons_data:
            style_str = data.get('style', 'blurple')
            style_map = {
                'blurple': discord.ButtonStyle.blurple,
                'red': discord.ButtonStyle.red,
                'green': discord.ButtonStyle.green,
                'grey': discord.ButtonStyle.grey,
            }
            btn = discord.ui.Button(
                label=data.get('label', 'Tombol'),
                style=style_map.get(style_str, discord.ButtonStyle.blurple),
                custom_id=data['id']
            )
            self.add_item(btn)

class UnifiedSenderView(discord.ui.View):
    def __init__(self, bot, channel: discord.TextChannel, initial_config=None):
        super().__init__(timeout=600)
        self.bot = bot
        self.channel = channel
        self.config = initial_config or {}

    def build_embed(self):
        embed = discord.Embed(
            title="Dashboard Pengiriman Universal",
            description=f"Target Kanal: {self.channel.mention} | Server: {self.channel.guild.name}",
            color=0x2b2d31
        )
        embed.add_field(name="Judul", value=f"`{self.config.get('title', 'Kosong')}`", inline=True)
        embed.add_field(name="Deskripsi", value=f"`{self.config.get('desc', 'Kosong')}`", inline=True)
        embed.add_field(name="Warna", value=f"`{self.config.get('color', 'Kosong')}`", inline=True)
        embed.add_field(name="Author", value=f"`{self.config.get('author', 'Kosong')}`", inline=True)
        embed.add_field(name="Media URL", value=f"`{self.config.get('media_url', 'Kosong')}`", inline=True)
        embed.add_field(name="Tombol", value=f"`{len(self.config.get('buttons', []))} tombol`", inline=True)
        
        sch = self.config.get('scheduled_time')
        sch_display = "Tidak"
        if sch:
            dt = datetime.fromisoformat(sch).astimezone(pytz.timezone('Asia/Jakarta'))
            sch_display = dt.strftime('%d %B %Y, %H:%M WIB')
        embed.add_field(name="Jadwal", value=f"`{sch_display}`", inline=False)
        
        return embed

    def get_message_payload(self, is_webhook):
        embed = None
        if self.config.get('title') or self.config.get('desc') or self.config.get('color') or self.config.get('media_url'):
            try:
                color = int(self.config['color'].replace('#', ''), 16) if self.config.get('color') else 0x2b2d31
                embed = discord.Embed(title=self.config.get('title'), description=self.config.get('desc'), color=color)
                if self.config.get('media_url'):
                    embed.set_image(url=self.config['media_url'])
            except (ValueError, TypeError):
                logging.error("Gagal membuat embed warna.")

        view = None
        buttons_data = self.config.get('buttons', [])
        if buttons_data:
            actions_map = {}
            for btn_data in buttons_data:
                btn_id = btn_data.get('id') or str(uuid.uuid4())
                btn_data['id'] = btn_id
                actions_map[btn_id] = {'action': btn_data.get('action'), 'value': btn_data.get('value')}
            self.bot.get_cog('RTMMedia').button_actions.update(actions_map)
            view = WebhookButtonView(buttons_data)

        payload = {'content': self.config.get('content'), 'embeds': [embed] if embed else []}
        if view:
            payload['view'] = view
            
        if is_webhook:
            payload['username'] = self.config.get('author') or self.bot.user.name
            if self.config.get('avatar'):
                payload['avatar_url'] = self.config['avatar']
                
        return payload

    @discord.ui.button(label="Judul & Desc", style=discord.ButtonStyle.blurple, row=0)
    async def btn_title_desc(self, interaction: discord.Interaction, button: discord.ui.Button):
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

    @discord.ui.button(label="Teks & Media", style=discord.ButtonStyle.blurple, row=0)
    async def btn_content_media(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TextMediaModal(self.config, self))

    @discord.ui.button(label="Warna", style=discord.ButtonStyle.blurple, row=0)
    async def btn_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=ColorView(self.config, self))

    @discord.ui.button(label="Author Webhook", style=discord.ButtonStyle.blurple, row=0)
    async def btn_author(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AuthorModal(self.config, self))

    @discord.ui.button(label="Tombol", style=discord.ButtonStyle.blurple, row=0)
    async def btn_buttons(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ButtonsModal(self.config, self))

    @discord.ui.button(label="Simpan Config", style=discord.ButtonStyle.secondary, row=1)
    async def btn_save(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SaveConfigModal(self.config, self.bot.get_cog('RTMMedia'), self.channel))

    @discord.ui.button(label="Set Jadwal", style=discord.ButtonStyle.secondary, row=1)
    async def btn_schedule(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ScheduleTimeModal(self.config, self))

    @discord.ui.button(label="Kirim Webhook", style=discord.ButtonStyle.green, row=2)
    async def btn_send_webhook(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        if self.config.get('scheduled_time'):
            self.bot.get_cog('RTMMedia').schedule_job(self.channel.guild.id, self.channel.id, self.config, is_webhook=True)
            await interaction.followup.send("Webhook berhasil dijadwalkan!", ephemeral=True)
            await interaction.message.delete()
            return

        webhook = discord.utils.get(await self.channel.webhooks(), name="Webhook Bot")
        if not webhook:
            try:
                webhook = await self.channel.create_webhook(name="Webhook Bot")
            except discord.Forbidden:
                return await interaction.followup.send("Gagal: Butuh izin Manage Webhooks.", ephemeral=True)

        payload = self.get_message_payload(is_webhook=True)
        try:
            msg = await webhook.send(wait=True, **payload)
            if msg:
                self.bot.get_cog('RTMMedia').save_config_to_file(self.channel.guild.id, self.channel.id, str(msg.id), self.config)
            await interaction.followup.send("Webhook terkirim!", ephemeral=True)
            await interaction.message.delete()
        except Exception as e:
            await interaction.followup.send(f"Gagal mengirim: {e}", ephemeral=True)

    @discord.ui.button(label="Kirim sbg Bot", style=discord.ButtonStyle.green, row=2)
    async def btn_send_bot(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        if self.config.get('scheduled_time'):
            self.bot.get_cog('RTMMedia').schedule_job(self.channel.guild.id, self.channel.id, self.config, is_webhook=False)
            await interaction.followup.send("Pesan bot berhasil dijadwalkan!", ephemeral=True)
            await interaction.message.delete()
            return

        payload = self.get_message_payload(is_webhook=False)
        try:
            msg = await self.channel.send(**payload)
            self.bot.get_cog('RTMMedia').save_config_to_file(self.channel.guild.id, self.channel.id, str(msg.id), self.config)
            await interaction.followup.send("Pesan terkirim!", ephemeral=True)
            await interaction.message.delete()
        except Exception as e:
            await interaction.followup.send(f"Gagal mengirim: {e}", ephemeral=True)

    @discord.ui.button(label="Batal", style=discord.ButtonStyle.red, row=2)
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()
        self.stop()

class RTMMedia(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.button_actions = {}
        self.active_tickets = {}
        self.data_dir = 'data'
        self.config_file = os.path.join(self.data_dir, 'webhook.json')
        self.backup_file = os.path.join(self.data_dir, 'configbackup.json')
        self.scheduled_file = os.path.join(self.data_dir, 'scheduled_announcements.json')
        self.single_role_file = os.path.join(self.data_dir, 'single_role_messages.json')
        self.wib_timezone = pytz.timezone('Asia/Jakarta')
        self.single_role_messages = self.load_json(self.single_role_file)
        self.bot.loop.create_task(self.check_schedules())

    @commands.Cog.listener()
    async def on_ready(self):
        self._load_all_button_actions()

    def load_json(self, path):
        if not os.path.exists(path):
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}

    def save_json(self, path, data):
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)

    def save_config_to_file(self, guild_id, channel_id, config_name, config_data):
        all_configs = self.load_json(self.config_file)
        g_id, c_id = str(guild_id), str(channel_id)
        if g_id not in all_configs: all_configs[g_id] = {}
        if c_id not in all_configs[g_id]: all_configs[g_id][c_id] = {}
        all_configs[g_id][c_id][config_name] = config_data
        self.save_json(self.config_file, all_configs)

    def _load_all_button_actions(self):
        all_configs = self.load_json(self.config_file)
        for g in all_configs.values():
            for c in g.values():
                for conf in c.values():
                    for btn in conf.get('buttons', []):
                        if btn.get('id'):
                            self.button_actions[btn['id']] = {'action': btn.get('action'), 'value': btn.get('value')}

    def schedule_job(self, guild_id, channel_id, config, is_webhook):
        schedules = self.load_json(self.scheduled_file)
        job_id = str(uuid.uuid4())
        schedules[job_id] = {
            'guild_id': guild_id,
            'channel_id': channel_id,
            'config': config,
            'is_webhook': is_webhook,
            'scheduled_time': config['scheduled_time'],
            'title': config.get('title'),
            'content': config.get('content')
        }
        self.save_json(self.scheduled_file, schedules)

    async def check_schedules(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                schedules = self.load_json(self.scheduled_file)
                now_wib = datetime.now(self.wib_timezone)
                to_remove = []

                for job_id, data in list(schedules.items()):
                    sch_time = datetime.fromisoformat(data['scheduled_time']).astimezone(self.wib_timezone)
                    if now_wib >= sch_time:
                        guild = self.bot.get_guild(data['guild_id'])
                        if guild:
                            channel = guild.get_channel(data['channel_id'])
                            if channel:
                                view = UnifiedSenderView(self.bot, channel, data.get('config', {}))
                                payload = view.get_message_payload(data.get('is_webhook', False))
                                try:
                                    if data.get('is_webhook', False):
                                        webhook = discord.utils.get(await channel.webhooks(), name="Webhook Bot")
                                        if not webhook:
                                            webhook = await channel.create_webhook(name="Webhook Bot")
                                        await webhook.send(**payload)
                                    else:
                                        await channel.send(**payload)
                                except Exception as e:
                                    logging.error(f"Schedule fail: {e}")
                        to_remove.append(job_id)

                if to_remove:
                    for j in to_remove:
                        schedules.pop(j, None)
                    self.save_json(self.scheduled_file, schedules)
            except Exception as e:
                logging.error(e)
            await asyncio.sleep(60)

    @commands.command(name='send', aliases=['s'])
    @commands.has_permissions(manage_messages=True)
    async def send_cmd(self, ctx, channel_id: int = None):
        try: await ctx.message.delete()
        except: pass

        if channel_id:
            target_channel = self.bot.get_channel(channel_id)
            if not target_channel:
                try: target_channel = await self.bot.fetch_channel(channel_id)
                except: return await ctx.send("Kanal tidak ditemukan atau bot tidak memiliki akses.", ephemeral=True)
        else:
            target_channel = ctx.channel

        if not isinstance(target_channel, discord.TextChannel):
            return await ctx.send("ID yang diberikan bukan text channel.", ephemeral=True)

        view = UnifiedSenderView(self.bot, target_channel)
        await ctx.send(embed=view.build_embed(), view=view)

    @commands.command(name='send_media')
    @commands.has_permissions(manage_messages=True)
    async def send_media(self, ctx, channel: discord.TextChannel = None):
        if not ctx.message.reference:
            await ctx.send("Silakan balas pesan yang berisi media yang ingin dikirim.", ephemeral=True)
            return
            
        try:
            replied_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        except discord.errors.NotFound:
            await ctx.send("Pesan tidak ditemukan.", ephemeral=True)
            return

        if not replied_message.attachments:
            await ctx.send("Pesan tidak memiliki media.", ephemeral=True)
            return

        target_channel = channel or ctx.channel

        try:
            for attachment in replied_message.attachments:
                file_to_send = await attachment.to_file()
                await target_channel.send(content=replied_message.content, file=file_to_send)
            await ctx.send(f"Media terkirim ke {target_channel.mention}!", ephemeral=True)
            await ctx.message.delete()
        except Exception as e:
            await ctx.send(f"Error: {e}", ephemeral=True)

    @commands.command(name='list_schedules')
    @commands.has_permissions(manage_messages=True)
    async def list_schedules(self, ctx):
        schedules = self.load_json(self.scheduled_file)
        if not schedules:
            return await ctx.send("Tidak ada pengumuman terjadwal.", ephemeral=True)

        embed = discord.Embed(title="Daftar Pengumuman Berjadwal", color=discord.Color.blue())
        for job_id, data in schedules.items():
            try:
                dt = datetime.fromisoformat(data['scheduled_time']).astimezone(self.wib_timezone)
                ch = self.bot.get_channel(data['channel_id'])
                ch_name = ch.mention if ch else str(data['channel_id'])
                c_text = data.get('content') or data.get('title') or "Tanpa konten"
                embed.add_field(name=f"ID: {job_id[:8]}", value=f"**Waktu:** `{dt.strftime('%H:%M WIB, %d-%m-%Y')}`\n**Kanal:** {ch_name}\n**Konten:** `{c_text[:47]}`", inline=False)
            except:
                embed.add_field(name=f"ID: {job_id[:8]}", value="Data tidak valid.", inline=False)
        await ctx.send(embed=embed, ephemeral=True)

    @commands.command(name='load_config')
    @commands.has_permissions(manage_webhooks=True)
    async def load_config(self, ctx, config_name: str, channel: discord.TextChannel):
        if not ctx.guild: return
        all_configs = self.load_json(self.config_file)
        try:
            config_data = all_configs[str(ctx.guild.id)][str(ctx.channel.id)][config_name]
            view = UnifiedSenderView(self.bot, channel, initial_config=config_data)
            await ctx.send(embed=view.build_embed(), view=view)
        except KeyError:
            await ctx.send(f"Konfigurasi `{config_name}` tidak ditemukan.", ephemeral=True)

    @commands.command(name='backup_config')
    @commands.has_permissions(manage_webhooks=True)
    async def backup_config(self, ctx, message: discord.Message):
        if not ctx.guild: return
        all_configs = self.load_json(self.config_file)
        try:
            config_data = all_configs[str(ctx.guild.id)][str(message.channel.id)][str(message.id)]
        except KeyError:
            return await ctx.send("Konfigurasi pesan ini tidak ditemukan.", ephemeral=True)
        
        backup_configs = self.load_json(self.backup_file)
        g_id, c_id, m_id = str(ctx.guild.id), str(message.channel.id), str(message.id)
        if g_id not in backup_configs: backup_configs[g_id] = {}
        if c_id not in backup_configs[g_id]: backup_configs[g_id][c_id] = {}
        backup_configs[g_id][c_id][m_id] = config_data
        
        self.save_json(self.backup_file, backup_configs)
        await ctx.send(f"Berhasil dicadangkan ke `{self.backup_file}`.", ephemeral=True)

    @commands.command(name='list_configs')
    @commands.has_permissions(manage_webhooks=True)
    async def list_configs(self, ctx):
        if not ctx.guild: return
        all_configs = self.load_json(self.config_file)
        g_configs = all_configs.get(str(ctx.guild.id))
        if not g_configs: return await ctx.send("Tidak ada konfigurasi tersimpan.", ephemeral=True)

        embed = discord.Embed(title=f"Konfigurasi Tersimpan", color=discord.Color.blue())
        for c_id, configs in g_configs.items():
            ch = ctx.guild.get_channel(int(c_id))
            ch_name = ch.name if ch else str(c_id)
            c_list = "\n".join([f"`{name}`" for name in configs.keys()])
            if c_list: embed.add_field(name=f"Kanal: #{ch_name}", value=c_list, inline=False)
        await ctx.send(embed=embed, ephemeral=True)

    @commands.command(name='set_single_role', aliases=['ssr'])
    @commands.has_permissions(manage_roles=True)
    async def set_single_role(self, ctx, message_id: int, channel: discord.TextChannel = None):
        try: await ctx.message.delete()
        except: pass

        target_channel = channel or ctx.channel
        try:
            msg = await target_channel.fetch_message(message_id)
        except:
            return await ctx.send("Pesan tidak ditemukan.", ephemeral=True)

        g_id, m_id = str(target_channel.guild.id), str(msg.id)
        if g_id not in self.single_role_messages:
            self.single_role_messages[g_id] = []

        if m_id in self.single_role_messages[g_id]:
            self.single_role_messages[g_id].remove(m_id)
            status = "dihapus"
        else:
            self.single_role_messages[g_id].append(m_id)
            status = "diaktifkan"
            
        self.save_json(self.single_role_file, self.single_role_messages)
        await ctx.send(f"Single role pada pesan `{m_id}` {status}.", ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component: return
        
        data = self.button_actions.get(interaction.data.get('custom_id'))
        if not data: return

        action, value = data.get('action'), data.get('value')
        
        if action == 'role':
            try:
                role_to_add = interaction.guild.get_role(int(value))
                if not role_to_add: return await interaction.response.send_message("Role hilang.", ephemeral=True)
                if role_to_add in interaction.user.roles:
                    return await interaction.response.send_message("Kamu sudah punya role ini.", ephemeral=True)

                is_single = str(interaction.guild.id) in self.single_role_messages and str(interaction.message.id) in self.single_role_messages[str(interaction.guild.id)]
                to_remove = []
                
                if is_single:
                    msg_role_ids = set()
                    for comp in interaction.message.components:
                        for child in comp.children:
                            btn_data = self.button_actions.get(child.custom_id)
                            if btn_data and btn_data.get('action') == 'role':
                                msg_role_ids.add(int(btn_data.get('value')))
                    for r in interaction.user.roles:
                        if r.id in msg_role_ids and r.id != role_to_add.id:
                            to_remove.append(r)
                            
                if to_remove: await interaction.user.remove_roles(*to_remove)
                await interaction.user.add_roles(role_to_add)
                await interaction.response.send_message(f"Role **{role_to_add.name}** ditambahkan!", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"Error: {e}", ephemeral=True)

        elif action == 'ticket':
            cfg = value if isinstance(value, dict) else {'category_id': value, 'allowed_roles': [], 'blocked_roles': []}
            cat_id = int(cfg.get('category_id')) if cfg.get('category_id') else None
            allowed = [int(r) for r in cfg.get('allowed_roles', [])]
            blocked = [int(r) for r in cfg.get('blocked_roles', [])]
            u_roles = [r.id for r in interaction.user.roles]

            if any(r in blocked for r in u_roles): return await interaction.response.send_message("Akses ditolak.", ephemeral=True)
            if allowed and not any(r in allowed for r in u_roles): return await interaction.response.send_message("Butuh role spesifik.", ephemeral=True)
            if interaction.user.id in self.active_tickets: return await interaction.response.send_message("Tiket sudah ada.", ephemeral=True)

            await interaction.response.defer(ephemeral=True)
            category = interaction.guild.get_channel(cat_id) if cat_id else None
            specific_role = interaction.guild.get_role(1264935423184998422)

            ow = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True)
            }
            if specific_role: ow[specific_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

            tc = await interaction.guild.create_text_channel(f"ticket-{interaction.user.name.lower()}", overwrites=ow, category=category)
            cid = str(uuid.uuid4())
            self.button_actions[cid] = {'action': 'close_ticket', 'value': str(interaction.user.id)}
            view = discord.ui.View(timeout=None)
            view.add_item(discord.ui.Button(label="Tutup Tiket", style=discord.ButtonStyle.red, custom_id=cid))

            await tc.send(f"Tiket dari {interaction.user.mention} {specific_role.mention if specific_role else ''}", view=view)
            await interaction.followup.send(f"Tiket: {tc.mention}", ephemeral=True)
            self.active_tickets[interaction.user.id] = tc.id
            self.bot.loop.create_task(self.delete_ticket_delay(tc, interaction.user.id))

        elif action == 'close_ticket':
            await interaction.response.defer()
            uid = int(value)
            if uid in self.active_tickets: del self.active_tickets[uid]
            await interaction.channel.delete()

        elif action == 'channel':
            try:
                tc = interaction.guild.get_channel(int(value))
                if tc:
                    await tc.set_permissions(interaction.user, view_channel=True)
                    await interaction.response.send_message(f"Akses {tc.mention} diberikan!", ephemeral=True)
            except:
                await interaction.response.send_message("Gagal akses kanal.", ephemeral=True)

    async def delete_ticket_delay(self, channel, user_id):
        await asyncio.sleep(3600)
        if self.active_tickets.get(user_id) == channel.id:
            replied = False
            async for msg in channel.history(limit=50):
                if msg.author.guild_permissions.manage_channels and msg.author.id != self.bot.user.id:
                    replied = True
                    break
            if not replied:
                try: await channel.delete()
                except: pass
            if user_id in self.active_tickets: del self.active_tickets[user_id]

async def setup(bot):
    await bot.add_cog(RTMMedia(bot))
