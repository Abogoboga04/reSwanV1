import discord
from discord.ext import commands
from discord import ui, app_commands

# Ganti dengan ID channel tempat command FAQ akan berfungsi
FAQ_CHANNEL_ID = 123456789012345678  # Contoh ID channel

# --- Kelas View untuk Tombol FAQ ---
class FAQView(ui.View):
    def __init__(self):
        super().__init__(timeout=180) # Timeout setelah 3 menit

    # --- Tombol untuk FAQ Umum ---
    @ui.button(label="FAQ Umum", style=discord.ButtonStyle.primary)
    async def faq_umum_button(self, interaction: discord.Interaction, button: ui.Button):
        message = (
            "**❔ FAQ Umum**\n"
            "• **Apa itu Discord?**\n"
            "   Discord adalah aplikasi komunikasi gratis yang dirancang untuk komunitas, gamer, dan grup.\n"
            "• **Bagaimana cara bergabung ke server Njan Discord?**\n"
            "   Anda dapat bergabung menggunakan tautan undangan yang valid.\n"
            "• **Apa itu 'role' di Discord?**\n"
            "   'Role' adalah peran atau status yang memberikan warna khusus dan akses ke channel tertentu."
        )
        await interaction.response.send_message(message, ephemeral=True)

    # --- Tombol untuk Profil & Media Sosial ---
    @ui.button(label="Profil & Media Sosial", style=discord.ButtonStyle.success)
    async def profil_button(self, interaction: discord.Interaction, button: ui.Button):
        message = (
            "**👤 Tentang Rizwan Fadilah**\n"
            "Rizwan Fadilah atau yang biasa dikenal dengan Njan, merupakan seorang Penyanyi, Host, YouTuber, dan Gamer. Njan mengawali karirnya sebagai Youtuber dengan konten bermain GTA V Roleplay dan sukses menghibur pengikutnya di Youtube dengan mendapatkan 165 ribu views. Saat ini Rizwan Fadilah tergabung dalam label RFAS Music. Pada tahun 2023 tepatnya tanggal 23 Juni, Rizwan telah merilis single pertamanya yang berjudul \"Tak Lagi Sama\". Selanjutnya Rizwan berencana untuk kembali merilis single keduanya.\n\n"
            "**🔗 Link Resmi**\n"
            "• **Youtube Game:** https://youtube.com/@njanlive\n"
            "• **Youtube Music:** http://music.youtube.com/channel/UCg7PAyD-Syp...\n"
            "• **Spotify:** open.spotify.com/artist/6usptTdSkyzOX8rWI...\n"
            "• **Apple Music:** https://music.apple.com/id/artist/rizwan-fadilah/164...\n"
            "• **TikTok:** https://tiktok.com/@rizwanfadilah.a.s\n"
            "• **Instagram:** https://instagram.com/rizwanfadilah.a.s\n"
            "• **Youtube Utama:** https://www.youtube.com/@RizwanFadilah"
        )
        await interaction.response.send_message(message, ephemeral=True)

    # --- Tombol untuk Membership YouTube ---
    @ui.button(label="Membership YouTube", style=discord.ButtonStyle.secondary)
    async def membership_button(self, interaction: discord.Interaction, button: ui.Button):
        message = (
            "**🎬 Membership YouTube**\n"
            "• **Cara menjadi anggota (member) di YouTube Njan?**\n"
            "   Bergabunglah melalui tautan: https://www.youtube.com/channel/UCW2TTb26sRBrU7jlKpjCHVA/join\n"
            "• **Cara menautkan akun YouTube dengan Discord?**\n"
            "   Buka **User Settings** > **Connections** > **YouTube**. Ikuti petunjuk untuk login. Role akan otomatis diberikan."
        )
        await interaction.response.send_message(message, ephemeral=True)

    # --- Tombol untuk Peraturan Server ---
    @ui.button(label="Aturan Server", style=discord.ButtonStyle.danger)
    async def rules_button(self, interaction: discord.Interaction, button: ui.Button):
        message = (
            "**📜 Aturan Utama Server**\n"
            "• **Peraturan Umum:** Jaga etika dan bahasa, hindari rasisme, pelecehan, dan drama.\n"
            "• **Konten Sesuai:** Dilarang memposting konten dewasa (NSFW), gore, phishing, atau spam.\n"
            "• **Kerja Sama:** Silakan berkoordinasi dengan staf jika ada kendala."
        )
        await interaction.response.send_message(message, ephemeral=True)

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
