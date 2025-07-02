import discord
from discord.ext import commands, tasks
import json
import random
import asyncio
import os
from datetime import datetime, time, timedelta
import string
import pytz # Import pytz untuk zona waktu

# Impor Music cog (pastikan file music.py ada di folder yang sama dengan games_global_events.py, yaitu 'cogs')
# from .music import Music 

# --- Helper Functions (Diulang agar cog ini mandiri) ---
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
        print(f"[{datetime.now()}] [DEBUG HELPER] Peringatan: File {full_path} tidak ditemukan. Menggunakan nilai default.")
        if default_value is not None:
            return default_value
        if 'bank_data.json' in file_path or 'level_data.json' in file_path or 'sick_users_cooldown.json' in file_path or 'protected_users' in file_path or 'inventory.json' in file_path: 
            return {}
        # Untuk monsters, anomalies, medicines, default adalah list kosong jika file tidak ditemukan
        elif 'monsters.json' in file_path: return {"monsters": [], "monster_quiz": []}
        elif 'world_anomalies.json' in file_path: return {"anomalies": []}
        elif 'medicines.json' in file_path: return {"medicines": []}
        return [] 
    except json.JSONDecodeError:
        print(f"[{datetime.now()}] [DEBUG HELPER] Peringatan: File {full_path} rusak (JSON tidak valid). Menggunakan nilai default.")
        if default_value is not None:
            return default_value
        if 'bank_data.json' in file_path or 'level_data.json' in file_path or 'sick_users_cooldown.json' in file_path or 'protected_users' in file_path or 'inventory.json' in file_path: 
            return {}
        elif 'monsters.json' in file_path: return {"monsters": [], "monster_quiz": []}
        elif 'world_anomalies.json' in file_path: return {"anomalies": []}
        elif 'medicines.json' in file_path: return {"medicines": []}
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
        # Menghapus input untuk vote_phase_audio_url dan game_end_audio_url
        # self.add_item(URLInput("Vote Phase Audio URL (MP3/WebM)", "url_vote_phase_audio", "URL audio untuk fase voting", current_audio_urls.get('vote_phase_audio_url', '')))
        # self.add_item(URLInput("Game End Audio URL (MP3/WebM)", "url_game_end_audio", "URL audio untuk akhir game", current_audio_urls.get('game_end_audio_url', '')))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        global_config_ref = self.game_cog.global_werewolf_config.setdefault('default_config', {})
        
        global_config_ref['image_urls'] = {
            'game_start_image_url': self.children[0].value or None,
            'night_phase_image_url': self.children[1].value or None,
            'day_phase_image_url': self.children[2].value or None,
            'night_resolution_image_url': self.children[3].value or None,
            # Menghapus werewolf_win_image_url dan villager_win_image_url
            # 'werewolf_win_image_url': self.children[4].value or None,
            # 'villager_win_image_url': self.children[5].value or None
        }

        global_config_ref['audio_urls'] = {
            'game_start_audio_url': self.children[4].value or None, # Index disesuaikan
            'night_phase_audio_url': self.children[5].value or None, # Index disesuaikan
            'day_phase_audio_url': self.children[6].value or None, # Index disesuaikan
            # Menghapus vote_phase_audio_url dan game_end_audio_url
            # 'vote_phase_audio_url': self.children[7].value or None,
            # 'game_end_audio_url': self.children[8].value or None
        }
        
        save_json_to_root(self.game_cog.global_werewolf_config, 'data/global_werewolf_config.json')
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Media Werewolf global disimpan oleh {interaction.user.display_name}.")

        try:
            message_to_update_id = self.game_cog.active_werewolf_setup_messages.get(interaction.channel_id)
            if message_to_update_id:
                message = await interaction.channel.fetch_message(message_to_update_id)
                view = WerewolfRoleSetupView(self.game_cog, interaction.channel_id, 
                                            self.game_cog.werewolf_game_states.get(interaction.channel.id, {}).get('total_players', 0), 
                                            self.game_cog.global_werewolf_config.get('default_config', {}))
                await message.edit(embed=view.create_embed(), view=view)
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pesan setup Werewolf di channel {interaction.channel.name} diperbarui.")
        except discord.NotFound:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pesan setup Werewolf tidak ditemukan untuk update.")
        except Exception as e:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Error update pesan setup Werewolf: {e}")

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
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] WerewolfRoleSetupView diinisialisasi untuk channel {channel_id}.")

    def _add_role_selects(self):
        for item in list(self.children):
            if isinstance(item, RoleSelect):
                self.remove_item(item)
        
        roles_to_display = [role for role in self.available_roles.keys() if role != "Warga Polos"]
        
        for i, role_name in enumerate(roles_to_display):
            current_value = self.selected_roles.get(role_name, 0)
            self.add_item(RoleSelect(role_name, current_value, self.total_players))
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] RoleSelects Werewolf ditambahkan.")

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

    def create_embed(self): # Dibuat fungsi terpisah agar bisa dipanggil dari modal on_submit
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
        # Menghapus display untuk werewolf_win_image_url dan villager_win_image_url
        # if self.image_urls.get('werewolf_win_image_url'): image_summary += "✅ Werewolf Win Image\n"
        # if self.image_urls.get('villager_win_image_url'): image_summary += "✅ Villager Win Image\n"
        if image_summary:
            embed.add_field(name="Status Gambar/GIF (Global)", value=image_summary, inline=False)

        audio_summary = ""
        if self.audio_urls.get('game_start_audio_url'): audio_summary += "🎵 Game Start Audio\n"
        if self.audio_urls.get('night_phase_audio_url'): audio_summary += "🎵 Night Audio\n"
        if self.audio_urls.get('day_phase_audio_url'): audio_summary += "🎵 Day Audio\n"
        # Menghapus display untuk vote_phase_audio_url dan game_end_audio_url
        # if self.audio_urls.get('vote_phase_audio_url'): audio_summary += "🎵 Vote Audio\n"
        # if self.audio_urls.get('game_end_audio_url'): audio_summary += "🎵 Game End Audio\n"
        if audio_summary:
            embed.add_field(name="Status Audio (Global - MP3/WebM)", value=audio_summary, inline=False)
        
        return embed

    async def update_message(self, message):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] update_message WerewolfRoleSetupView untuk channel {self.channel_id}.")
        self._add_role_selects() # Pastikan dropdown terbaru
        await message.edit(embed=self.create_embed(), view=self)


    @discord.ui.button(label="Atur Media Game (Global)", style=discord.ButtonStyle.secondary, custom_id="setup_media", row=4)
    async def setup_media_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Tombol 'Atur Media Game' diklik oleh {interaction.user.display_name}.")
        game_state = self.game_cog.werewolf_game_states.get(interaction.channel.id)
        # Hanya host game yang sedang aktif di channel ini yang bisa memanggil setup
        if not game_state or interaction.user.id != game_state['host'].id:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Bukan host atau game tidak aktif, blokir pengaturan media.")
            return await interaction.response.send_message("Hanya host game Werewolf yang aktif di channel ini yang bisa mengatur media global.", ephemeral=True)
        
        await interaction.response.send_modal(WerewolfMediaSetupModal(self.game_cog, self.game_cog.global_werewolf_config.get('default_config', {})))
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Modal WerewolfMediaSetupModal dikirim.")

    @discord.ui.button(label="Selesai Mengatur", style=discord.ButtonStyle.success, custom_id="finish_role_setup", row=4)
    async def finish_setup_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Tombol 'Selesai Mengatur' diklik oleh {interaction.user.display_name}.")
        game_state = self.game_cog.werewolf_game_states.get(interaction.channel.id)
        if not game_state or interaction.user.id != game_state['host'].id:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Bukan host atau game tidak aktif, blokir selesai pengaturan.")
            return await interaction.response.send_message("Hanya host yang bisa menyelesaikan pengaturan peran.", ephemeral=True)

        await interaction.response.defer()
        
        villager_count, warnings = self.calculate_balance()
        if warnings and (any("⚠️" in w for w in warnings) or any("⛔" in w for w in warnings)):
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Peringatan komposisi peran: {warnings}.")
            await interaction.followup.send("Ada masalah kritis dengan komposisi peran yang dipilih. Mohon perbaiki sebelum melanjutkan.", ephemeral=True)
            return

        self.game_cog.global_werewolf_config.setdefault('default_config', {})['roles'] = self.selected_roles
        save_json_to_root(self.game_cog.global_werewolf_config, 'data/global_werewolf_config.json')
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Konfigurasi peran global Werewolf disimpan.")
        
        for item in self.children:
            item.disabled = True
        
        embed = interaction.message.embeds[0]
        embed.description = f"**Komposisi peran untuk game ini telah diatur (Global)!**\n\nTotal Pemain: **{self.total_players}**"
        embed.color = discord.Color.green()
        embed.set_footer(text="Host bisa gunakan !forcestartwerewolf untuk memulai game!")

        await interaction.message.edit(embed=embed, view=self)
        self.stop() 
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pengaturan Werewolf selesai, view dihentikan.")


class GamesGlobalEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = set() # Channel IDs where a game is active in this cog (Werewolf, Wheel, Horse Racing)
        
        # --- Game States ---
        self.werewolf_join_queues = {} # {guild_id: {channel_id: [players]}}
        self.werewolf_game_states = {} # {channel_id: {'players': [members], 'roles': {member.id: role}, 'phase': 'day'/'night', 'day_num': 1, 'active_players': set(), 'killed_this_night': None, 'voted_out_today': None, 'host': member, 'role_actions_pending': {}, 'timers': {}, 'vote_message': None, 'players_who_voted': set(), 'last_role_setup_message': None, 'voice_client': None, 'game_task': None, 'total_players': int}} 
        self.active_werewolf_setup_messages = {} # {channel_id: message_id} to keep track of active setup messages

        # Wheel of Mad Fate States
        self.wheel_of_fate_config = {} # {channel_id: {'cost': int, 'segments': [], 'spinning_gif_url': '', 'outcome_image_urls': {}}}
        self.wheel_of_fate_data = load_json_from_root('data/wheel_of_mad_fate.json', default_value={"players_stats": {}}) # Store stats, default segment configs etc.
        self.wheel_spin_cost = 200 # Default Wheel of Mad Fate cost

        # Horse Racing States
        self.horse_racing_states = {} # {channel_id: {'status': 'betting'/'racing'/'finished', 'bets': {user_id: {'amount': int, 'horse_id': int}}, 'horses': [], 'race_message': None, 'betting_timer': None, 'race_timer': None, 'game_task': None, 'track_length': int, 'betting_duration': int, 'odds': {horse_id: float}}}
        self.horse_racing_data = load_json_from_root('data/horse_racing_data.json', default_value={"horses": []})

        # --- Konfigurasi Game dari JSON ---
        self.global_werewolf_config = load_json_from_root(
            'data/global_werewolf_config.json', 
            default_value={
                "default_config": {
                    "roles": {}, 
                    "image_urls": {
                        "game_start_image_url": None, "night_phase_image_url": None,
                        "day_phase_image_url": None, "night_resolution_image_url": None
                        # Menghapus werewolf_win_image_url dan villager_win_image_url dari default
                        # "werewolf_win_image_url": None,
                        # "villager_win_image_url": None
                    }, 
                    "audio_urls": {
                        "game_start_audio_url": None, "night_phase_audio_url": None,
                        "day_phase_audio_url": None
                        # Menghapus vote_phase_audio_url dan game_end_audio_url dari default
                        # "vote_phase_audio_url": None,
                        # "game_end_audio_url": None
                    }
                }
            }
        )
        self.werewolf_roles_data = load_json_from_root('data/werewolf_roles.json', default_value={"roles": {}})

        
        # --- Interaksi Cog Lain ---
        self.dunia_cog = None # Akan diisi di on_ready listener dari DuniaHidup.py
        self.music_cog = None # Akan diisi di on_ready listener dari music.py

        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Cog GamesGlobalEvents diinisialisasi.")

    @commands.Cog.listener()
    async def on_ready(self):
        await self.bot.wait_until_ready()
        
        self.dunia_cog = self.bot.get_cog('DuniaHidup')
        if not self.dunia_cog:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Peringatan: Cog 'DuniaHidup' tidak ditemukan. Fitur terkait anomali/mimic TIDAK AKAN BERFUNGSI.")

        self.music_cog = self.bot.get_cog('Music')
        if not self.music_cog:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Peringatan: Cog 'Music' tidak ditemukan. Fungsi audio Werewolf mungkin tidak berfungsi.")
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Cog GamesGlobalEvents siap!")

    def cog_unload(self):
        """Dipanggil saat cog dibongkar, membatalkan semua task loop."""
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Cog GamesGlobalEvents sedang dibongkar...")
        
        # Batalkan task game yang mungkin sedang berjalan
        for channel_id in list(self.werewolf_game_states.keys()):
            game_state = self.werewolf_game_states.get(channel_id)
            if game_state and game_state.get('voice_client'):
                self.bot.loop.create_task(game_state['voice_client'].disconnect())
            if game_state and 'game_task' in game_state and not game_state['game_task'].done():
                game_state['game_task'].cancel()
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Task Werewolf di channel {channel_id} dibatalkan.")
        
        for channel_id in list(self.horse_racing_states.keys()):
            game_state = self.horse_racing_states.get(channel_id)
            if game_state and 'game_task' in game_state and not game_state['game_task'].done():
                game_state['game_task'].cancel()
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Task Balapan Kuda di channel {channel_id} dibatalkan.")

        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Cog GamesGlobalEvents berhasil dibongkar.")

    def get_anomaly_multiplier(self):
        """Mengambil multiplier anomali EXP dari DuniaHidup cog jika ada."""
        if self.dunia_cog and hasattr(self.dunia_cog, 'active_anomaly') and self.dunia_cog.active_anomaly and self.dunia_cog.active_anomaly.get('type') == 'exp_boost':
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Anomali EXP Boost aktif. Multiplier: {self.dunia_cog.active_anomaly.get('effect', {}).get('multiplier', 1)}x")
            return self.dunia_cog.active_anomaly.get('effect', {}).get('multiplier', 1)
        return 1

    async def give_rewards_with_bonus_check(self, user: discord.Member, guild_id: int, channel: discord.TextChannel = None, custom_rsw: int = None, custom_exp: int = None):
        """
        Memberikan hadiah RSWN dan EXP kepada pengguna, dengan pengecekan bonus anomali.
        Ini adalah fungsi helper, bukan command.
        """
        anomaly_multiplier = self.get_anomaly_multiplier()
        
        # Untuk game ini, kita akan tentukan reward dasar langsung di sini
        # Atau bisa ambil dari config di cog ini jika ada.
        base_rsw = custom_rsw if custom_rsw is not None else 100 # Default reward Werewolf/Wheel
        base_exp = custom_exp if custom_exp is not None else 100 # Default reward Werewolf/Wheel

        final_rsw = int(base_rsw * anomaly_multiplier)
        final_exp = int(base_exp * anomaly_multiplier)
        
        if self.dunia_cog and hasattr(self.dunia_cog, 'give_rewards_base'):
            self.dunia_cog.give_rewards_base(user, guild_id, final_rsw, final_exp)
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Hadiah via DuniaHidup: {user.display_name} mendapat {final_rsw} RSWN & {final_exp} EXP.")
        else:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Peringatan: DuniaHidup cog atau give_rewards_base tidak ditemukan. Hadiah tidak disimpan untuk {user.display_name}.")
            pass 

        if anomaly_multiplier > 1 and channel:
            await channel.send(f"✨ **BONUS ANOMALI!** {user.mention} mendapatkan hadiah yang dilipatgandakan!", delete_after=15)
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Reward diberikan: {user.display_name} mendapatkan {final_rsw} RSWN, {final_exp} EXP (multiplier {anomaly_multiplier}).")

    async def start_game_check_global(self, ctx):
        """Memeriksa apakah ada game aktif di channel ini (untuk cog ini saja)."""
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Memeriksa start_game_check_global untuk channel {ctx.channel.name} ({ctx.channel.id}). Active games (this cog): {self.active_games}")
        if ctx.channel.id in self.active_games:
            await ctx.send("Maaf, sudah ada permainan dari grup game global (Werewolf/Roda Takdir/Balapan Kuda) lain di channel ini. Tunggu selesai ya!", ephemeral=True)
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Game dari cog ini sudah aktif di channel ini, blokir.")
            return False
        self.active_games.add(ctx.channel.id)
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Game ditambahkan ke active_games (this cog). Current: {self.active_games}")
        return True
    
    async def _check_mimic_attack(self, ctx):
        """Memeriksa apakah ada serangan mimic yang memblokir game di channel ini (dari DuniaHidup)."""
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Memeriksa _check_mimic_attack untuk channel {ctx.channel.name} ({ctx.channel.id}).")
        if self.dunia_cog and self.dunia_cog.active_mimic_attack_channel_id == ctx.channel.id:
            await ctx.send("💥 **SERANGAN MIMIC!** Permainan tidak bisa dimulai karena mimic sedang mengamuk di channel ini!", ephemeral=True)
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] MIMIC ATTACK aktif di channel ini, blokir game.")
            return True
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] MIMIC ATTACK tidak aktif di channel ini.")
        return False

    async def _check_mimic_effect(self, ctx):
        """Memeriksa apakah event mimic yang memengaruhi jawaban sedang aktif di channel ini (dari DuniaHidup)."""
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Memeriksa _check_mimic_effect untuk channel {ctx.channel.name} ({ctx.channel.id}).")
        if self.dunia_cog and self.dunia_cog.mimic_effect_active_channel_id == ctx.channel.id:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] MIMIC EFFECT pada jawaban aktif di channel ini.")
            return True
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] MIMIC EFFECT pada jawaban tidak aktif di channel ini.")
        return False

    def end_game_cleanup_global(self, channel_id, game_type=None):
        """Membersihkan state game dari cog ini setelah game berakhir."""
        self.active_games.discard(channel_id)
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] end_game_cleanup_global dipanggil untuk channel {channel_id}, tipe {game_type}. Active games (this cog): {self.active_games}")

        if game_type == 'werewolf' and channel_id in self.werewolf_game_states:
            game_state = self.werewolf_game_states.get(channel_id)
            if game_state and game_state.get('voice_client'):
                self.bot.loop.create_task(game_state['voice_client'].disconnect())
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Disconnect voice client Werewolf di channel {channel_id}.")
            if game_state and 'game_task' in game_state and not game_state['game_task'].done():
                game_state['game_task'].cancel()
            del self.werewolf_game_states[channel_id]
            self.active_werewolf_setup_messages.pop(channel_id, None) # Hapus referensi pesan setup
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Cleanup Werewolf state untuk channel {channel_id}.")
        
        if game_type == 'horse_racing' and channel_id in self.horse_racing_states:
            game_state = self.horse_racing_states[channel_id]
            if game_state.get('betting_timer') and not game_state['betting_timer'].done():
                game_state['betting_timer'].cancel()
            if game_state.get('race_timer') and not game_state['race_timer'].done():
                game_state['race_timer'].cancel()
            if game_state.get('game_task') and not game_state['game_task'].done():
                game_state['game_task'].cancel()
            del self.horse_racing_states[channel_id]
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Cleanup Horse Racing state untuk channel {channel_id}.")


    # --- GAME: WEREWOLF ---
    @commands.command(name="setwerewolf", help="[Admin/Host] Atur peran dan media game Werewolf global.")
    async def set_werewolf_config(self, ctx):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Command !setwerewolf dipanggil oleh {ctx.author.display_name} di channel: {ctx.channel.name} ({ctx.channel.id}).")
        
        game_state = self.werewolf_game_states.get(ctx.channel.id)
        if not (game_state and ctx.author.id == game_state['host'].id) and not ctx.author.guild_permissions.manage_channels:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !setwerewolf: Bukan host atau Admin, blokir.")
            return await ctx.send("Hanya host game Werewolf yang aktif di channel ini atau admin server yang bisa mengatur konfigurasi.", ephemeral=True)

        total_players_for_setup = game_state.get('total_players', 0) if game_state else 0 

        initial_view = WerewolfRoleSetupView(self, ctx.channel.id, total_players_for_setup, self.global_werewolf_config.get('default_config', {}))
        message = await ctx.send(embed=initial_view.create_embed(), view=initial_view)
        self.active_werewolf_setup_messages[ctx.channel.id] = message.id # Simpan ID pesan setup
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Menu setup Werewolf dikirim ke channel {ctx.channel.name}.")


    @commands.command(name="startwerewolf", help="Mulai game Werewolf (simulasi alur).")
    @commands.cooldown(1, 30, commands.BucketType.channel) 
    async def start_werewolf_game_example(self, ctx):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Command !startwerewolf dipanggil oleh {ctx.author.display_name} di channel: {ctx.channel.name} ({ctx.channel.id})")
        if await self._check_mimic_attack(ctx): return 
        if not await self.start_game_check_global(ctx): return
        
        self.werewolf_game_states[ctx.channel.id] = {
            'host': ctx.author,
            'players': [], 
            'voice_client': None,
            'game_task': None,
            'total_players': 0 
        }
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !startwerewolf: State game awal diinisialisasi.")
        
        if not ctx.author.voice or not ctx.author.voice.channel:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !startwerewolf: Pemanggil tidak di voice channel.")
            self.end_game_cleanup_global(ctx.channel.id, game_type='werewolf')
            return await ctx.send("Untuk bermain Werewolf, kamu dan pemain lain harus berada di **voice channel** yang sama!", ephemeral=True)

        vc_channel = ctx.author.voice.channel
        game_players = [m for m in vc_channel.members if not m.bot]
        self.werewolf_game_states[ctx.channel.id]['players'] = game_players
        self.werewolf_game_states[ctx.channel.id]['total_players'] = len(game_players)
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !startwerewolf: Pemain di VC ditemukan: {len(game_players)}.")

        players_in_vc = [m for m in vc_channel.members if not m.bot and m in game_players]
        
        if len(players_in_vc) < 3:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !startwerewolf: Jumlah pemain di VC kurang dari 3. ({len(players_in_vc)} pemain).")
            self.end_game_cleanup_global(ctx.channel.id, game_type='werewolf')
            return await ctx.send("Jumlah pemain di voice channel terlalu sedikit untuk memulai game Werewolf. Minimal 3 pemain aktif!", ephemeral=True)

        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !startwerewolf: Pengecekan awal berhasil. Mencoba bergabung VC.")
        
        try:
            if not ctx.voice_client or ctx.voice_client.channel != vc_channel:
                await vc_channel.connect()
                await ctx.send(f"Bot bergabung ke voice channel: **{vc_channel.name}** untuk Werewolf.", delete_after=10)
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !startwerewolf: Bot berhasil bergabung ke VC.")
            
            game_state = self.werewolf_game_states.setdefault(ctx.channel.id, {})
            game_state['voice_client'] = ctx.voice_client

        except discord.Forbidden:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !startwerewolf: Bot tidak punya izin join VC. Forbidden.")
            self.end_game_cleanup_global(ctx.channel.id, game_type='werewolf')
            return await ctx.send("Bot tidak memiliki izin untuk bergabung ke voice channel Anda. Pastikan saya memiliki izin `Connect` dan `Speak`.", ephemeral=True)
        except Exception as e:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !startwerewolf: Error saat bot bergabung VC: {e}.")
            self.end_game_cleanup_global(ctx.channel.id, game_type='werewolf')
            return await ctx.send(f"Terjadi kesalahan saat bot bergabung ke voice channel: `{e}`", ephemeral=True)

        await ctx.send("Game Werewolf akan dimulai! Bersiaplah...")
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !startwerewolf: Memulai alur game Werewolf...")
        
        game_task = self.bot.loop.create_task(self._werewolf_game_flow(ctx, ctx.channel.id, players_in_vc))
        self.werewolf_game_states[ctx.channel.id]['game_task'] = game_task


    async def _werewolf_game_flow(self, ctx, channel_id, players):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] _werewolf_game_flow dimulai untuk channel {channel_id}.")
        try:
            await self._send_werewolf_visual(ctx.channel, "game_start")
            await self._play_werewolf_audio(ctx.channel, "game_start_audio_url") # Memutar audio otomatis
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Werewolf Flow: Fase Game Start selesai.")
            
            await asyncio.sleep(7)
            await ctx.send("Malam telah tiba... Para Werewolf beraksi!")
            await self._send_werewolf_visual(ctx.channel, "night_phase")
            await self._play_werewolf_audio(ctx.channel, "night_phase_audio_url") # Memutar audio otomatis
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Werewolf Flow: Fase Malam selesai.")

            await asyncio.sleep(15)
            await ctx.send("Pagi telah tiba! Siapa yang menjadi korban malam ini?")
            await self._send_werewolf_visual(ctx.channel, "night_resolution")
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Werewolf Flow: Resolusi Malam selesai.")
            
            await asyncio.sleep(3)
            await ctx.send("Mari kita diskusikan!")
            await self._send_werewolf_visual(ctx.channel, "day_phase")
            await self._play_werewolf_audio(ctx.channel, "day_phase_audio_url") # Memutar audio otomatis
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Werewolf Flow: Fase Siang selesai.")
            
            await asyncio.sleep(10)
            await ctx.send("Waktunya voting!")
            # vote_phase_audio_url dihapus, jadi tidak diputar otomatis
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Werewolf Flow: Fase Voting selesai.")

            await asyncio.sleep(5)
            await ctx.send("Game Werewolf berakhir. Selamat kepada para pemenang!")
            # game_end_audio_url dihapus, jadi tidak diputar otomatis
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Werewolf Flow: Game berakhir secara normal.")
            
        except asyncio.CancelledError:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Werewolf game flow for channel {channel_id} dibatalkan (CancelledError).")
            await ctx.send("Game Werewolf dihentikan lebih awal.")
        except Exception as e:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Werewolf Flow: ERROR fatal di channel {channel_id}: {e}.")
            await ctx.send(f"Terjadi kesalahan fatal pada game Werewolf: `{e}`. Game dihentikan.")
        finally:
            self.end_game_cleanup_global(channel_id, game_type='werewolf')
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] _werewolf_game_flow selesai atau dibatalkan untuk channel {channel_id}.")

    # --- Fungsi Visual & Audio Werewolf ---
    async def _send_werewolf_visual(self, channel: discord.TextChannel, phase: str):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Mengirim visual Werewolf untuk fase: {phase} di channel {channel.name}.")
        global_config = self.global_werewolf_config.get('default_config', {})
        image_urls = global_config.get('image_urls', {})

        visual_url = None
        if phase == "game_start": visual_url = image_urls.get('game_start_image_url')
        elif phase == "night_phase": visual_url = image_urls.get('night_phase_image_url')
        elif phase == "day_phase": visual_url = image_urls.get('day_phase_image_url')
        elif phase == "night_resolution": visual_url = image_urls.get('night_resolution_image_url')
        # Menghapus werewolf_win_image_url dan villager_win_image_url dari pemilihan visual
        # elif phase == "werewolf_win": visual_url = image_urls.get('werewolf_win_image_url')
        # elif phase == "villager_win": visual_url = image_urls.get('villager_win_image_url')


        embed = discord.Embed(
            title=f"Fase Werewolf: {phase.replace('_', ' ').title()}",
            description="Detail informasi tentang fase game ini akan muncul di sini.",
            color=discord.Color.dark_purple()
        )

        if visual_url and visual_url.lower().endswith(('.gif', '.png', '.jpg', '.jpeg')):
            embed.set_image(url=visual_url)
            await channel.send(embed=embed)
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Visual Werewolf dengan URL {visual_url} dikirim.")
        else:
            await channel.send(embed=embed)
            if visual_url:
                await channel.send("ℹ️ URL gambar yang diberikan tidak valid atau bukan format gambar/GIF yang didukung. Mengirim pesan tanpa gambar.")
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] URL visual Werewolf tidak valid: {visual_url}.")
            else:
                await channel.send("ℹ️ URL gambar untuk fase ini belum diatur.")
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] URL visual Werewolf tidak diatur untuk fase {phase}.")


    async def _play_werewolf_audio(self, text_channel: discord.TextChannel, audio_type: str):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Mencoba memutar audio Werewolf: {audio_type} di channel {text_channel.name}.")
        game_state = self.werewolf_game_states.get(text_channel.id)
        if not game_state or not game_state.get('voice_client'):
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Tidak ada voice client atau game tidak aktif untuk audio Werewolf.")
            return

        voice_client = game_state['voice_client']
        global_config = self.global_werewolf_config.get('default_config', {})
        audio_urls = global_config.get('audio_urls', {})

        audio_url = None
        if audio_type == "game_start_audio_url": audio_url = audio_urls.get('game_start_audio_url')
        elif audio_type == "night_phase_audio_url": audio_url = audio_urls.get('night_phase_audio_url')
        elif audio_type == "day_phase_audio_url": audio_url = audio_urls.get('day_phase_audio_url')
        # vote_phase_audio_url dan game_end_audio_url sudah dihapus, jadi tidak perlu di sini
        # elif audio_type == "vote_phase_audio_url": audio_url = audio_urls.get('vote_phase_audio_url')
        # elif audio_type == "game_end_audio_url": audio_url = audio_urls.get('game_end_audio_url')

        if audio_url and self.music_cog: 
            try:
                if voice_client.is_playing() or voice_client.is_paused():
                    voice_client.stop()
                
                # Memastikan Music.YTDLSource diimpor atau didefinisikan di Music cog
                # Asumsi Music.YTDLSource adalah bagian dari Music cog yang dimuat
                if hasattr(self.music_cog, 'YTDLSource'): # Pengecekan lebih aman
                    source = await self.music_cog.YTDLSource.from_url(audio_url, loop=self.bot.loop, stream=True)
                    voice_client.play(source, after=lambda e: print(f'[{datetime.now()}] [DEBUG GLOBAL EVENTS] Player error in Werewolf audio: {e}') if e else None)
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Audio Werewolf '{audio_type}' berhasil diputar.")
                else:
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Music.YTDLSource tidak ditemukan di Music cog.")
            except Exception as e:
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Gagal memutar audio Werewolf '{audio_type}': {e}.")
                await text_channel.send(f"⚠️ Maaf, gagal memutar audio untuk fase ini: `{e}`")
        elif not self.music_cog:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Music cog tidak ditemukan, tidak dapat memutar audio Werewolf.")
        else:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] URL audio untuk '{audio_type}' tidak diatur.")


    @commands.command(name="stopwerewolfaudio", help="Hentikan audio Werewolf yang sedang diputar.")
    async def stop_werewolf_audio(self, ctx):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Command !stopwerewolfaudio dipanggil oleh {ctx.author.display_name}.")
        game_state = self.werewolf_game_states.get(ctx.channel.id)
        if not game_state or (ctx.author.id != game_state.get('host', None) and not ctx.author.guild_permissions.manage_channels):
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !stopwerewolfaudio: Bukan host atau moderator, blokir.")
            return await ctx.send("Hanya host game Werewolf atau moderator yang bisa menghentikan audio.", ephemeral=True)
        
        voice_client = game_state.get('voice_client')
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            await ctx.send("Audio Werewolf dihentikan.")
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Audio Werewolf dihentikan di channel {ctx.channel.name}.")
        else:
            await ctx.send("Tidak ada audio Werewolf yang sedang diputar.")
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Tidak ada audio Werewolf yang diputar di channel {ctx.channel.name}.")


    # --- GAME: RODA TAKDIR GILA! ---
    @commands.command(name="putarroda", aliases=['putar'], help="Putar Roda Takdir Gila untuk takdir tak terduga!")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def putarroda(self, ctx):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Command !putarroda dipanggil oleh {ctx.author.display_name} di channel: {ctx.channel.name} ({ctx.channel.id}).")
        if await self._check_mimic_attack(ctx): return # Cek mimic attack
        
        channel_id = ctx.channel.id
        guild = ctx.guild

        if not guild:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !putarroda: Command dipanggil di luar guild, blokir.")
            return await ctx.send("Roda Takdir Gila hanya bisa diputar di server Discord!", ephemeral=True)

        if channel_id not in self.wheel_of_fate_config:
            self.wheel_of_fate_config[channel_id] = {
                'cost': self.wheel_spin_cost,
                'spinning_gif_url': 'https://i.imgur.com/39hN44u.gif',
                'segments': self._get_default_wheel_segments(),
                'outcome_image_urls': {}
            }
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !putarroda: Konfigurasi roda takdir untuk channel {channel_id} diinisialisasi default.")
        
        current_wheel_config = self.wheel_of_fate_config[channel_id]
        
        user = ctx.author
        user_id_str = str(user.id)
        bank_data = load_json_from_root('data/bank_data.json')
        current_balance = bank_data.setdefault(user_id_str, {'balance': 0, 'debt': 0})['balance']

        if current_balance < current_wheel_config['cost']:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !putarroda: {user.display_name} saldo tidak cukup ({current_balance} < {current_wheel_config['cost']}).")
            return await ctx.send(f"Saldo RSWNmu tidak cukup untuk memutar roda ({current_wheel_config['cost']} RSWN diperlukan). Kamu punya: **{current_balance} RSWN**.", ephemeral=True)
        
        bank_data[user_id_str]['balance'] -= current_wheel_config['cost']
        save_json_to_root(bank_data, 'data/bank_data.json')
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !putarroda: Saldo {user.display_name} dikurangi {current_wheel_config['cost']} RSWN.")

        wheel_stats = self.wheel_of_fate_data.setdefault('players_stats', {})
        wheel_stats.setdefault(user_id_str, {'spins': 0, 'wins_rsw': 0, 'losses_rsw': 0, 'weird_effects': 0})
        wheel_stats[user_id_str]['spins'] += 1
        save_json_to_root(self.wheel_of_fate_data, 'data/wheel_of_mad_fate.json')
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !putarroda: Statistik roda takdir {user.display_name} diupdate.")

        spinning_gif_url = current_wheel_config.get('spinning_gif_url', 'https://i.imgur.com/39hN44u.gif')
        
        spin_embed = discord.Embed(
            title="🌀 Roda Takdir Gila Sedang Berputar! 🌀",
            description=f"{user.mention} telah membayar **{current_wheel_config['cost']} RSWN** dan memutar roda... Apa takdir yang menantinya?",
            color=discord.Color.gold()
        )
        if spinning_gif_url:
            spin_embed.set_image(url=spinning_gif_url)
        
        spin_message = await ctx.send(embed=spin_embed)
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !putarroda: Pesan putaran roda dikirim.")
        
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
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !putarroda: Hasil roda dikirim. Outcome: {outcome['type']}.")
        
        if self.dunia_cog:
            await self.dunia_cog._apply_wheel_consequence(guild, channel, user, outcome)
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !putarroda: Efek roda diterapkan melalui DuniaHidup cog.")
        else:
            await channel.send("⚠️ Error: DuniaHidup cog tidak ditemukan, efek roda takdir tidak dapat diterapkan.")
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !putarroda: DuniaHidup cog tidak ditemukan, efek tidak diterapkan.")


    def _get_default_wheel_segments(self):
        """Mendapatkan segmen default untuk Roda Takdir Gila."""
        return [
            {'type': 'jackpot_rsw', 'description': "🎉 JACKPOT! Kamu mendapatkan RSWN!", 'color': (255, 215, 0), 'weight': 15, 'amount': 500},
            {'type': 'jackpot_rsw_big', 'description': "MEGA JACKPOT! Kamu mendapatkan RSWN BESAR!", 'color': (255, 165, 0), 'weight': 3, 'amount': 1500},
            {'type': 'boost_exp', 'description': "⚡ Kamu mendapatkan Boost EXP 2x selama 1 jam! Maksimalkan diskusimu!", 'color': (0, 255, 0), 'weight': 10},
            {'type': 'protection', 'description': "🛡️ Kamu mendapatkan Perlindungan Absurd! Kebal dari 1 efek negatif berikutnya.", 'color': (173, 216, 230), 'weight': 7},
            {'type': 'tax', 'description': "💸 Roda menarik Pajak Takdir! Kamu kehilangan RSWN.", 'color': (139, 0, 0), 'weight': 15},
            {'type': 'nickname_transform', 'description': "✨ Wajahmu berubah! Nickname-mu jadi aneh selama 1 jam.", 'color': (147, 112, 219), 'weight': 10},
            {'type': 'message_mishap', 'description': "🗣️ Kata-katamu tersangkut! Pesanmu jadi aneh selama 30 menit.", 'color': (255, 69, 0), 'weight': 8},
            {'type': 'bless_random_user', 'description': "🎁 Sebuah Berkat Random! User acak mendapatkan RSWN.", 'color': (255, 192, 203), 'weight': 10, 'amount': 750},
            {'type': 'curse_mute_random', 'description': "🔇 Kutukan Mute Kilat! User acak kena timeout 60 detik.", 'color': (75, 0, 130), 'weight': 7},
            {'type': 'ping_random_user', 'description': "🔔 Panggilan Darurat! User acak di-ping sampai nongol.", 'color': (255, 255, 0), 'weight': 5},
            {'type': 'emoji_rain', 'description': "🥳 Hujan Emoji! Channel ini diguyur emoji acak.", 'color': (0, 255, 255), 'weight': 5},
            {'type': 'channel_rename', 'description': "📛 Nama Channel Berubah Absurd! Channel ini jadi konyol 15 menit.", 'color': (255, 105, 180), 'weight': 3},
            {'type': 'random_duck', 'description': "🦆 Tidak Terjadi Apa-Apa, Tapi Ada Bebek!", 'color': (255, 255, 255), 'weight': 5},
            {'type': 'absurd_fortune', 'description': "🔮 Sebuah Ramalan Halu! Takdirmu akan sangat aneh.", 'color': (128, 0, 128), 'weight': 4}
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
                    return {'type': 'jackpot_rsw', 'description': "MEGA JACKPOT! Kamu mendapatkan **1500 RSWN**!", 'color': (255,165,0), 'amount': 1500}
                return segment.copy() 
        return random.choice(segments).copy() # Fallback (seharusnya tidak terjadi)


    # --- GAME: BALAPAN KUDA ---
    @commands.command(name="balapan", aliases=['race'], help="Mulai sesi taruhan Balapan Kuda!")
    @commands.cooldown(1, 60, commands.BucketType.channel)
    async def start_horse_race(self, ctx):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Command !balapan dipanggil oleh {ctx.author.display_name} di channel: {ctx.channel.name} ({ctx.channel.id}).")
        if await self._check_mimic_attack(ctx): return
        if not await self.start_game_check_global(ctx): return

        channel_id = ctx.channel.id
        
        # Inisialisasi state balapan kuda
        self.horse_racing_states[channel_id] = {
            'status': 'betting',
            'bets': {}, # {user_id: {'amount': int, 'horse_id': int}}
            'horses': [], # List of horse dictionaries
            'race_message': None, # Message object for race updates
            'betting_timer': None,
            'race_timer': None,
            'game_task': None,
            'track_length': 20, # Panjang lintasan (dalam 'langkah')
            'betting_duration': 30, # Durasi fase taruhan dalam detik
            'odds': {} # Odds untuk setiap kuda {horse_id: float}
        }
        race_state = self.horse_racing_states[channel_id]

        # Ambil daftar kuda dari JSON atau gunakan default
        horses_data = self.horse_racing_data.get('horses', self._get_default_horses())
        
        # Pilih 5 kuda acak untuk balapan ini
        if len(horses_data) < 5:
            horses_to_race = horses_data # Jika kurang dari 5, pakai semua
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Data kuda kurang dari 5, menggunakan semua yang ada ({len(horses_data)} kuda).")
        else:
            horses_to_race = random.sample(horses_data, 5)
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Memilih 5 kuda acak.")
        
        # Inisialisasi kuda dan hitung odds
        total_speed_mod = sum(h.get('speed_mod', 1.0) for h in horses_to_race)
        base_odds_multiplier = 4.0 # Sesuaikan ini untuk mengontrol rentang odds

        for i, horse in enumerate(horses_to_race):
            horse['id'] = i + 1 # Beri ID 1-based
            horse['position'] = 0.0 # Posisi awal (float untuk pergerakan akurat)
            horse['emoji'] = horse.get('emoji', '🐎') # Pastikan ada emoji default
            race_state['horses'].append(horse)
            
            speed_mod = horse.get('speed_mod', 1.0)
            if speed_mod == 0: speed_mod = 0.1 # Hindari pembagian nol

            calculated_odds = (total_speed_mod / speed_mod) / (len(horses_to_race) / base_odds_multiplier)
            
            min_odds = 1.2 # Odds minimum (misal: 1.2x)
            max_odds = 5.0 # Odds maksimum (misal: 5.0x)
            race_state['odds'][horse['id']] = max(min_odds, min(max_odds, calculated_odds))

        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Inisialisasi state untuk channel {channel_id} dengan odds dinamis.")

        betting_embed = discord.Embed(
            title="🐎 Balapan Kuda Dimulai! 🐎",
            description=f"Waktunya memasang taruhan! Kamu punya **{race_state['betting_duration']} detik** untuk bertaruh.\n\n"
                        "**Taruhan Saat Ini:**\n" + self._get_current_bets_text(race_state['bets'], race_state['horses']), # Tambah ringkasan taruhan awal
            color=discord.Color.blue()
        )
        betting_embed.add_field(name="Kuda yang Berkompetisi", value=self._get_horse_list_text(race_state['horses'], race_state['odds']), inline=False)
        betting_embed.add_field(name="Cara Bertaruh", value="Gunakan `!taruhan <jumlah_rsw> <nomor_kuda>`\nContoh: `!taruhan 100 3` (bertaruh 100 RSWN pada Kuda #3)", inline=False)
        betting_embed.set_footer(text="Taruhan ditutup dalam...")
        betting_embed.set_image(url="https://media.giphy.com/media/l4FGJm7hXG1r0J0I/giphy.gif") # GIF taruhan

        race_state['race_message'] = await ctx.send(embed=betting_embed)
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Pesan taruhan dikirim.")

        # Start betting timer
        race_state['betting_timer'] = self.bot.loop.create_task(self._betting_countdown(ctx, channel_id))
        race_state['game_task'] = self.bot.loop.create_task(self._horse_race_flow(ctx, channel_id))


    def _get_default_horses(self):
        """Mengembalikan daftar kuda default."""
        return [
            {"name": "Shadowfax", "emoji": "🐎", "speed_mod": 1.1, "description": "Kuda legendaris yang cepat seperti angin."},
            {"name": "Black Beauty", "emoji": "🏇", "speed_mod": 1.0, "description": "Kuda klasik dengan stamina luar biasa."},
            {"name": "Spirit", "emoji": "🐴", "speed_mod": 1.05, "description": "Kuda liar yang tak kenal lelah."},
            {"name": "Thunderhoof", "emoji": "🦄", "speed_mod": 0.95, "description": "Kuda perkasa dengan kekuatan guntur."},
            {"name": "Starlight", "emoji": "💫", "speed_mod": 1.0, "description": "Kuda elegan yang bersinar di lintasan."},
            {"name": "Nightmare", "emoji": "👻", "speed_mod": 0.9, "description": "Kuda misterius yang sulit ditebak."},
            {"name": "Pegasus", "emoji": "🕊️", "speed_mod": 1.15, "description": "Kuda bersayap, favorit para dewa."},
            {"name": "Comet", "emoji": "🌠", "speed_mod": 1.0, "description": "Kuda lincah secepat komet."},
            {"name": "Ironhide", "emoji": "🧲", "speed_mod": 0.85, "description": "Kuda baja yang sangat tangguh, tapi sedikit lambat."},
            {"name": "Flash", "emoji": "⚡", "speed_mod": 1.2, "description": "Kuda tercepat, jarang terlihat kalah!"}
        ]

    def _get_horse_list_text(self, horses, odds):
        """Membuat teks daftar kuda untuk embed."""
        text = ""
        for horse in horses:
            odd_value = odds.get(horse['id'], 1.0)
            text += f"**{horse['id']}. {horse['emoji']} {horse['name']}** (Odds: {odd_value:.2f}x)\n"
        return text

    async def _betting_countdown(self, ctx, channel_id):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Betting countdown dimulai untuk channel {channel_id}.")
        race_state = self.horse_racing_states.get(channel_id)
        if not race_state: return

        for i in range(race_state['betting_duration'], 0, -5):
            if race_state.get('race_message') and i % 5 == 0: # Pastikan pesan masih ada
                await race_state['race_message'].edit(embed=race_state['race_message'].embeds[0].set_footer(text=f"Taruhan ditutup dalam {i} detik!"))
            await asyncio.sleep(5)
        
        if race_state.get('race_message'): # Pastikan pesan masih ada
            await race_state['race_message'].edit(embed=race_state['race_message'].embeds[0].set_footer(text="Taruhan DITUTUP!"))
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Betting countdown selesai untuk channel {channel_id}.")


    async def _horse_race_flow(self, ctx, channel_id):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Alur balapan dimulai untuk channel {channel_id}.")
        race_state = self.horse_racing_states.get(channel_id)
        if not race_state: return

        try:
            await asyncio.sleep(race_state['betting_duration']) # Tunggu fase taruhan selesai

            if not race_state['bets']:
                await ctx.send("Tidak ada yang bertaruh! Balapan dibatalkan.", delete_after=15)
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Tidak ada taruhan, balapan dibatalkan.")
                # Pastikan game dibersihkan jika dibatalkan karena tidak ada taruhan
                self.end_game_cleanup_global(channel_id, game_type='horse_racing')
                return
            
            race_state['status'] = 'racing'
            await ctx.send("🏁 **BALAPAN DIMULAI!** 🏁")
            
            # Update pesan balapan secara berkala
            race_state['race_message'] = await ctx.send(embed=self._get_race_progress_embed(race_state))
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Pesan progres balapan dikirim.")

            while True:
                await asyncio.sleep(2) # Update setiap 2 detik
                
                # Gerakkan kuda
                for horse in race_state['horses']:
                    move_distance = random.uniform(0.5, 2.5) * horse.get('speed_mod', 1.0) 
                    horse['position'] += move_distance
                    if horse['position'] >= race_state['track_length']:
                        horse['position'] = race_state['track_length'] 
                
                race_state['horses'].sort(key=lambda h: h['position'], reverse=True)

                if race_state.get('race_message'): # Pastikan pesan masih ada
                    await race_state['race_message'].edit(embed=self._get_race_progress_embed(race_state))
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Progres balapan diperbarui.")

                winner = None
                for horse in race_state['horses']:
                    if horse['position'] >= race_state['track_length']:
                        winner = horse
                        break
                
                if winner:
                    await ctx.send(f"🎉 **{winner['emoji']} {winner['name']}** MENANG! 🎉")
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Pemenang: {winner['name']}.")
                    await self._distribute_winnings(ctx, channel_id, winner['id'])
                    break

        except asyncio.CancelledError:
            await ctx.send("Balapan Kuda dihentikan.")
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Game flow dibatalkan (CancelledError) untuk channel {channel_id}.")
        except Exception as e:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: ERROR fatal di channel {channel_id}: {e}.")
            await ctx.send(f"Terjadi kesalahan fatal pada Balapan Kuda: `{e}`. Game dihentikan.")
        finally:
            self.end_game_cleanup_global(channel_id, game_type='horse_racing')
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: _horse_race_flow selesai atau dibatalkan untuk channel {channel_id}.")

    def _get_race_progress_embed(self, race_state):
        """Membuat embed yang menampilkan progres balapan."""
        embed = discord.Embed(
            title="🏁 Progres Balapan Kuda 🏁",
            description="Siapa yang akan mencapai garis finish duluan?",
            color=discord.Color.green()
        )
        
        track_length = race_state['track_length']
        progress_text = ""
        for horse in race_state['horses']:
            progress_int = int(horse['position'])
            progress = min(progress_int, track_length) # Gunakan int untuk visualisasi
            
            track_segment = "─" * progress
            remaining_segment = "─" * max(0, track_length - progress - 1)
            
            progress_bar = f"[{track_segment}{horse['emoji']}{remaining_segment}]"
            
            progress_text += f"**{horse['id']}. {horse['name']}**\n`{progress_bar}` {progress_int}/{track_length}\n\n"
        
        embed.add_field(name="Lintasan", value=progress_text, inline=False)
        embed.set_image(url="https://media.giphy.com/media/l4FGJm7hXG1r0J0I/giphy.gif") # GIF balapan
        return embed

    async def _distribute_winnings(self, ctx, channel_id, winning_horse_id):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Mendistribusikan kemenangan untuk channel {channel_id}.")
        race_state = self.horse_racing_states.get(channel_id)
        if not race_state: return

        bank_data = load_json_from_root('data/bank_data.json')
        odds = race_state['odds'].get(winning_horse_id, 1.0)
        
        winners = []
        losers = []

        for user_id_str, bet_info in race_state['bets'].items():
            user = ctx.guild.get_member(int(user_id_str))
            if not user: continue

            if bet_info['horse_id'] == winning_horse_id:
                winnings = int(bet_info['amount'] * odds)
                bank_data.setdefault(user_id_str, {'balance': 0, 'debt': 0})['balance'] += winnings
                winners.append(f"{user.mention} (Menang: **{winnings} RSWN**)")
                await self.give_rewards_with_bonus_check(user, ctx.guild.id, custom_rsw=winnings, custom_exp=50)
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: {user.display_name} menang {winnings} RSWN.")
            else:
                losers.append(f"{user.mention} (Kalah: {bet_info['amount']} RSWN)")
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: {user.display_name} kalah {bet_info['amount']} RSWN.")
        
        save_json_to_root(bank_data, 'data/bank_data.json')

        winning_horse_name = next((h['name'] for h in race_state['horses'] if h['id'] == winning_horse_id), "Kuda Misterius")

        result_embed = discord.Embed(
            title=f"🏆 Hasil Balapan Kuda! 🏆",
            description=f"Kuda **{winning_horse_name}** (#{winning_horse_id}) adalah pemenangnya dengan odds **{odds:.2f}x**!",
            color=discord.Color.gold()
        )

        if winners:
            result_embed.add_field(name="Pemenang Taruhan", value="\n".join(winners), inline=False)
        else:
            result_embed.add_field(name="Pemenang Taruhan", value="Tidak ada yang berhasil menebak dengan benar!", inline=False)
        
        if losers:
            result_embed.add_field(name="Kalah Taruhan", value="\n".join(losers), inline=False)

        await ctx.send(embed=result_embed)
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Hasil balapan dikirim.")


    @commands.command(name="taruhan", help="Pasang taruhanmu di Balapan Kuda! `!taruhan <jumlah> <nomor_kuda>`")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def place_horse_bet(self, ctx, amount: int, horse_id: int):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Command !taruhan dipanggil oleh {ctx.author.display_name} di channel: {ctx.channel.name} ({ctx.channel.id}) dengan jumlah {amount} untuk kuda {horse_id}.")
        channel_id = ctx.channel.id
        race_state = self.horse_racing_states.get(channel_id)

        if not race_state or race_state['status'] != 'betting':
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !taruhan: Tidak ada balapan aktif atau fase bukan taruhan.")
            return await ctx.send("Tidak ada sesi taruhan balapan kuda yang aktif di channel ini.", ephemeral=True)

        if amount <= 0:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !taruhan: Jumlah taruhan tidak valid ({amount}).")
            return await ctx.send("Jumlah taruhan harus lebih dari 0.", ephemeral=True)
        
        if amount > 5000: # Batas taruhan
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !taruhan: Jumlah taruhan terlalu besar ({amount}).")
            return await ctx.send("Jumlah taruhan maksimal adalah 5000 RSWN.", ephemeral=True)

        selected_horse = next((h for h in race_state['horses'] if h['id'] == horse_id), None)
        if not selected_horse:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !taruhan: Kuda tidak ditemukan ({horse_id}).")
            return await ctx.send(f"Kuda #{horse_id} tidak ditemukan. Pilih nomor kuda yang valid dari daftar.", ephemeral=True)

        user_id_str = str(ctx.author.id)
        bank_data = load_json_from_root('data/bank_data.json')
        current_balance = bank_data.setdefault(user_id_str, {'balance': 0, 'debt': 0})['balance']

        if current_balance < amount:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !taruhan: {ctx.author.display_name} saldo tidak cukup ({current_balance} < {amount}).")
            return await ctx.send(f"Saldo RSWNmu tidak cukup untuk taruhan ini. Kamu punya: **{current_balance} RSWN**.", ephemeral=True)
        
        # Jika sudah pernah bertaruh, timpa taruhan sebelumnya
        if user_id_str in race_state['bets']:
            old_bet = race_state['bets'][user_id_str]
            bank_data[user_id_str]['balance'] += old_bet['amount'] # Kembalikan taruhan lama
            await ctx.send(f"Taruhanmu sebelumnya sebesar {old_bet['amount']} RSWN pada Kuda #{old_bet['horse_id']} dikembalikan. ", ephemeral=True)
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !taruhan: Taruhan lama {ctx.author.display_name} dikembalikan.")

        bank_data[user_id_str]['balance'] -= amount
        save_json_to_root(bank_data, 'data/bank_data.json')

        race_state['bets'][user_id_str] = {'amount': amount, 'horse_id': horse_id}
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !taruhan: Taruhan {amount} RSWN pada Kuda #{horse_id} oleh {ctx.author.display_name} berhasil.")
        await ctx.send(f"✅ Taruhanmu sebesar **{amount} RSWN** pada **{selected_horse['emoji']} {selected_horse['name']}** (#**{horse_id}**) berhasil dipasang!", ephemeral=True)

        # Update embed taruhan jika pesan masih ada
        if race_state['race_message']:
            betting_embed = race_state['race_message'].embeds[0]
            # Temukan field "Kuda yang Berkompetisi" dan perbarui
            for i, field in enumerate(betting_embed.fields):
                if field.name == "Kuda yang Berkompetisi":
                    betting_embed.set_field_at(
                        index=i,
                        name="Kuda yang Berkompetisi",
                        value=self._get_horse_list_text(race_state['horses'], race_state['odds']),
                        inline=False
                    )
                    break
            # Tambahkan atau perbarui field "Taruhan Saat Ini"
            current_bets_field_value = self._get_current_bets_text(race_state['bets'], race_state['horses'])
            found_bets_field = False
            for i, field in enumerate(betting_embed.fields):
                if field.name == "Taruhan Saat Ini":
                    betting_embed.set_field_at(
                        index=i,
                        name="Taruhan Saat Ini",
                        value=current_bets_field_value,
                        inline=False
                    )
                    found_bets_field = True
                    break
            if not found_bets_field:
                betting_embed.add_field(name="Taruhan Saat Ini", value=current_bets_field_value, inline=False)

            await race_state['race_message'].edit(embed=betting_embed)
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !taruhan: Pesan taruhan diupdate.")

    def _get_current_bets_text(self, bets, horses):
        if not bets:
            return "Belum ada taruhan."
        
        bet_summary = {} # {horse_id: {'total_amount': 0, 'bettors': []}}
        for user_id_str, bet_info in bets.items():
            horse_id = bet_info['horse_id']
            amount = bet_info['amount']
            bet_summary.setdefault(horse_id, {'total_amount': 0, 'bettors': []})
            bet_summary[horse_id]['total_amount'] += amount
            
            user_obj = self.bot.get_user(int(user_id_str))
            user_display_name = user_obj.display_name if user_obj else f"User_{user_id_str[:4]}"
            
            bet_summary[horse_id]['bettors'].append(f"{user_display_name} ({amount} RSWN)")

        text = ""
        for horse in horses:
            summary = bet_summary.get(horse['id'])
            if summary:
                text += f"**{horse['emoji']} {horse['name']}** (#{horse['id']}): Total **{summary['total_amount']} RSWN**\n"
                text += "  " + ", ".join(summary['bettors']) + "\n"
            else:
                text += f"**{horse['emoji']} {horse['name']}** (#{horse['id']}): Belum ada taruhan.\n"
        return text

    @commands.command(name="stopbalapan", help="[Admin/Host] Hentikan balapan kuda yang sedang berjalan.")
    async def stop_horse_race(self, ctx):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Command !stopbalapan dipanggil oleh {ctx.author.display_name}.")
        channel_id = ctx.channel.id
        race_state = self.horse_racing_states.get(channel_id)

        if not race_state:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !stopbalapan: Tidak ada balapan aktif.")
            return await ctx.send("Tidak ada balapan kuda yang sedang berjalan di channel ini.", ephemeral=True)

        if not ctx.author.guild_permissions.manage_channels:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !stopbalapan: Bukan admin, blokir.")
            return await ctx.send("Hanya admin server yang bisa menghentikan balapan kuda.", ephemeral=True)

        await ctx.send("Balapan Kuda dihentikan secara paksa oleh admin.")
        self.end_game_cleanup_global(channel_id, game_type='horse_racing')
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda dihentikan secara paksa di channel {channel_id}.")


async def setup(bot):
    await bot.add_cog(GamesGlobalEvents(bot))
