import discord
from discord.ext import commands, tasks
import json
import random
import asyncio
import os
from datetime import datetime, time, timedelta
import string
import pytz # Import pytz untuk zona waktu

# Impor Music cog (pastikan file music.py ada di folder yang sama dengan multigame.py, yaitu 'cogs')
# from .music import Music 

# --- Helper Functions to handle JSON data from the bot's root directory ---
def load_json_from_root(file_path, default_value=None):
    """
    Memuat data JSON dari file yang berada di root direktori proyek bot.
    Menambahkan `default_value` yang lebih fleksibel.
    """
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        full_path = os.path.join(base_dir, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True) # Pastikan direktori 'data/' ada
        with open(full_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Peringatan: File {full_path} tidak ditemukan. Menggunakan nilai default.")
        if default_value is not None:
            return default_value
        # Mengembalikan struktur data default tergantung jenis file jika default_value tidak disediakan
        if 'bank_data.json' in file_path or 'level_data.json' in file_path or 'sick_users_cooldown.json' in file_path or 'protected_users.json' in file_path or 'inventory.json' in file_path:
            return {}
        elif 'werewolf_roles.json' in file_path or 'werewolf_config.json' in file_path or 'wheel_of_mad_fate.json' in file_path:
            return {} # Akan ditangani oleh inisialisasi cog
        return [] # Default untuk daftar seperti soal kuis, lokasi, dll.
    except json.JSONDecodeError:
        print(f"Peringatan: File {full_path} rusak (JSON tidak valid). Menggunakan nilai default.")
        if default_value is not None:
            return default_value
        if 'bank_data.json' in file_path or 'level_data.json' in file_path or 'sick_users_cooldown.json' in file_path or 'protected_users.json' in file_path or 'inventory.json' in file_path:
            return {}
        elif 'werewolf_roles.json' in file_path or 'werewolf_config.json' in file_path or 'wheel_of_mad_fate.json' in file_path:
            return {}
        return []

def save_json_to_root(data, file_path):
    """Menyimpan data ke file JSON di root direktori proyek."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    full_path = os.path.join(base_dir, file_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

# --- Discord UI Components for Werewolf Role Setup ---
class RoleSelect(discord.ui.Select):
    def __init__(self, role_name, current_value, max_value):
        self.role_name = role_name
        options = [
            discord.SelectOption(label=str(i), value=str(i), default=(i == current_value))
            for i in range(max_value + 1)
        ]
        super().__init__(placeholder=f"Jumlah {role_name} ({current_value})", options=options, custom_id=f"select_role_{role_name}")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view: WerewolfRoleSetupView = self.view
        selected_value = int(self.values[0])
        view.selected_roles[self.role_name] = selected_value
        await view.update_message(interaction.message)

class URLInput(discord.ui.TextInput):
    def __init__(self, label, custom_id, placeholder, default_value=""):
        super().__init__(
            label=label,
            placeholder=placeholder,
            custom_id=custom_id,
            style=discord.TextStyle.short,
            default=default_value,
            required=False
        )

class WerewolfMediaSetupModal(discord.ui.Modal):
    def __init__(self, game_cog, current_global_config):
        super().__init__(title="Atur Media Werewolf (Global)")
        self.game_cog = game_cog
        self.current_global_config = current_global_config
        
        current_image_urls = current_global_config.get('image_urls', {})
        current_audio_urls = current_global_config.get('audio_urls', {})

        self.add_item(URLInput("Game Start Image URL (GIF)", "url_game_start_img", "URL untuk awal game (GIF/PNG/JPG)", current_image_urls.get('game_start_image_url', '')))
        self.add_item(URLInput("Night Phase Image URL (GIF)", "url_night_phase_img", "URL untuk fase malam (GIF/PNG/JPG)", current_image_urls.get('night_phase_image_url', '')))
        self.add_item(URLInput("Day Phase Image URL (GIF)", "url_day_phase_img", "URL untuk fase siang (GIF/PNG/JPG)", current_image_urls.get('day_phase_image_url', '')))
        self.add_item(URLInput("Night Resolution Image URL (GIF)", "url_night_res_img", "URL untuk resolusi malam (korban) (GIF/PNG/JPG)", current_image_urls.get('night_resolution_image_url', '')))

        self.add_item(URLInput("Game Start Audio URL (MP3/WebM)", "url_game_start_audio", "URL audio untuk awal game", current_audio_urls.get('game_start_audio_url', '')))
        self.add_item(URLInput("Night Phase Audio URL (MP3/WebM)", "url_night_phase_audio", "URL audio untuk fase malam", current_audio_urls.get('night_phase_audio_url', '')))
        self.add_item(URLInput("Day Phase Audio URL (MP3/WebM)", "url_day_phase_audio", "URL audio untuk fase siang", current_audio_urls.get('day_phase_audio_url', '')))
        self.add_item(URLInput("Vote Phase Audio URL (MP3/WebM)", "url_vote_phase_audio", "URL audio untuk fase voting", current_audio_urls.get('vote_phase_audio_url', '')))
        self.add_item(URLInput("Game End Audio URL (MP3/WebM)", "url_game_end_audio", "URL audio untuk akhir game", current_audio_urls.get('game_end_audio_url', '')))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        global_config_ref = self.game_cog.global_werewolf_config.setdefault('default_config', {})
        
        global_config_ref['image_urls'] = {
            'game_start_image_url': self.children[0].value or None,
            'night_phase_image_url': self.children[1].value or None,
            'day_phase_image_url': self.children[2].value or None,
            'night_resolution_image_url': self.children[3].value or None
        }

        global_config_ref['audio_urls'] = {
            'game_start_audio_url': self.children[4].value or None,
            'night_phase_audio_url': self.children[5].value or None,
            'day_phase_audio_url': self.children[6].value or None,
            'vote_phase_audio_url': self.children[7].value or None,
            'game_end_audio_url': self.children[8].value or None
        }
        
        save_json_to_root(self.game_cog.global_werewolf_config, 'data/global_werewolf_config.json')

        view_for_update = next((v for v in self.game_cog.bot.cached_views if isinstance(v, WerewolfRoleSetupView) and v.channel_id == interaction.channel_id), None)
        if view_for_update:
            view_for_update.image_urls = global_config_ref['image_urls']
            view_for_update.audio_urls = global_config_ref['audio_urls']
            await view_for_update.update_message(interaction.message)

        await interaction.followup.send("URL gambar dan audio global berhasil disimpan!", ephemeral=True)


class WerewolfRoleSetupView(discord.ui.View):
    def __init__(self, game_cog, channel_id, total_players, current_config):
        super().__init__(timeout=300) 
        self.game_cog = game_cog
        self.channel_id = channel_id
        self.total_players = total_players
        self.selected_roles = current_config.get('roles', {}).copy()
        
        global_media_config = game_cog.global_werewolf_config.get('default_config', {})
        self.image_urls = global_media_config.get('image_urls', {}).copy() 
        self.audio_urls = global_media_config.get('audio_urls', {}).copy()
        self.available_roles = game_cog.werewolf_roles_data.get('roles', {})
        
        self._add_role_selects()
        
        self.add_item(discord.ui.Button(label="Atur Media Game (Global)", style=discord.ButtonStyle.secondary, custom_id="setup_media", row=4))
        self.add_item(discord.ui.Button(label="Selesai Mengatur", style=discord.ButtonStyle.success, custom_id="finish_role_setup", row=4))

    def _add_role_selects(self):
        for item in list(self.children):
            if isinstance(item, RoleSelect):
                self.remove_item(item)
        
        roles_to_display = [role for role in self.available_roles.keys() if role != "Warga Polos"]
        
        for i, role_name in enumerate(roles_to_display):
            current_value = self.selected_roles.get(role_name, 0)
            self.add_item(RoleSelect(role_name, current_value, self.total_players))

    def calculate_balance(self):
        total_special_roles_count = sum(self.selected_roles.values())
        werewolf_count = self.selected_roles.get('Werewolf', 0)
        villager_count = self.total_players - total_special_roles_count
        
        warnings = []
        if total_special_roles_count > self.total_players:
            warnings.append("⚠️ Jumlah peran khusus melebihi total pemain! Kurangi beberapa peran.")
        if werewolf_count == 0 and self.total_players > 0:
            warnings.append("⛔ Tidak ada Werewolf! Game mungkin tidak valid atau membosankan.")
        if werewolf_count > 0 and werewolf_count >= (self.total_players / 2):
            warnings.append("⛔ Jumlah Werewolf terlalu banyak (>= 50% pemain)! Game mungkin tidak seimbang.")
        if villager_count < 1 and self.total_players > werewolf_count:
            warnings.append("⚠️ Tidak ada Warga Polos murni tersisa! Game tidak valid.")
        if self.total_players < 3: 
            warnings.append("⚠️ Jumlah pemain terlalu sedikit untuk distribusi peran yang bermakna.")
        
        return villager_count, warnings

    async def update_message(self, message):
        villager_count, warnings = self.calculate_balance()
        
        embed = discord.Embed(
            title="🐺 Pengaturan Peran Werewolf (Global) 🐺",
            description=f"Total Pemain: **{self.total_players}**\n\nAtur jumlah peran untuk game ini:",
            color=discord.Color.blue()
        )
        
        roles_text = ""
        for role_name in self.available_roles.keys():
            if role_name == "Warga Polos":
                continue
            count = self.selected_roles.get(role_name, 0)
            roles_text += f"- **{role_name}**: `{count}`\n"
        roles_text += f"- **Warga Polos**: `{villager_count}` (Otomatis Dihitung)\n\n"
        
        if warnings:
            roles_text += "\n" + "\n".join(warnings)
            embed.color = discord.Color.red()
        else:
            embed.color = discord.Color.green()

        embed.add_field(name="Komposisi Peran Saat Ini", value=roles_text, inline=False)
        
        image_summary = ""
        if self.image_urls.get('game_start_image_url'): image_summary += "✅ Game Start Image\n"
        if self.image_urls.get('night_phase_image_url'): image_summary += "✅ Night Image\n"
        if self.image_urls.get('day_phase_image_url'): image_summary += "✅ Day Image\n"
        if self.image_urls.get('night_resolution_image_url'): image_summary += "✅ Night Resolution Image\n"
        if image_summary:
            embed.add_field(name="Status Gambar/GIF (Global)", value=image_summary, inline=False)

        audio_summary = ""
        if self.audio_urls.get('game_start_audio_url'): audio_summary += "🎵 Game Start Audio\n"
        if self.audio_urls.get('night_phase_audio_url'): audio_summary += "🎵 Night Audio\n"
        if self.audio_urls.get('day_phase_audio_url'): audio_summary += "🎵 Day Audio\n"
        if self.audio_urls.get('vote_phase_audio_url'): audio_summary += "🎵 Vote Audio\n"
        if self.audio_urls.get('game_end_audio_url'): audio_summary += "🎵 Game End Audio\n"
        if audio_summary:
            embed.add_field(name="Status Audio (Global - MP3/WebM)", value=audio_summary, inline=False)
        
        self._add_role_selects() 
        
        await message.edit(embed=embed, view=self)

    @discord.ui.button(label="Atur Media Game (Global)", style=discord.ButtonStyle.secondary, custom_id="setup_media", row=4)
    async def setup_media_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        game_state = self.game_cog.werewolf_game_states.get(self.channel_id)
        if not game_state or interaction.user.id != game_state['host'].id:
            await interaction.response.send_message("Hanya host game Werewolf yang aktif di channel ini yang bisa mengatur media global.", ephemeral=True)
            return
        
        await interaction.response.send_modal(WerewolfMediaSetupModal(self.game_cog, self.game_cog.global_werewolf_config.get('default_config', {})))

    @discord.ui.button(label="Selesai Mengatur", style=discord.ButtonStyle.success, custom_id="finish_role_setup", row=4)
    async def finish_setup_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        game_state = self.game_cog.werewolf_game_states.get(self.channel_id)
        if not game_state or interaction.user.id != game_state['host'].id:
            await interaction.response.send_message("Hanya host yang bisa menyelesaikan pengaturan peran.", ephemeral=True)
            return

        await interaction.response.defer()
        
        villager_count, warnings = self.calculate_balance()
        if warnings and any("⚠️" in w for w in warnings) or any("⛔" in w for w in warnings):
            await interaction.followup.send("Ada masalah kritis dengan komposisi peran yang dipilih. Mohon perbaiki sebelum melanjutkan.", ephemeral=True)
            return

        self.game_cog.global_werewolf_config.setdefault('default_config', {})['roles'] = self.selected_roles
        save_json_to_root(self.game_cog.global_werewolf_config, 'data/global_werewolf_config.json')
        
        for item in self.children:
            item.disabled = True
        
        embed = interaction.message.embeds[0]
        embed.description = f"**Komposisi peran untuk game ini telah diatur (Global)!**\n\nTotal Pemain: **{self.total_players}**"
        embed.color = discord.Color.green()
        embed.set_footer(text="Host bisa gunakan !forcestartwerewolf untuk memulai game!")

        await interaction.message.edit(embed=embed, view=self)
        self.stop() 

class TicTacToeView(discord.ui.View):
    def __init__(self, game_cog, player1, player2):
        super().__init__(timeout=300)
        self.game_cog = game_cog
        self.player1 = player1
        self.player2 = player2
        self.current_player = player1
        self.board = [None] * 9
        self.winner = None
        for i in range(9):
            self.add_item(TicTacToeButton(row=i // 3))

    async def update_board(self, interaction: discord.Interaction):
        winning_combinations = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]
        for combo in winning_combinations:
            if self.board[combo[0]] is not None and self.board[combo[0]] == self.board[combo[1]] == self.board[combo[2]]:
                self.winner = self.current_player
                break
        is_draw = all(spot is not None for spot in self.board) and self.winner is None
        embed = interaction.message.embeds[0]
        if self.winner:
            embed.description = f"🎉 **{self.winner.mention} Menang!** 🎉"
            embed.color = discord.Color.gold()
            await self.game_cog.give_rewards_with_bonus_check(self.winner, interaction.guild.id, interaction.channel)
            for item in self.children: item.disabled = True
        elif is_draw:
            embed.description = "⚖️ **Permainan Berakhir Seri!**"
            embed.color = discord.Color.light_grey()
            for item in self.children: item.disabled = True
        else:
            self.current_player = self.player2 if self.current_player == self.player1 else self.player1
            embed.description = f"Giliran: **{self.current_player.mention}**"
        await interaction.message.edit(embed=embed, view=self)
        if self.winner or is_draw:
            self.stop()
            self.game_cog.end_game_cleanup(interaction.channel.id)

class TicTacToeButton(discord.ui.Button):
    def __init__(self, row: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", row=row)

    async def callback(self, interaction: discord.Interaction):
        view: TicTacToeView = self.view
        if interaction.user != view.current_player:
            return await interaction.response.send_message("Bukan giliranmu!", ephemeral=True)
        await interaction.response.defer()
        self.style = discord.ButtonStyle.danger if view.current_player == view.player1 else discord.ButtonStyle.success
        self.label = "X" if view.current_player == view.player1 else "O"
        self.disabled = True
        button_index = self.view.children.index(self)
        self.view.board[button_index] = self.label
        await view.update_board(interaction)

class UltimateGameArena(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = set()
        # last_spy_id digunakan untuk mencegah pemilihan mata-mata yang sama di sesi berikutnya
        self.last_spy_id = None       

        # --- Game States (Diperluas untuk mencakup semua game Anda) ---
        self.spyfall_game_states = {} # {channel_id: {'spy': member, 'location': str, 'players': [members], 'discussion_start_time': datetime, 'vote_in_progress': bool}}
        self.werewolf_join_queues = {} # Untuk Werewolf (jika diimplementasikan secara penuh)
        self.werewolf_game_states = {} # Untuk Werewolf (jika diimplementasikan secara penuh)
        self.horse_race_games = {} # Untuk Balap Kuda
        self.wheel_of_fate_config = {} # Untuk Roda Takdir Gila
        self.wheel_of_fate_data = load_json_from_root('data/wheel_of_mad_fate.json', default_value={"players_stats": {}}) # Data statistik Roda Takdir

        # --- Data Game (Diambil dari backup Anda) ---
        self.siapakah_aku_data = load_json_from_root('data/siapakah_aku.json', default_value=[])
        self.pernah_gak_pernah_data = load_json_from_root('data/pernah_gak_pernah.json', default_value=[])
        self.hitung_cepat_data = load_json_from_root('data/hitung_cepat.json', default_value=[])
        self.mata_mata_locations = load_json_from_root('data/mata_mata_locations.json', default_value=[])
        self.deskripsi_data = load_json_from_root('data/deskripsi_tebak.json', default_value=[])
        self.perang_otak_data = load_json_from_root('data/perang_otak.json', default_value={}).get('questions', [])
        self.cerita_pembuka_data = load_json_from_root('data/cerita_pembuka.json', default_value=[])
        self.tekateki_harian_data = load_json_from_root('data/teka_teki_harian.json', default_value=[])

        # --- Konfigurasi Werewolf Global (Diambil dari versi UltimateGameArena yang lebih lengkap) ---
        self.global_werewolf_config = load_json_from_root(
            'data/global_werewolf_config.json', 
            default_value={
                "default_config": {
                    "roles": {}, 
                    "image_urls": {
                        "game_start_image_url": None, "night_phase_image_url": None,
                        "day_phase_image_url": None, "night_resolution_image_url": None
                    }, 
                    "audio_urls": {
                        "game_start_audio_url": None, "night_phase_audio_url": None,
                        "day_phase_audio_url": None, "vote_phase_audio_url": None,
                        "game_end_audio_url": None
                    }
                }
            }
        )
        self.werewolf_roles_data = load_json_from_root('data/werewolf_roles.json', default_value={"roles": {}})

        # --- Konfigurasi Balap Kuda (Diambil dari versi UltimateGameArena yang lebih lengkap) ---
        self.horse_names = ["merah", "biru", "hijau", "kuning"] 
        self.horse_emojis = ["🔴", "🔵", "🟢", "🟡"] 

        # --- Hadiah & Cooldown ---
        self.reward = {"rsw": 50, "exp": 100}
        self.wheel_spin_cost = 200 # Biaya putar roda takdir
        self.daily_puzzle = None
        self.daily_puzzle_solvers = set()
        self.daily_puzzle_channel_id = 765140300145360896 # Ganti dengan ID channel Anda

        # --- Interaksi Cog Lain ---
        self.dunia_cog = None # Akan diisi di on_ready listener dari DuniaHidup.py
        self.music_cog = None # Akan diisi di on_ready listener dari music.py

        self.post_daily_puzzle.start() # Memulai task loop untuk teka-teki harian

    @commands.Cog.listener()
    async def on_ready(self):
        # Pastikan bot sudah siap sebelum mengakses cog lain
        await self.bot.wait_until_ready()
        
        # Ambil referensi ke cog DuniaHidup
        self.dunia_cog = self.bot.get_cog('DuniaHidup')
        if not self.dunia_cog:
            print(f"[{datetime.now()}] Peringatan: Cog 'DuniaHidup' tidak ditemukan. Beberapa fitur game (anomali, mimic) mungkin tidak berfungsi.")

        # Ambil referensi ke cog Music
        self.music_cog = self.bot.get_cog('Music')
        if not self.music_cog:
            print(f"[{datetime.now()}] Peringatan: Cog 'Music' tidak ditemukan. Fungsi audio Werewolf mungkin tidak berfungsi.")

    def cog_unload(self):
        """Dipanggil saat cog dibongkar, membatalkan semua task loop."""
        self.post_daily_puzzle.cancel()
        
        # Batalkan task game yang mungkin sedang berjalan untuk cleanup yang lebih bersih
        for channel_id in list(self.spyfall_game_states.keys()):
            game_state = self.spyfall_game_states.get(channel_id)
            if game_state and 'game_task' in game_state and not game_state['game_task'].done():
                game_state['game_task'].cancel()
            # end_game_cleanup akan dipanggil oleh game_task atau logic game itu sendiri
            # atau di cleanup umum jika perlu
        
        # Contoh cleanup untuk game lain yang mungkin memiliki game_task aktif
        for channel_id in list(self.werewolf_game_states.keys()):
            game_state = self.werewolf_game_states.get(channel_id)
            if game_state and game_state.get('voice_client'):
                self.bot.loop.create_task(game_state['voice_client'].disconnect())
            if game_state and 'game_task' in game_state and not game_state['game_task'].done():
                game_state['game_task'].cancel()
        
        for channel_id in list(self.horse_race_games.keys()):
            game_state = self.horse_race_games.get(channel_id)
            if game_state and 'game_task' in game_state and not game_state['game_task'].done():
                game_state['game_task'].cancel()

    def get_anomaly_multiplier(self):
        """Mengambil multiplier anomali EXP dari DuniaHidup cog jika ada."""
        if self.dunia_cog and hasattr(self.dunia_cog, 'active_anomaly') and self.dunia_cog.active_anomaly and self.dunia_cog.active_anomaly.get('type') == 'exp_boost':
            return self.dunia_cog.active_anomaly.get('effect', {}).get('multiplier', 1)
        return 1

    async def give_rewards_with_bonus_check(self, user: discord.Member, guild_id: int, channel: discord.TextChannel = None, custom_rsw: int = None, custom_exp: int = None):
        """
        Memberikan hadiah RSWN dan EXP kepada pengguna, dengan pengecekan bonus anomali.
        Args:
            user (discord.Member): Pengguna yang akan menerima hadiah.
            guild_id (int): ID Guild tempat hadiah diberikan.
            channel (discord.TextChannel, optional): Channel untuk mengirim pesan bonus. Defaults to None.
            custom_rsw (int, optional): Jumlah RSWN kustom. Jika None, pakai self.reward['rsw'].
            custom_exp (int, optional): Jumlah EXP kustom. Jika None, pakai self.reward['exp'].
        """
        anomaly_multiplier = self.get_anomaly_multiplier()
        
        rsw_to_give = custom_rsw if custom_rsw is not None else self.reward['rsw']
        exp_to_give = custom_exp if custom_exp is not None else self.reward['exp']

        final_rsw = int(rsw_to_give * anomaly_multiplier)
        final_exp = int(exp_to_give * anomaly_multiplier)
        
        self.give_rewards_base(user, guild_id, final_rsw, final_exp)

        if anomaly_multiplier > 1 and channel:
            await channel.send(f"✨ **BONUS ANOMALI!** {user.mention} mendapatkan hadiah yang dilipatgandakan!", delete_after=15)

    def give_rewards_base(self, user: discord.Member, guild_id: int, rsw_amount: int, exp_amount: int):
        """Fungsi dasar untuk menyimpan hadiah ke file JSON."""
        user_id_str, guild_id_str = str(user.id), str(guild_id)
        
        bank_data = load_json_from_root('data/bank_data.json', default_value={})
        bank_data.setdefault(user_id_str, {'balance': 0, 'debt': 0})['balance'] += rsw_amount
        save_json_to_root(bank_data, 'data/bank_data.json')
        
        level_data = load_json_from_root('data/level_data.json', default_value={})
        guild_data = level_data.setdefault(guild_id_str, {})
        user_data = guild_data.setdefault(user_id_str, {'exp': 0, 'level': 1})
        user_data.setdefault('exp', 0) 
        user_data['exp'] += exp_amount
        save_json_to_root(level_data, 'data/level_data.json')

    async def start_game_check(self, ctx):
        """Memeriksa apakah ada game lain yang aktif di channel."""
        if ctx.channel.id in self.active_games:
            await ctx.send("Maaf, sudah ada permainan lain di channel ini. Tunggu selesai ya!", ephemeral=True)
            return False
        self.active_games.add(ctx.channel.id)
        return True
    
    async def _check_mimic_attack(self, ctx):
        """Memeriksa apakah ada serangan mimic yang memblokir game di channel ini."""
        # Memblokir total game jika ada serangan mimic global di channel ini
        if self.dunia_cog and self.dunia_cog.active_mimic_attack_channel_id == ctx.channel.id:
            await ctx.send("💥 **SERANGAN MIMIC!** Permainan tidak bisa dimulai karena mimic sedang mengamuk di channel ini!", ephemeral=True)
            return True
        return False

    async def _check_mimic_effect(self, ctx):
        """Memeriksa apakah event mimic yang memengaruhi jawaban sedang aktif di channel ini."""
        # Asumsi DuniaHidup cog memiliki `mimic_effect_active_channel_id` untuk tujuan ini
        if self.dunia_cog and self.dunia_cog.mimic_effect_active_channel_id == ctx.channel.id:
            return True
        return False

    def end_game_cleanup(self, channel_id, game_type=None):
        """Membersihkan state game setelah game berakhir."""
        self.active_games.discard(channel_id)
        print(f"[{datetime.now()}] end_game_cleanup called for channel {channel_id}, type {game_type}. Active games: {self.active_games}")

        # Pembersihan spesifik untuk setiap jenis game
        if game_type == 'spyfall' and channel_id in self.spyfall_game_states:
            # last_spy_id sudah diset di _spyfall_game_flow atau tuduh/ungkap_lokasi
            del self.spyfall_game_states[channel_id]
        elif game_type == 'werewolf' and channel_id in self.werewolf_game_states:
            game_state = self.werewolf_game_states.get(channel_id)
            if game_state and game_state.get('voice_client'):
                self.bot.loop.create_task(game_state['voice_client'].disconnect())
            if game_state and 'game_task' in game_state and not game_state['game_task'].done():
                game_state['game_task'].cancel()
            del self.werewolf_game_states[channel_id]
        elif game_type == 'horse_race' and channel_id in self.horse_race_games:
            game_state = self.horse_race_games.get(channel_id)
            if game_state and 'game_task' in game_state and not game_state['game_task'].done():
                game_state['game_task'].cancel()
            del self.horse_race_games[channel_id]
        elif game_type == 'siapakahaku': 
             if self.dunia_cog and self.dunia_cog.quiz_punishment_active:
                pass 
             else:
                pass
        elif game_type == 'tictactoe': # TicTacToe cleanup
            pass # View akan timeout sendiri dan cleanup.

        # Cleanup untuk antrean join Werewolf (jika masih relevan)
        guild_id_to_remove = None
        for g_id, channels_data in list(self.werewolf_join_queues.items()):
            if channel_id in channels_data:
                del channels_data[channel_id]
                if not channels_data:
                    guild_id_to_remove = g_id
                break
        if guild_id_to_remove:
            del self.werewolf_join_queues[guild_id_to_remove]


    # --- GAME 0: WEREWOLF (Simulasi) ---
    @commands.command(name="startwerewolf", help="Mulai game Werewolf (contoh, perlu integrasi lebih lanjut).")
    @commands.cooldown(1, 30, commands.BucketType.channel) # Cooldown dipertahankan
    async def start_werewolf_game_example(self, ctx):
        if await self._check_mimic_attack(ctx): return # Cek mimic attack
        if not await self.start_game_check(ctx): return
        
        self.werewolf_game_states[ctx.channel.id] = {
            'host': ctx.author,
            'players': [ctx.author], # Akan diisi dengan pemain dari VC
            'voice_client': None,
            'game_task': None
        }
        
        if not ctx.author.voice or not ctx.author.voice.channel:
            self.end_game_cleanup(ctx.channel.id, game_type='werewolf')
            return await ctx.send("Untuk bermain Werewolf, kamu dan pemain lain harus berada di **voice channel** yang sama!", ephemeral=True)

        vc_channel = ctx.author.voice.channel
        game_players = [m for m in vc_channel.members if not m.bot]
        # Ini akan mengambil semua user non-bot di VC sebagai pemain
        self.werewolf_game_states[ctx.channel.id]['players'] = game_players

        players_in_vc = [m for m in vc_channel.members if not m.bot and m in game_players]
        
        if len(players_in_vc) < 3:
            self.end_game_cleanup(ctx.channel.id, game_type='werewolf')
            return await ctx.send("Jumlah pemain di voice channel terlalu sedikit untuk memulai game Werewolf. Minimal 3 pemain aktif!", ephemeral=True)

        # Bagian Music cog dikomentari sesuai diskusi, bisa diaktifkan jika Music cog ada dan berfungsi
        # if not self.music_cog: 
        #     self.end_game_cleanup(ctx.channel.id, game_type='werewolf')
        #     return await ctx.send("Cog musik bot tidak aktif. Tidak bisa memulai Werewolf dengan fitur audio.", ephemeral=True)
        
        try:
            if not ctx.voice_client or ctx.voice_client.channel != vc_channel:
                await vc_channel.connect()
                await ctx.send(f"Bot bergabung ke voice channel: **{vc_channel.name}** untuk Werewolf.", delete_after=10)
            
            game_state = self.werewolf_game_states.setdefault(ctx.channel.id, {})
            game_state['voice_client'] = ctx.voice_client

        except discord.Forbidden:
            self.end_game_cleanup(ctx.channel.id, game_type='werewolf')
            return await ctx.send("Bot tidak memiliki izin untuk bergabung ke voice channel Anda. Pastikan saya memiliki izin `Connect` dan `Speak`.", ephemeral=True)
        except Exception as e:
            self.end_game_cleanup(ctx.channel.id, game_type='werewolf')
            return await ctx.send(f"Terjadi kesalahan saat bot bergabung ke voice channel: `{e}`", ephemeral=True)

        await ctx.send("Game Werewolf akan dimulai! Bersiaplah...")
        
        game_task = self.bot.loop.create_task(self._werewolf_game_flow(ctx, ctx.channel.id, players_in_vc))
        self.werewolf_game_states[ctx.channel.id]['game_task'] = game_task


    async def _werewolf_game_flow(self, ctx, channel_id, players):
        try:
            await self._send_werewolf_visual(ctx.channel, "game_start")
            # await self._play_werewolf_audio(ctx.channel, "game_start_audio_url") 
            
            await asyncio.sleep(7)
            await ctx.send("Malam telah tiba... Para Werewolf beraksi!")
            await self._send_werewolf_visual(ctx.channel, "night_phase")
            # await self._play_werewolf_audio(ctx.channel, "night_phase_audio_url")

            await asyncio.sleep(15)
            await ctx.send("Pagi telah tiba! Siapa yang menjadi korban malam ini?")
            await self._send_werewolf_visual(ctx.channel, "night_resolution")
            
            await asyncio.sleep(3)
            await ctx.send("Mari kita diskusikan!")
            await self._send_werewolf_visual(ctx.channel, "day_phase")
            # await self._play_werewolf_audio(ctx.channel, "day_phase_audio_url")
            
            await asyncio.sleep(10)
            await ctx.send("Waktunya voting!")
            # await self._play_werewolf_audio(ctx.channel, "vote_phase_audio_url")

            await asyncio.sleep(5)
            await ctx.send("Game Werewolf berakhir. Selamat kepada para pemenang!")
            # await self._play_werewolf_audio(ctx.channel, "game_end_audio_url")
            
        except asyncio.CancelledError:
            print(f"[{datetime.now()}] Werewolf game flow for channel {channel_id} was cancelled.")
            await ctx.send("Game Werewolf dihentikan lebih awal.")
        except Exception as e:
            print(f"[{datetime.now()}] Error in Werewolf game flow for channel {channel_id}: {e}")
            await ctx.send(f"Terjadi kesalahan fatal pada game Werewolf: `{e}`. Game dihentikan.")
        finally:
            self.end_game_cleanup(channel_id, game_type='werewolf')

    # --- Fungsi Visual & Audio Werewolf (Dipertahankan) ---
    async def _send_werewolf_visual(self, channel: discord.TextChannel, phase: str):
        global_config = self.global_werewolf_config.get('default_config', {})
        image_urls = global_config.get('image_urls', {})

        visual_url = None
        if phase == "game_start": visual_url = image_urls.get('game_start_image_url')
        elif phase == "night_phase": visual_url = image_urls.get('night_phase_image_url')
        elif phase == "day_phase": visual_url = image_urls.get('day_phase_image_url')
        elif phase == "night_resolution": visual_url = image_urls.get('night_resolution_image_url')

        embed = discord.Embed(
            title=f"Fase Werewolf: {phase.replace('_', ' ').title()}",
            description="Detail informasi tentang fase game ini akan muncul di sini.",
            color=discord.Color.dark_purple()
        )

        if visual_url and visual_url.lower().endswith(('.gif', '.png', '.jpg', '.jpeg')):
            embed.set_image(url=visual_url)
            await channel.send(embed=embed)
        else:
            await channel.send(embed=embed)
            if visual_url:
                await channel.send("ℹ️ URL gambar yang diberikan tidak valid atau bukan format gambar/GIF yang didukung. Mengirim pesan tanpa gambar.")
            else:
                await channel.send("ℹ️ URL gambar untuk fase ini belum diatur.")


    async def _play_werewolf_audio(self, text_channel: discord.TextChannel, audio_type: str):
        game_state = self.werewolf_game_states.get(text_channel.id)
        if not game_state or not game_state.get('voice_client'):
            print(f"[{datetime.now()}] Tidak ada voice client untuk channel {text_channel.id} atau game tidak aktif.")
            return

        voice_client = game_state['voice_client']
        global_config = self.global_werewolf_config.get('default_config', {})
        audio_urls = global_config.get('audio_urls', {})

        audio_url = None
        if audio_type == "game_start_audio_url": audio_url = audio_urls.get('game_start_audio_url')
        elif audio_type == "night_phase_audio_url": audio_url = audio_urls.get('night_phase_audio_url')
        elif audio_type == "day_phase_audio_url": audio_url = audio_urls.get('day_phase_audio_url')
        elif audio_type == "vote_phase_audio_url": audio_url = audio_urls.get('vote_phase_audio_url')
        elif audio_type == "game_end_audio_url": audio_url = audio_urls.get('game_end_audio_url')

        # Asumsi Music.YTDLSource sudah diimpor jika Music cog digunakan
        # if audio_url and self.music_cog and hasattr(Music, 'YTDLSource'): 
        #     try:
        #         if voice_client.is_playing() or voice_client.is_paused():
        #             voice_client.stop()
        #         
        #         source = await Music.YTDLSource.from_url(audio_url, loop=self.bot.loop, stream=True)
        #         voice_client.play(source, after=lambda e: print(f'[{datetime.now()}] Player error in Werewolf audio: {e}') if e else None)
        #         print(f"[{datetime.now()}] Memutar audio Werewolf '{audio_type}' di {voice_client.channel.name}: {source.title if hasattr(source, 'title') else 'Unknown Title'}")
        #     except Exception as e:
        #         print(f"[{datetime.now()}] Gagal memutar audio Werewolf '{audio_type}': {e}")
        #         await text_channel.send(f"⚠️ Maaf, gagal memutar audio untuk fase ini: `{e}`")
        # elif not self.music_cog:
        #     print(f"[{datetime.now()}] Music cog tidak ditemukan, tidak dapat memutar audio Werewolf.")
        # else:
        #     print(f"[{datetime.now()}] URL audio untuk '{audio_type}' tidak diatur.")
        pass # Placeholder agar fungsi tidak kosong


    @commands.command(name="stopwerewolfaudio", help="Hentikan audio Werewolf yang sedang diputar.")
    async def stop_werewolf_audio(self, ctx):
        game_state = self.werewolf_game_states.get(ctx.channel.id)
        if not game_state or (ctx.author.id != game_state.get('host', None) and not ctx.author.guild_permissions.manage_channels):
            return await ctx.send("Hanya host game Werewolf atau moderator yang bisa menghentikan audio.", ephemeral=True)
        
        voice_client = game_state.get('voice_client')
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            await ctx.send("Audio Werewolf dihentikan.")
        else:
            await ctx.send("Tidak ada audio Werewolf yang sedang diputar.")

    # --- GAME 1: SIAPAKAH AKU? ---
    @commands.command(name="siapakahaku", help="Mulai sesi tebak-tebakan 'Siapakah Aku?' dengan 10 soal.")
    @commands.cooldown(1, 60, commands.BucketType.channel)
    async def siapakahaku(self, ctx):
        if await self._check_mimic_attack(ctx): return
        if not await self.start_game_check(ctx): return
        
        mimic_effect_active = await self._check_mimic_effect(ctx) # Cek efek mimic
        
        if not ctx.guild.me.guild_permissions.moderate_members:
            await ctx.send("⚠️ **Peringatan Izin:** Saya tidak memiliki izin `Moderate Members` untuk memberikan timeout jika ada yang spam jawaban.")
        
        if len(self.siapakah_aku_data) < 10:
            await ctx.send("Tidak cukup soal di database untuk memulai sesi (butuh minimal 10).", ephemeral=True)
            self.end_game_cleanup(ctx.channel.id)
            return
            
        questions = random.sample(self.siapakah_aku_data, 10) # 10 Pertanyaan per sesi
        leaderboard = {} # Melacak skor pemain di sesi ini
        
        game_start_embed = discord.Embed(
            title="🕵️‍♂️ Sesi Kuis 'Siapakah Aku?' Dimulai!",
            description="Akan ada **10 soal** berturut-turut. Petunjuk akan muncul setiap **10 detik**.",
            color=0x1abc9c
        )
        await ctx.send(embed=game_start_embed)
        await asyncio.sleep(5)

        for i, item in enumerate(questions):
            word = item['name'].lower()
            clues = item['clues']
            attempts = {} # Melacak percobaan salah per pengguna untuk soal ini
            timed_out_users_this_round = set() # Melacak pengguna yang di-timeout hanya untuk ronde ini
            winner = None
            round_over = False

            embed = discord.Embed(
                title=f"SOAL #{i+1} dari 10",
                description=f"Kategori: **{item['category']}**",
                color=0x1abc9c
            )
            embed.set_footer(text="Anda punya 5x kesempatan menjawab salah per soal! Jika lebih, Anda di-timeout.")
            msg = await ctx.send(embed=embed)

            for clue_index, clue in enumerate(clues):
                if round_over: break # Keluar dari loop petunjuk jika ada pemenang

                # Menggunakan set_field_at untuk update jika ada, add_field jika baru
                if clue_index < len(embed.fields):
                    embed.set_field_at(
                        index=clue_index,
                        name=f"Petunjuk #{clue_index + 1}", 
                        value=f"_{clue}_", 
                        inline=False
                    )
                else:
                    embed.add_field(
                        name=f"Petunjuk #{clue_index + 1}", 
                        value=f"_{clue}_", 
                        inline=False
                    )
                await msg.edit(embed=embed)

                try:
                    async def listen_for_answer():
                        nonlocal winner, round_over
                        while True:
                            message = await self.bot.wait_for(
                                "message", 
                                check=lambda m: m.channel == ctx.channel and not m.author.bot # Jawaban LANGSUNG
                            )
                            if message.author.id in timed_out_users_this_round: 
                                continue 

                            if message.content.lower() == word:
                                winner = message.author
                                round_over = True
                                return
                            # Logika untuk jawaban 'mimic'
                            elif mimic_effect_active and message.content.lower() == "mimic":
                                winner = message.author
                                round_over = True
                                await ctx.send(f"🎉 **KAMU BERHASIL MENANGKAP MIMIC!** {message.author.mention} menebak 'Mimic' dengan tepat! Hadiah tersembunyi untukmu!")
                                # Hadiah 3x lipat
                                await self.give_rewards_with_bonus_check(message.author, ctx.guild.id, ctx.channel, custom_rsw=self.reward['rsw']*3, custom_exp=self.reward['exp']*3) 
                                return
                            else:
                                await message.add_reaction("❌")
                                user_attempts = attempts.get(message.author.id, 0) + 1
                                attempts[message.author.id] = user_attempts
                                
                                # Batas kesempatan 5x (dari backup)
                                if user_attempts >= 5: 
                                    timed_out_users_this_round.add(message.author.id)
                                    try:
                                        await message.author.timeout(timedelta(seconds=60), reason="Melebihi batas percobaan menjawab di game 'Siapakah Aku?'")
                                        await ctx.send(f"🚨 {message.author.mention}, Anda kehabisan kesempatan menjawab di ronde ini & di-timeout sementara (60 detik).", delete_after=10)
                                    except discord.Forbidden:
                                        await ctx.send(f"🚨 {message.author.mention}, Anda kehabisan kesempatan menjawab di ronde ini.", delete_after=10)
                                    except Exception as e:
                                        print(f"Error giving timeout to {message.author}: {e}")
                                        await ctx.send(f"Gagal memberi timeout {message.author.mention}. {e}", delete_after=10)
                    
                    await asyncio.wait_for(listen_for_answer(), timeout=10.0)

                except asyncio.TimeoutError:
                    if clue_index == len(clues) - 1:
                        await ctx.send(f"Waktu habis! Jawaban yang benar adalah **{item['name']}**.")
                    else:
                        continue

            # Update leaderboard dan berikan hadiah (jika belum menang karena mimic)
            if winner and winner.name not in [lb_name for lb_name, _ in leaderboard.items()]:
                await self.give_rewards_with_bonus_check(winner, ctx.guild.id, ctx.channel)
                leaderboard[winner.name] = leaderboard.get(winner.name, 0) + 1
            # Kasus jika sudah menang karena 'Mimic' dan namanya sudah ada di leaderboard, tidak perlu ditambahkan lagi
            elif winner and winner.name in [lb_name for lb_name, _ in leaderboard.items()] and winner.name != "Mimic_Caught":
                pass


            for user_id in timed_out_users_this_round:
                member = ctx.guild.get_member(user_id)
                if member:
                    try:
                        # Pembersihan timeout hanya jika tidak ada hukuman kuis monster aktif dari DuniaHidup
                        if self.dunia_cog and self.dunia_cog.quiz_punishment_active:
                            pass 
                        else:
                            await member.timeout(None, reason="Ronde game 'Siapakah Aku?' telah berakhir.")
                    except discord.Forbidden: 
                        print(f"Bot tidak memiliki izin untuk mengakhiri timeout {member.name}.")
                    except Exception as e:
                        print(f"Error removing timeout for {member.name}: {e}")

            if i < len(questions) - 1:
                await ctx.send(f"Soal berikutnya dalam **5 detik**...", delete_after=4.5)
                await asyncio.sleep(5)
        
        if leaderboard:
            sorted_leaderboard = sorted(leaderboard.items(), key=lambda item: item[1], reverse=True)
            leaderboard_text = "\n".join([f"{rank}. {name}: **{score}** poin" for rank, (name, score) in enumerate(sorted_leaderboard, 1)])
            final_embed = discord.Embed(title="🏆 Papan Skor Akhir 'Siapakah Aku?'", description=leaderboard_text, color=0xffd700)
            await ctx.send(embed=final_embed)
        else:
            await ctx.send("Sesi game berakhir tanpa ada pemenang.")
            
        self.end_game_cleanup(ctx.channel.id, game_type='siapakahaku')
    
    # --- GAME 2: PERNAH GAK PERNAH ---
    @commands.command(name="pernahgak", help="Mulai sesi 'Pernah Gak Pernah' dengan 10 pernyataan.")
    @commands.cooldown(1, 60, commands.BucketType.channel)
    async def pernahgak(self, ctx):
        if await self._check_mimic_attack(ctx): return
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("Kamu harus berada di voice channel untuk memulai game ini.", ephemeral=True)
        vc = ctx.author.voice.channel
        members = [m for m in vc.members if not m.bot]
        if len(members) < 2:
            return await ctx.send("Game ini butuh minimal 2 orang di voice channel.", ephemeral=True)
        if not await self.start_game_check(ctx): return
        
        if len(self.pernah_gak_pernah_data) < 10:
            await ctx.send("Tidak cukup pernyataan di database untuk memulai sesi (butuh minimal 10).", ephemeral=True)
            self.end_game_cleanup(ctx.channel.id)
            return

        statements = random.sample(self.pernah_gak_pernah_data, 10) # 10 Pernyataan per sesi
        overall_rewarded_users = set() # Melacak user yang sudah dapat hadiah di sesi ini
        
        game_start_embed = discord.Embed(
            title="🤔 Sesi 'Pernah Gak Pernah' Dimulai!",
            description="Akan ada **10 pernyataan** berturut-turut. Berikan reaksimu!",
            color=0xf1c40f
        )
        await ctx.send(embed=game_start_embed)
        await asyncio.sleep(3)

        for i, statement in enumerate(statements):
            embed = discord.Embed(
                title=f"PERNYATAAN #{i+1} dari 10",
                description=f"## _{statement}_",
                color=0xf1c40f
            )
            embed.set_footer(text="Jawab dengan jujur menggunakan reaksi di bawah! Waktu 20 detik.")
            msg = await ctx.send(embed=embed)
            await msg.add_reaction("✅"); await msg.add_reaction("❌")
            await asyncio.sleep(20) # Waktu untuk bereaksi

            try:
                cached_msg = await ctx.channel.fetch_message(msg.id)
                pernah_count, gak_pernah_count = 0, 0
                round_rewarded_users = set() # User yang dapat hadiah di ronde ini

                for reaction in cached_msg.reactions:
                    if str(reaction.emoji) == "✅":
                        async for user in reaction.users():
                            if not user.bot and user.id in [m.id for m in members] and user.id not in round_rewarded_users:
                                pernah_count = reaction.count - 1 # Menghitung setelah bot mereaksi
                                await self.give_rewards_with_bonus_check(user, ctx.guild.id, ctx.channel)
                                round_rewarded_users.add(user.id)
                    elif str(reaction.emoji) == "❌":
                        async for user in reaction.users():
                            if not user.bot and user.id in [m.id for m in members] and user.id not in round_rewarded_users:
                                gak_pernah_count = reaction.count - 1 # Menghitung setelah bot mereaksi
                                await self.give_rewards_with_bonus_check(user, ctx.guild.id, ctx.channel)
                                round_rewarded_users.add(user.id)
                
                overall_rewarded_users.update(round_rewarded_users) # Tambahkan ke set total

                result_embed = discord.Embed(title=f"Hasil Pernyataan #{i+1}", color=0xf1c40f)
                result_embed.description = (
                    f"Untuk pernyataan:\n**_{statement}_**\n\n"
                    f"✅ **{pernah_count} orang** mengaku pernah.\n"
                    f"❌ **{gak_pernah_count} orang** mengaku tidak pernah."
                )
                await ctx.send(embed=result_embed)
                if round_rewarded_users:
                    await ctx.send(f"Pemain yang berpartisipasi di ronde ini ({len(round_rewarded_users)} orang) telah mendapatkan hadiah.")
                else:
                    await ctx.send("Tidak ada yang berpartisipasi di ronde ini.")

            except discord.NotFound:
                await ctx.send("Pesan pernyataan tidak ditemukan untuk ronde ini.")
            except Exception as e:
                print(f"Error di pernahgak, ronde {i+1}: {e}")
                await ctx.send(f"Terjadi kesalahan di ronde ini: `{e}`")

            if i < len(statements) - 1:
                await ctx.send(f"Pernyataan berikutnya dalam **5 detik**...", delete_after=4.5)
                await asyncio.sleep(5)
        
        await ctx.send(f"🎉 **Sesi 'Pernah Gak Pernah' berakhir!** Total {len(overall_rewarded_users)} pemain telah mendapatkan hadiah.")
        self.end_game_cleanup(ctx.channel.id, game_type='pernahgak')

    # --- GAME 3: HITUNG CEPAT ---
    @commands.command(name="hitungcepat", help="Mulai sesi 'Hitung Cepat' dengan 10 soal matematika.")
    @commands.cooldown(1, 15, commands.BucketType.channel)
    async def hitungcepat(self, ctx):
        if await self._check_mimic_attack(ctx): return
        if not await self.start_game_check(ctx): return
        
        mimic_effect_active = await self._check_mimic_effect(ctx) # Cek efek mimic
        
        if not self.hitung_cepat_data or len(self.hitung_cepat_data) < 10:
            await ctx.send("Data untuk game Hitung Cepat tidak cukup atau formatnya salah (butuh minimal 10 soal).", ephemeral=True)
            self.end_game_cleanup(ctx.channel.id, game_type='hitungcepat')
            return

        questions = random.sample(self.hitung_cepat_data, 10) # 10 Soal per sesi
        leaderboard = {} # Melacak skor pemain di sesi ini
        
        game_start_embed = discord.Embed(
            title="🧮 Sesi 'Hitung Cepat' Dimulai!",
            description="Akan ada **10 soal matematika** berturut-turut. Jawablah secepat mungkin!",
            color=0xe74c3c
        )
        await ctx.send(embed=game_start_embed)
        await asyncio.sleep(5)

        for i, item in enumerate(questions):
            problem, answer = item['problem'], str(item['answer'])
            winner = None
            
            embed = discord.Embed(title=f"SOAL #{i+1} dari 10", description=f"Selesaikan soal ini!\n\n## `{problem} = ?`", color=0xe74c3c)
            msg = await ctx.send(embed=embed)

            try:
                async def listen_for_math_answer():
                    nonlocal winner
                    while True:
                        message = await self.bot.wait_for("message", check=lambda m: m.channel == ctx.channel and not m.author.bot) # Jawaban LANGSUNG
                        if message.content.strip() == answer: 
                            winner = message.author
                            return message
                        # Logika untuk jawaban 'mimic'
                        elif mimic_effect_active and message.content.lower() == "mimic":
                            winner = message.author
                            await ctx.send(f"🎉 **KAMU BERHASIL MENANGKAP MIMIC!** {message.author.mention} menebak 'Mimic' dengan tepat! Hadiah tersembunyi untukmu!")
                            # Hadiah 3x lipat
                            await self.give_rewards_with_bonus_check(message.author, ctx.guild.id, ctx.channel, custom_rsw=self.reward['rsw']*3, custom_exp=self.reward['exp']*3) 
                            return message # Anggap ini kemenangan ronde, meskipun bukan jawaban soal
                        else:
                            # Hanya beri reaksi X jika jawabannya terlihat seperti angka (untuk menghindari spam karakter)
                            if message.content.strip().replace('-', '').replace('.', '').isdigit(): 
                                await message.add_reaction("❌")
                
                winner_msg = await asyncio.wait_for(listen_for_math_answer(), timeout=30.0) # Waktu menjawab 30 detik
                winner = winner_msg.author
                
                # Berikan hadiah normal jika jawaban asli yang benar, karena 'mimic' sudah ditangani di atas
                if winner_msg.content.strip().lower() == answer:
                    await self.give_rewards_with_bonus_check(winner, ctx.guild.id, ctx.channel)
                    await ctx.send(f"⚡ **Luar Biasa Cepat!** {winner.mention} menjawab **{answer}** dengan benar dan mendapat hadiah!")
                # else: Jika jawaban mimic, hadiah sudah diberikan di atas, tidak perlu pesan lagi
                
                leaderboard[winner.name] = leaderboard.get(winner.name, 0) + 1 # Tambahkan ke leaderboard

            except asyncio.TimeoutError:
                await ctx.send(f"Waktu habis! Jawaban yang benar adalah **{answer}**.")
            except Exception as e:
                print(f"Error di hitungcepat, soal {i+1}: {e}")
                await ctx.send(f"Terjadi kesalahan di soal ini: `{e}`")

            if i < len(questions) - 1:
                await ctx.send(f"Soal berikutnya dalam **5 detik**...", delete_after=4.5)
                await asyncio.sleep(5)
        
        if leaderboard:
            sorted_leaderboard = sorted(leaderboard.items(), key=lambda item: item[1], reverse=True)
            leaderboard_text = "\n".join([f"{rank}. {name}: **{score}** poin" for rank, (name, score) in enumerate(sorted_leaderboard, 1)])
            final_embed = discord.Embed(title="🏆 Papan Skor Akhir 'Hitung Cepat'!", description=leaderboard_text, color=0xffd700)
            await ctx.send(embed=final_embed)
        else:
            await ctx.send("Sesi game berakhir tanpa ada pemenang.")

        self.end_game_cleanup(ctx.channel.id, game_type='hitungcepat')

    # --- GAME 4: PERANG OTAK (Placeholder) ---
    @commands.command(name="perangotak", help="Mulai game Family Feud.")
    @commands.cooldown(1, 60, commands.BucketType.channel)
    async def perangotak(self, ctx):
        if await self._check_mimic_attack(ctx): return
        if not await self.start_game_check(ctx): return
        
        # mimic_effect_active = await self._check_mimic_effect(ctx) # Cek efek mimic, tanpa pesan di sini
        
        await ctx.send("Fitur **Perang Otak** sedang dalam pengembangan! Nantikan update selanjutnya. 🚧", ephemeral=True)
        # Jika mimic_effect_active, logika game di sini akan disesuaikan
        # Contoh: Menambahkan jawaban 'Mimic' yang valid jika game ini sudah berfungsi
        # if mimic_effect_active:
        #     # Implementasi logika khusus Perang Otak di sini untuk jawaban 'Mimic'
        #     pass

        self.end_game_cleanup(ctx.channel.id, game_type='perangotak')

    # --- GAME 5: CERITA BERSAMBUNG ---
    @commands.command(name="cerita", help="Mulai game membuat cerita bersama.")
    @commands.cooldown(1, 60, commands.BucketType.channel)
    async def cerita(self, ctx):
        if await self._check_mimic_attack(ctx): return
        if not await self.start_game_check(ctx): return

        vc = ctx.author.voice.channel if ctx.author.voice else None
        if not vc or len(vc.members) < 2:
            self.end_game_cleanup(ctx.channel.id, game_type='cerita')
            return await ctx.send("Ayo kumpul di voice channel dulu (minimal 2 orang) buat bikin cerita!", ephemeral=True)

        players = [m for m in vc.members if not m.bot]
        random.shuffle(players)
        
        if not self.cerita_pembuka_data or not isinstance(self.cerita_pembuka_data, list):
            await ctx.send("Data untuk cerita pembuka tidak ditemukan atau formatnya salah.", ephemeral=True)
            self.end_game_cleanup(ctx.channel.id, game_type='cerita')
            return

        story = [random.choice(self.cerita_pembuka_data)]
        
        embed = discord.Embed(title="📜 Mari Membuat Cerita!", color=0x2ecc71)
        embed.description = f"**Kalimat Pembuka:**\n> {story[0]}"
        embed.set_footer(text="Setiap orang mendapat giliran untuk menambahkan satu kalimat.")
        await ctx.send(embed=embed)
        await asyncio.sleep(3)

        for i, player in enumerate(players):
            await ctx.send(f"Giliran {player.mention}, lanjutkan ceritanya! (Waktu 30 detik)")
            def check(m):
                return m.author == player and m.channel == ctx.channel
            try:
                msg = await self.bot.wait_for('message', timeout=30.0, check=check)
                story.append(msg.content)
                await msg.add_reaction("✅")
            except asyncio.TimeoutError:
                story.append(f"({player.display_name} terdiam kebingungan...)")
        
        final_story = " ".join(story)
        final_embed = discord.Embed(title="📚 Inilah Cerita Kita!", description=f"> {final_story}", color=0x2ecc71)
        await ctx.send(embed=final_embed)
        await ctx.send("Kisah yang unik! Semua yang berpartisipasi mendapat hadiah!")
        for p in players:
            await self.give_rewards_with_bonus_check(p, ctx.guild.id, ctx.channel)
        
        self.end_game_cleanup(ctx.channel.id, game_type='cerita')
        
    # --- GAME 6: TIC-TAC-TOE ---
    @commands.command(name="tictactoe", help="Tantang temanmu bermain Tic-Tac-Toe.")
    @commands.cooldown(1, 10, commands.BucketType.channel)
    async def tictactoe(self, ctx, opponent: discord.Member):
        if await self._check_mimic_attack(ctx): return
        if opponent.bot or opponent == ctx.author:
            return await ctx.send("Kamu tidak bisa bermain melawan bot atau dirimu sendiri.", ephemeral=True)
        if not await self.start_game_check(ctx): return
        
        view = TicTacToeView(self, ctx.author, opponent)
        embed = discord.Embed(title="❌⭕ Tic-Tac-Toe ❌⭕", description=f"Giliran: **{ctx.author.mention}**", color=discord.Color.blue())
        embed.add_field(name=f"Player 1 (X)", value=ctx.author.mention, inline=True)
        embed.add_field(name=f"Player 2 (O)", value=opponent.mention, inline=True)
        await ctx.send(content=f"{opponent.mention}, kamu ditantang oleh {ctx.author.mention}!", embed=embed, view=view)

    # --- GAME 7: TEKA-TEKI HARIAN ---
    @tasks.loop(time=time(hour=5, minute=0, tzinfo=pytz.timezone('Asia/Jakarta'))) # Menggunakan pytz
    async def post_daily_puzzle(self):
        await self.bot.wait_until_ready()
        now = datetime.now(pytz.timezone('Asia/Jakarta')) # Menggunakan pytz
        target_time = now.replace(hour=5, minute=0, second=0, microsecond=0)
        
        if now > target_time:
            target_time += timedelta(days=1)
        
        time_until_post = (target_time - now).total_seconds()
        
        if time_until_post > 0:
            await asyncio.sleep(time_until_post)

        if not self.tekateki_harian_data: 
            print(f"[{datetime.now()}] Peringatan: Data teka-teki harian tidak ditemukan atau kosong.")
            return
        
        self.daily_puzzle = random.choice(self.tekateki_harian_data)
        self.daily_puzzle_solvers.clear()
        
        channel = self.bot.get_channel(self.daily_puzzle_channel_id)
        if channel:
            embed = discord.Embed(title="🤔 Teka-Teki Harian!", description=f"**Teka-teki untuk hari ini:**\n\n> {self.daily_puzzle['riddle']}", color=0x99aab5)
            embed.set_footer(text="Gunakan !jawab <jawabanmu> untuk menebak!")
            await channel.send(embed=embed)

    @post_daily_puzzle.before_loop
    async def before_daily_puzzle(self):
        await self.bot.wait_until_ready()

    @commands.command(name="jawab", help="Jawab teka-teki harian.")
    async def jawab(self, ctx, *, answer: str):
        if not self.daily_puzzle: return await ctx.send("Belum ada teka-teki untuk hari ini. Sabar ya!")
        if ctx.author.id in self.daily_puzzle_solvers: return await ctx.send("Kamu sudah menjawab dengan benar hari ini!", ephemeral=True)
            
        if answer.lower() == self.daily_puzzle['answer'].lower():
            self.daily_puzzle_solvers.add(ctx.author.id)
            await self.give_rewards_with_bonus_check(ctx.author, ctx.guild.id, ctx.channel)
            await ctx.message.add_reaction("✅")
            await ctx.send(f"🎉 Selamat {ctx.author.mention}! Jawabanmu benar!")
        else:
            await ctx.message.add_reaction("❌")

    # --- GAME 8: TARUHAN BALAP KUDA ---
    @commands.command(name="balapankuda", help="Mulai taruhan balap kuda.")
    @commands.cooldown(1, 120, commands.BucketType.channel)
    async def balapankuda(self, ctx):
        if await self._check_mimic_attack(ctx): return
        if not await self.start_game_check(ctx): return
        
        channel_id = ctx.channel.id
        self.horse_race_games[channel_id] = {
            'status': 'betting',
            'bets': {}, 
            'horses': {name: {'emoji': self.horse_emojis[i], 'progress': 0} for i, name in enumerate(self.horse_names)},
            'race_message': None,
            'winner_horse': None,
            'players_who_bet': set(),
            'game_task': None
        }
        game_state = self.horse_race_games[channel_id]

        embed = discord.Embed(title="🏇 Taruhan Balap Kuda Dimulai!", color=0xf1c40f)
        embed.description = "Pasang taruhanmu pada kuda jagoanmu! Waktu taruhan: **60 detik**.\n\n"
        horse_list = "\n".join([f"{data['emoji']} **Kuda {name.capitalize()}**" for name, data in game_state['horses'].items()])
        embed.add_field(name="Daftar Kuda", value=horse_list, inline=False)
        embed.set_footer(text="Gunakan !taruhan <jumlah> <warna_kuda>")
        
        await ctx.send(embed=embed)
        
        game_task = self.bot.loop.create_task(self._horse_race_game_flow(ctx, channel_id, game_state))
        self.horse_race_games[channel_id]['game_task'] = game_task


    async def _horse_race_game_flow(self, ctx, channel_id, game_state):
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            print(f"[{datetime.now()}] Horse race betting phase for channel {channel_id} was cancelled.")
            return
        
        try:
            game_state['status'] = 'racing'
            if not game_state['bets']:
                await ctx.send("Tidak ada yang bertaruh. Balapan dibatalkan.")
                self.end_game_cleanup(channel_id, game_type='horse_race')
                return

            await ctx.send("--- TARUHAN DITUTUP! BALAPAN DIMULAI! ---")
            
            race_embed = discord.Embed(title="🐎 LINTASAN BALAP", color=0x2ecc71)
            for name, data in game_state['horses'].items():
                race_embed.add_field(name=f"{data['emoji']} Kuda {name.capitalize()}", value="`[          🏁]`", inline=False) 
            game_state['race_message'] = await ctx.send(embed=race_embed)
            
            track_length = 20 
            winner_declared = False

            for _ in range(track_length * 2):
                if winner_declared: break
                await asyncio.sleep(2) 

                new_embed = discord.Embed(title=f"🐎 LINTASAN BALAP - Putaran {_+1}", color=0x2ecc71)
                for name, horse_data in game_state['horses'].items():
                    horse_data['progress'] += random.randint(1, 3) 
                    
                    current_progress = min(horse_data['progress'], track_length)
                    
                    track_display = "`[" + "█" * current_progress + " " * (track_length - current_progress) + "🏁]`"
                    
                    new_embed.add_field(name=f"{horse_data['emoji']} Kuda {name.capitalize()}", value=track_display, inline=False)
                    
                    if horse_data['progress'] >= track_length and not winner_declared:
                        game_state['winner_horse'] = name
                        winner_declared = True
                
                await game_state['race_message'].edit(embed=new_embed)
                if winner_declared: break
            
            if not game_state['winner_horse']:
                game_state['winner_horse'] = max(game_state['horses'], key=lambda k: game_state['horses'][k]['progress'])

            await ctx.send(f"--- BALAPAN SELESAI! --- \n\n🏆 **Kuda {game_state['winner_horse'].capitalize()}** adalah pemenangnya!")
            
            winners_info = []
            for user_id, bet_info in game_state['bets'].items():
                user = ctx.guild.get_member(user_id)
                if bet_info['horse'] == game_state['winner_horse']:
                    if user:
                        payout = bet_info['amount'] * 2 
                        self.give_rewards_base(user, ctx.guild.id, payout, 0)
                        winners_info.append(f"{user.mention} menang **{payout} RSWN**!") 

            if winners_info:
                await ctx.send("\n".join(winners_info))
            else:
                await ctx.send("Sayang sekali, tidak ada yang bertaruh pada kuda pemenang.")
        
        except asyncio.CancelledError:
            print(f"[{datetime.now()}] Horse race game flow for channel {channel_id} was cancelled during racing phase.")
            await ctx.send("Balapan kuda dihentikan lebih awal.")
        except Exception as e:
            print(f"[{datetime.now()}] Error in horse race game flow for channel {channel_id}: {e}")
            await ctx.send(f"Terjadi kesalahan fatal pada balapan kuda: `{e}`. Game dihentikan.")
        finally:
            self.end_game_cleanup(channel_id, game_type='horse_race')


    @commands.command(name="taruhan", help="Pasang taruhan pada balap kuda.")
    async def taruhan(self, ctx, amount: int, horse_name: str):
        channel_id = ctx.channel.id
        game_state = self.horse_race_games.get(channel_id)

        if not game_state or game_state['status'] != 'betting':
            return await ctx.send("Tidak ada sesi taruhan balap kuda yang aktif saat ini.", ephemeral=True)
        
        horse_name = horse_name.lower()
        if horse_name not in game_state['horses']:
            return await ctx.send(f"Kuda '{horse_name.capitalize()}' tidak valid. Pilih dari: {', '.join(game_state['horses'].keys())}", ephemeral=True)
        
        if amount <= 0:
            return await ctx.send("Jumlah taruhan harus lebih dari 0.", ephemeral=True)
        
        user_id_str = str(ctx.author.id)
        bank_data = load_json_from_root('data/bank_data.json')
        current_balance = bank_data.setdefault(user_id_str, {'balance': 0, 'debt': 0})['balance']
        
        if current_balance < amount:
            return await ctx.send(f"Saldo RSWNmu tidak cukup. Kamu punya: **{current_balance} RSWN**.", ephemeral=True)
        
        bank_data[user_id_str]['balance'] -= amount
        save_json_to_root(bank_data, 'data/bank_data.json')

        game_state['bets'][ctx.author.id] = {'amount': amount, 'horse': horse_name}
        game_state['players_who_bet'].add(ctx.author.id)

        await ctx.message.add_reaction("✅")
        await ctx.send(f"{ctx.author.mention} berhasil bertaruh **{amount} RSWN** pada Kuda **{horse_name.capitalize()}**!")


    # --- GAME 9: RODA TAKDIR GILA! ---
    @commands.command(name="putarroda", aliases=['putar'], help="Putar Roda Takdir Gila untuk takdir tak terduga!")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def putarroda(self, ctx):
        if await self._check_mimic_attack(ctx): return
        
        channel_id = ctx.channel.id
        guild = ctx.guild

        if not guild:
            return await ctx.send("Roda Takdir Gila hanya bisa diputar di server Discord!", ephemeral=True)

        if channel_id not in self.wheel_of_fate_config:
            self.wheel_of_fate_config[channel_id] = {
                'cost': self.wheel_spin_cost,
                'spinning_gif_url': 'https://i.imgur.com/39hN44u.gif',
                'segments': self._get_default_wheel_segments(),
                'outcome_image_urls': {}
            }
        
        current_wheel_config = self.wheel_of_fate_config[channel_id]
        
        user = ctx.author
        user_id_str = str(user.id)
        bank_data = load_json_from_root('data/bank_data.json')
        current_balance = bank_data.setdefault(user_id_str, {'balance': 0, 'debt': 0})['balance']

        if current_balance < current_wheel_config['cost']:
            return await ctx.send(f"Saldo RSWNmu tidak cukup untuk memutar roda ({current_wheel_config['cost']} RSWN diperlukan). Kamu punya: **{current_balance} RSWN**.", ephemeral=True)
        
        bank_data[user_id_str]['balance'] -= current_wheel_config['cost']
        save_json_to_root(bank_data, 'data/bank_data.json')

        wheel_stats = self.wheel_of_fate_data.setdefault('players_stats', {})
        wheel_stats.setdefault(user_id_str, {'spins': 0, 'wins_rsw': 0, 'losses_rsw': 0, 'weird_effects': 0})
        wheel_stats[user_id_str]['spins'] += 1
        save_json_to_root(self.wheel_of_fate_data, 'data/wheel_of_mad_fate.json')

        spinning_gif_url = current_wheel_config.get('spinning_gif_url', 'https://i.imgur.com/39hN44u.gif')
        
        spin_embed = discord.Embed(
            title="🌀 Roda Takdir Gila Sedang Berputar! 🌀",
            description=f"{user.mention} telah membayar **{current_wheel_config['cost']} RSWN** dan memutar roda... Apa takdir yang menantinya?",
            color=discord.Color.gold()
        )
        if spinning_gif_url:
            spin_embed.set_image(url=spinning_gif_url)
        
        spin_message = await ctx.send(embed=spin_embed)
        
        await asyncio.sleep(random.uniform(3, 5))
        
        outcome = self._get_wheel_outcome(current_wheel_config['segments'])
        outcome_image_url = current_wheel_config.get('outcome_image_urls', {}).get(outcome['type'])

        result_embed = discord.Embed(
            title=f"✨ **Roda Berhenti!** ✨",
            description=f"Untuk {user.mention}: **{outcome['description']}**",
            color=discord.Color.from_rgb(*outcome['color'])
        )
        if outcome_image_url:
            result_embed.set_image(url=outcome_image_url)
        else:
            if outcome['type'] == 'jackpot_rsw': result_embed.set_image(url="https://media.giphy.com/media/xT39D7PvWnJ14wD5c4/giphy.gif")
            elif outcome['type'] == 'boost_exp': result_embed.set_image(url="https://media.giphy.com/media/l0HlSZ0V5725j9M9W/giphy.gif")
            elif outcome['type'] == 'protection': result_embed.set_image(url="https://media.giphy.com/media/3o7WIJFA5r5d9n7jcA/giphy.gif")
            elif outcome['type'] == 'tax': result_embed.set_image(url="https://media.giphy.com/media/l3V0cE3tV6h6rC3m0/giphy.gif")
            elif outcome['type'] == 'nickname_transform': result_embed.set_image(url="https://media.giphy.com/media/rY9zudf2f2o8M/giphy.gif")
            elif outcome['type'] == 'message_mishap': result_embed.set_image(url="https://media.giphy.com/media/l3V0qXjXG2XW2tM/giphy.gif")
            elif outcome['type'] == 'bless_random_user': result_embed.set_image(url="https://media.giphy.com/media/l4FGJm7hXG1r0J0I/giphy.gif")
            elif outcome['type'] == 'curse_mute_random': result_embed.set_image(url="https://media.giphy.com/media/l4FGJm7hXG1r0J0I/giphy.gif")
            elif outcome['type'] == 'ping_random_user': result_embed.set_image(url="https://media.giphy.com/media/3ohhwpvL89Q8zN0n2g/giphy.gif")
            elif outcome['type'] == 'emoji_rain': result_embed.set_image(url="https://media.giphy.com/media/l0HlSZ0V5725j9M9W/giphy.gif")
            elif outcome['type'] == 'channel_rename': result_embed.set_image(url="https://media.giphy.com/media/l4FGJm7hXG1r0J0I/giphy.gif")
            elif outcome['type'] == 'random_duck': result_embed.set_image(url="https://media.giphy.com/media/f3ekFq7v18B9lTzY/giphy.gif")
            elif outcome['type'] == 'absurd_fortune': result_embed.set_image(url="https://media.giphy.com/media/l3V0qXjXG2XW2tM/giphy.gif")

        await spin_message.edit(embed=result_embed)
        
        # Panggil _apply_wheel_consequence dari self.dunia_cog
        if self.dunia_cog:
            await self.dunia_cog._apply_wheel_consequence(guild, channel, user, outcome)
        else:
            await channel.send("⚠️ Error: DuniaHidup cog tidak ditemukan, efek roda takdir tidak dapat diterapkan.")


    def _get_default_wheel_segments(self):
        """Mendapatkan segmen default untuk Roda Takdir Gila."""
        return [
            {'type': 'jackpot_rsw', 'description': "JACKPOT! Kamu mendapatkan RSWN!", 'color': (255,215,0), 'weight': 15, 'amount': 500},
            {'type': 'jackpot_rsw_big', 'description': "MEGA JACKPOT! Kamu mendapatkan RSWN BESAR!", 'color': (255,165,0), 'weight': 3, 'amount': 1000},
            {'type': 'boost_exp', 'description': "Kamu mendapatkan Boost EXP 2x selama 1 jam!", 'color': (0,255,0), 'weight': 10},
            {'type': 'protection', 'description': "Kamu mendapatkan Perlindungan Absurd! Kebal dari 1 efek negatif berikutnya.", 'color': (173,216,230), 'weight': 7},
            {'type': 'tax', 'description': "Roda menarik Pajak Takdir! Kamu kehilangan RSWN.", 'color': (139,0,0), 'weight': 15},
            {'type': 'nickname_transform', 'description': "Wajahmu berubah! Nickname-mu jadi aneh selama 1 jam.", 'color': (147,112,219), 'weight': 10},
            {'type': 'message_mishap', 'description': "Kata-katamu tersangkut! Pesanmu jadi aneh selama 30 menit.", 'color': (255,69,0), 'weight': 8},
            {'type': 'bless_random_user', 'description': "Sebuah Berkat Random! User acak mendapatkan RSWN.", 'color': (255,192,203), 'weight': 10, 'amount': 500},
            {'type': 'curse_mute_random', 'description': "Kutukan Mute Kilat! User acak kena timeout 60 detik.", 'color': (75,0,130), 'weight': 7},
            {'type': 'ping_random_user', 'description': "Panggilan Darurat! User acak di-ping sampai nongol.", 'color': (255,255,0), 'weight': 5},
            {'type': 'emoji_rain', 'description': "Hujan Emoji! Channel ini diguyur emoji acak.", 'color': (0,255,255), 'weight': 5},
            {'type': 'channel_rename', 'description': "Nama Channel Berubah Absurd! Channel ini jadi konyol 15 menit.", 'color': (255,105,180), 'weight': 3},
            {'type': 'random_duck', 'description': "Tidak Terjadi Apa-Apa, Tapi Ada Bebek!", 'color': (255,255,255), 'weight': 5},
            {'type': 'absurd_fortune', 'description': "Sebuah Ramalan Halu! Takdirmu akan sangat aneh.", 'color': (128,0,128), 'weight': 4}
        ]

    def _get_wheel_outcome(self, segments):
        """Memilih hasil putaran roda berdasarkan bobot."""
        total_weight = sum(s['weight'] for s in segments)
        rand_num = random.uniform(0, total_weight)
        
        current_weight = 0
        for segment in segments:
            current_weight += segment['weight']
            if rand_num <= current_weight:
                if segment['type'] == 'jackpot_rsw_big':
                    return {'type': 'jackpot_rsw', 'description': "MEGA JACKPOT! Kamu mendapatkan **1000 RSWN**!", 'color': (255,165,0), 'amount': 1000}
                return segment.copy() 
        return random.choice(segments).copy() # Fallback (seharusnya tidak terjadi)


    # --- SPYFALL (MATA-MATA) GAME LOGIC ---
    @commands.command(name="matamata", help="Mulai game Mata-Mata. Temukan siapa mata-matanya!")
    # COOLDOWN DIHAPUS agar bisa langsung main lagi
    # commands.cooldown(1, 300, commands.BucketType.channel) <-- BARIS INI DIHAPUS
    async def matamata(self, ctx):
        if await self._check_mimic_attack(ctx): return # Cek mimic attack
        # start_game_check masih diperlukan untuk mencegah game tumpang tindih di channel yang sama
        if not await self.start_game_check(ctx): 
            return
        
        if not ctx.author.voice or not ctx.author.voice.channel: 
            self.end_game_cleanup(ctx.channel.id, game_type='spyfall')
            return await ctx.send("Kamu harus berada di voice channel untuk memulai game ini.", ephemeral=True)
        
        vc = ctx.author.voice.channel
        members = [m for m in vc.members if not m.bot]
        if len(members) < 3: 
            self.end_game_cleanup(ctx.channel.id, game_type='spyfall')
            return await ctx.send("Game ini butuh minimal 3 orang di voice channel.", ephemeral=True)
        
        location = random.choice(self.mata_mata_locations)
        
        # --- Logika Pemilihan Mata-Mata yang Diperbarui (Sesuai Permintaan Anda) ---
        eligible_spies = [m for m in members if m.id != self.last_spy_id]
        
        if eligible_spies: # Jika ada pemain yang BUKAN mata-mata terakhir, pilih dari mereka
            spy = random.choice(eligible_spies)
        else: # Jika semua pemain di sesi saat ini adalah last_spy_id (atau hanya sedikit pemain)
              # atau tidak ada pilihan lain, maka last_spy_id harus dipilih lagi.
            spy = random.choice(members)
        # --- Akhir Logika Pemilihan Mata-Mata yang Diperbarui ---
        
        self.spyfall_game_states[ctx.channel.id] = {
            'spy': spy,
            'location': location,
            'players': members,
            'discussion_start_time': datetime.now(), 
            'vote_in_progress': False,
            'game_task': None # Menambahkan inisialisasi game_task
        }

        failed_dms = []
        for member in members:
            try:
                if member.id == spy.id:
                    await member.send("🤫 Kamu adalah **Mata-Mata**! Tugasmu adalah menebak lokasi tanpa ketahuan.")
                else:
                    await member.send(f"📍 Lokasi rahasia adalah: **{location}**. Temukan siapa mata-matanya!")
            except discord.Forbidden:
                failed_dms.append(member.mention)
        
        if failed_dms:
            await ctx.send(f"Gagal memulai game karena tidak bisa mengirim DM ke: {', '.join(failed_dms)}. Pastikan DM-nya terbuka."); 
            self.end_game_cleanup(ctx.channel.id, game_type='spyfall')
            return

        embed = discord.Embed(title="🎭 Game Mata-Mata Dimulai!", color=0x7289da)
        embed.description = "Peran dan lokasi telah dikirim melalui DM. Salah satu dari kalian adalah mata-mata!\n\n" \
                            "**Tujuan Pemain Biasa:** Temukan mata-matanya.\n" \
                            "**Tujuan Mata-Mata:** Bertahan tanpa ketahuan & menebak lokasi.\n\n" \
                            "Waktu diskusi: **5 menit**. Kalian bisa `!tuduh @user` kapan saja (akan memicu voting).\n\n" \
                            "**Diskusi bisa dimulai sekarang!**"
        embed.set_footer(text="Jika 5 menit habis, fase penuduhan akhir dimulai, atau mata-mata bisa coba menebak lokasi.")
        game_start_message = await ctx.send(embed=embed)
        self.spyfall_game_states[ctx.channel.id]['game_start_message_id'] = game_start_message.id

        # Menggunakan asyncio.Task untuk mengelola alur game
        game_task = self.bot.loop.create_task(self._spyfall_game_flow(ctx, ctx.channel.id, spy, location, members))
        self.spyfall_game_states[ctx.channel.id]['game_task'] = game_task


    async def _spyfall_game_flow(self, ctx, channel_id, spy, location, players):
        """Alur utama game Mata-Mata."""
        try:
            await asyncio.sleep(300) # Waktu diskusi 5 menit
            
            # Cek jika game masih aktif (belum diakhiri oleh !tuduh atau !ungkap_lokasi)
            if channel_id not in self.spyfall_game_states:
                return # Game sudah berakhir oleh command lain

            await ctx.send(f"⏰ **Waktu diskusi 5 menit habis!** Sekarang adalah fase penuduhan akhir. "
                           f"Pemain biasa bisa menggunakan `!tuduh @nama_pemain` untuk memulai voting.\n"
                           f"Mata-mata bisa menggunakan `!ungkap_lokasi <lokasi>` untuk mencoba menebak lokasi.\n\n"
                           f"Jika mata-mata berhasil menebak lokasi dengan benar dan belum dituduh, mata-mata menang! Jika tidak ada yang menuduh atau mata-mata tidak menebak lokasi dalam waktu 2 menit, maka **mata-mata menang secara otomatis.**")
            
            await asyncio.sleep(120) # Waktu tambahan untuk penuduhan/pengungkapan lokasi
            
            if channel_id in self.spyfall_game_states:
                await ctx.send(f"Waktu penuduhan habis! Mata-mata ({spy.mention}) menang karena tidak ada yang berhasil menuduh atau mata-mata tidak mengungkapkan lokasi! Lokasi sebenarnya adalah **{location}**.")
                await self.give_rewards_with_bonus_check(spy, ctx.guild.id, ctx.channel)
                # Simpan ID mata-mata terakhir untuk sesi berikutnya
                self.last_spy_id = spy.id
                self.end_game_cleanup(channel_id, game_type='spyfall')


        except asyncio.CancelledError:
            print(f"[{datetime.now()}] Spyfall game flow for channel {channel_id} was cancelled.")
            await ctx.send("Game Mata-Mata dihentikan lebih awal.")
        except Exception as e:
            print(f"[{datetime.now()}] Error in _spyfall_game_flow for channel {channel_id}: {e}")
            await ctx.send(f"Terjadi kesalahan fatal pada game Mata-Mata: `{e}`. Game dihentikan.")
            # Simpan ID mata-mata terakhir bahkan jika ada error
            if channel_id in self.spyfall_game_states: # Pastikan game_state masih ada
                self.last_spy_id = self.spyfall_game_states[channel_id]['spy'].id
            self.end_game_cleanup(channel_id, game_type='spyfall')


    @commands.command(name="tuduh", help="Tuduh seseorang sebagai mata-mata.")
    async def tuduh(self, ctx, member: discord.Member):
        if ctx.channel.id not in self.spyfall_game_states:
            return await ctx.send("Game Mata-Mata belum dimulai di channel ini.", ephemeral=True)
        
        game = self.spyfall_game_states[ctx.channel.id]
        spy, location, players = game['spy'], game['location'], game['players']

        if ctx.author not in players or member not in players: 
            return await ctx.send("Hanya pemain yang berpartisipasi yang bisa menuduh atau dituduh.", ephemeral=True)
        
        if game['vote_in_progress']:
            return await ctx.send("Saat ini sedang ada voting lain. Tunggu sampai selesai.", ephemeral=True)

        game['vote_in_progress'] = True 
        
        vote_embed = discord.Embed(
            title="🗳️ VOTING UNTUK MATA-MATA!",
            description=f"{ctx.author.mention} menuduh {member.mention} sebagai mata-mata!\n\n"
                        f"**Setuju (✅) atau Tidak Setuju (❌)?**",
            color=discord.Color.red()
        )
        vote_embed.set_footer(text="Voting akan berakhir dalam 30 detik. Mayoritas menentukan.")
        
        vote_msg = await ctx.send(embed=vote_embed)
        await vote_msg.add_reaction("✅")
        await vote_msg.add_reaction("❌")
        
        await asyncio.sleep(30) # Waktu untuk voting
        
        # Cek apakah game state masih ada, jika tidak berarti sudah diakhiri oleh ungkap_lokasi atau timeout
        if ctx.channel.id not in self.spyfall_game_states:
            print(f"[{datetime.now()}] Spyfall game state not found during vote tally for channel {ctx.channel.id}. (Already ended by other means)")
            return 

        game = self.spyfall_game_states[ctx.channel.id] # Refresh game state karena mungkin ada perubahan
        game['vote_in_progress'] = False # Akhiri status voting
        game_task = game.get('game_task')
        if game_task and not game_task.done():
            game_task.cancel() # Batalkan alur game utama jika voting berhasil/gagal

        try:
            cached_vote_msg = await ctx.channel.fetch_message(vote_msg.id)
            yes_votes = 0
            no_votes = 0
            actual_voters = set() # Untuk melacak siapa saja yang sudah vote

            for reaction in cached_vote_msg.reactions:
                if str(reaction.emoji) == "✅":
                    async for user_reaction in reaction.users():
                        # Hanya hitung vote dari pemain yang valid dan belum vote
                        if not user_reaction.bot and user_reaction.id in [p.id for p in players] and user_reaction.id not in actual_voters:
                            yes_votes += 1
                            actual_voters.add(user_reaction.id)
                elif str(reaction.emoji) == "❌":
                    async for user_reaction in reaction.users():
                        if not user_reaction.bot and user_reaction.id in [p.id for p in players] and user_reaction.id not in actual_voters:
                            no_votes += 1
                            actual_voters.add(user_reaction.id)
            
            # Hitung jumlah pemain yang bisa vote (kecuali yang menuduh dan yang dituduh, jika mereka berbeda)
            # Total pemain yang valid untuk voting = semua pemain - (penuduh) - (yang dituduh jika beda dari penuduh)
            total_eligible_voters_in_game = len(players)
            
            # Jika yang menuduh adalah bagian dari pemain yang bisa vote, kurangi 1
            if ctx.author in players:
                 total_eligible_voters_in_game -= 1 
            # Jika yang dituduh adalah bagian dari pemain dan berbeda dari penuduh, kurangi 1
            if member in players and member != ctx.author:
                 total_eligible_voters_in_game -= 1

            # Mayoritas sederhana (lebih dari setengah dari yang bisa vote)
            majority_needed = total_eligible_voters_in_game / 2.0
            
            if yes_votes > no_votes and yes_votes > majority_needed: 
                await ctx.send(f"✅ **Voting Berhasil!** Mayoritas setuju {member.mention} adalah mata-mata.")
                if member.id == spy.id:
                    await ctx.send(f"**Tuduhan Benar!** {member.mention} memang mata-matanya. Lokasinya adalah **{location}**.")
                    await ctx.send(f"Selamat kepada tim warga, kalian semua mendapat hadiah!")
                    for p in players:
                        if p.id != spy.id: await self.give_rewards_with_bonus_check(p, ctx.guild.id, ctx.channel)
                else:
                    await ctx.send(f"**Tuduhan Salah!** {member.mention} bukan mata-matanya. Lokasi sebenarnya adalah **{location}**.")
                    await ctx.send(f"**Mata-mata ({spy.mention}) menang!**")
                    await self.give_rewards_with_bonus_check(spy, ctx.guild.id, ctx.channel)
                
                # Simpan ID mata-mata terakhir setelah game selesai
                self.last_spy_id = spy.id
                self.end_game_cleanup(ctx.channel.id, game_type='spyfall')
            else:
                await ctx.send(f"❌ **Voting Gagal.** Tidak cukup suara untuk menuduh {member.mention}. Permainan dilanjutkan!")
                # Game tidak berakhir, voting in_progress sudah False
        
        except discord.NotFound:
            await ctx.send("Pesan voting tidak ditemukan.")
            game['vote_in_progress'] = False 
        except Exception as e:
            print(f"[{datetime.now()}] Error during Spyfall voting for channel {ctx.channel.id}: {e}")
            await ctx.send(f"Terjadi kesalahan saat memproses voting: `{e}`. Permainan dilanjutkan.")


    @commands.command(name="ungkap_lokasi", aliases=['ulokasi'], help="Sebagai mata-mata, coba tebak lokasi rahasia.")
    async def ungkap_lokasi(self, ctx, *, guessed_location: str):
        if ctx.channel.id not in self.spyfall_game_states:
            return await ctx.send("Game Mata-Mata belum dimulai.", ephemeral=True)

        game = self.spyfall_game_states[ctx.channel.id]
        spy, location = game['spy'], game['location']

        if ctx.author.id != spy.id:
            return await ctx.send("Hanya mata-mata yang bisa menggunakan perintah ini.", ephemeral=True)
        
        if game['vote_in_progress']:
            return await ctx.send("Saat ini sedang ada voting. Tunggu sampai selesai.", ephemeral=True)

        # Cek jika game_task sedang berjalan, batalkan
        game_task = game.get('game_task')
        if game_task and not game_task.done():
            game_task.cancel() # Ini akan memicu asyncio.CancelledError di _spyfall_game_flow

        if guessed_location.lower() == location.lower():
            await ctx.send(f"🎉 **Mata-Mata Ungkap Lokasi Dengan Benar!** {spy.mention} berhasil menebak lokasi rahasia yaitu **{location}**! Mata-mata menang!")
            await self.give_rewards_with_bonus_check(spy, ctx.guild.id, ctx.channel)
        else:
            await ctx.send(f"❌ **Mata-Mata Gagal Mengungkap Lokasi!** Tebakan `{guessed_location}` salah. Lokasi sebenarnya adalah **{location}**. Warga menang!")
            for p in game['players']:
                if p.id != spy.id:
                    await self.give_rewards_with_bonus_check(p, ctx.guild.id, ctx.channel)

        # Simpan ID mata-mata terakhir setelah game selesai
        self.last_spy_id = spy.id
        self.end_game_cleanup(ctx.channel.id, game_type='spyfall')

    # --- TEKA-TEKI HARIAN ---
    @tasks.loop(time=time(hour=5, minute=0, tzinfo=pytz.timezone('Asia/Jakarta'))) # Menggunakan pytz
    async def post_daily_puzzle(self):
        await self.bot.wait_until_ready()
        now = datetime.now(pytz.timezone('Asia/Jakarta')) # Menggunakan pytz
        target_time = now.replace(hour=5, minute=0, second=0, microsecond=0)
        
        if now > target_time:
            target_time += timedelta(days=1)
        
        time_until_post = (target_time - now).total_seconds()
        
        if time_until_post > 0:
            await asyncio.sleep(time_until_post)

        if not self.tekateki_harian_data: 
            print(f"[{datetime.now()}] Peringatan: Data teka-teki harian tidak ditemukan atau kosong.")
            return
        
        self.daily_puzzle = random.choice(self.tekateki_harian_data)
        self.daily_puzzle_solvers.clear()
        
        channel = self.bot.get_channel(self.daily_puzzle_channel_id)
        if channel:
            embed = discord.Embed(title="🤔 Teka-Teki Harian!", description=f"**Teka-teki untuk hari ini:**\n\n> {self.daily_puzzle['riddle']}", color=0x99aab5)
            embed.set_footer(text="Gunakan !jawab <jawabanmu> untuk menebak!")
            await channel.send(embed=embed)

    @post_daily_puzzle.before_loop
    async def before_daily_puzzle(self):
        await self.bot.wait_until_ready()

    @commands.command(name="jawab", help="Jawab teka-teki harian.")
    async def jawab(self, ctx, *, answer: str):
        if not self.daily_puzzle: return await ctx.send("Belum ada teka-teki untuk hari ini. Sabar ya!")
        if ctx.author.id in self.daily_puzzle_solvers: return await ctx.send("Kamu sudah menjawab dengan benar hari ini!", ephemeral=True)
            
        if answer.lower() == self.daily_puzzle['answer'].lower():
            self.daily_puzzle_solvers.add(ctx.author.id)
            await self.give_rewards_with_bonus_check(ctx.author, ctx.guild.id, ctx.channel)
            await ctx.message.add_reaction("✅")
            await ctx.send(f"🎉 Selamat {ctx.author.mention}! Jawabanmu benar!")
        else:
            await ctx.message.add_reaction("❌")

    # --- PERINTAH ADMINISTRASI UNTUK SIMULASI MIMIC ---
    @commands.command(name="setmimicattack", help="[ADMIN] Simulasi serangan mimic di channel ini.")
    @commands.has_permissions(manage_channels=True)
    async def set_mimic_attack(self, ctx):
        if self.dunia_cog: 
            self.dunia_cog.active_mimic_attack_channel_id = ctx.channel.id
            await ctx.send(f"💥 Serangan mimic sekarang aktif di channel ini ({ctx.channel.mention})! Game lain tidak bisa dimulai di sini.")
        else:
            await ctx.send("DuniaHidup cog tidak ditemukan. Tidak dapat mengatur serangan mimic.")

    @commands.command(name="clearmimicattack", help="[ADMIN] Hapus serangan mimic dari channel ini.")
    @commands.has_permissions(manage_channels=True)
    async def clear_mimic_attack(self, ctx):
        if self.dunia_cog and self.dunia_cog.active_mimic_attack_channel_id == ctx.channel.id:
            self.dunia_cog.active_mimic_attack_channel_id = None
            await ctx.send(f"✅ Serangan mimic di channel ini ({ctx.channel.mention}) telah dihentikan. Game bisa dimulai lagi.")
        elif self.dunia_cog:
            await ctx.send("Tidak ada serangan mimic aktif di channel ini.")
        else:
            await ctx.send("DuniaHidup cog tidak ditemukan. Tidak dapat menghapus serangan mimic.")
            
    # Perintah admin untuk mengaktifkan/menonaktifkan efek mimic pada jawaban kuis
    # Perintah ini diasumsikan ada di DuniaHidup.py, bukan di sini.

async def setup(bot):
    await bot.add_cog(UltimateGameArena(bot))
