import discord
from discord.ext import commands
from discord import ui, app_commands

# Ganti dengan ID channel tempat command FAQ akan berfungsi
FAQ_CHANNEL_ID = 1379458566452154438  # Contoh ID channel

# --- Kelas View untuk Tombol FAQ ---
class FAQView(ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    # --- Tombol untuk FAQ Umum ---
    @ui.button(label="FAQ Umum", style=discord.ButtonStyle.primary, emoji="❔")
    async def faq_umum_button(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(
            title="❔ FAQ Umum",
            description="Pertanyaan dan jawaban dasar seputar server ini.",
            color=discord.Color.from_rgb(123, 0, 255) # Ungu neon
        )
        embed.add_field(name="Apa itu Discord?", value="Discord adalah aplikasi komunikasi gratis yang dirancang untuk komunitas, gamer, dan grup. Anda dapat mengobrol melalui teks, suara, dan video.", inline=False)
        embed.add_field(name="Bagaimana cara bergabung ke server Njan Discord?", value="Anda dapat bergabung menggunakan tautan undangan yang valid. Pastikan Anda sudah memiliki akun Discord.", inline=False)
        embed.add_field(name="Apa itu 'role'?", value="Role adalah peran atau status yang memberikan warna khusus pada nama dan dapat memberikan akses ke channel atau fitur tertentu di server.", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- Tombol untuk Profil & Media Sosial ---
    @ui.button(label="Profil & Media Sosial", style=discord.ButtonStyle.success, emoji="👤")
    async def profil_button(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(
            title="👤 Tentang Rizwan Fadilah",
            description="Rizwan Fadilah atau yang biasa dikenal dengan Njan, merupakan seorang Penyanyi, Host, YouTuber, dan Gamer. Njan mengawali karirnya sebagai Youtuber dengan konten bermain GTA V Roleplay dan sukses menghibur pengikutnya di Youtube.",
            color=discord.Color.from_rgb(0, 255, 209) # Cyan
        )
        embed.add_field(name="Karir & Musik", value="""
Rizwan Fadilah tergabung dalam label RFAS Music. Pada 23 Juni 2023, Rizwan merilis single pertamanya yang berjudul "Tak Lagi Sama".
""", inline=False)
        
        embed.add_field(name="Link Resmi", value="""
• **YouTube Game:** [youtube.com/@njanlive](https://youtube.com/@njanlive)
• **YouTube Music:** [music.youtube.com/...](http://music.youtube.com/channel/UCg7PAyD-Syp...)
• **Spotify:** [googleusercontent.com/spotify...](open.spotify.com/artist/6usptTdSkyzOX8rWI...)
• **Apple Music:** [music.apple.com/...](https://music.apple.com/id/artist/rizwan-fadilah/164...)
• **TikTok:** [tiktok.com/@rizwanfadilah.a.s](https://tiktok.com/@rizwanfadilah.a.s)
• **Instagram:** [instagram.com/rizwanfadilah.a.s](https://instagram.com/rizwanfadilah.a.s)
• **Youtube Utama:** [youtube.com/@RizwanFadilah](https://www.youtube.com/@RizwanFadilah)
""", inline=False)
        
        # Contoh menambahkan gambar thumbnail (ganti URL)
        embed.set_thumbnail(url="https://i.imgur.com/your-thumbnail-image.png") # Ganti dengan URL gambar thumbnail

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- Tombol untuk Membership YouTube ---
    @ui.button(label="Membership YouTube", style=discord.ButtonStyle.secondary, emoji="▶️")
    async def membership_button(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(
            title="▶️ Membership YouTube",
            description="Informasi penting untuk mendapatkan role membership YouTube Anda.",
            color=discord.Color.from_rgb(255, 94, 94) # Merah menyala
        )
        embed.add_field(name="Cara menjadi anggota (member)?", value="Untuk menjadi anggota resmi, Anda bisa bergabung melalui tautan: [Bergabung Menjadi Anggota YouTube](https://www.youtube.com/channel/UCW2TTb26sRBrU7jlKpjCHVA/join)", inline=False)
        embed.add_field(name="Cara menautkan akun?", value="""
1. Buka **User Settings** > **Connections**.
2. Klik ikon **YouTube**.
3. Ikuti petunjuk untuk login ke akun yang memiliki membership.
4. Role akan otomatis disinkronkan ke Discord.""", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- Tombol untuk Peraturan Server ---
    @ui.button(label="Aturan Server", style=discord.ButtonStyle.danger, emoji="📜")
    async def rules_button(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(
            title="📜 Aturan Utama Server",
            description="Aturan ini dibuat untuk menjaga lingkungan yang nyaman bagi semua anggota.",
            color=discord.Color.from_rgb(255, 69, 0) # Oranye terang
        )
        embed.add_field(name="Poin Penting", value="""
• **Peraturan Umum:** Jaga sikap, bahasa, dan hindari pelecehan atau drama.
• **Channel yang Sesuai:** Gunakan setiap channel sesuai dengan topiknya.
• **Konten:** Dilarang keras memposting konten dewasa (NSFW), gore, phishing, atau spam.
• **Kerja Sama:** Jika ada kendala, laporkan ke tim Moderasi.
""", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Kelas Cog untuk Bot ---
class FAQBot(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="faq", help="Menampilkan FAQ dengan tombol.")
    async def faq_command(self, ctx: commands.Context):
        if ctx.channel.id != FAQ_CHANNEL_ID:
            await ctx.send("Perintah ini hanya bisa digunakan di channel FAQ.", ephemeral=True, delete_after=5)
            return

        embed = discord.Embed(
            title="📚 FAQ - Njan Discord",
            description="Halo! Silakan pilih salah satu tombol di bawah untuk melihat informasi yang Anda butuhkan.",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed, view=FAQView())

# --- Fungsi setup untuk memuat cog ---
async def setup(bot: commands.Bot):
    await bot.add_cog(FAQBot(bot))
