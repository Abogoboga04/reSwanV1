import discord
from discord.ext import commands
import json
import os
import shutil

class Backup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="backup", description="Backup semua file JSON dari folder data dan config.")
    @commands.has_permissions(administrator=True)
    async def backup(self, ctx):
        user_id = 1000737066822410311  # Ganti dengan ID Anda
        user = await self.bot.fetch_user(user_id)

        # Folder untuk menyimpan backup
        backup_dir = 'backup/'
        os.makedirs(backup_dir, exist_ok=True)

        # Daftar folder yang ingin dibackup
        folders_to_backup = ['data', 'config']
        for folder in folders_to_backup:
            if os.path.exists(folder):
                for filename in os.listdir(folder):
                    if filename.endswith('.json'):
                        src = os.path.join(folder, filename)
                        dst = os.path.join(backup_dir, filename)
                        shutil.copy(src, dst)

        # Kirim file JSON yang dibackup ke DM
        for filename in os.listdir(backup_dir):
            if filename.endswith('.json'):
                file_path = os.path.join(backup_dir, filename)
                await user.send(file=discord.File(file_path))

        await ctx.send("✅ Semua file JSON berhasil dibackup dan dikirim ke DM Anda.")

async def setup(bot):
    await bot.add_cog(Backup(bot))