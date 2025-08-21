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

def wrap_text(draw, text, font, max_width):
    """Memecah teks menjadi baris-baris yang sesuai dengan lebar maksimum."""
    lines = []
    if not text:
        return lines
    
    words = text.split(' ')
    current_line = ""
    for word in words:
        # Coba tambahkan kata ke baris saat ini
        if draw.textlength(current_line + " " + word, font=font) < max_width:
            if current_line == "":
                current_line = word
            else:
                current_line += " " + word
        else:
            # Jika melebihi lebar, mulai baris baru
            lines.append(current_line)
            current_line = word
    lines.append(current_line)
    return lines

def buat_tulisan_tangan(teks, nama):
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
        ukuran_font = 18 
        font_tulisan = ImageFont.truetype(temp_font_path, ukuran_font)
        
        # Tambahan untuk nama
        ukuran_font_nama = 20
        font_nama = ImageFont.truetype(temp_font_path, ukuran_font_nama)
    except Exception as e:
        print(f"Error dalam memuat aset: {e}")
        return None
    
    # Bagian penting: menyesuaikan posisi dan spasi
    start_x = 345
    start_y = 135
    line_spacing = 20 
    max_width = 900 # Lebar maksimum untuk teks
    
    # Posisi untuk nama pengguna
    nama_x = 500 
    nama_y = 100
    
    draw = ImageDraw.Draw(gambar_latar)
    
    # Tambahkan nama pengguna di bagian atas
    draw.text((nama_x, nama_y), nama, font=font_nama, fill=(0, 0, 0))
    
    x_pos, y_pos = start_x, start_y
    # Pecah teks input berdasarkan baris manual (\n)
    paragraphs = teks.split('\n')
    
    for paragraph in paragraphs:
        # Pecah setiap paragraf menjadi baris-baris otomatis
        lines_to_draw = wrap_text(draw, paragraph, font_tulisan, max_width)
        for line in lines_to_draw:
            draw.text((x_pos, y_pos), line, font=font_tulisan, fill=(0, 0, 0))
            y_pos += line_spacing
        y_pos += line_spacing * 0.5 # Tambahkan spasi antar paragraf
    
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
    async def tulis_tangan(self, ctx, nama: str, *, teks: str):
        if not nama or not teks:
            await ctx.send("Mohon berikan nama dan teks yang ingin Anda ubah menjadi tulisan tangan. Contoh: `!tulis Rhdevs Ini adalah teks`")
            return

        await ctx.send("Sedang menulis... Mohon tunggu sebentar.")
        
        nama_file_hasil = buat_tulisan_tangan(teks, nama)

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
