import discord
from discord.ext import commands
from discord.ui import Button, View
import json
import os

# Tentukan PATH ke folder data relatif dari file cog ini
DATA_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
PSIKOTES_QUESTIONS_FILE = os.path.join(DATA_FOLDER, 'psikotes_questions.json') # Nama file baru
PSIKOTES_RESULTS_FILE = os.path.join(DATA_FOLDER, 'psikotes_results.json')     # Nama file baru

class Psikotes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_states = {} # Menyimpan progres tes setiap user
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
            # Kamu bisa memilih untuk raise exception atau tetap jalankan bot tanpa fitur ini
            raise FileNotFoundError(f"Missing data files: {PSIKOTES_QUESTIONS_FILE} or {PSIKOTES_RESULTS_FILE}")
        except json.JSONDecodeError as e:
            print(f"[{self.__class__.__name__}] Error: Pastikan format JSON valid di file data. Detail: {e}")
            # Kamu bisa memilih untuk raise exception atau tetap jalankan bot tanpa fitur ini
            raise json.JSONDecodeError(f"Invalid JSON in data files: {e}")

    @commands.command(name='psikotes')
    async def start_quiz(self, ctx):
        """Memulai tes kepribadian interaktif dengan tombol."""
        user_id = ctx.author.id
        if user_id in self.user_states:
            await ctx.send(f"{ctx.author.mention}, kamu sudah dalam sesi tes. Selesaikan dulu atau ketik `!batalkanpsikotes` untuk memulai ulang.", ephemeral=True)
            return

        # Inisialisasi state user, termasuk semua trait dengan skor 0
        all_traits = set(self.results_data.get("trait_descriptions", {}).keys())
        # Pastikan semua trait dari questions.json juga ada di inisialisasi
        for q_id, q_data in self.questions_data.items():
            for opt_key, opt_data in q_data.get("options", {}).items():
                for trait in opt_data.get("traits_impact", {}).keys():
                    all_traits.add(trait)
        
        self.user_states[user_id] = {
            "current_question_id": "q1_start",
            "scores": {trait: 0 for trait in all_traits},
            "message_to_edit": None # Pesan yang akan diedit/dihapus
        }
        
        await self._send_question(ctx, user_id, ctx.channel)

    @commands.command(name='batalkanpsikotes')
    async def cancel_quiz(self, ctx):
        """Membatalkan sesi tes kepribadian."""
        user_id = ctx.author.id
        if user_id in self.user_states:
            message_to_delete = self.user_states[user_id].get("message_to_edit")
            if message_to_delete:
                try:
                    # Nonaktifkan tombol sebelum menghapus
                    view = discord.View.from_message(message_to_delete)
                    for item in view.children:
                        item.disabled = True
                    await message_to_delete.edit(view=view)
                    await message_to_delete.delete(delay=3) # Hapus setelah beberapa detik
                except discord.NotFound:
                    pass
            del self.user_states[user_id]
            await ctx.send(f"✅ Sesi tesmu telah dibatalkan, {ctx.author.mention}. Sampai jumpa lagi!", ephemeral=True)
        else:
            await ctx.send(f"{ctx.author.mention}, kamu tidak sedang dalam sesi tes.", ephemeral=True)

    async def _send_question(self, ctx, user_id, channel):
        state = self.user_states[user_id]
        q_id = state["current_question_id"]
        question_data = self.questions_data.get(q_id)

        if not question_data:
            await channel.send(f"{ctx.author.mention}, terjadi kesalahan pada pertanyaan. Mohon hubungi admin bot. (ID pertanyaan tidak ditemukan: {q_id})", ephemeral=True)
            if user_id in self.user_states:
                del self.user_states[user_id]
            return

        embed = discord.Embed(
            title="💡 Tes Kepribadian",
            description=f"**{question_data['text']}**",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Progress: {self._get_progress(q_id)}") # Menampilkan progress

        # Mengambil label tombol dan custom_id untuk QuestionView
        options_for_view = {key: val for key, val in question_data["options"].items()}
        view = QuestionView(self, user_id, q_id, options_for_view)
        
        # Jika ada pesan sebelumnya, edit pesan itu. Jika tidak, kirim pesan baru.
        if state["message_to_edit"]:
            try:
                await state["message_to_edit"].edit(embed=embed, view=view)
            except discord.NotFound: # Pesan mungkin sudah dihapus atau tidak ditemukan
                state["message_to_edit"] = await channel.send(embed=embed, view=view)
            except discord.HTTPException as e: # Error lain seperti invalid form body
                print(f"Error editing message: {e} - Attempting to send new message.")
                state["message_to_edit"] = await channel.send(embed=embed, view=view)
        else:
            state["message_to_edit"] = await channel.send(embed=embed, view=view)

    def _get_progress(self, current_q_id):
        """Menghitung progress tes (estimasi)."""
        all_q_ids = list(self.questions_data.keys())
        try:
            current_index = all_q_ids.index(current_q_id)
            # Karena alur bercabang, total pertanyaan bukan 100% dari all_q_ids.
            # Ini hanya estimasi kasar berdasarkan index ID yang ada.
            # Untuk akurasi, perlu menghitung path terpanjang.
            progress_percent = (current_index / len(all_q_ids)) * 100
            return f"Pertanyaan ke-{current_index + 1} dari {len(self.questions_data)} ({progress_percent:.0f}%)"
        except ValueError:
            return "Progress: N/A" # Jika ID tidak ditemukan

    async def _process_answer(self, interaction: discord.Interaction, user_id, q_id, selected_option_key):
        state = self.user_states.get(user_id)
        if not state or state["current_question_id"] != q_id:
            await interaction.response.send_message("Ini bukan pertanyaanmu saat ini atau tes sudah selesai.", ephemeral=True)
            return

        question_data = self.questions_data.get(q_id)
        if not question_data or selected_option_key not in question_data["options"]:
            await interaction.response.send_message("Opsi tidak valid. Terjadi kesalahan internal.", ephemeral=True)
            return

        selected_option = question_data["options"][selected_option_key]

        # Nonaktifkan tombol setelah dijawab untuk mencegah jawaban ganda
        if interaction.message:
            try:
                view = discord.View.from_message(interaction.message)
                for item in view.children:
                    item.disabled = True
                await interaction.message.edit(view=view)
            except discord.NotFound:
                pass # Pesan mungkin sudah dihapus oleh timeout
            except discord.HTTPException:
                pass # Gagal edit, mungkin pesan sudah terlalu tua

        # Akumulasi skor trait
        for trait, value in selected_option.get("traits_impact", {}).items():
            if trait not in state["scores"]:
                state["scores"][trait] = 0
            state["scores"][trait] += value

        # Lanjutkan ke pertanyaan berikutnya atau tampilkan hasil
        if "next_question_id" in selected_option:
            state["current_question_id"] = selected_option["next_question_id"]
            await self._send_question(interaction, user_id, interaction.channel)
            await interaction.response.defer() # Acknowledge interaction without sending message
        else:
            # Tes selesai
            await self._display_final_results(interaction, user_id, interaction.channel)
            await interaction.response.defer() # Acknowledge interaction
            
            # Hapus pesan terakhir setelah hasil ditampilkan (jika belum dihapus oleh _display_final_results)
            if state["message_to_edit"]:
                try:
                    await state["message_to_edit"].delete(delay=5)
                except discord.NotFound:
                    pass

    async def _display_final_results(self, interaction, user_id, channel):
        state = self.user_states.get(user_id)
        if not state: # User state might have been deleted if test was cancelled or timed out
            return
        
        final_scores = state["scores"]
        
        # --- LOGIKA PENENTUAN TIPE KEPRIBADIAN (INTI DARI PERUBAHAN INI) ---
        best_match_type = None
        highest_score_match = -1
        
        personality_types = self.results_data.get("personality_types", [])
        trait_descriptions = self.results_data.get("trait_descriptions", {})

        for p_type in personality_types:
            match_score = 0
            is_excluded = False

            # Cek required_traits
            required_met = True
            for req_trait, min_val in p_type.get("required_traits", {}).items():
                if final_scores.get(req_trait, 0) < min_val:
                    required_met = False
                    break
                match_score += final_scores.get(req_trait, 0) # Tambahkan skor trait yang cocok

            if not required_met:
                continue

            # Cek excluded_traits
            for excl_trait, max_val in p_type.get("excluded_traits", {}).items():
                if final_scores.get(excl_trait, 0) >= max_val: # Jika skor excluded trait terlalu tinggi
                    is_excluded = True
                    break
            if is_excluded:
                continue

            # Jika tipe ini lebih baik dari yang sebelumnya
            if match_score > highest_score_match:
                highest_score_match = match_score
                best_match_type = p_type
        
        # --- Fallback jika tidak ada tipe yang cocok sempurna ---
        if not best_match_type:
            dominant_trait_name = None
            max_score_overall = -1
            if final_scores:
                for trait, score in final_scores.items():
                    # Hanya pertimbangkan trait dengan skor positif
                    if score > max_score_overall:
                        max_score_overall = score
                        dominant_trait_name = trait

            if dominant_trait_name and max_score_overall > 0:
                best_match_type = {
                    "name": f"Sang {dominant_trait_name.replace('_', ' ').title()}",
                    "kesimpulan": f"Berdasarkan jawabanmu, trait **{dominant_trait_name.replace('_', ' ').title()}** sangat menonjol. Ini berarti {trait_descriptions.get(dominant_trait_name, 'kamu memiliki karakteristik unik.')}",
                    "pujian": f"Kekuatanmu adalah kemampuanmu dalam aspek **{dominant_trait_name.replace('_', ' ').title()}**.",
                    "evaluasi": "Mungkin ada area lain yang perlu kamu kembangkan.",
                    "saran": "Terus eksplorasi dirimu dan pahami kekuatanmu!"
                }
            else:
                 best_match_type = {
                    "name": "Pribadi yang Unik & Misterius",
                    "kesimpulan": "Kami belum bisa menentukan tipe kepribadianmu secara spesifik karena data yang terbatas. Kamu adalah individu yang sangat unik dan menarik!",
                    "pujian": "Keunikanmu adalah kekuatanmu yang sesungguhnya.",
                    "evaluasi": "Mungkin kamu belum menunjukkan semua potensimu, atau kepribadianmu sangat kompleks.",
                    "saran": "Coba ikuti tes lagi dengan lebih detail untuk hasil yang lebih akurat!"
                }


        # --- Tampilan Hasil Akhir ---
        member = channel.guild.get_member(user_id) if channel.guild else interaction.user
        member_name = member.display_name # Menggunakan display_name untuk nama yang lebih ramah

        result_embed = discord.Embed(
            title=f"🎉 Hasil Tes Kepribadianmu, {member_name}!",
            description=f"Dari jawaban-jawabanmu, tampaknya kamu memiliki kecenderungan sebagai:\n\n**{best_match_type['name']}**",
            color=discord.Color.gold() # Warna cerah untuk hasil
        )
        result_embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)

        result_embed.add_field(name="✨ Kesimpulan:", value=best_match_type["kesimpulan"], inline=False)
        result_embed.add_field(name="👍 Pujian Untukmu:", value=best_match_type["pujian"], inline=False)
        result_embed.add_field(name="🔍 Evaluasi:", value=best_match_type["evaluasi"], inline=False)
        result_embed.add_field(name="💡 Saran Pengembangan:", value=best_match_type["saran"], inline=False)
        
        # --- Menampilkan Data Trait ---
        trait_data_text = ""
        
        significant_traits = {trait: score for trait, score in final_scores.items() if score > 0}
        
        if significant_traits:
            sorted_traits = sorted(significant_traits.items(), key=lambda item: item[1], reverse=True)
            sum_of_positive_scores = sum(score for score in significant_traits.values())

            trait_data_text += "**📊 Data Trait Utama:**\n"
            for trait, score in sorted_traits: # Tampilkan semua trait positif
                percentage_of_sum = (score / sum_of_positive_scores * 100) if sum_of_positive_scores > 0 else 0
                trait_description_short = trait_descriptions.get(trait, "Tidak ada deskripsi.").split('.')[0] # Ambil kalimat pertama
                trait_data_text += f"- **{trait.replace('_', ' ').title()}**: {score:.1f} poin ({percentage_of_sum:.1f}%)\n"
                trait_data_text += f"  *_{trait_description_short}._*\n"
                
        # Contoh spesifik untuk Pemarah dan Penyabar
        pemarah_score = final_scores.get('Pemarah', 0)
        penyabar_score = final_scores.get('Penyabar', 0)
        
        if pemarah_score > 0 or penyabar_score > 0:
            total_temper_score = abs(pemarah_score) + abs(penyabar_score) # Pakai abs jika skor bisa negatif
            pemarah_percent = (pemarah_score / total_temper_score * 100) if total_temper_score > 0 else 0
            penyabar_percent = (penyabar_score / total_temper_score * 100) if total_temper_score > 0 else 0
            
            trait_data_text += "\n**Temperamenmu:**\n"
            if pemarah_score > penyabar_score:
                trait_data_text += f"- Kamu cenderung **pemarah** dengan {pemarah_percent:.1f}% kecenderungan. ({trait_descriptions.get('Pemarah', '').split('.')[0]}.)\n"
            elif penyabar_score > pemarah_score:
                trait_data_text += f"- Kamu cenderung sangat **penyabar** dengan {penyabar_percent:.1f}% kecenderungan. ({trait_descriptions.get('Penyabar', '').split('.')[0]}.)\n"
            else:
                trait_data_text += "- Temperamenmu cukup seimbang antara Pemarah dan Penyabar.\n"

        if trait_data_text:
            result_embed.add_field(name="--- Detail Data Trait Anda ---", value=trait_data_text, inline=False)


        result_embed.set_footer(text="Ingat, ini hanyalah hasil tes, bukan diagnosis profesional. Tetaplah menjadi versi terbaik dari dirimu!")

        await channel.send(embed=result_embed)


class QuestionView(View):
    def __init__(self, cog, user_id, question_id, options_data):
        super().__init__(timeout=120) # Timeout setelah 2 menit tanpa interaksi
        self.cog = cog
        self.user_id = user_id
        self.question_id = question_id
        self.options_data = options_data
        self._add_buttons()

    def _add_buttons(self):
        # Tambahkan tombol untuk setiap opsi jawaban
        for option_key, _ in self.options_data.items():
            # Label tombol dibuat dari option_key dengan mengganti underscore jadi spasi dan kapitalisasi awal
            label = option_key.replace('_', ' ').title()
            # custom_id akan digunakan untuk mengidentifikasi tombol mana yang ditekan
            button = Button(label=label, custom_id=f"psikotes_{self.question_id}_{option_key}")
            self.add_item(button)

        # Tambahkan tombol 'Batalkan Tes'
        cancel_button = Button(label="Batalkan Tes", style=discord.ButtonStyle.red, custom_id=f"psikotes_cancel_{self.question_id}")
        self.add_item(cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Pastikan hanya user yang memulai tes yang bisa berinteraksi dengan tombol
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Ini bukan tesmu! Silakan mulai tesmu sendiri dengan `!psikotes`.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        # Ketika view timeout (tidak ada interaksi dalam 2 menit)
        if self.user_id in self.cog.user_states:
            channel = self.cog.bot.get_channel(self.message.channel.id) # Get channel to send message
            if not channel: # Fallback for private messages or specific channel types
                channel = self.message.channel
            await channel.send(f"Tes dibatalkan karena tidak ada respons dari <@{self.user_id}> selama 2 menit. Silakan mulai lagi dengan `!psikotes`.", ephemeral=True)
            del self.cog.user_states[self.user_id]
        
        # Nonaktifkan semua tombol
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)


    @discord.ui.button(label="Placeholder", custom_id="button_placeholder_ignore_this_one", style=discord.ButtonStyle.secondary)
    async def handle_button_click(self, interaction: discord.Interaction, button: Button):
        # Logika ini akan dipicu oleh setiap tombol yang tidak memiliki callback spesifik
        # Custom ID format: "psikotes_{question_id}_{option_key}" atau "psikotes_cancel_{question_id}"
        
        parts = button.custom_id.split('_')
        action = parts[1] # "cancel" atau "qX"
        q_id_from_button = parts[2] # Question ID dari custom_id

        if action == "cancel":
            if interaction.user.id == self.user_id: # Pastikan user yang benar
                # Batalkan tes
                if self.user_id in self.cog.user_states:
                    del self.cog.user_states[self.user_id]
                
                # Nonaktifkan semua tombol di pesan ini
                for item in self.children:
                    item.disabled = True
                await interaction.message.edit(content=f"Tes dibatalkan oleh {interaction.user.mention}.", view=self)
                await interaction.response.send_message("Tes kepribadian dibatalkan.", ephemeral=True)
            else:
                await interaction.response.send_message("Ini bukan tesmu!", ephemeral=True)
            return

        # Jika bukan tombol cancel, berarti ini jawaban pertanyaan
        selected_option_key = '_'.join(parts[3:]) # Rekonstruksi option_key dari custom_id
        
        # Panggil fungsi proses jawaban di cog
        await self.cog._process_answer(interaction, self.user_id, q_id_from_button, selected_option_key)


async def setup(bot):
    await bot.add_cog(Psikotes(bot))
