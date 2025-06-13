import discord
from discord.ext import commands, tasks
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)

class Repeat(commands.Cog):
    def init(self, bot):
        self.bot = bot
        self.channel_id = None  # Inisialisasi dengan None
        self.is_repeating = False
        logging.info("Cog Repeat diinisialisasi.")

    @commands.Cog.listener()
    async def on_ready(self):
        """Mulai mengirim pesan saat bot siap dan online."""
        if self.channel_id is not None:
            logging.info("Bot sudah online, memulai pengiriman pesan.")
            self.is_repeating = True
            self.send_message.start()
        else:
            logging.warning("ID saluran belum diatur. Gunakan !set_channel [ID] untuk mengatur ID saluran.")

    @commands.command()
    async def set_channel(self, ctx, channel_id: int):
        """Atur ID saluran untuk mengirim pesan."""
        self.channel_id = channel_id
        await ctx.send(f"ID saluran telah diatur ke: {channel_id}")
        logging.info(f"ID saluran diatur ke: {channel_id}")

    @tasks.loop(minutes=2)
    async def send_message(self):
        """Kirim pesan '!rank' setiap 2 menit ke saluran yang ditentukan."""
        if self.is_repeating:
            logging.info("Fungsi send_message dipanggil.")
            channel = self.bot.get_channel(self.channel_id)
            if channel:
                logging.info(f"Kirim pesan ke {channel.name}: !rank")
                await channel.send("!rank")
            else:
                logging.error("Channel tidak ditemukan.")

    @send_message.before_loop
    async def before_send_message(self):
        """Menunggu hingga bot siap sebelum memulai pengiriman pesan."""
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Repeat(bot))