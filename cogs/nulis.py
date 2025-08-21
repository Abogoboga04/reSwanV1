import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
import requests
import io
import os

# URL aset dari repositori GitHub
FONT_URL = "https://github.com/MFarelS/RajinNulis-BOT/raw/master/font/Zahraaa.ttf"
IMAGE_URL = "https://github.com/MFarelS/RajinNulis-BOT/raw/master/MFarelSZ/Farelll/magernulis1.jpg"

def download_asset(url, is_font=False):
    """Mengunduh file dari URL dan mengembalikan objek file-like (bytes)."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        if is_font:
            return response.content
        else:
            return io.BytesIO(response.content)
    except requests.exceptions.RequestException as e:
        print(f"Error saat mengunduh aset: {e}")
        return None

def buat_tulisan_tangan(teks):
    """
    Mengubah teks menjadi gambar tulisan tangan dengan mengunduh aset.
    """
    try:
        gambar_data = download_asset(IMAGE_URL)
        if not gambar_data:
            return None
        gambar_latar = Image.open(gambar_data)
        
        font_data = download_asset(FONT_URL, is_font=True)
        if not font_data:
            return None
            
        temp_font_path = "temp_font.ttf"
        with open(temp_font_path, "wb") as f:
            f.write(font_data)

        # Ukuran font dan spasi yang sudah disesuaikan
        ukuran_font = 16 
        font_tulisan = ImageFont.truetype(temp_font_path, ukuran_font)
    except Exception as e:
        print(f"Error dalam memuat aset: {e}")
        return None
    
    # Bagian penting: menyesuaikan posisi dan spasi
    start_x = 140
    start_y = 140
    line_spacing = 20 

    draw = ImageDraw.Draw(gambar_latar)
    x_pos, y_pos = start_x, start_y
    baris_teks = teks.split('\n')
    
    for baris in baris_teks:
        draw.text((x_pos, y_pos), baris, font=font_tulisan, fill=(0, 0, 0))
        y_pos += line_spacing
    
    nama_file_hasil = "tulisan_tangan_hasil.png"
    gambar_latar.save(nama_file_hasil)

    if os.path.exists(temp_font_path):
        os.remove(temp_font_path)

    return nama_file_hasil

# --- Class Cog ---
class TulisanCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='tulis', help='Mengubah teks menjadi gambar tulisan tangan.')
    async def tulis_tangan(self, ctx, *, teks: str):
        if not teks:
            await ctx.send("Mohon berikan teks yang ingin Anda ubah menjadi tulisan tangan.")
            return

        await ctx.send("Sedang menulis... Mohon tunggu sebentar.")
        
        nama_file_hasil = buat_tulisan_tangan(teks)

        if nama_file_hasil:
            try:
                await ctx.send(file=discord.File(nama_file_hasil))
            finally:
                if os.path.exists(nama_file_hasil):
                    os.remove(nama_file_hasil)
        else:
            await ctx.send("Terjadi kesalahan saat membuat gambar. Coba lagi nanti.")

# Fungsi setup untuk memuat cogs
async def setup(bot):
    await bot.add_cog(TulisanCog(bot))
