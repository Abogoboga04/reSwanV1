import discord
from discord.ext import commands, tasks
import json
import random
import asyncio
import os
from datetime import datetime, time, timedelta

# --- Helper Functions (reusable from other cogs) ---
def load_json_from_root(file_path, default_value=None):
    """
    Memuat data JSON dari file yang berada di root direktori proyek bot.
    Menambahkan `default_value` yang lebih fleksibel.
    """
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        full_path = os.path.join(base_dir, file_path)
        os.makedirs(os.path.dirname(os.path.abspath(full_path)), exist_ok=True) # Pastikan direktori ada
        with open(full_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[{datetime.now()}] [DEBUG HELPER] Peringatan: File {full_path} tidak ditemukan. Mengembalikan nilai default.")
        if default_value is not None:
            save_json_to_root(default_value, file_path)
            return default_value
        # Default value for common JSON types
        if 'questions' in file_path or 'sambung_kata_words' in file_path: # Ini untuk jiwabot_questions.json juga
            return []
        if 'bank_data' in file_path or 'level_data' in file_path:
            return {}
        return {} # Fallback
    except json.JSONDecodeError:
        print(f"[{datetime.now()}] [DEBUG HELPER] Peringatan: File {full_path} rusak (JSON tidak valid). Mengembalikan nilai default.")
        if default_value is not None:
            save_json_to_root(default_value, file_path)
            return default_value
        if 'questions' in file_path or 'sambung_kata_words' in file_path:
            return []
        if 'bank_data' in file_path or 'level_data' in file_path:
            return {}
        return {}


def save_json_to_root(data, file_path):
    """Menyimpan data ke file JSON di root direktori proyek."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    full_path = os.path.join(base_dir, file_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)


class JiwaBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # {user_id: {'thread': thread_obj, 'current_q_idx': int, 'scores': {}, 'user_obj': member_obj, 'questions_for_session': [], 'message_for_reaction_vote': msg_obj}}
        self.active_sessions = {}  
        self.questions = load_json_from_root('data/jiwabot_questions.json', default_value=[])
        self.results_config = load_json_from_root('data/jiwabot_results.json', default_value={
            "dimensions": {},
            "advice": [], "critique": [], "evaluation": [], "future_steps": []
        })
        self.admin_role_id = 1255204693391441920 # GANTI DENGAN ID ROLE ADMIN (contoh: 123456789012345678) jika ingin admin diundang ke thread
        
        # Mapping numerical emojis to option keys (A, B)
        self.number_emojis = {
            "1️⃣": "A", 
            "2️⃣": "B"
        }
        self.reverse_number_emojis = {v: k for k, v in self.number_emojis.items()}

        # Initiate cleanup task in case bot restarts unexpectedly
        self._cleanup_threads_task = self.cleanup_stale_threads.start()

    def cog_unload(self):
        # Cancel any running tasks when the cog is unloaded
        if self._cleanup_threads_task:
            self._cleanup_threads_task.cancel()
        print(f"[{datetime.now()}] [JIWABOT] Cog JiwaBot dibongkar. Tugas cleanup dihentikan.")


    @tasks.loop(minutes=30) # Run cleanup every 30 minutes
    async def cleanup_stale_threads(self):
        print(f"[{datetime.now()}] [JIWABOT] Menjalankan tugas pembersihan thread yang macet.")
        # Identify sessions that might be stuck or whose threads exist but bot lost track
        # This is a basic cleanup. More robust would involve saving session state to file.
        guilds_to_check = {} # {guild_id: [channel_id, ...]} to avoid fetching channels multiple times

        # Collect threads that are managed by JiwaBot
        for user_id, session in list(self.active_sessions.items()):
            if session.get('thread') and session['thread'].id:
                try:
                    # Attempt to fetch the thread to see if it's still alive or valid
                    fetched_thread = await self.bot.fetch_channel(session['thread'].id)
                    # If it's a private thread and the participant is no longer in guild/bot restarted mid-session
                    # You might need more complex logic based on your specific 'stuck' criteria.
                    pass # If fetch is successful, thread is still alive and we leave it.
                except discord.NotFound:
                    print(f"[{datetime.now()}] [JIWABOT] Menghapus sesi macet untuk {user_id} karena thread tidak ditemukan.")
                    del self.active_sessions[user_id]
                except Exception as e:
                    print(f"[{datetime.now()}] [JIWABOT ERROR] Error saat membersihkan thread untuk {user_id}: {e}")
                    # Potentially remove session if too many errors


    @cleanup_stale_threads.before_loop
    async def before_cleanup_threads(self):
        await self.bot.wait_until_ready()
        print(f"[{datetime.now()}] [JIWABOT] Menunggu bot siap sebelum memulai tugas pembersihan thread.")


    @commands.command(name="jiwaku", help="Mulai sesi tes kepribadian JiwaBot.")
    @commands.guild_only() # Pastikan hanya bisa di guild (server)
    async def start_personality_test(self, ctx):
        user_id = ctx.author.id

        if user_id in self.active_sessions:
            thread_id = self.active_sessions[user_id]['thread'].id
            return await ctx.send(f"Anda sudah memiliki sesi tes yang sedang berjalan di <#{thread_id}>. Selesaikan sesi Anda saat ini atau tunggu hingga berakhir.", ephemeral=True)

        if not self.questions:
            return await ctx.send("Maaf, bank pertanyaan tes kepribadian tidak ditemukan atau kosong. Silakan hubungi admin bot.", ephemeral=True)
        # Jumlah pertanyaan di JSON harus sama dengan jumlah yang akan diambil (50)
        if len(self.questions) < 50:
            return await ctx.send(f"Maaf, tes membutuhkan minimal 50 pertanyaan. Saat ini hanya ada {len(self.questions)} pertanyaan. Silakan hubungi admin bot.", ephemeral=True)

        # Buat thread privat
        try:
            thread = await ctx.channel.create_thread(
                name=f"Tes-Kepribadian-{ctx.author.name}",
                type=discord.ChannelType.private_thread,
                invitable=False, # Tidak bisa di-invite sembarangan
                auto_archive_duration=60 # Arsip setelah 1 jam tidak aktif
            )
            await thread.add_user(ctx.author) # Tambahkan peserta
            if self.admin_role_id: # Tambahkan admin jika ID role tersedia
                admin_role = ctx.guild.get_role(self.admin_role_id)
                if admin_role:
                    for member in admin_role.members:
                        try:
                            # Check if bot can actually add this user to private thread.
                            # It needs "Manage Threads" permission.
                            # Also, user must allow DMs from server members.
                            await thread.add_user(member)
                        except discord.HTTPException as e:
                            print(f"[{datetime.now()}] [JIWABOT WARNING] Gagal menambahkan admin {member.display_name} ke thread {thread.name}: {e}")
                            # This is a warning, not fatal. Continue.
            
            await ctx.send(f"Tes kepribadian Anda telah dimulai! Silakan lanjutkan di thread privat: <#{thread.id}>", ephemeral=False)
            
        except discord.Forbidden:
            return await ctx.send("Saya tidak memiliki izin untuk membuat private thread. Pastikan saya punya izin 'Manage Threads' dan 'Send Messages in Threads'.", ephemeral=True)
        except Exception as e:
            print(f"[{datetime.now()}] [JIWABOT ERROR] Gagal membuat thread untuk {ctx.author.name}: {e}")
            return await ctx.send(f"Terjadi kesalahan saat memulai sesi: `{e}`. Silakan coba lagi nanti.", ephemeral=True)

        # Inisialisasi semua dimensi skor yang mungkin ada di questions.json
        all_possible_dimensions = self._get_all_dimensions()
        initial_scores = {dim: 0 for dim in all_possible_dimensions}

        self.active_sessions[user_id] = {
            'thread': thread,
            'current_q_idx': 0,
            'scores': initial_scores, 
            'user_obj': ctx.author,
            'questions_for_session': random.sample(self.questions, 50), # Ambil 50 pertanyaan acak
            'message_for_reaction_vote': None, # Pesan untuk reaksi jawaban
            'answered_this_question': False # Flag untuk mencegah double answer
        }
        
        await self._send_question(user_id)


    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore bots and messages outside active session threads (unless it's the command to start)
        # This listener is for general messages. Answers are handled by reactions.
        if message.author.bot or not isinstance(message.channel, discord.Thread):
            return
        
        # Check if the message is in a JiwaBot session thread
        user_id_from_session = None
        for uid, s in self.active_sessions.items():
            if s.get('thread') and s['thread'].id == message.channel.id:
                user_id_from_session = uid
                break

        if not user_id_from_session or message.author.id != user_id_from_session:
            return # Not the session owner, or not a JiwaBot thread

        # If the user sends any text message during a question, it's just general chat.
        # Answers are handled by reactions. We don't process text input as answer here.
        pass


    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        # Ignore bots and reactions not from the session owner
        if user.bot or user.id not in self.active_sessions:
            return

        session = self.active_sessions[user.id]

        # Ensure reaction is in the correct thread and on the current question message
        if reaction.message.channel.id != session['thread'].id or \
           not session.get('message_for_reaction_vote') or \
           reaction.message.id != session['message_for_reaction_vote'].id:
            return

        # Ensure it's a valid choice reaction (1 or 2)
        chosen_option_key = self.number_emojis.get(str(reaction.emoji))
        if chosen_option_key is None:
            try:
                await reaction.remove(user) # Remove invalid reaction
            except discord.Forbidden:
                pass
            return

        # Only process if this is the user's first choice for this question
        if session['answered_this_question']: # Prevents multiple answers for one question
             try:
                 await reaction.remove(user)
             except discord.Forbidden:
                 pass
             return

        # Mark as answered
        session['answered_this_question'] = True

        # Process the answer
        await self._process_answer(user.id, chosen_option_key, reaction.message, user)


    async def _send_question(self, user_id):
        session = self.active_sessions.get(user_id)
        if not session: return

        thread = session['thread']
        q_idx = session['current_q_idx']
        
        if q_idx >= len(session['questions_for_session']):
            await self._end_session(user_id)
            return

        question_data = session['questions_for_session'][q_idx]
        
        embed = discord.Embed(
            title=f"❓ Pertanyaan #{q_idx + 1}/50",
            description=f"**{question_data['question']}**\n\n"
                        f"**1.** {question_data['options']['A']}\n"
                        f"**2.** {question_data['options']['B']}",
            color=discord.Color.blue()
        )
        if 'category' in question_data:
            embed.add_field(name="Kategori", value=question_data['category'], inline=True) 

        # Add reaction instructions
        embed.set_footer(text=f"Silakan bereaksi dengan 1️⃣ atau 2️⃣ untuk memilih jawaban Anda.")

        try:
            question_msg = await thread.send(embed=embed)
            session['message_for_reaction_vote'] = question_msg # Store message for reaction listener

            # Add reactions for options
            await question_msg.add_reaction("1️⃣")
            await question_msg.add_reaction("2️⃣")

            # Reset answered flag for the next question
            session['answered_this_question'] = False
        except discord.Forbidden:
            await thread.send("Saya tidak bisa mengirim atau bereaksi di thread ini. Pastikan izin saya sudah benar (Manage Threads, Send Messages in Threads, Add Reactions).")
            await self._end_session(user_id)
        except Exception as e:
            print(f"[{datetime.now()}] [JIWABOT ERROR] Gagal mengirim pertanyaan ke {session['user_obj'].name}: {e}")
            await thread.send(f"Terjadi kesalahan saat menampilkan pertanyaan: `{e}`. Sesi dihentikan.")
            await self._end_session(user_id)

    async def _process_answer(self, user_id, chosen_option_key, question_message, reacting_user):
        session = self.active_sessions.get(user_id)
        if not session: return

        q_idx = session['current_q_idx']
        question_data = session['questions_for_session'][q_idx]
        
        # Accumulate scores
        selected_scores = question_data['scores'].get(chosen_option_key, {})
        for dimension, points in selected_scores.items():
            session['scores'][dimension] = session['scores'].get(dimension, 0) + points
        
        session['current_q_idx'] += 1

        # Remove all reactions from the processed question message to prevent further interaction
        try:
            await question_message.clear_reactions()
        except discord.Forbidden:
            print(f"[{datetime.now()}] [JIWABOT WARNING] Bot tidak bisa menghapus reaksi dari pesan pertanyaan di thread {question_message.id}.")
        except Exception as e:
            print(f"[{datetime.now()}] [JIWABOT ERROR] Error menghapus reaksi dari pesan {question_message.id}: {e}")

        # Send next question or end session
        await self._send_question(user_id)


    def _get_all_dimensions(self):
        """Collects all unique dimension keys from questions to initialize scores."""
        dimensions = set()
        for q_data in self.questions:
            for option_key in q_data['options']: # Iterate through A, B
                if option_key in q_data['scores']: # Check if scores exist for this option key
                    for dim in q_data['scores'][option_key].keys():
                        dimensions.add(dim)
        return list(dimensions)


    async def _end_session(self, user_id):
        session = self.active_sessions.pop(user_id, None)
        if not session: return

        thread = session['thread']
        user_obj = session['user_obj']
        final_scores = session['scores']

        await thread.send(f"✅ Tes Kepribadian Anda telah selesai, {user_obj.mention}!\nMemproses hasil Anda...", embed=discord.Embed(title="Tes Selesai!", description="Terima kasih telah berpartisipasi!", color=discord.Color.green()))
        
        # Give some processing time illusion
        await asyncio.sleep(3)

        # Generate and send results to thread and DM
        await self._analyze_and_present_results(thread, user_obj, final_scores)

        # Delete the thread after a delay
        # Thread will be deleted after 3 minutes (180 seconds)
        asyncio.create_task(self._delete_thread_after_delay(thread, 180, user_obj))

    async def _delete_thread_after_delay(self, thread, delay, user_obj):
        await asyncio.sleep(delay)
        try:
            await thread.delete()
            print(f"[{datetime.now()}] [JIWABOT] Thread tes kepribadian {thread.name} untuk {user_obj.display_name} dihapus.")
        except discord.NotFound:
            print(f"[{datetime.now()}] [JIWABOT] Thread {thread.name} sudah tidak ditemukan (mungkin sudah dihapus manual).")
        except discord.Forbidden:
            print(f"[{datetime.now()}] [JIWABOT ERROR] Bot tidak memiliki izin untuk menghapus thread {thread.name} untuk {user_obj.display_name}.")
            # Send a DM to the user if thread cannot be deleted
            try:
                await user_obj.send(f"⚠️ Maaf, saya tidak bisa menghapus thread tes kepribadian Anda ({thread.mention}). Mohon hapus secara manual untuk menjaga privasi.")
            except discord.Forbidden:
                print(f"[{datetime.now()}] [JIWABOT ERROR] Gagal mengirim DM ke {user_obj.display_name} tentang kegagalan hapus thread.")
        except Exception as e:
            print(f"[{datetime.now()}] [JIWABOT ERROR] Error menghapus thread {thread.name} untuk {user_obj.display_name}: {e}")


    async def _analyze_and_present_results(self, thread, user_obj, final_scores):
        """
        Menganalisis skor dan menyajikan hasil psikotes secara rinci ke thread dan DM user.
        """
        if not self.results_config.get('dimensions'):
            await thread.send("Maaf, konfigurasi hasil tes tidak ditemukan. Tidak bisa menganalisis hasil.")
            # Attempt to send to user DM as well
            try:
                await user_obj.send("Maaf, konfigurasi hasil tes tidak ditemukan. Tidak bisa menganalisis hasil.")
            except discord.Forbidden:
                pass
            return

        results_embed = discord.Embed(
            title=f"📊 Laporan Psikotes: Profil Kepribadian Diri",
            description=f"Berikut adalah hasil analisis kepribadian untuk **{user_obj.display_name}**:",
            color=discord.Color.dark_teal()
        )
        results_embed.set_thumbnail(url=user_obj.avatar.url if user_obj.avatar else None)
        results_embed.set_author(name=f"Oleh JiwaBot", icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None)

        # --- Bagian 1: Identitas Diri (Profil Discord) ---
        created_at = user_obj.created_at.strftime("%d %B %Y")
        joined_at = user_obj.joined_at.strftime("%d %B %Y")
        profile_value = (
            f"• **Nama Lengkap Discord**: {user_obj.name} (ID: {user_obj.id})\n"
            f"• **Display Name (Nickname)**: {user_obj.display_name}\n"
            f"• **Bergabung Discord**: {created_at}\n"
            f"• **Bergabung Server**: {joined_at}"
        )
        results_embed.add_field(name="📋 Identitas Diri", value=profile_value, inline=False)


        # --- Bagian 2: Kecenderungan Sosial (Introvert/Ekstrovert/Ambivert) ---
        intro_score = final_scores.get("introvert", 0)
        extro_score = final_scores.get("ekstrovert", 0)
        intro_extro_relative_score = intro_score - extro_score 

        social_type = "Tidak Terdefinisi"
        social_description = "Analisis lebih lanjut diperlukan untuk mengidentifikasi kecenderungan sosial Anda."

        if "introvert_ekstrovert" in self.results_config['dimensions']:
            for threshold in self.results_config['dimensions']['introvert_ekstrovert']['thresholds']:
                if threshold['min_score'] <= intro_extro_relative_score <= threshold['max_score']:
                    social_type = threshold['type']
                    social_description = threshold['description']
                    break
        
        results_embed.add_field(
            name=f"2. Kecenderungan Sosial Utama: **{social_type}**",
            value=f"Anda menunjukkan karakteristik yang dominan sebagai individu dengan kecenderungan **{social_type}**. \n_{social_description}_",
            inline=False
        )
        results_embed.add_field(name="Detail Skor Sosial", value=f"Poin Introvert: **{intro_score}** | Poin Ekstrovert: **{extro_score}**", inline=False)


        # --- Bagian 3: Profil Sifat & Sikap Mendalam ---
        sifat_texts = []
        identified_traits_for_reco = [] # Collect names for recommendations later

        if "sifat_dasar" in self.results_config['dimensions']:
            sorted_sifat_categories = sorted(
                self.results_config['dimensions']['sifat_dasar']['categories'],
                key=lambda cat: final_scores.get(cat['name'].lower().replace(" ", "_"), 0), # Score key is lowercase, snake_case
                reverse=True
            )
            for category in sorted_sifat_categories:
                # Convert category name to score key format (e.g., "Percaya Diri" -> "percaya_diri")
                dim_name_lower = category['name'].lower().replace(" ", "_") 
                current_dim_score = final_scores.get(dim_name_lower, 0)
                
                if current_dim_score >= category.get('min_score', 0): 
                    sifat_texts.append(f"• **{category['name']}** (Skor: {current_dim_score}): {category['description']}")
                    identified_traits_for_reco.append(category['name']) # Add to list for recommendations
        
        if sifat_texts:
            results_embed.add_field(name="3. Analisis Sifat & Sikap Dominan", value="\n".join(sifat_texts), inline=False)
        else:
            results_embed.add_field(name="3. Analisis Sifat & Sikap Dominan", value="Berdasarkan respons, Anda memiliki beragam sifat dan sikap yang cukup seimbang dan adaptif, tidak ada yang terlalu dominan menonjol. Ini menunjukkan fleksibilitas dalam menghadapi berbagai situasi.", inline=False)

        # --- Bagian 4: Gaya Interaksi / Bagaimana Anda Berinteraksi dengan Dunia ---
        gaya_interaksi_texts = []
        if "gaya_interaksi" in self.results_config['dimensions']:
            sorted_gaya_categories = sorted(
                self.results_config['dimensions']['gaya_interaksi']['categories'],
                key=lambda cat: final_scores.get(cat['name'].lower().replace(" ", "_"), 0), # Score key is lowercase, snake_case
                reverse=True
            )
            for category in sorted_gaya_categories:
                dim_name_lower = category['name'].lower().replace(" ", "_")
                current_dim_score = final_scores.get(dim_name_lower, 0)

                if current_dim_score >= category.get('min_score', 0):
                    gaya_interaksi_texts.append(f"• **{category['name']}** (Skor: {current_dim_score}): {category['description']}")
                    identified_traits_for_reco.append(category['name']) # Add to list for recommendations
        
        if gaya_interaksi_texts:
            results_embed.add_field(name="4. Gaya Interaksi & Peran dalam Lingkungan", value="\n".join(gaya_interaksi_texts), inline=False)
        else:
            results_embed.add_field(name="4. Gaya Interaksi & Peran dalam Lingkungan", value="Gaya interaksi Anda cukup fleksibel dan unik, sehingga tidak masuk dalam satu kategori dominan berdasarkan tes ini. Anda dapat menyesuaikan diri dengan berbagai peran.", inline=False)


        # --- Bagian 5: Rekomendasi Komprehensif ---
        
        # Collect all relevant types/traits for recommendations
        # This includes the primary social type AND all identified dominant traits/interaction styles
        all_relevant_types_for_reco = [social_type] + identified_traits_for_reco 

        recommendations_combined = {
            'advice': set(),    # Use set to avoid duplicate recommendations if multiple traits match
            'critique': set(),
            'evaluation': set(),
            'future_steps': set()
        }

        # Iterate through each recommendation category (advice, critique, etc.)
        for rec_key in recommendations_combined.keys():
            if self.results_config.get(rec_key): # Check if the category exists in results_config
                for rec_item in self.results_config[rec_key]:
                    # If this recommendation item is relevant to any identified type/trait
                    if rec_item['for_type'] in all_relevant_types_for_reco:
                        recommendations_combined[rec_key].add(rec_item['text']) # Add to set to maintain uniqueness
        
        # Convert sets to sorted lists for final presentation
        advice_val = "\n".join(f"• {text}" for text in sorted(list(recommendations_combined['advice']))) if recommendations_combined['advice'] else "Tidak ada saran spesifik yang teridentifikasi dari tes ini."
        critique_val = "\n".join(f"• {text}" for text in sorted(list(recommendations_combined['critique']))) if recommendations_combined['critique'] else "Tidak ada area pengembangan spesifik yang teridentifikasi dari tes ini."
        evaluation_val = "\n".join(f"• {text}" for text in sorted(list(recommendations_combined['evaluation']))) if recommendations_combined['evaluation'] else "Evaluasi potensi diri memerlukan analisis lebih lanjut atau tes yang lebih komprehensif."
        future_steps_val = "\n".join(f"• {text}" for text in sorted(list(recommendations_combined['future_steps']))) if recommendations_combined['future_steps'] else "Langkah ke depan dapat disesuaikan dengan tujuan personal Anda dan eksplorasi diri berkelanjutan."


        results_embed.add_field(name="5. Rekomendasi: Saran Peningkatan Diri", value=advice_val, inline=False)
        results_embed.add_field(name="6. Rekomendasi: Area Pengembangan & Tantangan", value=critique_val, inline=False)
        results_embed.add_field(name="7. Rekomendasi: Potensi & Evaluasi Diri", value=evaluation_val, inline=False)
        results_embed.add_field(name="8. Rekomendasi: Rencana Tindak Lanjut", value=future_steps_val, inline=False)

        results_embed.set_footer(text="Analisis ini bersifat indikatif dan tidak menggantikan asesmen profesional. Gunakan sebagai panduan awal untuk eksplorasi diri.")

        # Send to thread
        await thread.send(embed=results_embed)

        # Send to user DM
        try:
            await user_obj.send(embed=results_embed)
            print(f"[{datetime.now()}] [JIWABOT] Laporan hasil tes kepribadian dikirim ke DM {user_obj.display_name}.")
        except discord.Forbidden:
            print(f"[{datetime.now()}] [JIWABOT WARNING] Gagal mengirim laporan hasil ke DM {user_obj.display_name} (DM ditutup).")
            await thread.send(f"⚠️ Maaf, saya tidak dapat mengirim laporan lengkap ke DM Anda, {user_obj.mention}, karena DM Anda mungkin tertutup. Laporan tetap tersedia di sini.", delete_after=30)
        except Exception as e:
            print(f"[{datetime.now()}] [JIWABOT ERROR] Error mengirim laporan hasil ke DM {user_obj.display_name}: {e}")


async def setup(bot):
    await bot.add_cog(JiwaBot(bot))
