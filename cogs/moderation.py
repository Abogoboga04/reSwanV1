import discord
from discord.ext import commands
from discord.ext.commands import has_permissions
import asyncio  # Untuk menangani timeout

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auto_delete_settings = {}  # Menyimpan pengaturan penghapusan pesan per channel
        self.user_warnings = {}
        self.bad_words = ['kata1', 'kata2', 'kata3']
        self.reason_map = {
            'url': "dilarang mengirimkan URL",
            'kasar': "dilarang berkata kasar atau rasis",
            'bot': "pesan dari bot tidak diperbolehkan"
        }

    @commands.command(name='set_auto_delete')
    @has_permissions(manage_messages=True)
    async def set_auto_delete(self, ctx, channel: discord.TextChannel, config_id: int, action: str, warning_channel: discord.TextChannel = None, notify: str = None, *, categories: str):
        """Mengatur channel untuk menghapus pesan berdasarkan kategori tertentu dengan ID konfigurasi dan peringatan."""

        if channel.id not in self.auto_delete_settings:
            self.auto_delete_settings[channel.id] = {}  # Inisialisasi dictionary untuk channel jika belum ada

        if config_id in self.auto_delete_settings[channel.id]:
            await ctx.send(f"Pengaturan auto delete dengan ID {config_id} sudah ada untuk channel {channel.mention}. Silakan hapus pengaturan tersebut sebelum mengatur yang baru.")
            return

        if config_id not in range(1, 10):  # Pastikan ID konfigurasi antara 1 - 9
            await ctx.send("ID konfigurasi harus antara 1 dan 9.")
            return

        if action not in ['warn', 'nowarn']:
            await ctx.send("Opsi harus 'warn' atau 'nowarn'.")
            return

        if notify not in ['active', 'deactive']:
            await ctx.send("Opsi notifikasi harus 'active' atau 'deactive'.")
            return

        categories_list = categories.split(',')
        self.auto_delete_settings[channel.id][config_id] = {
            'categories': [cat.strip().lower() for cat in categories_list],
            'warning_channel': warning_channel.id if warning_channel else None,
            'action': action,
            'notify': notify
        }

        await ctx.send(f"Pengaturan penghapusan pesan di channel {channel.mention} untuk konfigurasi {config_id}: {', '.join(self.auto_delete_settings[channel.id][config_id]['categories'])} dengan tindakan: {action}, dan notifikasi: {notify}")

        # Hapus pesan yang dikirim oleh pengguna
        await ctx.message.delete()

    @commands.command(name='delete_config')
    @has_permissions(manage_messages=True)
    async def delete_config(self, ctx):
        """Menampilkan konfigurasi yang ada dan menghapus salah satu dari mereka."""
        channel_id = ctx.channel.id

        if channel_id not in self.auto_delete_settings or not self.auto_delete_settings[channel_id]:
            await ctx.send("Tidak ada pengaturan auto delete yang tersedia untuk channel ini.")
            return

        available_configs = self.auto_delete_settings[channel_id]
        config_list = "\n".join([f"ID: {config_id}, Kategori: {', '.join(config['categories'])}" for config_id, config in available_configs.items()])

        await ctx.send(f"Pengaturan yang tersedia untuk dihapus:\n{config_list}\nSilakan pilih ID konfigurasi yang ingin dihapus:")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit() and int(m.content) in available_configs

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=30)  # Tunggu input dari admin
            config_id = int(msg.content)
            del self.auto_delete_settings[channel_id][config_id]
            await ctx.send(f"Pengaturan dengan ID {config_id} telah dihapus.")
        except asyncio.TimeoutError:
            await ctx.send("Waktu habis! Silakan coba lagi.")

    @commands.command(name='unactive')
    @has_permissions(manage_messages=True)
    async def unactive(self, ctx, config_id: int):
        """Menonaktifkan pengaturan auto delete berdasarkan ID konfigurasi."""
        channel_id = ctx.channel.id

        if channel_id in self.auto_delete_settings and config_id in self.auto_delete_settings[channel_id]:
            del self.auto_delete_settings[channel_id][config_id]
            await ctx.send(f"Pengaturan auto delete untuk konfigurasi {config_id} di channel ini telah dinonaktifkan.")
        else:
            await ctx.send(f"Tidak ada pengaturan auto delete dengan ID konfigurasi {config_id} di channel ini.")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Dengarkan pesan dan hapus jika sesuai dengan kategori yang ditentukan."""
        if message.author == self.bot.user:
            return  # Jangan hapus pesan dari bot

        user_warnings = self.user_warnings.setdefault(message.author.id, 0)

        # Cek pengaturan auto delete berdasarkan channel
        if message.channel.id in self.auto_delete_settings:
            configs = self.auto_delete_settings[message.channel.id]

            for config_id, config in configs.items():
                categories = config['categories']
                warning_channel_id = config['warning_channel']
                action = config['action']
                notify = config['notify']

                # Cek kategori yang diatur
                for category in categories:
                    if category in self.reason_map:
                        reason = self.reason_map[category]

                        if category == 'bot' and message.author.bot:
                            await message.delete()
                            if action == 'warn' and notify == 'active':
                                await self.send_warning(message, warning_channel_id, reason, config_id)
                            return

                        if category == 'url' and any(word in message.content for word in ["http://", "https://"]):
                            await message.delete()
                            if action == 'warn' and notify == 'active':
                                await self.send_warning(message, warning_channel_id, reason, config_id)
                            return

                        if category == 'kasar':
                            if any(bad_word in message.content.lower() for bad_word in self.bad_words):
                                await message.delete()
                                if action == 'warn' and notify == 'active':
                                    await self.send_warning(message, warning_channel_id, reason, config_id)
                                return

    async def send_warning(self, message, warning_channel_id, reason, config_id):
        """Mengirim peringatan kepada pengguna."""
        if warning_channel_id:
            warning_channel = self.bot.get_channel(warning_channel_id)
            if warning_channel:
                await warning_channel.send(f"Peringatan: Pesan dari {message.author.mention} telah dihapus karena melanggar aturan server mengenal \"{reason}\". Mohon dibaca lagi rules-nya.")

# Pastikan untuk menambahkan setup
async def setup(bot):
    await bot.add_cog(Moderation(bot))