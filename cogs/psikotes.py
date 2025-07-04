import discord
from discord.ext import commands
from discord.ui import Button, View
import json
import os

# Tentukan PATH ke folder data relatif dari file cog ini
# Pastikan nama file JSON yang kamu pakai sesuai dengan yang di sini
DATA_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
PSIKOTES_QUESTIONS_FILE = os.path.join(DATA_FOLDER, 'psikotes_questions.json') 
PSIKOTES_RESULTS_FILE = os.path.join(DATA_FOLDER, 'psikotes_results.json')

class PsikotesAssessment(commands.Cog): # Nama kelas cog
    def __init__(self, bot):
        self.bot = bot
        self.user_states = {}
        self.questions_data = {}
        self.results_data = {}
        self._load_data()

    def _load_data(self):
        """Memuat data pertanyaan dan hasil dari file JSON."""
        try:
            with open(PSIKOTES_QUESTIONS_FILE, 'r', encoding='utf-8') as f:
                self.questions_data = json.load(f)
            with open(PSIKOTES_RESULTS_FILE, 'r', encoding='utf-8') as f:
                self.results_data = json.load(f)
            print(f"[{self.__class__.__name__}] Data pertanyaan dan hasil berhasil dimuat dari {PSIKOTES_QUESTIONS_FILE} dan {PSIKOTES_RESULTS_FILE}.")
        except FileNotFoundError:
            print(f"[{self.__class__.__name__}] Error: File tidak ditemukan. Pastikan '{PSIKOTES_QUESTIONS_FILE}' dan '{PSIKOTES_RESULTS_FILE}' ada di '{DATA_FOLDER}'.")
            raise FileNotFoundError(f"Missing data files: {PSIKOTES_QUESTIONS_FILE} or {PSIKOTES_RESULTS_FILE}")
        except json.JSONDecodeError as e:
            print(f"[{self.__class__.__name__}] Error: Pastikan format JSON valid di file data. Detail: {e}")
            raise json.JSONDecodeError(f"Invalid JSON in data files: {e}")

    @commands.command(name='psikotes') # Perintah untuk memulai tes
    async def start_quiz(self, ctx):
        """Memulai tes psikotes dengan tombol."""
        user_id = ctx.author.id
        if user_id in self.user_states:
            await ctx.send(f"{ctx.author.mention}, kamu sudah dalam sesi psikotes. Selesaikan dulu atau ketik `!batalpsikotes` untuk memulai ulang.", ephemeral=True)
            return

        # Inisialisasi semua trait yang mungkin ada dari data results atau questions
        all_traits = set(self.results_data.get("trait_descriptions", {}).keys())
        for q_id, q_data in self.questions_data.items():
            for opt_key, opt_data in q_data.get("options", {}).items():
                for trait in opt_data.get("traits_impact", {}).keys():
                    all_traits.add(trait)

        self.user_states[user_id] = {
            "current_question_id": list(self.questions_data.keys())[0], # Ambil ID pertanyaan pertama dari JSON
            "scores": {trait: 0 for trait in all_traits},
            "message_to_edit": None
        }
        
        await self._send_question(ctx, user_id, ctx.channel)

    @commands.command(name='batalpsikotes') # Perintah untuk membatalkan tes
    async def cancel_quiz(self, ctx):
        """Membatalkan sesi tes psikotes."""
        user_id = ctx.author.id
        if user_id in self.user_states:
            message_to_delete = self.user_states[user_id].get("message_to_edit")
            if message_to_delete:
                try:
                    view = discord.View.from_message(message_to_delete)
                    for item in view.children:
                        item.disabled = True
                    await message_to_delete.edit(view=view)
                    await message_to_delete.delete(delay=3)
                except discord.NotFound:
                    pass
            del self.user_states[user_id]
            await ctx.send(f"✅ Sesi psikotesmu telah dibatalkan, {ctx.author.mention}. Sampai jumpa lagi!", ephemeral=True)
        else:
            await ctx.send(f"{ctx.author.mention}, kamu tidak sedang dalam sesi psikotes.", ephemeral=True)

    async def _send_question(self, ctx_or_interaction, user_id, channel):
        state = self.user_states[user_id]
        q_id = state["current_question_id"]
        question_data = self.questions_data.get(q_id)

        if not question_data:
            await channel.send(f"Maaf, terjadi kesalahan pada pertanyaan psikotes. Mohon hubungi admin bot. (ID pertanyaan tidak ditemukan: {q_id})", ephemeral=True)
            if user_id in self.user_states:
                del self.user_states[user_id]
            return

        embed = discord.Embed(
            title="🧠 Tes Psikotes", # Judul yang berbeda dari cog kepribadian umum
            description=f"**{question_data['text']}**",
            color=discord.Color.dark_blue() # Warna yang berbeda dari cog kepribadian umum
        )
        embed.set_footer(text=f"Progress: {self._get_progress(q_id)}")

        # Passing reference to this cog instance
        view = PsikotesQuestionView(self, user_id, q_id, question_data["options"])
        
        if state["message_to_edit"]:
            try:
                # Jika ctx_or_interaction adalah Interaction yang belum direspons
                if isinstance(ctx_or_interaction, discord.Interaction) and not ctx_or_interaction.response.is_done():
                    await ctx_or_interaction.response.edit_message(embed=embed, view=view)
                else: # Jika ini dipanggil dari command atau interaction yang sudah di-defer
                    await state["message_to_edit"].edit(embed=embed, view=view)
            except discord.NotFound:
                # Pesan mungkin sudah dihapus, jadi kirim yang baru
                state["message_to_edit"] = await channel.send(embed=embed, view=view)
            except discord.HTTPException as e:
                print(f"Error editing message: {e} - Attempting to send new message.")
                state["message_to_edit"] = await channel.send(embed=embed, view=view)
        else:
            # Ini untuk pesan awal command !psikotes
            if isinstance(ctx_or_interaction, commands.Context):
                state["message_to_edit"] = await ctx_or_interaction.send(embed=embed, view=view)
            else: # Fallback
                state["message_to_edit"] = await channel.send(embed=embed, view=view)


    def _get_progress(self, current_q_id):
        all_q_ids = list(self.questions_data.keys())
        try:
            current_index = all_q_ids.index(current_q_id)
            progress_percent = (current_index / len(all_q_ids)) * 100
            return f"Pertanyaan ke-{current_index + 1} dari {len(self.questions_data)} ({progress_percent:.0f}%)"
        except ValueError:
            return "Progress: N/A"

    async def _process_answer(self, interaction: discord.Interaction, user_id, q_id, selected_option_key):
        state = self.user_states.get(user_id)
        if not state or state["current_question_id"] != q_id:
            # Penting: Pastikan interaction direspons hanya sekali
            if not interaction.response.is_done():
                await interaction.response.send_message("Ini bukan pertanyaan psikotesmu saat ini atau tes sudah selesai.", ephemeral=True)
            return

        question_data = self.questions_data.get(q_id)
        if not question_data or selected_option_key not in question_data["options"]:
            if not interaction.response.is_done():
                await interaction.response.send_message("Opsi tidak valid. Terjadi kesalahan internal pada psikotes.", ephemeral=True)
            return

        selected_option = question_data["options"][selected_option_key]

        # Nonaktifkan tombol di pesan yang sedang diinteraksi
        if interaction.message:
            try:
                view = discord.View.from_message(interaction.message)
                for item in view.children:
                    item.disabled = True
                await interaction.message.edit(view=view)
            except discord.NotFound:
                pass
            except discord.HTTPException:
                pass

        for trait, value in selected_option.get("traits_impact", {}).items():
            if trait not in state["scores"]:
                state["scores"][trait] = 0
            state["scores"][trait] += value

        if "next_question_id" in selected_option:
            state["current_question_id"] = selected_option["next_question_id"]
            if not interaction.response.is_done():
                await interaction.response.defer() # Akui interaksi sebelum mengirim pertanyaan berikutnya
            await self._send_question(interaction, user_id, interaction.channel)
            
        else: # Tes selesai
            if not interaction.response.is_done():
                await interaction.response.defer() # Akui interaksi sebelum menampilkan hasil
            await self._display_final_results(interaction, user_id, interaction.channel)
            
            # Hapus pesan terakhir setelah hasil ditampilkan (jika belum dihapus)
            if state["message_to_edit"]:
                try:
                    await state["message_to_edit"].delete(delay=5)
                except discord.NotFound:
                    pass

    async def _display_final_results(self, interaction, user_id, channel):
        state = self.user_states.get(user_id)
        if not state:
            return
        
        final_scores = state["scores"]
        trait_descriptions = self.results_data.get("trait_descriptions", {})
        psikotes_result_types = self.results_data.get("psikotes_result_types", []) 
        
        best_match_type = None
        highest_score_match = -1

        if psikotes_result_types:
            for p_type in psikotes_result_types:
                match_score = 0
                required_met = True
                for req_trait, min_val in p_type.get("required_traits", {}).items():
                    if final_scores.get(req_trait, 0) < min_val:
                        required_met = False
                        break
                    match_score += final_scores.get(req_trait, 0)
                
                if required_met and match_score > highest_score_match:
                    highest_score_match = match_score
                    best_match_type = p_type
        
        if not best_match_type: # Fallback jika tidak ada yang cocok sempurna
            # Bisa dibuat logika fallback yang lebih cerdas berdasarkan trait paling dominan
            dominant_trait_name = None
            max_score_overall = -1
            if final_scores:
                for trait, score in final_scores.items():
                    if score > max_score_overall:
                        max_score_overall = score
                        dominant_trait_name = trait

            if dominant_trait_name and max_score_overall > 0:
                best_match_type = {
                    "name": f"Gaya Psikotes: {dominant_trait_name.replace('_', ' ').title()}",
                    "kesimpulan": f"Berdasarkan psikotes ini, trait **{dominant_trait_name.replace('_', ' ').title()}** sangat menonjol. Ini berarti {trait_descriptions.get(dominant_trait_name, 'kamu memiliki karakteristik unik dalam berpikir dan bertindak.')}",
                    "keunggulan": f"Keunggulanmu adalah kemampuanmu dalam aspek **{dominant_trait_name.replace('_', ' ').title()}** yang membedakanmu.",
                    "kekurangan": "Ada area yang bisa dikembangkan lebih lanjut untuk hasil yang optimal.",
                    "saran": "Terus latih kemampuanmu di berbagai bidang dan eksplorasi potensi lainnya!"
                }
            else:
                 best_match_type = {
                    "name": "Gaya Psikotes: Potensial Tersembunyi",
                    "kesimpulan": "Analisis psikotes ini menunjukkan kamu memiliki potensi yang besar, namun hasilnya belum sangat spesifik. Kamu adalah individu yang kompleks dan penuh kejutan!",
                    "keunggulan": "Potensimu yang belum tergali sepenuhnya adalah keunggulan terbesarmu.",
                    "kekurangan": "Mungkin ada beberapa area yang belum kamu eksplorasi secara penuh dalam dirimu.",
                    "saran": "Jangan berhenti belajar dan mencoba hal baru. Setiap pengalaman akan membentuk dan mengungkapkan lebih banyak tentang gayamu!"
                }


        member = channel.guild.get_member(user_id) if channel.guild else interaction.user
        member_name = member.display_name

        result_embed = discord.Embed(
            title=f"📊 Hasil Psikotesmu, {member_name}!", # Judul hasil yang berbeda
            description=f"Analisis gaya berpikir dan pendekatanmu:\n\n**{best_match_type.get('name', 'Gaya Tidak Dikenal')}**",
            color=discord.Color.dark_green() # Warna hasil yang berbeda
        )
        result_embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)

        result_embed.add_field(name="✨ Kesimpulan:", value=best_match_type.get('kesimpulan', 'Tidak ada kesimpulan.'), inline=False)
        result_embed.add_field(name="👍 Keunggulan:", value=best_match_type.get('keunggulan', 'Tidak ada keunggulan.'), inline=False)
        result_embed.add_field(name="🔍 Area Pengembangan:", value=best_match_type.get('kekurangan', 'Tidak ada kekurangan.'), inline=False)
        result_embed.add_field(name="💡 Saran Lanjutan:", value=best_match_type.get('saran', 'Tidak ada saran.'), inline=False)
        
        trait_data_text = "**Data Skor Trait Utama:**\n"
        # Tampilkan detail skor trait seperti di cog sebelumnya (sesuaikan trait untuk psikotes)
        if final_scores:
            sorted_traits = sorted(final_scores.items(), key=lambda item: item[1], reverse=True)
            sum_of_positive_scores = sum(score for score in final_scores.values() if score > 0)

            for trait, score in sorted_traits[:10]: # Batasi hingga 10 trait teratas untuk ringkasan
                if score > 0: # Hanya tampilkan trait dengan skor positif
                    percentage_of_sum = (score / sum_of_positive_scores * 100) if sum_of_positive_scores > 0 else 0
                    trait_description_short = trait_descriptions.get(trait, "Tidak ada deskripsi.").split('.')[0]
                    trait_data_text += f"- **{trait.replace('_', ' ').title()}**: {score:.1f} poin ({percentage_of_sum:.1f}% dari total positif).\n  *_{trait_description_short}._*\n"
        
        if not trait_data_text.strip():
            trait_data_text = "Tidak ada trait menonjol yang terdeteksi."

        result_embed.add_field(name="--- Detail Analisis Trait ---", value=trait_data_text, inline=False)


        result_embed.set_footer(text="Hasil psikotes ini adalah gambaran umum. Untuk analisis lebih dalam, konsultasikan dengan profesional.")

        await channel.send(embed=result_embed)
        del self.user_states[user_id] # Hapus state user setelah hasil ditampilkan


class PsikotesQuestionView(View): # Kelas View yang berbeda untuk psikotes
    def __init__(self, cog, user_id, question_id, options_data):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.question_id = question_id
        self.options_data = options_data
        self._add_buttons()

    def _add_buttons(self):
        for option_key, _ in self.options_data.items():
            label = option_key.replace('_', ' ').title()
            # Custom ID yang unik untuk psikotes: "psikotes_qID_optionKey"
            button = Button(label=label, custom_id=f"psikotes_{self.question_id}_{option_key}") 
            self.add_item(button)

        # Tombol 'Batal' juga punya custom_id yang unik untuk psikotes
        cancel_button = Button(label="Batalkan Psikotes", style=discord.ButtonStyle.red, custom_id=f"psikotes_cancel_{self.question_id}")
        self.add_item(cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Ini bukan psikotesmu! Silakan mulai psikotesmu sendiri dengan `!psikotes`.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.user_id in self.cog.user_states:
            channel = self.cog.bot.get_channel(self.message.channel.id)
            if not channel:
                channel = self.message.channel
            await channel.send(f"Psikotes dibatalkan karena tidak ada respons dari <@{self.user_id}> selama 2 menit. Silakan mulai lagi dengan `!psikotes`.", ephemeral=True)
            del self.cog.user_states[self.user_id]
        
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)

    # Ini adalah metode generik untuk menangani semua klik tombol dalam View ini.
    # @discord.ui.button DECORATOR HANYA BOLEH ADA SATU KALI PER VIEW UNTUK BUTTON DENGAN custom_id TERTENTU
    # Atau jika ingin generik, jangan pakai custom_id di decorator, tapi cek custom_id di dalam handler
    # Karena kita membuat custom_id secara dinamis, kita tidak bisa menaruh decorator di setiap tombol.
    # Solusi: Pakai @discord.ui.button() tanpa argumen custom_id, yang akan menangkap semua tombol di View
    @discord.ui.button(label="Generic Handler (Jangan munculkan)", style=discord.ButtonStyle.secondary, custom_id="generic_handler_for_psikotes_buttons_do_not_add_this_button") # Placeholder button for decorator, never actually added
    async def handle_any_button_click(self, interaction: discord.Interaction, button: Button):
        # Akui interaksi dengan cepat
        if not interaction.response.is_done():
            await interaction.response.defer() # Akui interaksi
            
        parts = button.custom_id.split('_')
        # Format custom_id: "psikotes_{question_id}_{option_key}" atau "psikotes_cancel_{question_id}"
        
        # Contoh: custom_id = "psikotes_q1_start_berkumpul_dengan_teman_dan_bersosialisasi"
        # parts[0] = "psikotes"
        # parts[1] = "q1" (ini q_id) atau "cancel"
        # parts[2] = "start" (ini bagian dari q_id) atau "q1_start" (jika question_id_from_button)
        # parts[3:] = sisa dari option_key

        if parts[1] == "cancel": # Cek apakah ini tombol batal
            q_id_from_button = parts[2] # q_id setelah "psikotes_cancel_"
            # Panggil fungsi cancel_quiz di cog
            await self.cog.cancel_quiz(interaction) # ctx diubah ke interaction untuk consistency
            return
        
        # Jika bukan tombol batal, maka itu adalah tombol jawaban pertanyaan
        q_id_from_button = parts[1] # "q1_start" atau sejenisnya
        # option_key_start_index = 2 karena "psikotes_IDPERTANYAAN_OPSIJAWABAN"
        # Contoh custom_id: "psikotes_q1_start_berkumpul_dengan_teman_dan_bersosialisasi"
        # parts[0]="psikotes", parts[1]="q1", parts[2]="start", parts[3]="berkumpul", dst.
        # Jadi q_id adalah parts[1] + "_" + parts[2] = "q1_start"
        # Dan option_key adalah parts[3] + "_" + parts[4] + ... = "berkumpul_dengan_teman_dan_bersosialisasi"
        
        # Perbaiki parsing custom_id untuk mendapatkan q_id dan selected_option_key
        # Custom ID: "{prefix}_{q_id}_{option_key}"
        # Contoh: "psikotes_q1_start_berkumpul_dengan_teman_dan_bersosialisasi"
        # prefix = parts[0]
        # q_id = parts[1]
        # option_key = parts[2] dan seterusnya
        
        # Ini akan membutuhkan penyesuaian pada format custom_id yang dibuat sebelumnya.
        # Format custom_id kita adalah f"psikotes_{self.question_id}_{option_key}"
        # Jadi: parts[0] = "psikotes"
        #       parts[1] = self.question_id (misal "q1_start")
        #       parts[2:] = option_key (misal "berkumpul_dengan_teman_dan_bersosialisasi")

        actual_q_id = parts[1]
        actual_option_key = '_'.join(parts[2:]) # Gabungkan kembali sisa parts menjadi option_key
        
        await self.cog._process_answer(interaction, self.user_id, actual_q_id, actual_option_key)


async def setup(bot):
    await bot.add_cog(PsikotesAssessment(bot))
