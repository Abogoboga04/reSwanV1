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
        response.raise_for_status()  # Cek jika unduhan sukses
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
        # Unduh gambar latar belakang dari URL
        gambar_data = download_asset(IMAGE_URL)
        if not gambar_data:
            return None
        gambar_latar = Image.open(gambar_data)
        
        # Unduh font dari URL
        font_data = download_asset(FONT_URL, is_font=True)
        if not font_data:
            return None
            
        # Simpan font sementara agar bisa diakses oleh Pillow
        temp_font_path = "temp_font.ttf"
        with open(temp_font_path, "wb") as f:
            f.write(font_data)

        font_tulisan = ImageFont.truetype(temp_font_path, 30)
    except Exception as e:
        print(f"Error dalam memuat aset: {e}")
        return None
    
    # Bagian menggambar teks (sama seperti sebelumnya)
    draw = ImageDraw.Draw(gambar_latar)
    x_pos, y_pos = 50, 50
    spasi_baris = 50
    baris_teks = teks.split('\n')
    
    for baris in baris_teks:
        draw.text((x_pos, y_pos), baris, font=font_tulisan, fill=(0, 0, 0))
        y_pos += spasi_baris
    
    nama_file_hasil = "tulisan_tangan_hasil.png"
    gambar_latar.save(nama_file_hasil)

    # Hapus file font sementara
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
        
        # Jalankan fungsi utama
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
