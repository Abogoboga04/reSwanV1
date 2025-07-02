import discord
from discord.ext import commands, tasks
import json
import random
import asyncio
import os
from datetime import datetime, time, timedelta
import string
import pytz # Import pytz untuk zona waktu
import sys # Untuk stderr

# --- Helper Functions ---
def load_json_from_root(file_path, default_value=None):
    """
    Memuat data JSON dari file yang berada di root direktori proyek bot.
    Menambahkan `default_value` yang lebih fleksibel.
    """
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        full_path = os.path.join(base_dir, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True) # Pastikan direktori ada
        with open(full_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[{datetime.now()}] [DEBUG HELPER] Peringatan: File {full_path} tidak ditemukan. Menggunakan nilai default.")
        return default_value if default_value is not None else {}
    except json.JSONDecodeError:
        print(f"[{datetime.now()}] [DEBUG HELPER] Peringatan: File {full_path} rusak (JSON tidak valid). Menggunakan nilai default.")
        return default_value if default_value is not None else {}

def save_json_to_root(data, file_path):
    """Menyimpan data ke file JSON di root direktori proyek."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    full_path = os.path.join(base_dir, file_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

# --- Discord UI Components for Werewolf Role Setup ---
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

# New Modal for quantity input
class RoleQuantityModal(discord.ui.Modal):
    def __init__(self, game_cog, role_name, current_quantity, total_players, message_to_update_id, channel_id):
        super().__init__(title=f"Atur Jumlah {role_name}")
        self.game_cog = game_cog
        self.role_name = role_name
        self.total_players = total_players
        self.message_to_update_id = message_to_update_id
        self.channel_id = channel_id

        self.quantity_input = discord.ui.TextInput(
            label=f"Jumlah {role_name} (Max: {total_players})",
            placeholder=f"Masukkan jumlah {role_name} (saat ini: {current_quantity})",
            default=str(current_quantity),
            style=discord.TextStyle.short,
            custom_id="role_quantity",
            max_length=2, # Max 99 players should be enough
            required=True
        )
        self.add_item(self.quantity_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True) # Defer the interaction

        try:
            new_quantity = int(self.quantity_input.value)
            if new_quantity < 0:
                return await interaction.followup.send("Jumlah peran tidak boleh negatif.", ephemeral=True)
            if new_quantity > self.total_players:
                return await interaction.followup.send(f"Jumlah peran melebihi total pemain ({self.total_players}).", ephemeral=True)

            # Update the global config
            current_config = self.game_cog.global_werewolf_config.setdefault('default_config', {})
            current_roles = current_config.setdefault('roles', {})
            current_roles[self.role_name] = new_quantity
            save_json_to_root(self.game_cog.global_werewolf_config, 'data/global_werewolf_config.json')

            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Jumlah {self.role_name} diatur ke {new_quantity} oleh {interaction.user.display_name}.")

            # Update the original message with the new roles
            try:
                channel = self.game_cog.bot.get_channel(self.channel_id)
                if channel:
                    message = await channel.fetch_message(self.message_to_update_id)
                    # Recreate the view to update buttons
                    updated_view = WerewolfRoleSetupView(
                        self.game_cog,
                        self.channel_id,
                        self.total_players,
                        self.game_cog.global_werewolf_config.get('default_config', {})
                    )
                    await message.edit(embed=updated_view.create_embed(), view=updated_view)
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pesan setup Werewolf di channel {channel.name} diperbarui setelah modal submit.")
            except discord.NotFound:
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pesan setup Werewolf tidak ditemukan untuk update setelah modal submit.")
            except Exception as e:
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Error update pesan setup Werewolf setelah modal submit: {e}")

            await interaction.followup.send(f"Jumlah **{self.role_name}** berhasil diatur ke `{new_quantity}`.", ephemeral=True)

        except ValueError:
            await interaction.followup.send("Input tidak valid. Harap masukkan angka.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Terjadi kesalahan: {e}", ephemeral=True)


class WerewolfMediaSetupModal(discord.ui.Modal):
    def __init__(self, game_cog, current_global_config, message_to_update_id, channel_id):
        super().__init__(title="Atur Media Werewolf (Global)")
        self.game_cog = game_cog
        self.current_global_config = current_global_config
        self.message_to_update_id = message_to_update_id
        self.channel_id = channel_id

        current_image_urls = current_global_config.get('image_urls', {})
        current_audio_urls = current_global_config.get('audio_urls', {})

        self.add_item(URLInput("Game Start Image URL (GIF)", "url_game_start_img", "URL untuk awal game (GIF/PNG/JPG)", current_image_urls.get('game_start_image_url', '')))
        self.add_item(URLInput("Night Phase Image URL (GIF)", "url_night_phase_img", "URL untuk fase malam (GIF/PNG/JPG)", current_image_urls.get('night_phase_image_url', '')))
        self.add_item(URLInput("Day Phase Image URL (GIF)", "url_day_phase_img", "URL untuk fase siang (GIF/PNG/JPG)", current_image_urls.get('day_phase_image_url', '')))
        self.add_item(URLInput("Night Resolution Image URL (GIF)", "url_night_res_img", "URL untuk resolusi malam (korban) (GIF/PNG/JPG)", current_image_urls.get('night_resolution_image_url', '')))

        self.add_item(URLInput("Game Start Audio URL (MP3/WebM)", "url_game_start_audio", "URL audio untuk awal game", current_audio_urls.get('game_start_audio_url', '')))
        self.add_item(URLInput("Night Phase Audio URL (MP3/WebM)", "url_night_phase_audio", "URL audio untuk fase malam", current_audio_urls.get('night_phase_audio_url', '')))
        self.add_item(URLInput("Day Phase Audio URL (MP3/WebM)", "url_day_phase_audio", "URL audio untuk fase siang", current_audio_urls.get('day_phase_audio_url', '')))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        global_config_ref = self.game_cog.global_werewolf_config.setdefault('default_config', {})

        global_config_ref['image_urls'] = {
            'game_start_image_url': self.children[0].value or None,
            'night_phase_image_url': self.children[1].value or None,
            'day_phase_image_url': self.children[2].value or None,
            'night_resolution_image_url': self.children[3].value or None,
        }

        global_config_ref['audio_urls'] = {
            'game_start_audio_url': self.children[4].value or None,
            'night_phase_audio_url': self.children[5].value or None,
            'day_phase_audio_url': self.children[6].value or None,
        }

        save_json_to_root(self.game_cog.global_werewolf_config, 'data/global_werewolf_config.json')
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Media Werewolf global disimpan oleh {interaction.user.display_name}.")

        try:
            channel = self.game_cog.bot.get_channel(self.channel_id)
            if channel:
                message = await channel.fetch_message(self.message_to_update_id)
                # Recreate the view to update its internal state and buttons/embed
                # Use the actual total_players from the current setup message or game state
                total_players_for_view = self.game_cog.werewolf_game_states.get(self.channel_id, {}).get('total_players')
                if not total_players_for_view:
                    # Fallback to current setup's total players if game not started
                    # This might require parsing the embed or storing total_players in active_werewolf_setup_messages
                    # For simplicity, if game not started, use the total_players from setup command
                    setup_message_id = self.game_cog.active_werewolf_setup_messages.get(self.channel_id)
                    if setup_message_id: # Use the ID stored
                        try:
                            # Try to extract from embed description of the existing message
                            # This is a bit fragile, better to pass total_players explicitly
                            description = message.embeds[0].description
                            total_players_line = next((line for line in description.split('\n') if "Total Pemain:" in line), None)
                            if total_players_line:
                                # Extract number between **
                                try:
                                    total_players_for_view = int(total_players_line.split('**')[1])
                                except (ValueError, IndexError):
                                    total_players_for_view = self.game_cog.global_werewolf_config.get('default_config', {}).get('min_players', 3)
                            else:
                                total_players_for_view = self.game_cog.global_werewolf_config.get('default_config', {}).get('min_players', 3)
                        except Exception:
                            total_players_for_view = self.game_cog.global_werewolf_config.get('default_config', {}).get('min_players', 3)
                    else:
                        total_players_for_view = self.game_cog.global_werewolf_config.get('default_config', {}).get('min_players', 3)


                view = WerewolfRoleSetupView(self.game_cog, self.channel_id,
                                            total_players_for_view,
                                            self.game_cog.global_werewolf_config.get('default_config', {}))
                await message.edit(embed=view.create_embed(), view=view)
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pesan setup Werewolf di channel {channel.name} diperbarui setelah media modal submit.")
        except discord.NotFound:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pesan setup Werewolf tidak ditemukan untuk update setelah media modal submit.")
        except Exception as e:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Error update pesan setup Werewolf setelah media modal submit: {e}")

        await interaction.followup.send("URL gambar dan audio global berhasil disimpan!", ephemeral=True)


class WerewolfRoleSetupView(discord.ui.View):
    def __init__(self, game_cog, channel_id, total_players, current_config):
        super().__init__(timeout=300)
        self.game_cog = game_cog
        self.channel_id = channel_id
        self.total_players = total_players
        # Always read from the global config for current values
        self.current_roles_config = current_config.get('roles', {}).copy()

        global_media_config = game_cog.global_werewolf_config.get('default_config', {})
        self.image_urls = global_media_config.get('image_urls', {}).copy()
        self.audio_urls = global_media_config.get('audio_urls', {}).copy()
        self.available_roles = game_cog.werewolf_roles_data.get('roles', {})

        self._add_role_buttons()

        # BARIS INI DIHAPUS UNTUK MENGHINDARI DUPLIKASI custom_id
        # Karena tombol 'setup_media' dan 'finish_role_setup'
        # sudah ditambahkan secara otomatis oleh decorator @discord.ui.button
        # self.add_item(discord.ui.Button(label="Atur Media Game (Global)", style=discord.ButtonStyle.secondary, custom_id="setup_media", row=4))
        # self.add_item(discord.ui.Button(label="Selesai Mengatur", style=discord.ButtonStyle.success, custom_id="finish_role_setup", row=4))
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] WerewolfRoleSetupView diinisialisasi untuk channel {channel_id}.")

    def _add_role_buttons(self):
        # Clear existing dynamic buttons (only those starting with "set_role_")
        for item in list(self.children):
            if isinstance(item, discord.ui.Button) and item.custom_id.startswith("set_role_"):
                self.remove_item(item)

        roles_to_display = [role for role in self.available_roles.keys() if role != "Warga Polos"]
        roles_to_display.sort(key=lambda r: self.game_cog.werewolf_roles_data['roles'][r].get('order', 99))

        # Add buttons for each role, managing rows
        current_row = 0
        buttons_in_row = 0
        for i, role_name in enumerate(roles_to_display):
            current_value = self.current_roles_config.get(role_name, 0)
            # Ensure the row does not exceed Discord's limit (0-4)
            # Standard buttons go up to row=4, so dynamic ones should be <= 3
            # Or consider using multiple views if you have too many roles
            button = discord.ui.Button(
                label=f"{role_name} ({current_value})",
                style=discord.ButtonStyle.primary,
                custom_id=f"set_role_{role_name}",
                row=current_row # Assign current row dynamically
            )
            button.callback = self._role_button_callback
            self.add_item(button)

            buttons_in_row += 1
            if buttons_in_row >= 5: # Max 5 buttons per row
                current_row += 1
                buttons_in_row = 0
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Role buttons Werewolf ditambahkan.")

    async def _role_button_callback(self, interaction: discord.Interaction):
        role_name = interaction.data['custom_id'].replace("set_role_", "")
        current_quantity = self.current_roles_config.get(role_name, 0)

        # Pass the message ID to the modal so it can update the original message
        message_to_update_id = interaction.message.id

        modal = RoleQuantityModal(
            self.game_cog,
            role_name,
            current_quantity,
            self.total_players,
            message_to_update_id,
            self.channel_id
        )
        await interaction.response.send_modal(modal)

    def calculate_balance(self):
        total_special_roles_count = sum(self.current_roles_config.values())
        werewolf_count = self.current_roles_config.get('Werewolf', 0)
        villager_count = self.total_players - total_special_roles_count

        warnings = []
        if total_special_roles_count > self.total_players:
            warnings.append("⚠️ Jumlah peran khusus melebihi total pemain! Kurangi beberapa peran.")
        if werewolf_count == 0 and self.total_players > 0 and self.total_players >= 3: # Only warn if players exist and it's a typical game size
            warnings.append("⛔ Tidak ada Werewolf! Game mungkin tidak valid atau membosankan.")
        if werewolf_count > 0 and werewolf_count >= (self.total_players / 2):
            warnings.append("⛔ Jumlah Werewolf terlalu banyak (>= 50% pemain)! Game mungkin tidak seimbang.")
        if villager_count < 0:
            warnings.append("⚠️ Jumlah Warga Polos murni negatif! Pastikan total peran khusus tidak melebihi total pemain.")
        if self.total_players < 3:
            warnings.append("⚠️ Jumlah pemain terlalu sedikit untuk distribusi peran yang bermakna.")
        # Add default role checks based on your description (1 WW, 1 Penjaga, 1 Penyihir for 3-8 players)
        if 3 <= self.total_players <= 8:
            if self.current_roles_config.get('Werewolf', 0) == 0: warnings.append("⚠️ Disarankan ada setidaknya 1 Werewolf untuk 3-8 pemain.")
            if self.current_roles_config.get('Dokter', 0) == 0: warnings.append("⚠️ Disarankan ada setidaknya 1 Dokter untuk 3-8 pemain.")
            if self.current_roles_config.get('Peramal', 0) == 0: warnings.append("⚠️ Disarankan ada setidaknya 1 Peramal untuk 3-8 pemain.")


        return villager_count, warnings

    def create_embed(self):
        # Ensure the current config is up-to-date from the global config
        self.current_roles_config = self.game_cog.global_werewolf_config.get('default_config', {}).get('roles', {}).copy()

        villager_count, warnings = self.calculate_balance()

        embed = discord.Embed(
            title="🐺 Pengaturan Peran Werewolf (Global) 🐺",
            description=f"Total Pemain: **{self.total_players}**\n\nAtur jumlah peran untuk game ini dengan mengklik tombol peran:",
            color=discord.Color.blue()
        )

        roles_text = ""
        sorted_role_names = sorted(self.available_roles.keys(),
                                   key=lambda r: self.available_roles[r].get('order', 99))

        for role_name in sorted_role_names:
            if role_name == "Warga Polos":
                continue
            count = self.current_roles_config.get(role_name, 0)
            roles_text += f"- **{role_name}**: `{count}`\n"
        roles_text += f"- **Warga Polos**: `{max(0, villager_count)}` (Otomatis Dihitung)\n\n"

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
            embed.add_field(name="Status Gambar/GIF (Global)", value=image_summary, inline=True)

        audio_summary = ""
        if self.audio_urls.get('game_start_audio_url'): audio_summary += "🎵 Game Start Audio\n"
        if self.audio_urls.get('night_phase_audio_url'): audio_summary += "🎵 Night Audio\n"
        if self.audio_urls.get('day_phase_audio_url'): audio_summary += "🎵 Day Audio\n"
        if audio_summary:
            embed.add_field(name="Status Audio (Global - MP3/WebM)", value=audio_summary, inline=True)

        return embed


    @discord.ui.button(label="Atur Media Game (Global)", style=discord.ButtonStyle.secondary, custom_id="setup_media", row=4)
    async def setup_media_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Tombol 'Atur Media Game' diklik oleh {interaction.user.display_name}.")
        game_state = self.game_cog.werewolf_game_states.get(interaction.channel.id)
        # Hanya host game yang sedang aktif di channel ini ATAU admin server yang bisa memanggil setup
        if not ((game_state and interaction.user.id == game_state['host'].id) or interaction.user.guild_permissions.manage_channels):
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Bukan host atau Admin, blokir pengaturan media.")
            return await interaction.response.send_message("Hanya host game Werewolf yang aktif di channel ini atau admin server yang bisa mengatur media global.", ephemeral=True)

        # Pass the message ID to the modal so it can update the original message
        message_to_update_id = interaction.message.id

        # When opening the media setup modal, also ensure the main view's embed updates
        modal = WerewolfMediaSetupModal(self.game_cog, self.game_cog.global_werewolf_config.get('default_config', {}),
                                        message_to_update_id, self.channel_id)
        await interaction.response.send_modal(modal)
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Modal WerewolfMediaSetupModal dikirim.")

    @discord.ui.button(label="Selesai Mengatur", style=discord.ButtonStyle.success, custom_id="finish_role_setup", row=4)
    async def finish_setup_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Tombol 'Selesai Mengatur' diklik oleh {interaction.user.display_name}.")
        game_state = self.game_cog.werewolf_game_states.get(interaction.channel.id)
        if not game_state or interaction.user.id != game_state['host'].id:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Bukan host, blokir selesai pengaturan.")
            return await interaction.response.send_message("Hanya host yang bisa menyelesaikan pengaturan peran.", ephemeral=True)

        await interaction.response.defer()

        # Re-read the latest config before final check
        self.current_roles_config = self.game_cog.global_werewolf_config.get('default_config', {}).get('roles', {}).copy()

        villager_count, warnings = self.calculate_balance()
        if warnings and any("⛔" in w for w in warnings): # Hanya blokir jika ada peringatan kritis (⛔)
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Peringatan kritis komposisi peran: {warnings}.")
            await interaction.followup.send("Ada masalah kritis dengan komposisi peran yang dipilih. Mohon perbaiki sebelum melanjutkan.", ephemeral=True)
            return

        # No need to save again here as RoleQuantityModal already saves it
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Konfigurasi peran global Werewolf sudah disimpan (oleh modal).")

        for item in self.children:
            item.disabled = True

        embed = interaction.message.embeds[0]
        embed.description = f"**Komposisi peran untuk game ini telah diatur (Global)!**\n\nTotal Pemain: **{self.total_players}**"
        embed.color = discord.Color.green()
        embed.set_footer(text="Host bisa gunakan !ww mulai untuk memulai game!") # Command diubah

        await interaction.message.edit(embed=embed, view=self)
        self.stop()
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pengaturan Werewolf selesai, view dihentikan.")


class GamesGlobalEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = set() # Channel IDs where a game is active in this cog (Werewolf, Wheel, Horse Racing)

        # --- Game States ---
        self.werewolf_join_queues = {} # {guild_id: {channel_id: [players]}}
        self.werewolf_game_states = {}
        # {channel_id: {
        # 'host': member, 'players': [members], 'roles': {member.id: role_name}, 'living_players': set(member.id),
        # 'main_channel': discord.TextChannel, 'voice_channel': discord.VoiceChannel, 'voice_client': None,
        # 'phase': 'day'/'night'/'voting'/'game_over', 'day_num': 1,
        # 'killed_this_night': None, 'voted_out_today': None,
        # 'role_actions_pending': {}, # {role_name: {member_id: target_id or None}}
        # 'role_actions_votes': {}, # {role_name: {target_id: [voter_ids]}} for WW group vote
        # 'timers': {},
        # 'vote_message': None, 'players_who_voted': set(),
        # 'player_map': {}, # {player_number: member_object} for DM commands
        # 'reverse_player_map': {}, # {member_id: player_number} for convenience
        # 'werewolf_dm_thread': None # For Werewolf group chat
        # }}
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
                    "roles": { # Default roles and counts for a balanced small game (e.g., 5-7 players)
                        "Werewolf": 1,
                        "Dokter": 1,
                        "Peramal": 1,
                        "Pengawal": 0 # Guard is optional for simpler games
                    },
                    "image_urls": {
                        "game_start_image_url": "https://i.imgur.com/Gj3H2a4.gif",
                        "night_phase_image_url": "https://i.imgur.com/vH1B6jA.gif",
                        "day_phase_image_url": "https://i.imgur.com/oWbWb2v.gif",
                        "night_resolution_image_url": "https://i.imgur.com/Yh3zY0A.gif"
                    },
                    "audio_urls": {
                        "game_start_audio_url": None,
                        "night_phase_audio_url": None,
                        "day_phase_audio_url": None
                    },
                    "min_players": 3, # Add this for your minimum player check
                    "night_duration_seconds": 90, # Durasi malam untuk aksi DM
                    "day_discussion_duration_seconds": 180, # Durasi diskusi siang
                    "voting_duration_seconds": 60 # Durasi voting siang
                }
            }
        )
        self.werewolf_roles_data = load_json_from_root(
            'data/werewolf_roles.json',
            default_value={
                "roles": {
                    "Werewolf": {"team": "Werewolf", "action_prompt": "Siapa yang ingin kamu bunuh malam ini?", "dm_command": "!bunuh warga", "can_target_self": false, "emoji": "🐺", "order": 1, "night_action_order": 2, "description": "Tugasmu adalah membunuh para penduduk desa setiap malam hingga jumlahmu sama atau lebih banyak dari mereka.", "goal": "Musnahkan semua penduduk desa!"},
                    "Dokter": {"team": "Village", "action_prompt": "Siapa yang ingin kamu lindungi malam ini?", "dm_command": "!lindungi warga", "can_target_self": true, "emoji": "⚕️", "order": 2, "night_action_order": 1, "description": "Kamu bisa melindungi satu orang setiap malam agar tidak dibunuh oleh Werewolf.", "goal": "Lindungi penduduk desa dan singkirkan Werewolf!"},
                    "Peramal": {"team": "Village", "action_prompt": "Siapa yang ingin kamu cek perannya malam ini?", "dm_command": "!cek warga", "can_target_self": true, "emoji": "🔮", "order": 3, "night_action_order": 3, "description": "Setiap malam, kamu bisa memilih satu pemain untuk mengetahui apakah dia Werewolf atau bukan.", "goal": "Temukan Werewolf dan bantu penduduk desa menggantung mereka!"},
                    "Pengawal": {"team": "Village", "action_prompt": "Siapa yang ingin kamu jaga dari hukuman mati siang nanti?", "dm_command": "!jaga warga", "can_target_self": true, "emoji": "🛡️", "order": 4, "night_action_order": 4, "description": "Kamu bisa melindungi satu pemain dari hukuman gantung di siang hari.", "goal": "Lindungi warga dari keputusan gantung yang salah."},
                    "Warga Polos": {"team": "Village", "action_prompt": None, "dm_command": None, "can_target_self": false, "emoji": "🧑‍🌾", "order": 5, "night_action_order": None, "description": "Kamu adalah penduduk desa biasa. Tujuanmu adalah menemukan Werewolf dan menggantung mereka.", "goal": "Gantung semua Werewolf!"}
                }
            }
        )

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

        base_rsw = custom_rsw if custom_rsw is not None else 100
        base_exp = custom_exp if custom_exp is not None else 100

        final_rsw = int(base_rsw * anomaly_multiplier)
        final_exp = int(base_exp * anomaly_multiplier)

        if self.dunia_cog and hasattr(self.dunia_cog, 'give_rewards_base'):
            self.dunia_cog.give_rewards_base(user, guild_id, final_rsw, final_exp)
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Hadiah via DuniaHidup: {user.display_name} mendapat {final_rsw} RSWN & {final_exp} EXP.")
        else:
            # Fallback jika DuniaHidup tidak ada/fungsi tidak ditemukan
            bank_data = load_json_from_root('data/bank_data.json', default_value={})
            level_data = load_json_from_root('data/level_data.json', default_value={})

            user_id_str = str(user.id)
            guild_id_str = str(guild_id)

            bank_data.setdefault(user_id_str, {'balance': 0})['balance'] += final_rsw
            level_data.setdefault(guild_id_str, {}).setdefault(user_id_str, {'exp': 0})['exp'] += final_exp

            save_json_to_root(bank_data, 'data/bank_data.json')
            save_json_to_root(level_data, 'data/level_data.json')
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Hadiah (fallback): {user.display_name} mendapat {final_rsw} RSWN & {final_exp} EXP.")

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
        if self.dunia_cog and hasattr(self.dunia_cog, 'mimic_effect_active_channel_id') and self.dunia_cog.mimic_effect_active_channel_id == ctx.channel.id:
            await ctx.send("💥 **SERANGAN MIMIC!** Permainan tidak bisa dimulai karena mimic sedang mengamuk di channel ini!", ephemeral=True)
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] MIMIC ATTACK aktif di channel ini, blokir game.")
            return True
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] MIMIC ATTACK tidak aktif di channel ini.")
        return False

    async def _check_mimic_effect(self, ctx):
        """Memeriksa apakah event mimic yang memengaruhi jawaban sedang aktif di channel ini (dari DuniaHidup)."""
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Memeriksa _check_mimic_effect untuk channel {ctx.channel.name} ({ctx.channel.id}).")
        if self.dunia_cog and hasattr(self.dunia_cog, 'mimic_effect_active_channel_id') and self.dunia_cog.mimic_effect_active_channel_id == ctx.channel.id:
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

            # Hapus pesan setup jika ada
            if game_state.get('last_role_setup_message') and hasattr(game_state['last_role_setup_message'], 'delete'):
                try:
                    self.bot.loop.create_task(game_state['last_role_setup_message'].delete())
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pesan setup Werewolf dihapus di channel {channel_id}.")
                except discord.NotFound:
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pesan setup Werewolf tidak ditemukan saat cleanup, mungkin sudah dihapus manual.")
                    pass
                except Exception as e:
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Error menghapus pesan setup Werewolf: {e}.")

            # Hapus thread Werewolf jika ada dan aktif
            if game_state.get('werewolf_dm_thread') and isinstance(game_state['werewolf_dm_thread'], discord.Thread):
                try:
                    self.bot.loop.create_task(game_state['werewolf_dm_thread'].delete())
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Thread Werewolf dihapus di channel {channel_id}.")
                except discord.Forbidden:
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Bot tidak punya izin menghapus thread Werewolf di channel {channel_id}.")
                except Exception as e:
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Error menghapus thread Werewolf: {e}.")

            del self.werewolf_game_states[channel_id]
            self.active_werewolf_setup_messages.pop(channel_id, None)
            self.werewolf_join_queues.pop(channel_id, None) # Clear join queue too
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
    # Grup untuk command Werewolf (misal: !ww join, !ww mulai, !ww set)
    @commands.group(name="ww", invoke_without_command=True, help="Kumpulan perintah untuk game Werewolf.")
    async def werewolf_group(self, ctx):
        print(f"[{datetime.now()}] [DEBUG WW] Command !ww (group) dipanggil oleh {ctx.author.display_name}. Subcommand tidak ditentukan.")
        if ctx.invoked_subcommand is None:
            # Ini akan berfungsi sebagai alias untuk !ww join jika tidak ada subcommand
            await self.join_werewolf(ctx)

    @werewolf_group.command(name="join", help="Bergabung ke antrean game Werewolf.")
    async def join_werewolf(self, ctx):
        print(f"[{datetime.now()}] [DEBUG WW] Command !ww join dipanggil oleh {ctx.author.display_name} di {ctx.channel.name}.")
        if ctx.channel.id in self.active_games:
            return await ctx.send("Sudah ada game aktif di channel ini. Kamu tidak bisa bergabung sekarang.", ephemeral=True)

        if not ctx.guild:
            return await ctx.send("Werewolf hanya bisa dimainkan di server Discord.", ephemeral=True)

        channel_id = ctx.channel.id

        if channel_id not in self.werewolf_join_queues:
            self.werewolf_join_queues[channel_id] = []

        if ctx.author not in self.werewolf_join_queues[channel_id]:
            self.werewolf_join_queues[channel_id].append(ctx.author)
            current_players = len(self.werewolf_join_queues[channel_id])
            await ctx.send(f"**{ctx.author.display_name}** telah bergabung ke antrean Werewolf! ({current_players} pemain dalam antrean)")
            print(f"[{datetime.now()}] [DEBUG WW] {ctx.author.display_name} bergabung antrean Werewolf di channel {channel_id}.")

            # Otomatis konfirmasi untuk memulai jika jumlah pemain sudah cukup
            global_config = self.global_werewolf_config.get('default_config', {})
            min_players_for_game = global_config.get('min_players', 3) # Asumsi min_players di global_werewolf_config

            if current_players >= min_players_for_game:
                await ctx.send(f"Antrean mencapai {current_players} pemain! Ketik `!ww mulai` untuk memulai game sekarang!", delete_after=30)
                print(f"[{datetime.now()}] [DEBUG WW] Antrean cukup, minta host untuk memulai.")
        else:
            await ctx.send(f"Kamu sudah ada di antrean Werewolf.", ephemeral=True)

    @werewolf_group.command(name="keluar", help="Keluar dari antrean game Werewolf.")
    async def leave_werewolf(self, ctx):
        print(f"[{datetime.now()}] [DEBUG WW] Command !ww keluar dipanggil oleh {ctx.author.display_name} di {ctx.channel.name}.")
        channel_id = ctx.channel.id
        if channel_id in self.werewolf_join_queues and ctx.author in self.werewolf_join_queues[channel_id]:
            self.werewolf_join_queues[channel_id].remove(ctx.author)
            current_players = len(self.werewolf_join_queues[channel_id])
            await ctx.send(f"**{ctx.author.display_name}** telah keluar dari antrean Werewolf. ({current_players} pemain tersisa)")
            print(f"[{datetime.now()}] [DEBUG WW] {ctx.author.display_name} keluar antrean Werewolf di channel {channel_id}.")
            if current_players == 0:
                del self.werewolf_join_queues[channel_id]
        else:
            await ctx.send("Kamu tidak ada di antrean Werewolf.", ephemeral=True)

    @werewolf_group.command(name="set", help="[Admin/Host] Atur peran dan media game Werewolf global.")
    async def set_werewolf_config(self, ctx):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Command !ww set dipanggil oleh {ctx.author.display_name} di channel: {ctx.channel.name} ({ctx.channel.id}).")

        game_state = self.werewolf_game_states.get(ctx.channel.id)
        if not (game_state and ctx.author.id == game_state['host'].id) and not ctx.author.guild_permissions.manage_channels:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !ww set: Bukan host atau Admin, blokir.")
            return await ctx.send("Hanya host game Werewolf yang aktif di channel ini atau admin server yang bisa mengatur konfigurasi.", ephemeral=True)

        total_players_for_setup = len(self.werewolf_join_queues.get(ctx.channel.id, []))
        if game_state: # If a game is already active, use actual player count
            total_players_for_setup = len(game_state['living_players']) + len(game_state['dead_players'])

        # Ensure total_players_for_setup is at least the minimum allowed for setup if queue is empty
        if total_players_for_setup == 0:
            total_players_for_setup = self.global_werewolf_config.get('default_config', {}).get('min_players', 3)
            await ctx.send(f"Antrean pemain kosong. Mengatur peran untuk minimal {total_players_for_setup} pemain. Anda bisa mengubah ini nanti.", delete_after=15)
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Antrean kosong, mengatur peran untuk minimal {total_players_for_setup} pemain.")

        initial_view = WerewolfRoleSetupView(self, ctx.channel.id, total_players_for_setup, self.global_werewolf_config.get('default_config', {}))
        message = await ctx.send(embed=initial_view.create_embed(), view=initial_view)
        # Simpan ID pesan setup ke dalam game state jika game sudah ada, atau ke active_werewolf_setup_messages
        if game_state:
            game_state['last_role_setup_message'] = message # Simpan message object bukan ID
        self.active_werewolf_setup_messages[ctx.channel.id] = message.id
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Menu setup Werewolf dikirim ke channel {ctx.channel.name}.")


    @werewolf_group.command(name="mulai", help="[Host] Memulai game Werewolf dengan pemain di antrean.")
    @commands.cooldown(1, 30, commands.BucketType.channel)
    async def force_start_werewolf_game(self, ctx):
        print(f"[{datetime.now()}] [DEBUG WW] Command !ww mulai dipanggil oleh {ctx.author.display_name} di {ctx.channel.name}.")
        if await self._check_mimic_attack(ctx): return
        if not await self.start_game_check_global(ctx): return

        channel_id = ctx.channel.id
        guild = ctx.guild

        if channel_id not in self.werewolf_join_queues or not self.werewolf_join_queues[channel_id]:
            return await ctx.send("Tidak ada pemain di antrean untuk memulai game. Gunakan `!ww` dulu!", ephemeral=True)

        queued_players = self.werewolf_join_queues[channel_id]

        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("Untuk memulai Werewolf, kamu (host) harus berada di **voice channel**!", ephemeral=True)

        vc_channel = ctx.author.voice.channel

        game_players_raw = [m for m in vc_channel.members if not m.bot and m in queued_players]

        global_config_data = self.global_werewolf_config.get('default_config', {})
        min_players_for_game = global_config_data.get('min_players', 3)

        if len(game_players_raw) < min_players_for_game:
            return await ctx.send(f"Jumlah pemain di voice channel ({len(game_players_raw)}) terlalu sedikit untuk memulai game Werewolf. Minimal {min_players_for_game} pemain aktif!", ephemeral=True)

        # Konfirmasi apakah host mau melanjutkan dengan pemain yang difilter
        confirm_embed = discord.Embed(
            title="Konfirmasi Mulai Game Werewolf",
            description=(f"Akan memulai game Werewolf dengan **{len(game_players_raw)} pemain** yang saat ini berada di voice channel **{vc_channel.name}**.\n\n"
                         "Pemain yang akan bermain:\n" + "\n".join([p.mention for p in game_players_raw])),
            color=discord.Color.orange()
        )
        confirm_embed.set_footer(text="Tekan ✅ untuk konfirmasi, ❌ untuk batal. (30 detik)")

        confirmation_msg = await ctx.send(embed=confirm_embed)
        await confirmation_msg.add_reaction("✅")
        await confirmation_msg.add_reaction("❌")

        try:
            reaction, user = await self.bot.wait_for(
                'reaction_add',
                timeout=30.0,
                check=lambda r, u: u == ctx.author and str(r.emoji) in ["✅", "❌"] and r.message.id == confirmation_msg.id
            )
            if str(reaction.emoji) == "❌":
                await ctx.send("Memulai game Werewolf dibatalkan.", delete_after=10)
                await confirmation_msg.delete()
                self.active_games.discard(channel_id)
                print(f"[{datetime.now()}] [DEBUG WW] Konfirmasi batal oleh host.")
                return
            await confirmation_msg.delete()
            print(f"[{datetime.now()}] [DEBUG WW] Konfirmasi diterima dari host.")
        except asyncio.TimeoutError:
            await ctx.send("Konfirmasi waktu habis, memulai game Werewolf dibatalkan.", delete_after=10)
            await confirmation_msg.delete()
            self.active_games.discard(channel_id)
            print(f"[{datetime.now()}] [DEBUG WW] Konfirmasi waktu habis.")
            return

        self.active_games.add(channel_id) # Tandai channel sebagai aktif

        # Clear the join queue once game starts
        if channel_id in self.werewolf_join_queues:
            del self.werewolf_join_queues[channel_id]
            print(f"[{datetime.now()}] [DEBUG WW] Antrean Werewolf dibersihkan.")

        # Connect bot to voice channel
        try:
            if ctx.voice_client: # If bot is already connected to any VC
                if ctx.voice_client.channel != vc_channel: # If it's not the right VC, move
                    await ctx.voice_client.move_to(vc_channel)
                    await ctx.send(f"Bot pindah ke voice channel: **{vc_channel.name}** untuk Werewolf.", delete_after=10)
                    print(f"[{datetime.now()}] [DEBUG WW] Bot pindah VC ke {vc_channel.name}.")
            else: # If bot is not connected at all
                await vc_channel.connect()
                await ctx.send(f"Bot bergabung ke voice channel: **{vc_channel.name}** untuk Werewolf.", delete_after=10)
                print(f"[{datetime.now()}] [DEBUG WW] Bot berhasil bergabung ke VC {vc_channel.name}.")

            game_state = self.werewolf_game_states.setdefault(channel_id, {})
            game_state['voice_client'] = ctx.voice_client

        except discord.Forbidden:
            print(f"[{datetime.now()}] [DEBUG WW] Bot tidak punya izin join/pindah VC. Forbidden.")
            self.end_game_cleanup_global(channel_id, game_type='werewolf')
            return await ctx.send("Bot tidak memiliki izin untuk bergabung atau pindah ke voice channel Anda. Pastikan saya memiliki izin `Connect` dan `Speak`.", ephemeral=True)
        except Exception as e:
            print(f"[{datetime.now()}] [DEBUG WW] Error saat bot bergabung/pindah VC: {e}.")
            self.end_game_cleanup_global(channel_id, game_type='werewolf')
            return await ctx.send(f"Terjadi kesalahan saat bot bergabung/pindah ke voice channel: `{e}`", ephemeral=True)

        await ctx.send("Game Werewolf akan dimulai! Bersiaplah...")
        print(f"[{datetime.now()}] [DEBUG WW] Memulai alur game Werewolf di channel {channel_id}...")

        # Inisialisasi game state
        game_state['host'] = ctx.author
        game_state['players'] = game_players_raw
        game_state['main_channel'] = ctx.channel
        game_state['voice_channel'] = vc_channel
        game_state['living_players'] = {p.id for p in game_players_raw} # Set ID pemain yang hidup
        game_state['dead_players'] = set() # Set ID pemain yang mati
        game_state['roles'] = {} # {member.id: role_name}
        game_state['phase'] = 'starting'
        game_state['day_num'] = 0
        game_state['killed_this_night'] = None
        game_state['voted_out_today'] = None
        game_state['role_actions_pending'] = {}
        game_state['role_actions_votes'] = {}
        game_state['timers'] = {}
        game_state['vote_message'] = None
        game_state['players_who_voted'] = set()
        game_state['player_map'] = {}
        game_state['reverse_player_map'] = {}
        game_state['werewolf_dm_thread'] = None
        game_state['total_players'] = len(game_players_raw)

        game_task = self.bot.loop.create_task(self._werewolf_game_flow(ctx, channel_id))
        game_state['game_task'] = game_task


    @werewolf_group.command(name="batal", help="[Host/Admin] Batalkan game Werewolf yang sedang berjalan.")
    async def cancel_werewolf_game(self, ctx):
        print(f"[{datetime.now()}] [DEBUG WW] Command !ww batal dipanggil oleh {ctx.author.display_name}.")
        channel_id = ctx.channel.id
        game_state = self.werewolf_game_states.get(channel_id)

        if not game_state:
            return await ctx.send("Tidak ada game Werewolf yang sedang berjalan di channel ini.", ephemeral=True)

        if not (ctx.author.id == game_state['host'].id or ctx.author.guild_permissions.administrator):
            return await ctx.send("Hanya host game atau administrator yang bisa membatalkan game ini.", ephemeral=True)

        await ctx.send("Game Werewolf dibatalkan secara paksa. Dunia kembali damai... untuk sementara.")
        print(f"[{datetime.now()}] [DEBUG WW] Game Werewolf di channel {channel_id} dibatalkan secara paksa.")
        self.end_game_cleanup_global(channel_id, game_type='werewolf')

    @werewolf_group.command(name="status", help="Melihat status game Werewolf saat ini.")
    async def werewolf_status(self, ctx):
        print(f"[{datetime.now()}] [DEBUG WW] Command !ww status dipanggil oleh {ctx.author.display_name}.")
        channel_id = ctx.channel.id
        game_state = self.werewolf_game_states.get(channel_id)

        if not game_state or game_state['phase'] == 'game_over':
            return await ctx.send("Tidak ada game Werewolf yang sedang berjalan di channel ini.", ephemeral=True)

        living_players_mentions = []
        for p_id in game_state['living_players']:
            player = ctx.guild.get_member(p_id)
            if player:
                player_num = game_state['reverse_player_map'].get(p_id, 'N/A')
                living_players_mentions.append(f"`{player_num}` {player.display_name} ({player.mention})")
            else:
                living_players_mentions.append(f"Pemain tidak ditemukan (ID: {p_id})")

        dead_players_mentions = []
        for p_id in game_state['dead_players']:
            player = ctx.guild.get_member(p_id)
            if player:
                role = game_state['roles'].get(p_id, 'Unknown Role')
                dead_players_mentions.append(f"☠️ {player.display_name} ({role})")
            else:
                dead_players_mentions.append(f"☠️ Pemain tidak ditemukan (ID: {p_id})")

        embed = discord.Embed(
            title="🐺 Status Game Werewolf 🐺",
            description=f"Host: {game_state['host'].mention}\n"
                        f"Fase Saat Ini: **{game_state['phase'].replace('_', ' ').title()}** (Hari {game_state['day_num']})",
            color=discord.Color.purple()
        )

        embed.add_field(name="Pemain Hidup", value="\n".join(living_players_mentions) if living_players_mentions else "Tidak ada.", inline=False)
        embed.add_field(name="Pemain Mati", value="\n".join(dead_players_mentions) if dead_players_mentions else "Tidak ada.", inline=False)

        if game_state['phase'] == 'night':
            embed.set_footer(text=f"Aksi malam akan berakhir dalam {self._get_time_remaining(game_state['timers'].get('night_end_time'))}")
        elif game_state['phase'] == 'day':
            embed.set_footer(text=f"Diskusi siang akan berakhir dalam {self._get_time_remaining(game_state['timers'].get('day_discussion_end_time'))}")
        elif game_state['phase'] == 'voting':
            embed.set_footer(text=f"Voting akan berakhir dalam {self._get_time_remaining(game_state['timers'].get('voting_end_time'))}")

        await ctx.send(embed=embed)
        print(f"[{datetime.now()}] [DEBUG WW] Status game Werewolf dikirim ke channel {ctx.channel.name}.")

    def _get_time_remaining(self, end_time_str):
        if not end_time_str:
            return "N/A"
        end_time = datetime.fromisoformat(end_time_str)
        time_left = end_time - datetime.utcnow()
        total_seconds = int(time_left.total_seconds())
        if total_seconds <= 0:
            return "Waktu habis!"

        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes} menit {seconds} detik"

    async def _werewolf_game_flow(self, ctx, channel_id):
        print(f"[{datetime.now()}] [DEBUG WW] _werewolf_game_flow dimulai untuk channel {channel_id}.")
        game_state = self.werewolf_game_states[channel_id]
        main_channel = game_state['main_channel']
        global_config = self.global_werewolf_config.get('default_config', {})

        try:
            # --- Inisialisasi Peran ---
            await self._assign_roles(game_state)

            # --- Game Start Visual & Audio ---
            game_state['phase'] = 'starting'
            await self._send_werewolf_visual(main_channel, "game_start")
            await self._play_werewolf_audio(main_channel, "game_start_audio_url")
            await main_channel.send(f"Selamat datang di {main_channel.guild.name} The Werewolf! Setiap pemain telah menerima peran mereka melalui DM.")
            await asyncio.sleep(5)

            # Game Loop
            while True:
                # --- Pengecekan Kondisi Kemenangan Awal Ronde ---
                winner = self._check_win_condition(game_state)
                if winner:
                    print(f"[{datetime.now()}] [DEBUG WW] Kondisi kemenangan terpenuhi di awal ronde: {winner}.")
                    await self._end_game(game_state, winner)
                    break

                game_state['day_num'] += 1

                # --- Fase Malam ---
                game_state['phase'] = 'night'
                game_state['killed_this_night'] = None # Reset korban malam
                game_state['role_actions_pending'] = {} # Reset aksi peran
                game_state['role_actions_votes'] = {} # Reset voting Werewolf

                await self._send_werewolf_visual(main_channel, "night_phase")
                await self._play_werewolf_audio(main_channel, "night_phase_audio_url")
                await main_channel.send(f"🌙 **MALAM HARI {game_state['day_num']} TIBA!** Semua pemain tertidur. Para peran khusus, periksa DM kalian untuk beraksi!")
                print(f"[{datetime.now()}] [DEBUG WW] Fase Malam Hari {game_state['day_num']} dimulai.")

                # Kirim DM untuk aksi malam
                await self._send_night_action_DMs(game_state)

                # Tunggu aksi malam
                night_duration = global_config.get("night_duration_seconds", 90)
                game_state['timers']['night_end_time'] = datetime.utcnow() + timedelta(seconds=night_duration)
                print(f"[{datetime.now()}] [DEBUG WW] Malam Hari {game_state['day_num']} akan berakhir pada: {game_state['timers']['night_end_time']}.")
                try:
                    await asyncio.sleep(night_duration)
                except asyncio.CancelledError:
                    raise # Rethrow jika game dibatalkan

                # --- Resolusi Malam ---
                game_state['phase'] = 'night_resolution'
                print(f"[{datetime.now()}] [DEBUG WW] Memproses aksi malam untuk Hari {game_state['day_num']}.")
                await self._process_night_actions(game_state)

                # Pengumuman korban
                await self._send_werewolf_visual(main_channel, "night_resolution")
                if game_state['killed_this_night']:
                    killed_member_id = game_state['killed_this_night']
                    killed_member = main_channel.guild.get_member(killed_member_id)
                    killed_role = game_state['roles'].get(killed_member_id, 'Tidak Diketahui')

                    if killed_member: # Pastikan member masih ada
                        await main_channel.send(f"☀️ **PAGI HARI {game_state['day_num']}!** Teror semalam berakhir... Warga **{killed_member.display_name}** ({killed_member.mention}) ditemukan tak bernyawa! Dia adalah seorang **{killed_role}**.")
                        # Pindahkan ke VC 'mati' jika ada dan bot punya izin
                        if game_state['voice_client']:
                            try:
                                afk_channel = main_channel.guild.afk_channel
                                if afk_channel and killed_member.voice and killed_member.voice.channel: # Only move if in VC
                                    await killed_member.move_to(afk_channel)
                                else: # Atau mute dan deafen
                                    await killed_member.edit(mute=True, deafen=True)
                                print(f"[{datetime.now()}] [DEBUG WW] {killed_member.display_name} dipindahkan/dimute-deafen.")
                            except discord.Forbidden:
                                print(f"[{datetime.now()}] [DEBUG WW] Bot tidak punya izin untuk memindahkan/mute {killed_member.display_name}.")
                            except Exception as e:
                                print(f"[{datetime.now()}] [DEBUG WW] Error memindahkan/mute {killed_member.display_name}: {e}")
                    else:
                        await main_channel.send(f"☀️ **PAGI HARI {game_state['day_num']}!** Teror semalam berakhir... Seorang warga ditemukan tak bernyawa! (ID: {killed_member_id})")
                else:
                    await main_channel.send(f"☀️ **PAGI HARI {game_state['day_num']}!** Malam berlalu tanpa korban... Keberuntungan masih berpihak pada penduduk!")
                print(f"[{datetime.now()}] [DEBUG WW] Resolusi malam untuk Hari {game_state['day_num']} selesai.")
                await asyncio.sleep(5)

                # --- Pengecekan Kondisi Kemenangan Setelah Malam ---
                winner = self._check_win_condition(game_state)
                if winner:
                    print(f"[{datetime.now()}] [DEBUG WW] Kondisi kemenangan terpenuhi setelah malam: {winner}.")
                    await self._end_game(game_state, winner)
                    break

                # --- Fase Siang (Diskusi & Voting) ---
                game_state['phase'] = 'day'
                game_state['voted_out_today'] = None # Reset vote siang
                game_state['players_who_voted'] = set() # Reset voter

                await self._send_werewolf_visual(main_channel, "day_phase")
                await self._play_werewolf_audio(main_channel, "day_phase_audio_url")
                await main_channel.send(f"🗣️ **DISKUSI HARI {game_state['day_num']}!** Para penduduk, diskusikan siapa yang harus digantung hari ini. Gunakan `!vote warga <nomor_warga>`")
                print(f"[{datetime.now()}] [DEBUG WW] Fase Siang Hari {game_state['day_num']} dimulai.")

                # Tunggu diskusi & voting
                day_discussion_duration = global_config.get("day_discussion_duration_seconds", 180)
                voting_duration = global_config.get("voting_duration_seconds", 60)

                day_discussion_end_time = datetime.utcnow() + timedelta(seconds=day_discussion_duration)
                game_state['timers']['day_discussion_end_time'] = day_discussion_end_time.isoformat()

                voting_start_time = day_discussion_end_time - timedelta(seconds=voting_duration)
                game_state['timers']['voting_end_time'] = (day_discussion_end_time).isoformat() # Waktu voting berakhir sama dengan diskusi berakhir

                self.bot.loop.create_task(self._voting_reminder(game_state, voting_start_time))

                try:
                    await asyncio.sleep(day_discussion_duration)
                except asyncio.CancelledError:
                    raise # Rethrow jika game dibatalkan

                # --- Resolusi Siang (Lynch) ---
                game_state['phase'] = 'voting_resolution'
                print(f"[{datetime.now()}] [DEBUG WW] Memproses voting siang untuk Hari {game_state['day_num']}.")
                await self._process_day_vote(game_state)

                # Pengumuman yang dilynch
                if game_state['voted_out_today']:
                    lynched_member_id = game_state['voted_out_today']
                    lynched_member = main_channel.guild.get_member(lynched_member_id)
                    lynched_role = game_state['roles'].get(lynched_member_id, 'Tidak Diketahui')

                    if lynched_member: # Pastikan member masih ada
                        await main_channel.send(f"🔥 **KEPUTUSAN HARI INI!** Warga **{lynched_member.display_name}** ({lynched_member.mention}) telah digantung! Dia adalah seorang **{lynched_role}**.")
                        if game_state['voice_client']:
                            try:
                                afk_channel = main_channel.guild.afk_channel
                                if afk_channel and lynched_member.voice and lynched_member.voice.channel: # Only move if in VC
                                    await lynched_member.move_to(afk_channel)
                                else:
                                    await lynched_member.edit(mute=True, deafen=True)
                                print(f"[{datetime.now()}] [DEBUG WW] {lynched_member.display_name} dipindahkan/dimute-deafen.")
                            except discord.Forbidden:
                                print(f"[{datetime.now()}] [DEBUG WW] Bot tidak punya izin untuk memindahkan/mute {lynched_member.display_name}.")
                            except Exception as e:
                                print(f"[{datetime.now()}] [DEBUG WW] Error memindahkan/mute {lynched_member.display_name}: {e}")
                    else:
                         await main_channel.send(f"🔥 **KEPUTUSAN HARI INI!** Seorang warga telah digantung! (ID: {lynched_member_id}) Dia adalah seorang **{lynched_role}**.")
                else:
                    await main_channel.send(f"🔥 **KEPUTUSAN HARI INI!** Tidak ada yang digantung hari ini. Para penduduk desa tidak bisa sepakat, atau tidak ada yang mencurigakan...")
                print(f"[{datetime.now()}] [DEBUG WW] Resolusi voting Hari {game_state['day_num']} selesai.")
                await asyncio.sleep(5)

        except asyncio.CancelledError:
            print(f"[{datetime.now()}] [DEBUG WW] Werewolf game flow for channel {channel_id} dibatalkan.")
            await main_channel.send("Game Werewolf dihentikan.")
        except Exception as e:
            print(f"[{datetime.now()}] [DEBUG WW] Werewolf Flow: ERROR fatal di channel {channel_id}: {e}", file=sys.stderr)
            await main_channel.send(f"Terjadi kesalahan fatal pada game Werewolf: `{e}`. Game dihentikan.")
        finally:
            self.end_game_cleanup_global(channel_id, game_type='werewolf')
            print(f"[{datetime.now()}] [DEBUG WW] _werewolf_game_flow selesai atau dibatalkan untuk channel {channel_id}.")

    async def _assign_roles(self, game_state):
        print(f"[{datetime.now()}] [DEBUG WW] Memulai penetapan peran Werewolf.")
        players = list(game_state['players'])
        random.shuffle(players)

        assigned_roles_map = {} # {member.id: role_name}

        # Get configured roles from global config, default if not set
        configured_roles_counts = self.global_werewolf_config.get('default_config', {}).get('roles', {})

        # Buat daftar peran berdasarkan konfigurasi
        role_pool = []
        for role_name, count in configured_roles_counts.items():
            if role_name != "Warga Polos": # Warga Polos dihitung terakhir
                role_pool.extend([role_name] * count)

        # Hitung sisa untuk Warga Polos
        villager_count = len(players) - len(role_pool)
        if villager_count > 0:
            role_pool.extend(["Warga Polos"] * villager_count)

        random.shuffle(role_pool)

        # Pastikan jumlah peran sesuai dengan jumlah pemain
        if len(role_pool) != len(players):
            print(f"[{datetime.now()}] [DEBUG WW] Peringatan: Jumlah peran awal ({len(role_pool)}) tidak sesuai jumlah pemain ({len(players)}). Menyesuaikan.")
            # Jika peran terlalu banyak dari pemain, pangkas
            if len(role_pool) > len(players):
                role_pool = random.sample(role_pool, len(players)) # Ambil acak sejumlah pemain
            # Jika peran terlalu sedikit, tambahkan Warga Polos
            while len(role_pool) < len(players):
                role_pool.append("Warga Polos")
            print(f"[{datetime.now()}] [DEBUG WW] Peran disesuaikan, jumlah akhir: {len(role_pool)}.")

        # Assign roles to players and send DMs
        for i, player in enumerate(players):
            role_name = role_pool[i]
            assigned_roles_map[player.id] = role_name
            game_state['roles'][player.id] = role_name # Store in game state

            # Send DM with role info
            role_info = self.werewolf_roles_data['roles'].get(role_name, {})
            dm_embed = discord.Embed(
                title=f"🐺 Peranmu dalam Werewolf: **{role_name}** {role_info.get('emoji', '')} 🐺",
                description=role_info.get('description', 'Tidak ada deskripsi peran.'),
                color=discord.Color.dark_grey()
            )
            dm_embed.add_field(name="Tujuanmu", value=role_info.get('goal', 'Tujuanmu adalah membantu timmu menang!'), inline=False)

            # Additional info for Werewolf (their pack)
            if role_name == "Werewolf":
                # Find living werewolves for their pack info
                # Menggunakan game_state['players'] karena di awal semua masih hidup
                werewolves_in_game = [p for p in players if game_state['roles'].get(p.id) == "Werewolf" and p.id != player.id]

                if werewolves_in_game:
                    pack_list = "\n".join([f"- {pm.display_name} ({pm.mention})" for pm in werewolves_in_game if pm])
                    if pack_list:
                         dm_embed.add_field(name="Rekan Werewolfmu", value=pack_list, inline=False)
                    else:
                         dm_embed.add_field(name="Rekan Werewolfmu", value="Kamu adalah satu-satunya Werewolf yang kesepian.", inline=False)
                else:
                    dm_embed.add_field(name="Rekan Werewolfmu", value="Kamu adalah satu-satunya Werewolf yang kesepian.", inline=False)

            try:
                await player.send(embed=dm_embed)
                print(f"[{datetime.now()}] [DEBUG WW] Peran {role_name} dikirim ke DM {player.display_name}.")
            except discord.Forbidden:
                print(f"[{datetime.now()}] [DEBUG WW] Gagal DM {player.display_name} untuk peran. DM tertutup.")
                await game_state['main_channel'].send(f"⚠️ Gagal mengirim DM peran ke {player.mention}. Pastikan DM-mu terbuka!", delete_after=15)

        print(f"[{datetime.now()}] [DEBUG WW] Peran telah ditetapkan: {game_state['roles']}")

        # Create player mapping for DM commands
        game_state['player_map'] = {i+1: p for i, p in enumerate(players)}
        game_state['reverse_player_map'] = {p.id: i+1 for i, p in enumerate(players)}


    async def _send_night_action_DMs(self, game_state):
        print(f"[{datetime.now()}] [DEBUG WW] Mengirim DM aksi malam.")
        main_channel = game_state['main_channel']
        living_players_list = []

        # Rebuild player_map and reverse_player_map for current living players for Night Action DMs display
        temp_player_map_living = {}
        temp_reverse_player_map_living = {}
        player_num = 1
        for p_id in game_state['living_players']:
            player = main_channel.guild.get_member(p_id)
            if player:
                temp_player_map_living[player_num] = player
                temp_reverse_player_map_living[player.id] = player_num
                living_players_list.append(f"{player_num}. {player.display_name} ({player.mention})")
                player_num += 1

        player_list_text = "\n".join(living_players_list)
        if not player_list_text:
            player_list_text = "Tidak ada pemain yang hidup."

        # Send to Werewolf DM group/thread
        werewolves_living = [p_id for p_id in game_state['living_players'] if game_state['roles'][p_id] == "Werewolf"]
        if werewolves_living:
            if not game_state.get('werewolf_dm_thread') or game_state['werewolf_dm_thread'] == 'disabled':
                try:
                    thread = await main_channel.create_thread(
                        name=f"Werewolf Den - Hari {game_state['day_num']}",
                        type=discord.ChannelType.private_thread,
                        invitable=False,
                        auto_archive_duration=60
                    )
                    game_state['werewolf_dm_thread'] = thread
                    print(f"[{datetime.now()}] [DEBUG WW] Private thread Werewolf dibuat: {thread.name}.")
                    for ww_id in werewolves_living:
                        ww_member = main_channel.guild.get_member(ww_id)
                        if ww_member:
                            await thread.add_user(ww_member)
                            # Kirim pesan aksi Werewolf ke thread
                            if ww_member.id == werewolves_living[0]:
                                await thread.send(f"**MALAM HARI {game_state['day_num']}!** Kalian adalah Werewolf. Diskusikan dan pilih target pembunuhan kalian. Kirim `{self.werewolf_roles_data['roles']['Werewolf']['dm_command']} <nomor_warga>` di sini.\n\n**Daftar Pemain Hidup:**\n{player_list_text}")
                    print(f"[{datetime.now()}] [DEBUG WW] Member Werewolf ditambahkan ke thread.")
                except discord.Forbidden:
                    print(f"[{datetime.now()}] [DEBUG WW] Bot tidak punya izin membuat private thread untuk Werewolf. Akan menggunakan DM pribadi.", file=sys.stderr)
                    game_state['werewolf_dm_thread'] = 'disabled'
                    for ww_id in werewolves_living:
                        ww_member = main_channel.guild.get_member(ww_id)
                        if ww_member:
                            dm_channel = await ww_member.create_dm()
                            await dm_channel.send(f"**MALAM HARI {game_state['day_num']}!** Kamu adalah Werewolf. Diskusikan dengan rekanmu (jika ada) siapa yang akan dibunuh. Kemudian, kirim `{self.werewolf_roles_data['roles']['Werewolf']['dm_command']} <nomor_warga>` di DM ini.\n\n**Daftar Pemain Hidup:**\n{player_list_text}")
                            print(f"[{datetime.now()}] [DEBUG WW] DM aksi malam untuk Werewolf ({ww_member.display_name}) dikirim sebagai fallback.")
                except Exception as e:
                    print(f"[{datetime.now()}] [DEBUG WW] Error creating Werewolf thread: {e}. Falling back to DMs.", file=sys.stderr)
                    game_state['werewolf_dm_thread'] = 'disabled'
                    for ww_id in werewolves_living:
                        ww_member = main_channel.guild.get_member(ww_id)
                        if ww_member:
                            dm_channel = await ww_member.create_dm()
                            await dm_channel.send(f"**MALAM HARI {game_state['day_num']}!** Kamu adalah Werewolf. Diskusikan dengan rekanmu (jika ada) siapa yang akan dibunuh. Kemudian, kirim `{self.werewolf_roles_data['roles']['Werewolf']['dm_command']} <nomor_warga>` di DM ini.\n\n**Daftar Pemain Hidup:**\n{player_list_text}")
                            print(f"[{datetime.now()}] [DEBUG WW] DM aksi malam untuk Werewolf ({ww_member.display_name}) dikirim sebagai fallback.")
            elif isinstance(game_state['werewolf_dm_thread'], discord.Thread): # If thread exists and is enabled
                await game_state['werewolf_dm_thread'].send(f"**MALAM HARI {game_state['day_num']}!** Waktunya beraksi! Diskusikan dan pilih target. Kirim `{self.werewolf_roles_data['roles']['Werewolf']['dm_command']} <nomor_warga>`.\n\n**Daftar Pemain Hidup:**\n{player_list_text}")
                print(f"[{datetime.now()}] [DEBUG WW] Pesan aksi malam dikirim ke thread Werewolf.")


        # Send to other roles via individual DMs
        # Sort roles by 'night_action_order' for consistent processing
        role_action_order = sorted([r_data for r_data in self.werewolf_roles_data['roles'].values() if r_data.get('night_action_order') is not None],
                                   key=lambda x: x['night_action_order'])

        for role_data in role_action_order:
            role_name = next(k for k, v in self.werewolf_roles_data['roles'].items() if v == role_data) # Get role name from data
            if role_name == "Werewolf": continue # Already handled

            players_of_role = [p_id for p_id in game_state['living_players'] if game_state['roles'][p_id] == role_name]

            for player_id in players_of_role:
                player_member = main_channel.guild.get_member(player_id)
                if player_member:
                    try:
                        dm_channel = await player_member.create_dm()
                        # Menggunakan info dari werewolf_roles_data untuk prompt dan command
                        prompt_message = (
                            f"**MALAM HARI {game_state['day_num']}!** Kamu adalah **{role_name}**. "
                            f"{role_data.get('action_prompt', 'Saatnya beraksi!')} "
                            f"Kirim `{role_data.get('dm_command', '!aksi warga') + ' <nomor_warga>'}` di DM ini.\n\n"
                            f"**Daftar Pemain Hidup:**\n{player_list_text}"
                        )
                        await dm_channel.send(prompt_message)
                        print(f"[{datetime.now()}] [DEBUG WW] DM aksi malam untuk {role_name} ({player_member.display_name}) dikirim.")
                    except discord.Forbidden:
                        print(f"[{datetime.now()}] [DEBUG WW] Gagal DM {player_member.display_name} untuk aksi malam. DM tertutup.")
                        await main_channel.send(f"⚠️ Gagal mengirim DM aksi malam ke {player_member.mention}. Pastikan DM-mu terbuka!", delete_after=15)

    async def _process_night_actions(self, game_state):
        print(f"[{datetime.now()}] [DEBUG WW] Memproses aksi malam.")
        main_channel = game_state['main_channel']

        # 1. Resolve Werewolf kill
        werewolf_target_id = None
        if "Werewolf" in game_state['role_actions_votes']:
            ww_votes = game_state['role_actions_votes']['Werewolf']
            if ww_votes:
                target_counts = {}
                for target_id in ww_votes.values():
                    target_counts[target_id] = target_counts.get(target_id, 0) + 1

                max_votes = 0
                potential_targets = []
                for target_id, count in target_counts.items():
                    if count > max_votes:
                        max_votes = count
                        potential_targets = [target_id]
                    elif count == max_votes:
                        potential_targets.append(target_id)

                werewolf_target_id = random.choice(potential_targets) # Random if tie
                print(f"[{datetime.now()}] [DEBUG WW] Werewolf memilih target: {werewolf_target_id}.")

        # 2. Resolve Doctor protection
        doctor_target_id = game_state['role_actions_pending'].get('Dokter')
        print(f"[{datetime.now()}] [DEBUG WW] Dokter melindungi target: {doctor_target_id}.")

        # 3. Determine actual killed player
        killed_player_id = None
        if werewolf_target_id and werewolf_target_id != doctor_target_id:
            killed_player_id = werewolf_target_id

        game_state['killed_this_night'] = killed_player_id

        if killed_player_id and killed_player_id in game_state['living_players']: # Pastikan target masih hidup sebelum membunuh
            game_state['living_players'].discard(killed_player_id)
            game_state['dead_players'].add(killed_player_id)
            print(f"[{datetime.now()}] [DEBUG WW] {main_channel.guild.get_member(killed_player_id).display_name} dibunuh di malam hari.")
        elif killed_player_id: # Target dibunuh tapi mungkin sudah mati/invalid
            print(f"[{datetime.now()}] [DEBUG WW] Target pembunuhan ({killed_player_id}) sudah mati atau tidak valid.")
        else: # Tidak ada target atau target dilindungi
            print(f"[{datetime.now()}] [DEBUG WW] Tidak ada korban pembunuhan malam ini.")


    @commands.command(name="bunuh", hidden=True) # Hidden from help command
    async def werewolf_kill_cmd(self, ctx, target_type: str, target_num: int):
        print(f"[{datetime.now()}] [DEBUG WW] !bunuh DM command dipanggil oleh {ctx.author.display_name} ({ctx.author.id}).")
        if not isinstance(ctx.channel, discord.DMChannel) and not (isinstance(ctx.channel, discord.Thread) and ctx.channel.name.startswith("Werewolf Den")): # Check for DM or WW Thread
            return await ctx.send("Perintah ini hanya bisa digunakan di DM atau thread pribadi Werewolf dengan bot.", ephemeral=True)

        # Find the game this player is in
        game_state = None
        for ch_id, state in self.werewolf_game_states.items():
            if ctx.author.id in state['living_players'] and state['phase'] == 'night':
                # Pastikan perintah datang dari DM atau thread yang benar
                if (isinstance(ctx.channel, discord.DMChannel) and state.get('werewolf_dm_thread') == 'disabled') or \
                   (isinstance(ctx.channel, discord.Thread) and state.get('werewolf_dm_thread') == ctx.channel):
                    game_state = state
                    break

        if not game_state:
            print(f"[{datetime.now()}] [DEBUG WW] !bunuh: Game tidak aktif, bukan fase malam, atau bukan Werewolf DM/thread yang benar.")
            return await ctx.send("Tidak ada game Werewolf yang aktif, bukan fase malam sekarang, atau Anda bukan Werewolf di game ini.", ephemeral=True)

        player_role = game_state['roles'].get(ctx.author.id)
        if player_role != "Werewolf":
            print(f"[{datetime.now()}] [DEBUG WW] !bunuh: {ctx.author.display_name} bukan Werewolf.")
            return await ctx.send("Hanya Werewolf yang bisa menggunakan perintah ini.", ephemeral=True)

        if target_type.lower() != "warga":
            print(f"[{datetime.now()}] [DEBUG WW] !bunuh: Format target salah: {target_type}.")
            return await ctx.send("Format yang benar: `!bunuh warga <nomor_warga>`", ephemeral=True)

        target_member = game_state['player_map'].get(target_num)
        if not target_member or target_member.id not in game_state['living_players']:
            print(f"[{datetime.now()}] [DEBUG WW] !bunuh: Target {target_num} tidak valid atau sudah mati.")
            return await ctx.send(f"Warga {target_num} tidak valid atau sudah mati. Pilih warga yang hidup dari daftar.", ephemeral=True)

        if target_member.id == ctx.author.id:
            print(f"[{datetime.now()}] [DEBUG WW] !bunuh: Werewolf mencoba bunuh diri sendiri.")
            return await ctx.send("Werewolf tidak bisa membunuh diri sendiri!", ephemeral=True)

        # For Werewolves, store individual vote for later majority processing
        game_state['role_actions_votes'].setdefault('Werewolf', {})[ctx.author.id] = target_member.id
        await ctx.send(f"Kamu telah memilih **{target_member.display_name}** untuk dibunuh. (Pilihanmu telah dicatat, Werewolf lain mungkin juga memilih).")
        print(f"[{datetime.now()}] [DEBUG WW] {ctx.author.display_name} (WW) memilih {target_member.display_name} ({target_member.id}).")

    @commands.command(name="lindungi", hidden=True)
    async def doctor_protect_cmd(self, ctx, target_type: str, target_num: int):
        print(f"[{datetime.now()}] [DEBUG WW] !lindungi DM command dipanggil oleh {ctx.author.display_name} ({ctx.author.id}).")
        if not isinstance(ctx.channel, discord.DMChannel):
            return await ctx.send("Perintah ini hanya bisa digunakan di DM dengan bot.", ephemeral=True)

        game_state = None
        for ch_id, state in self.werewolf_game_states.items():
            if ctx.author.id in state['living_players'] and state['phase'] == 'night':
                game_state = state
                break

        if not game_state:
            return await ctx.send("Tidak ada game Werewolf yang aktif atau bukan fase malam sekarang.", ephemeral=True)

        player_role = game_state['roles'].get(ctx.author.id)
        if player_role != "Dokter":
            return await ctx.send("Hanya Dokter yang bisa menggunakan perintah ini.", ephemeral=True)

        if target_type.lower() != "warga":
            return await ctx.send("Format yang benar: `!lindungi warga <nomor_warga>`", ephemeral=True)

        target_member = game_state['player_map'].get(target_num)
        if not target_member or target_member.id not in game_state['living_players']:
            return await ctx.send(f"Warga {target_num} tidak valid atau sudah mati. Pilih warga yang hidup dari daftar.", ephemeral=True)

        game_state['role_actions_pending']['Dokter'] = target_member.id
        await ctx.send(f"Kamu telah memilih **{target_member.display_name}** untuk dilindungi.")
        print(f"[{datetime.now()}] [DEBUG WW] {ctx.author.display_name} (Doc) melindungi {target_member.display_name} ({target_member.id}).")

    @commands.command(name="cek", hidden=True)
    async def seer_check_cmd(self, ctx, target_type: str, target_num: int):
        print(f"[{datetime.now()}] [DEBUG WW] !cek DM command dipanggil oleh {ctx.author.display_name} ({ctx.author.id}).")
        if not isinstance(ctx.channel, discord.DMChannel):
            return await ctx.send("Perintah ini hanya bisa digunakan di DM dengan bot.", ephemeral=True)

        game_state = None
        for ch_id, state in self.werewolf_game_states.items():
            if ctx.author.id in state['living_players'] and state['phase'] == 'night':
                game_state = state
                break

        if not game_state:
            return await ctx.send("Tidak ada game Werewolf yang aktif atau bukan fase malam sekarang.", ephemeral=True)

        player_role = game_state['roles'].get(ctx.author.id)
        if player_role != "Peramal":
            return await ctx.send("Hanya Peramal yang bisa menggunakan perintah ini.", ephemeral=True)

        if target_type.lower() != "warga":
            return await ctx.send("Format yang benar: `!cek warga <nomor_warga>`", ephemeral=True)

        target_member = game_state['player_map'].get(target_num)
        if not target_member or target_member.id not in game_state['living_players']:
            return await ctx.send(f"Warga {target_num} tidak valid atau sudah mati. Pilih warga yang hidup dari daftar.", ephemeral=True)

        target_actual_role = game_state['roles'].get(target_member.id)
        # Seer will see "Werewolf" team as Werewolf, other teams as "not Werewolf"
        is_werewolf = (self.werewolf_roles_data['roles'].get(target_actual_role, {}).get('team') == "Werewolf")

        result_text = f"Warga {target_num} ({target_member.display_name}) adalah seorang **Werewolf**." if is_werewolf else f"Warga {target_num} ({target_member.display_name}) adalah **bukan Werewolf**."
        await ctx.send(f"Hasil ramalanmu: {result_text}")
        print(f"[{datetime.now()}] [DEBUG WW] {ctx.author.display_name} (Seer) cek {target_member.display_name} ({result_text}).")

    @commands.command(name="jaga", hidden=True)
    async def guard_protect_cmd(self, ctx, target_type: str, target_num: int):
        print(f"[{datetime.now()}] [DEBUG WW] !jaga DM command dipanggil oleh {ctx.author.display_name} ({ctx.author.id}).")
        if not isinstance(ctx.channel, discord.DMChannel):
            return await ctx.send("Perintah ini hanya bisa digunakan di DM dengan bot.", ephemeral=True)

        game_state = None
        for ch_id, state in self.werewolf_game_states.items():
            if ctx.author.id in state['living_players'] and state['phase'] == 'night':
                game_state = state
                break

        if not game_state:
            return await ctx.send("Tidak ada game Werewolf yang aktif atau bukan fase malam sekarang.", ephemeral=True)

        player_role = game_state['roles'].get(ctx.author.id)
        if player_role != "Pengawal":
            return await ctx.send("Hanya Pengawal yang bisa menggunakan perintah ini.", ephemeral=True)

        if target_type.lower() != "warga":
            return await ctx.send("Format yang benar: `!jaga warga <nomor_warga>`", ephemeral=True)

        target_member = game_state['player_map'].get(target_num)
        if not target_member or target_member.id not in game_state['living_players']:
            return await ctx.send(f"Warga {target_num} tidak valid atau sudah mati. Pilih warga yang hidup dari daftar.", ephemeral=True)

        game_state['role_actions_pending']['Pengawal'] = target_member.id
        await ctx.send(f"Kamu telah memilih **{target_member.display_name}** untuk dijaga dari hukuman mati.")
        print(f"[{datetime.now()}] [DEBUG WW] {ctx.author.display_name} (Guard) menjaga {target_member.display_name} ({target_member.id}).")


    @commands.command(name="vote")
    async def werewolf_vote_cmd(self, ctx, target_type: str, target_num: int):
        print(f"[{datetime.now()}] [DEBUG WW] !vote command dipanggil oleh {ctx.author.display_name} di {ctx.channel.name}.")
        channel_id = ctx.channel.id
        game_state = self.werewolf_game_states.get(channel_id)

        if not game_state or game_state['phase'] not in ['day', 'voting']:
            return await ctx.send("Tidak ada game Werewolf yang aktif, atau bukan fase diskusi/voting.", ephemeral=True)

        if ctx.author.id not in game_state['living_players']:
            return await ctx.send("Kamu sudah mati dan tidak bisa memilih.", ephemeral=True)

        if target_type.lower() != "warga":
            return await ctx.send("Format yang benar: `!vote warga <nomor_warga>`", ephemeral=True)

        target_member = game_state['player_map'].get(target_num)
        if not target_member or target_member.id not in game_state['living_players']:
            return await ctx.send(f"Warga {target_num} tidak valid atau sudah mati. Pilih warga yang hidup dari daftar.", ephemeral=True)

        if target_member.id == ctx.author.id:
            return await ctx.send("Kamu tidak bisa memilih dirimu sendiri untuk digantung!", ephemeral=True)

        # Store the vote
        game_state['role_actions_votes'].setdefault('vote', {})
        game_state['role_actions_votes']['vote'][ctx.author.id] = target_member.id
        game_state['players_who_voted'].add(ctx.author.id)

        await ctx.send(f"✅ **{ctx.author.display_name}** telah memilih untuk menggantung **{target_member.display_name}**.", delete_after=5)
        print(f"[{datetime.now()}] [DEBUG WW] {ctx.author.display_name} memilih untuk menggantung {target_member.display_name}.")

    async def _voting_reminder(self, game_state, voting_start_time):
        main_channel = game_state['main_channel']
        while datetime.utcnow() < voting_start_time:
            await asyncio.sleep(10) # Check every 10 seconds
            if game_state['phase'] not in ['day', 'voting']:
                return # Stop if phase changes

        if game_state['phase'] == 'day': # Only send reminder if still in discussion phase
            game_state['phase'] = 'voting' # Transition to voting phase
            await main_channel.send("🔔 **WAKTU VOTING!** Kalian punya waktu singkat untuk memilih siapa yang akan digantung. Gunakan `!vote warga <nomor_warga>` sekarang!")

        # Continuously update remaining time for voting
        voting_end_time = datetime.fromisoformat(game_state['timers']['voting_end_time'])
        while datetime.utcnow() < voting_end_time:
            time_left = voting_end_time - datetime.utcnow()
            total_seconds = int(time_left.total_seconds())
            if total_seconds <= 0: break # Time's up

            minutes, seconds = divmod(total_seconds, 60)
            if minutes < 1 and seconds % 10 == 0: # Update every 10 seconds for last minute
                await main_channel.send(f"⏳ **{seconds} detik** tersisa untuk voting!", delete_after=10)
            elif minutes > 0 and minutes % 1 == 0 and seconds == 0: # Update every minute
                 await main_channel.send(f"⏳ **{minutes} menit** tersisa untuk voting!", delete_after=10)
            await asyncio.sleep(min(10, total_seconds if total_seconds > 0 else 1)) # Wait up to 10s or less if time is almost up

    async def _process_day_vote(self, game_state):
        print(f"[{datetime.now()}] [DEBUG WW] Memproses voting siang.")
        main_channel = game_state['main_channel']

        votes = game_state['role_actions_votes'].get('vote', {})

        if not votes:
            game_state['voted_out_today'] = None
            print(f"[{datetime.now()}] [DEBUG WW] Tidak ada vote siang.")
            return # No votes, no one lynched

        # Count votes for each target
        target_counts = {}
        for voter_id, target_id in votes.items():
            # Only count votes from living players
            if voter_id in game_state['living_players']:
                target_counts[target_id] = target_counts.get(target_id, 0) + 1

        if not target_counts: # No valid votes from living players
            game_state['voted_out_today'] = None
            print(f"[{datetime.now()}] [DEBUG WW] Tidak ada vote valid dari pemain hidup.")
            return

        # Find the target with the most votes
        max_votes = 0
        potential_lynch_targets = []
        for target_id, count in target_counts.items():
            if count > max_votes:
                max_votes = count
                potential_lynch_targets = [target_id]
            elif count == max_votes:
                potential_lynch_targets.append(target_id)

        lynched_player_id = random.choice(potential_lynch_targets) # Random if tie
        print(f"[{datetime.now()}] [DEBUG WW] Target lynch terpilih: {lynched_player_id} dengan {max_votes} suara.")

        # Check if lynched player was guarded by Guard
        guard_target_id = game_state['role_actions_pending'].get('Pengawal')
        if lynched_player_id == guard_target_id:
            await main_channel.send(f"🛡️ **{main_channel.guild.get_member(lynched_player_id).display_name}** diselamatkan dari hukuman mati oleh seorang Pengawal misterius!")
            game_state['voted_out_today'] = None # No one was actually lynched
            print(f"[{datetime.now()}] [DEBUG WW] {main_channel.guild.get_member(lynched_player_id).display_name} diselamatkan oleh Pengawal.")
        else:
            game_state['voted_out_today'] = lynched_player_id
            game_state['living_players'].discard(lynched_player_id)
            game_state['dead_players'].add(lynched_player_id)
            print(f"[{datetime.now()}] [DEBUG WW] {main_channel.guild.get_member(lynched_player_id).display_name} dilynch.")

    def _check_win_condition(self, game_state):
        living_werewolves = {p_id for p_id in game_state['living_players'] if game_state['roles'][p_id] == "Werewolf"}
        # Pastikan ini mengambil semua peran non-Werewolf dari data roles
        living_villagers = {p_id for p_id in game_state['living_players'] if self.werewolf_roles_data['roles'].get(game_state['roles'][p_id], {}).get('team') == "Village"}

        print(f"[{datetime.now()}] [DEBUG WW] Cek kondisi kemenangan. WW hidup: {len(living_werewolves)}, Warga hidup: {len(living_villagers)}.")

        if not living_werewolves: # Semua Werewolf mati
            print(f"[{datetime.now()}] [DEBUG WW] Kondisi menang: Desa menang (semua WW mati).")
            return "Village"

        # Werewolf menang jika jumlah mereka >= jumlah warga yang hidup (tidak termasuk diri mereka sendiri)
        if len(living_werewolves) >= len(living_villagers):
            print(f"[{datetime.now()}] [DEBUG WW] Kondisi menang: Werewolf menang (jumlah WW >= jumlah Warga).")
            return "Werewolf"

        # Ini adalah kasus jika semua warga telah mati dan hanya Werewolf yang tersisa
        if not living_villagers and living_werewolves:
            print(f"[{datetime.now()}] [DEBUG WW] Kondisi menang: Werewolf menang (semua warga mati, WW masih ada).")
            return "Werewolf"

        print(f"[{datetime.now()}] [DEBUG WW] Belum ada kondisi kemenangan terpenuhi. (WW: {len(living_werewolves)}, Warga: {len(living_villagers)})")
        return None # Belum ada yang menang

    async def _end_game(self, game_state, winner):
        print(f"[{datetime.now()}] [DEBUG WW] _end_game dipanggil. Pemenang: {winner}.")
        main_channel = game_state['main_channel']
        game_state['phase'] = 'game_over'

        if winner == "Werewolf":
            embed = discord.Embed(
                title="🐺 Para Werewolf Berjaya! 🐺",
                description="Kegelapan menyelimuti desa. Para Werewolf telah menguasai dan memangsa semua penduduk!",
                color=discord.Color.dark_red()
            )
            embed.set_image(url=self.global_werewolf_config['default_config']['image_urls'].get('night_phase_image_url', 'https://i.imgur.com/vH1B6jA.gif')) # Re-use night image for WW win
        else: # Village wins
            embed = discord.Embed(
                title="🌟 Penduduk Desa Selamat! 🌟",
                description="Para penduduk telah bersatu dan berhasil mengusir semua Werewolf dari desa!",
                color=discord.Color.gold()
            )
            embed.set_image(url=self.global_werewolf_config['default_config']['image_urls'].get('day_phase_image_url', 'https://i.imgur.com/oWbWb2v.gif')) # Re-use day image for Villager win

        await main_channel.send(embed=embed)
        await asyncio.sleep(3)

        # Show final roles
        final_roles_text = ""
        for player_id in game_state['players']: # Iterate all original players for rewards
            member = main_channel.guild.get_member(player_id)
            role = game_state['roles'].get(player_id, "Tidak Diketahui")
            status = "HIDUP" if player_id in game_state['living_players'] else "MATI"
            if member:
                final_roles_text += f"**{game_state['reverse_player_map'].get(player_id, '?')}. {member.display_name}** ({role}) - {status}\n"

        final_roles_embed = discord.Embed(
            title="📜 Ringkasan Akhir Permainan 📜",
            description=final_roles_text,
            color=discord.Color.greyple()
        )
        await main_channel.send(embed=final_roles_embed)

        # Disconnect bot from voice channel
        if game_state.get('voice_client'):
            await game_state['voice_client'].disconnect()
            game_state['voice_client'] = None
            print(f"[{datetime.now()}] [DEBUG WW] Bot disconnect dari VC.")

        # Give rewards
        for player_id in game_state['players']:
            player = main_channel.guild.get_member(player_id)
            if not player:
                print(f"[{datetime.now()}] [DEBUG WW] Pemain {player_id} tidak ditemukan untuk hadiah.")
                continue

            player_role = game_state['roles'][player_id]
            is_living = player_id in game_state['living_players']

            # Determine if player's team won
            player_team_won = False
            # Menggunakan werewolf_roles_data untuk mendapatkan team dari role
            player_role_data = self.werewolf_roles_data['roles'].get(player_role, {})
            if winner == "Werewolf" and player_role_data.get('team') == "Werewolf":
                player_team_won = True
            elif winner == "Village" and player_role_data.get('team') == "Village":
                player_team_won = True

            if player_team_won:
                if is_living:
                    await self.give_rewards_with_bonus_check(player, main_channel.guild.id, main_channel, custom_rsw=500, custom_exp=300)
                    print(f"[{datetime.now()}] [DEBUG WW] {player.display_name} (HIDUP, TIM MENANG) mendapat hadiah penuh.")
                else:
                    await self.give_rewards_with_bonus_check(player, main_channel.guild.id, main_channel, custom_rsw=100, custom_exp=50)
                    print(f"[{datetime.now()}] [DEBUG WW] {player.display_name} (MATI, TIM MENANG) mendapat hadiah parsial.")
            else: # Losing side
                await self.give_rewards_with_bonus_check(player, main_channel.guild.id, main_channel, custom_rsw=50, custom_exp=25)
                print(f"[{datetime.now()}] [DEBUG WW] {player.display_name} (TIM KALAH) mendapat hadiah partisipasi.")

        print(f"[{datetime.now()}] [DEBUG WW] Game berakhir di channel {game_state['main_channel'].name}. Pemenang: {winner}.")

        # --- Tambahkan Bagian Donasi di Sini ---
        donasi_embed = discord.Embed(
            title="✨ Suka dengan permainannya? Dukung kami! ✨",
            description=(
                "Pengembangan bot ini membutuhkan waktu dan usaha. "
                "Setiap dukungan kecil dari Anda sangat berarti untuk menjaga bot ini tetap aktif "
                "dan menghadirkan fitur-fitur baru yang lebih seru!\n\n"
                "Terima kasih telah bermain!"
            ),
            color=discord.Color.gold()
        )
        donasi_view = discord.ui.View()
        donasi_view.add_item(discord.ui.Button(label="Bagi Bagi (DANA/Gopay/OVO)", style=discord.ButtonStyle.url, url="https://bagibagi.co/Rh7155"))
        donasi_view.add_item(discord.ui.Button(label="Saweria (All Payment Method)", style=discord.ButtonStyle.url, url="https://saweria.co/RH7155"))

        await main_channel.send(embed=donasi_embed, view=donasi_view)
        print(f"[{datetime.now()}] [DEBUG WW] Pesan donasi dikirim di akhir game Werewolf.")


    async def _send_werewolf_visual(self, channel: discord.TextChannel, phase: str):
        print(f"[{datetime.now()}] [DEBUG WW] Mengirim visual Werewolf untuk fase: {phase} di channel {channel.name}.")
        global_config = self.global_werewolf_config.get('default_config', {})
        image_urls = global_config.get('image_urls', {})

        visual_url = None
        title = ""
        description = ""
        color = discord.Color.dark_purple()

        if phase == "game_start":
            visual_url = image_urls.get('game_start_image_url')
            title = "🐺 Game Werewolf Dimulai! 🐺"
            description = "Selamat datang di desa yang diserang Werewolf. Setiap pemain telah menerima peran mereka di DM."
            color = discord.Color.blue()
        elif phase == "night_phase":
            visual_url = image_urls.get('night_phase_image_url')
            title = "🌙 Malam Telah Tiba! 🌙"
            description = "Para penduduk desa tertidur. Peran-peran malam, saatnya beraksi di DM kalian!"
            color = discord.Color.dark_blue()
        elif phase == "day_phase":
            visual_url = image_urls.get('day_phase_image_url')
            title = "☀️ Pagi Telah Datang! ☀️"
            description = "Teror semalam telah berakhir. Waktunya berdiskusi dan mencari tahu siapa pembunuhnya!"
            color = discord.Color.orange()
        elif phase == "night_resolution":
            visual_url = image_urls.get('night_resolution_image_url')
            title = "💔 Korban Ditemukan! 💔"
            description = "Keheningan pagi dipecah oleh penemuan jasad. Siapa yang menjadi korban tak berdosa ini?"
            color = discord.Color.dark_red()

        embed = discord.Embed(
            title=title,
            description=description,
            color=color
        )

        if visual_url and visual_url.lower().endswith(('.gif', '.png', '.jpg', '.jpeg')):
            embed.set_image(url=visual_url) # Menampilkan GIF secara besar
            await channel.send(embed=embed)
            print(f"[{datetime.now()}] [DEBUG WW] Visual Werewolf dengan URL {visual_url} dikirim.")
        else:
            await channel.send(embed=embed)
            if visual_url:
                await channel.send("ℹ️ URL gambar yang diberikan tidak valid atau bukan format gambar/GIF yang didukung untuk fase ini. Mengirim pesan tanpa gambar.")
                print(f"[{datetime.now()}] [DEBUG WW] URL visual Werewolf tidak valid: {visual_url}.")
            else:
                await channel.send("ℹ️ URL gambar untuk fase ini belum diatur.")
                print(f"[{datetime.now()}] [DEBUG WW] URL visual Werewolf tidak diatur untuk fase {phase}.")


    async def _play_werewolf_audio(self, text_channel: discord.TextChannel, audio_type: str):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Mencoba memutar audio Werewolf: {audio_type} di channel {text_channel.name}.")
        game_state = self.werewolf_game_states.get(text_channel.id)
        if not game_state or not game_state.get('voice_client'):
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Tidak ada voice client atau game tidak aktif untuk audio Werewolf.")
            return

        voice_client = game_state['voice_client']
        global_config = self.global_werewolf_config.get('default_config', {})
        audio_urls = global_config.get('audio_urls', {})

        audio_url = audio_urls.get(audio_type)

        if audio_url and self.music_cog:
            try:
                # Memastikan Music.YTDLSource diimpor atau didefinisikan di Music cog
                # Asumsi Music.YTDLSource adalah bagian dari Music cog yang dimuat
                if hasattr(self.music_cog, 'YTDLSource'): # Pengecekan lebih aman
                    if voice_client.is_playing() or voice_client.is_paused():
                        voice_client.stop()
                    source = await self.music_cog.YTDLSource.from_url(audio_url, loop=self.bot.loop, stream=True)
                    voice_client.play(source, after=lambda e: print(f'[{datetime.now()}] [DEBUG GLOBAL EVENTS] Player error in Werewolf audio: {e}') if e else None)
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Audio Werewolf '{audio_type}' berhasil diputar.")
                else:
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] 'YTDLSource' method not found in Music cog.")
            except Exception as e:
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Gagal memutar audio Werewolf '{audio_type}': {e}.", file=sys.stderr)
                await text_channel.send(f"⚠️ Maaf, gagal memutar audio untuk fase ini: `{e}`")
        elif not self.music_cog:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Music cog tidak ditemukan, tidak dapat memutar audio Werewolf.")
        else:
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] URL audio untuk '{audio_type}' tidak diatur.")


    @commands.command(name="stopwerewolfaudio", help="Hentikan audio Werewolf yang sedang diputar.")
    async def stop_werewolf_audio(self, ctx):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Command !stopwerewolfaudio dipanggil oleh {ctx.author.display_name}.")
        channel_id = ctx.channel.id
        game_state = self.werewolf_game_states.get(channel_id)
        if not game_state or (ctx.author.id != game_state.get('host', None).id and not ctx.author.guild_permissions.manage_channels):
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
        if await self._check_mimic_attack(ctx): return

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
            # Fallback GIFs for default segments
            if outcome['type'] == 'jackpot_rsw': result_embed.set_image(url="https://media.giphy.com/media/xT39D7PvWnJ14wD5c4/giphy.gif")
            elif outcome['type'] == 'jackpot_rsw_big': result_embed.set_image(url="https://media.giphy.com/media/l0HlSZ0V5725j9M9W/giphy.gif")
            elif outcome['type'] == 'boost_exp': result_embed.set_image(url="https://media.giphy.com/media/l0HlSZ0V5725j9M9W/giphy.gif")
            elif outcome['type'] == 'protection': result_embed.set_image(url="https://media.giphy.com/media/3o7WIJFA5r5d9n7jcA/giphy.gif")
            elif outcome['type'] == 'tax': result_embed.set_image(url="https://media.giphy.com/media/l3V0cE3tV6h6rC3m0/giphy.gif")
            elif outcome['type'] == 'nickname_transform': result_embed.set_image(url="https://media.giphy.com/media/rY9zudf2f2o8M/giphy.gif")
            elif outcome['type'] == 'message_mishap': result_embed.set_image(url="https://media.giphy.com/media/l3V0qXjXG2X2tM/giphy.gif")
            elif outcome['type'] == 'bless_random_user': result_embed.set_image(url="https://media.giphy.com/media/l4FGJm7hXG1r0J0I/giphy.gif")
            elif outcome['type'] == 'curse_mute_random': result_embed.set_image(url="https://media.giphy.com/media/l4FGJm7hXG1r0J0I/giphy.gif") # Reused, ideally unique
            elif outcome['type'] == 'ping_random_user': result_embed.set_image(url="https://media.giphy.com/media/3ohhwpvL89Q8zN0n2g/giphy.gif")
            elif outcome['type'] == 'emoji_rain': result_embed.set_image(url="https://media.giphy.com/media/l0HlSZ0V5725j9M9W/giphy.gif") # Reused, ideally unique
            elif outcome['type'] == 'channel_rename': result_embed.set_image(url="https://media.giphy.com/media/l4FGJm7hXG1r0J0I/giphy.gif") # Reused, ideally unique
            elif outcome['type'] == 'random_duck': result_embed.set_image(url="https://media.giphy.com/media/f3ekFq7v18B9lTzY/giphy.gif")
            elif outcome['type'] == 'absurd_fortune': result_embed.set_image(url="https://media.giphy.com/media/l3V0qXjXG2X2tM/giphy.gif") # Reused, ideally unique

        await spin_message.edit(embed=result_embed)
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !putarroda: Hasil roda dikirim. Outcome: {outcome['type']}.")

        if self.dunia_cog and hasattr(self.dunia_cog, '_apply_wheel_consequence'):
            await self.dunia_cog._apply_wheel_consequence(guild, ctx.channel, user, outcome)
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !putarroda: Efek roda diterapkan melalui DuniaHidup cog.")
        else:
            await ctx.send("⚠️ Warning: DuniaHidup cog not found. Applying basic wheel consequence locally.")
            await self._apply_wheel_consequence_fallback(ctx, user, outcome)
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] !putarroda: DuniaHidup cog tidak ditemukan, efek diterapkan secara fallback.")


    async def _apply_wheel_consequence_fallback(self, ctx, user: discord.Member, outcome: dict):
        """Fallback function to apply wheel consequences if DuniaHidup cog is not loaded."""
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Applying wheel consequence (fallback) for {user.display_name}, type: {outcome['type']}.")
        user_id_str = str(user.id)
        bank_data = load_json_from_root('data/bank_data.json', default_value={})
        level_data = load_json_from_root('data/level_data.json', default_value={})

        wheel_stats = self.wheel_of_fate_data.setdefault('players_stats', {}).setdefault(user_id_str, {'spins': 0, 'wins_rsw': 0, 'losses_rsw': 0, 'weird_effects': 0})

        if outcome['type'].startswith('jackpot_rsw'):
            amount = outcome.get('amount', 500)
            bank_data.setdefault(user_id_str, {'balance': 0})['balance'] += amount
            wheel_stats['wins_rsw'] += amount
            await ctx.send(f"Selamat! Kamu memenangkan **{amount} RSWN**!")
        elif outcome['type'] == 'boost_exp':
            await ctx.send("Kamu merasa lebih energik! (Efek boost EXP tidak dapat diterapkan tanpa sistem EXP aktif).")
            wheel_stats['weird_effects'] += 1
        elif outcome['type'] == 'protection':
            await ctx.send("Kamu merasa terlindungi. (Efek perlindungan tidak dapat diterapkan tanpa sistem terkait).")
            wheel_stats['weird_effects'] += 1
        elif outcome['type'] == 'tax':
            amount = outcome.get('amount', random.randint(100, 300))
            bank_data.setdefault(user_id_str, {'balance': 0})['balance'] = max(0, bank_data[user_id_str]['balance'] - amount)
            wheel_stats['losses_rsw'] += amount
            await ctx.send(f"Oh tidak! Kamu kehilangan **{amount} RSWN** sebagai pajak takdir.")
        elif outcome['type'] == 'nickname_transform':
            original_nickname = user.nick if user.nick else user.name
            random_suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=5))
            new_nickname = f"Warga Absurd {random_suffix}"
            try:
                await user.edit(nick=new_nickname)
                await ctx.send(f"Nickname {user.display_name} berubah menjadi **{new_nickname}** untuk 1 jam!")
                await asyncio.sleep(3600)
                await user.edit(nick=original_nickname)
                await ctx.send(f"Nickname {new_nickname} kembali normal.")
            except discord.Forbidden:
                await ctx.send("Tidak dapat mengubah nickname user (izin kurang).")
            except Exception as e:
                await ctx.send(f"Terjadi error saat mengubah nickname: {e}")
            wheel_stats['weird_effects'] += 1
        elif outcome['type'] == 'message_mishap':
             await ctx.send("Kata-katamu tersangkut! Pesanmu jadi aneh selama 30 menit. (Efek ini tidak diimplementasikan penuh tanpa message listener).")
             wheel_stats['weird_effects'] += 1
        elif outcome['type'] == 'bless_random_user':
            eligible_users = [m for m in ctx.guild.members if not m.bot and m.id != user.id]
            if eligible_users:
                blessed_user = random.choice(eligible_users)
                amount = outcome.get('amount', 750)
                bank_data.setdefault(str(blessed_user.id), {'balance': 0})['balance'] += amount
                await ctx.send(f"Sebuah berkat tak terduga! **{blessed_user.mention}** mendapatkan **{amount} RSWN**!")
                self.wheel_of_fate_data.setdefault('players_stats', {}).setdefault(str(blessed_user.id), {'spins': 0, 'wins_rsw': 0, 'losses_rsw': 0, 'weird_effects': 0})['wins_rsw'] += amount
            else:
                await ctx.send("Tidak ada user lain yang bisa diberkati.")
            wheel_stats['weird_effects'] += 1
        elif outcome['type'] == 'curse_mute_random':
            eligible_users = [m for m in ctx.guild.members if not m.bot and m.id != user.id and m.voice and m.voice.channel]
            if eligible_users:
                cursed_user = random.choice(eligible_users)
                try:
                    await cursed_user.timeout(timedelta(seconds=60), reason="Roda Takdir Gila!")
                    await ctx.send(f"Sebuah kutukan! **{cursed_user.mention}** kena timeout 60 detik di voice channel!")
                except discord.Forbidden:
                    await ctx.send("Tidak dapat timeout user (izin kurang).")
                except Exception as e:
                    await ctx.send(f"Terjadi error saat timeout: {e}")
            else:
                await ctx.send("Tidak ada user lain yang bisa dikutuk (tidak ada di VC).")
            wheel_stats['weird_effects'] += 1
        elif outcome['type'] == 'ping_random_user':
            eligible_users = [m for m in ctx.guild.members if not m.bot and m.id != user.id]
            if eligible_users:
                pinged_user = random.choice(eligible_users)
                await ctx.send(f"Panggilan Darurat! {pinged_user.mention}, roda takdir memanggilmu!")
            else:
                await ctx.send("Tidak ada user lain yang bisa di-ping.")
            wheel_stats['weird_effects'] += 1
        elif outcome['type'] == 'emoji_rain':
            await ctx.send("🥳🎉🎊✨💫🌟")
            wheel_stats['weird_effects'] += 1
        elif outcome['type'] == 'channel_rename':
            original_name = ctx.channel.name
            random_suffix = ''.join(random.choices(string.ascii_letters, k=5))
            new_name = f"channel-konyol-{random_suffix}"
            try:
                await ctx.channel.edit(name=new_name)
                await ctx.send(f"Nama channel ini berubah menjadi **#{new_name}** selama 15 menit!")
                await asyncio.sleep(900)
                await ctx.channel.edit(name=original_name)
                await ctx.send(f"Nama channel kembali normal: **#{original_name}**.")
            except discord.Forbidden:
                await ctx.send("Tidak dapat mengubah nama channel (izin kurang).")
            except Exception as e:
                await ctx.send(f"Terjadi error saat mengubah nama channel: {e}")
            wheel_stats['weird_effects'] += 1
        elif outcome['type'] == 'random_duck':
            await ctx.send("Quack! 🦆 Tidak terjadi apa-apa yang serius, tapi ada bebek!")
            wheel_stats['weird_effects'] += 1
        elif outcome['type'] == 'absurd_fortune':
            await ctx.send("Takdirmu akan sangat aneh, siapkan dirimu untuk kejutan tak terduga... di masa depan!")
            wheel_stats['weird_effects'] += 1

        save_json_to_root(bank_data, 'data/bank_data.json')
        save_json_to_root(self.wheel_of_fate_data, 'data/wheel_of_mad_fate.json')

        # --- Tambahkan Bagian Donasi di Sini ---
        donasi_embed = discord.Embed(
            title="✨ Senang dengan Takdir Gila Hari Ini? Dukung kami! ✨",
            description=(
                "Pengembangan bot ini membutuhkan waktu dan usaha. "
                "Setiap dukungan kecil dari Anda sangat berarti untuk menjaga bot ini tetap aktif "
                "dan menghadirkan fitur-fitur baru yang lebih seru!\n\n"
                "Terima kasih telah bermain!"
            ),
            color=discord.Color.gold()
        )
        donasi_view = discord.ui.View()
        donasi_view.add_item(discord.ui.Button(label="Bagi Bagi (DANA/Gopay/OVO)", style=discord.ButtonStyle.url, url="https://bagibagi.co/Rh7155"))
        donasi_view.add_item(discord.ui.Button(label="Saweria (All Payment Method)", style=discord.ButtonStyle.url, url="https://saweria.co/RH7155"))

        await ctx.send(embed=donasi_embed, view=donasi_view)
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pesan donasi dikirim di akhir game Roda Takdir Gila (fallback).")


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
                try:
                    await race_state['race_message'].edit(embed=race_state['race_message'].embeds[0].set_footer(text=f"Taruhan ditutup dalam {i} detik!"))
                except discord.NotFound:
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pesan balapan tidak ditemukan saat update countdown.")
                    break # Exit loop if message is gone
                except Exception as e:
                    print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Error updating betting countdown message: {e}")
                    break
            await asyncio.sleep(5)

        if race_state.get('race_message'): # Pastikan pesan masih ada
            try:
                await race_state['race_message'].edit(embed=race_state['race_message'].embeds[0].set_footer(text="Taruhan DITUTUP!"))
            except discord.NotFound:
                pass
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
                    try:
                        await race_state['race_message'].edit(embed=self._get_race_progress_embed(race_state))
                        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Progres balapan diperbarui.")
                    except discord.NotFound:
                        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pesan balapan tidak ditemukan saat update progres.")
                        break # Exit loop if message is gone

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
            print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: ERROR fatal di channel {channel_id}: {e}.", file=sys.stderr)
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
            # Calculate integer position for display, ensuring it doesn't exceed track length
            progress_int = min(int(horse['position']), track_length)

            # Create the track segments (ensure no negative length)
            track_segment = "─" * progress_int
            remaining_segment = "─" * max(0, track_length - progress_int - 1) # -1 for horse emoji space

            progress_bar = f"[{track_segment}{horse['emoji']}{remaining_segment}]"

            progress_text += f"**{horse['id']}. {horse['name']}**\n`{progress_bar}` {progress_int}/{track_length}\n\n"

        embed.add_field(name="Lintasan", value=progress_text, inline=False)
        embed.set_image(url="https://media.giphy.com/media/l4FGJm7hXG1r0J0I/giphy.gif") # GIF balapan
        return embed

    async def _distribute_winnings(self, ctx, channel_id, winning_horse_id):
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: Mendistribusikan kemenangan untuk channel {channel_id}.")
        race_state = self.horse_racing_states.get(channel_id)
        if not race_state: return

        bank_data = load_json_from_root('data/bank_data.json', default_value={})
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
                await self.give_rewards_with_bonus_check(user, ctx.guild.id, custom_rsw=winnings, custom_exp=50) # Assuming 50 exp for winning a bet
                print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Balapan Kuda: {user.display_name} menang {winnings} RSWN.")
            else:
                losers.append(f"{user.mention} (Kalah: {bet_info['amount']} RSWN)")
                # No reward for losers, their money is already deducted
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

        # --- Tambahkan Bagian Donasi di Sini ---
        donasi_embed = discord.Embed(
            title="✨ Suka dengan Balapan Kudanya? Dukung kami! ✨",
            description=(
                "Pengembangan bot ini membutuhkan waktu dan usaha. "
                "Setiap dukungan kecil dari Anda sangat berarti untuk menjaga bot ini tetap aktif "
                "dan menghadirkan fitur-fitur baru yang lebih seru!\n\n"
                "Terima kasih telah bermain!"
            ),
            color=discord.Color.gold()
        )
        donasi_view = discord.ui.View()
        donasi_view.add_item(discord.ui.Button(label="Bagi Bagi (DANA/Gopay/OVO)", style=discord.ButtonStyle.url, url="https://bagibagi.co/Rh7155"))
        donasi_view.add_item(discord.ui.Button(label="Saweria (All Payment Method)", style=discord.ButtonStyle.url, url="https://saweria.co/RH7155"))

        await ctx.send(embed=donasi_embed, view=donasi_view)
        print(f"[{datetime.now()}] [DEBUG GLOBAL EVENTS] Pesan donasi dikirim di akhir game Balapan Kuda.")

    def _get_current_bets_text(self, bets, horses):
        if not bets:
            return "Belum ada taruhan."

        bet_summary = {} # {horse_id: {'total_amount': 0, 'bettors': []}}
        for user_id_str, bet_info in bets.items():
            horse_id = bet_info['horse_id']
            amount = bet_info['amount']
            bet_summary.setdefault(horse_id, {'total_amount': 0, 'bettors': []})
            bet_summary[horse_id]['bettors'].append(f"<@{user_id_str}> ({amount} RSWN)") # Use mention for users
            bet_summary[horse_id]['total_amount'] += amount

        text = ""
        sorted_horses = sorted(horses, key=lambda h: h['id'])
        for horse in sorted_horses:
            summary = bet_summary.get(horse['id'])
            if summary:
                text += f"**{horse['emoji']} {horse['name']}** (#{horse['id']}): Total **{summary['total_amount']} RSWN**\n"
                bettors_display = ", ".join(summary['bettors'][:5])
                if len(summary['bettors']) > 5:
                    bettors_display += f", dan {len(summary['bettors']) - 5} lainnya"
                text += f"  > {bettors_display}\n"
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
