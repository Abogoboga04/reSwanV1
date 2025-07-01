import discord
from discord.ext import commands, tasks
import json
import random
import asyncio
import os
from datetime import datetime, time, timedelta

# Impor Music cog
from .music import Music # Sesuaikan path ini jika file music.py Anda ada di folder yang berbeda

# --- Helper Functions to handle JSON data from the bot's root directory ---
def load_json_from_root(file_path):
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        full_path = os.path.join(base_dir, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True) # Ensure directory exists
        with open(full_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Peringatan: Tidak dapat memuat {full_path}. Pastikan file ada dan formatnya benar.")
        return {} # Mengembalikan dictionary kosong untuk menghindari error jika file baru/kosong

def save_json_to_root(data, file_path):
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
    def __init__(self, game_cog, channel_id, current_config):
        super().__init__(title="Atur Media Werewolf")
        self.game_cog = game_cog
        self.channel_id = channel_id
        
        current_image_urls = current_config.get('image_urls', {})
        current_audio_urls = current_config.get('audio_urls', {})

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
        game_config = self.game_cog.werewolf_roles_config.setdefault(self.channel_id, {})
        
        if 'image_urls' not in game_config:
            game_config['image_urls'] = {}
        if 'audio_urls' not in game_config:
            game_config['audio_urls'] = {}

        game_config['image_urls']['game_start_image_url'] = self.children[0].value or None
        game_config['image_urls']['night_phase_image_url'] = self.children[1].value or None
        game_config['image_urls']['day_phase_image_url'] = self.children[2].value or None
        game_config['image_urls']['night_resolution_image_url'] = self.children[3].value or None

        game_config['audio_urls']['game_start_audio_url'] = self.children[4].value or None
        game_config['audio_urls']['night_phase_audio_url'] = self.children[5].value or None
        game_config['audio_urls']['day_phase_audio_url'] = self.children[6].value or None
        game_config['audio_urls']['vote_phase_audio_url'] = self.children[7].value or None
        game_config['audio_urls']['game_end_audio_url'] = self.children[8].value or None

        view_for_update = next((v for v in self.game_cog.bot.cached_views if isinstance(v, WerewolfRoleSetupView) and v.channel_id == self.channel_id), None)
        if view_for_update:
            view_for_update.image_urls = game_config['image_urls']
            view_for_update.audio_urls = game_config['audio_urls']
            await view_for_update.update_message(interaction.message)

        await interaction.followup.send("URL gambar dan audio berhasil disimpan!", ephemeral=True)


class WerewolfRoleSetupView(discord.ui.View):
    def __init__(self, game_cog, channel_id, total_players, current_config):
        super().__init__(timeout=300) 
        self.game_cog = game_cog
        self.channel_id = channel_id
        self.total_players = total_players
        self.selected_roles = current_config.get('roles', {}).copy()
        self.image_urls = current_config.get('image_urls', {}).copy() 
        self.audio_urls = current_config.get('audio_urls', {}).copy()
        self.available_roles = game_cog.werewolf_roles_data.get('roles', {})
        
        self._add_role_selects()
        
        self.add_item(discord.ui.Button(label="Atur Media Game", style=discord.ButtonStyle.secondary, custom_id="setup_media", row=4))
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
            title="🐺 Pengaturan Peran Werewolf 🐺",
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
        
        # Ringkasan Gambar/GIF
        image_summary = ""
        if self.image_urls.get('game_start_image_url'): image_summary += "✅ Game Start Image\n"
        if self.image_urls.get('night_phase_image_url'): image_summary += "✅ Night Image\n"
        if self.image_urls.get('day_phase_image_url'): image_summary += "✅ Day Image\n"
        if self.image_urls.get('night_resolution_image_url'): image_summary += "✅ Night Resolution Image\n"
        if image_summary:
            embed.add_field(name="Status Gambar/GIF", value=image_summary, inline=False)

        # Ringkasan Audio
        audio_summary = ""
        if self.audio_urls.get('game_start_audio_url'): audio_summary += "🎵 Game Start Audio\n"
        if self.audio_urls.get('night_phase_audio_url'): audio_summary += "🎵 Night Audio\n"
        if self.audio_urls.get('day_phase_audio_url'): audio_summary += "🎵 Day Audio\n"
        if self.audio_urls.get('vote_phase_audio_url'): audio_summary += "🎵 Vote Audio\n"
        if self.audio_urls.get('game_end_audio_url'): audio_summary += "🎵 Game End Audio\n"
        if audio_summary:
            embed.add_field(name="Status Audio (MP3/WebM)", value=audio_summary, inline=False)
        
        self._add_role_selects() 
        
        await message.edit(embed=embed, view=self)

    @discord.ui.button(label="Atur Media Game", style=discord.ButtonStyle.secondary, custom_id="setup_media", row=4)
    async def setup_media_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        game_state = self.game_cog.werewolf_game_states.get(self.channel_id)
        if not game_state or interaction.user.id != game_state['host'].id:
            await interaction.response.send_message("Hanya host yang bisa mengatur media.", ephemeral=True)
            return
        
        current_config = self.game_cog.werewolf_roles_config.get(self.channel_id, {})
        await interaction.response.send_modal(WerewolfMediaSetupModal(self.game_cog, self.channel_id, current_config))

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

        current_config_for_channel = self.game_cog.werewolf_roles_config.get(self.channel_id, {})
        self.image_urls = current_config_for_channel.get('image_urls', {})
        self.audio_urls = current_config_for_channel.get('audio_urls', {})

        self.game_cog.werewolf_roles_config[self.channel_id] = {
            'roles': self.selected_roles,
            'image_urls': self.image_urls,
            'audio_urls': self.audio_urls
        }
        
        for item in self.children:
            item.disabled = True
        
        embed = interaction.message.embeds[0]
        embed.description = f"**Komposisi peran untuk game ini telah diatur!**\n\nTotal Pemain: **{self.total_players}**"
        embed.color = discord.Color.green()
        embed.set_footer(text="Host bisa gunakan !forcestartwerewolf untuk memulai game!")

        await interaction.message.edit(embed=embed, view=self)
        self.stop() 

# --- Tic Tac Toe (from previous code) ---
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
            embed.description = "🤝 **Permainan Berakhir Seri!**"
            embed.color = discord.Color.light_grey()
            for item in self.children: item.disabled = True
        else:
            self.current_player = self.player2 if self.current_player == self.player1 else self.player1
            embed.description = f"Giliran: **{self.current_player.mention}**"
        await interaction.message.edit(embed=embed, view=self)
        if self.winner or is_draw:
            self.stop()
            self.game_cog.end_game_cleanup(interaction.channel.id, game_type='tictactoe') # Added game_type


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


# --- Roda Takdir Gila! UI & Logic ---
class WheelOfMadFateView(discord.ui.View):
    def __init__(self, game_cog, channel_id, cost):
        super().__init__(timeout=120) # 2 minute timeout for the view
        self.game_cog = game_cog
        self.channel_id = channel_id
        self.cost = cost
        self.add_item(discord.ui.Button(label=f"Putar Roda ({cost} RSWN)", style=discord.ButtonStyle.success, custom_id="spin_wheel"))
    
    @discord.ui.button(label="Putar Roda", style=discord.ButtonStyle.success, custom_id="spin_wheel")
    async def spin_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True) # Defer to prevent timeout message, ephemeral
        
        user = interaction.user
        channel = interaction.channel
        
        # Check balance
        user_id_str = str(user.id)
        bank_data = load_json_from_root('data/bank_data.json')
        current_balance = bank_data.setdefault(user_id_str, {'balance': 0, 'debt': 0})['balance']

        if current_balance < self.cost:
            return await interaction.followup.send(f"Saldo RSWNmu tidak cukup untuk memutar roda ({self.cost} RSWN diperlukan). Kamu punya: **{current_balance} RSWN**.", ephemeral=True)
        
        # Deduct cost
        bank_data[user_id_str]['balance'] -= self.cost
        save_json_to_root(bank_data, 'data/bank_data.json')
        
        # Update user's spin count for leaderboard
        wheel_data = self.game_cog.wheel_of_fate_data.setdefault('players_stats', {})
        wheel_data.setdefault(user_id_str, {'spins': 0, 'wins_rsw': 0, 'losses_rsw': 0, 'weird_effects': 0})
        wheel_data[user_id_str]['spins'] += 1
        save_json_to_root(self.game_cog.wheel_of_fate_data, 'data/wheel_of_mad_fate.json')


        # Get image URLs from cog config
        config = self.game_cog.wheel_of_fate_config.get(self.channel_id, {})
        spinning_gif_url = config.get('spinning_gif_url', 'https://i.imgur.com/39hN44u.gif') # Default spinning wheel gif
        
        # Announce the spin
        spin_embed = discord.Embed(
            title="🌀 Roda Takdir Gila Sedang Berputar! 🌀",
            description=f"{user.mention} telah memutar roda... Apa takdir yang menantinya?",
            color=discord.Color.gold()
        )
        if spinning_gif_url:
            spin_embed.set_image(url=spinning_gif_url)
        
        spin_message = await channel.send(embed=spin_embed)
        
        await asyncio.sleep(random.uniform(3, 5)) # Simulate spinning time
        
        # Resolve the outcome
        outcome = self.game_cog._get_wheel_outcome(config['segments'])
        outcome_image_url = config.get('outcome_image_urls', {}).get(outcome['type'])
        
        result_embed = discord.Embed(
            title=f"✨ **Roda Berhenti!** ✨",
            description=f"Untuk {user.mention}: **{outcome['description']}**",
            color=discord.Color.from_rgb(*outcome['color'])
        )
        if outcome_image_url:
            result_embed.set_image(url=outcome_image_url)
        else:
            # Fallback for generic outcome images if specific ones not set
            if outcome['type'] == 'jackpot_rsw': result_embed.set_image(url="https://media.giphy.com/media/xT39D7PvWnJ14wD5c4/giphy.gif")
            elif outcome['type'] == 'boost_exp': result_embed.set_image(url="https://media.giphy.com/media/l0HlSZ0V5725j9M9W/giphy.gif")
            elif outcome['type'] == 'protection': result_embed.set_image(url="https://media.giphy.com/media/3o7WIJFA5r5d9n7jcA/giphy.gif")
            elif outcome['type'] == 'tax': result_embed.set_image(url="https://media.giphy.com/media/l3V0cE3tV6h6rC3m0/giphy.gif")
            elif outcome['type'] == 'nickname_transform': result_embed.set_image(url="https://media.giphy.com/media/rY9zudf2f2o8M/giphy.gif")
            elif outcome['type'] == 'message_mishap': result_embed.set_image(url="https://media.giphy.com/media/l3V0qXjXG2XW2tM/giphy.gif")
            elif outcome['type'] == 'bless_random_user': result_embed.set_image(url="https://media.giphy.com/media/l4FGJm7hXG1rE0J0I/giphy.gif")
            elif outcome['type'] == 'curse_mute_random': result_embed.set_image(url="https://media.giphy.com/media/l4FGJm7hXG1rE0J0I/giphy.gif")
            elif outcome['type'] == 'ping_random_user': result_embed.set_image(url="https://media.giphy.com/media/3ohhwpvL89Q8zN0n2g/giphy.gif")
            elif outcome['type'] == 'emoji_rain': result_embed.set_image(url="https://media.giphy.com/media/l0HlSZ0V5725j9M9W/giphy.gif")
            elif outcome['type'] == 'channel_rename': result_embed.set_image(url="https://media.giphy.com/media/l4FGJm7hXG1rE0J0I/giphy.gif")
            elif outcome['type'] == 'random_duck': result_embed.set_image(url="https://media.giphy.com/media/f3ekFq7v18B9lTzY/giphy.gif")
            elif outcome['type'] == 'absurd_fortune': result_embed.set_image(url="https://media.giphy.com/media/l3V0qXjXG2XW2tM/giphy.gif")

        await spin_message.edit(embed=result_embed)
        
        await self.game_cog._apply_wheel_consequence(interaction.guild, channel, user, outcome)


class UltimateGameArena(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = set() # Channel IDs where a game is active
        
        # --- Game States ---
        self.spyfall_game_states = {} # For Spyfall (Mata-Mata)
        self.last_spy_id = None       # To avoid repeating Spyfall spies

        # Werewolf Game States
        self.werewolf_join_queues = {} # {guild_id: {channel_id: [players]}}
        self.werewolf_game_states = {} # {channel_id: {'players': [members], 'roles': {member.id: role}, 'phase': 'day'/'night', 'day_num': 1, 'active_players': set(), 'killed_this_night': None, 'voted_out_today': None, 'host': member, 'role_actions_pending': {}, 'timers': {}, 'vote_message': None, 'players_who_voted': set(), 'last_role_setup_message': None, 'voice_client': None, 'game_task': None}} # Added 'game_task' for Werewolf
        # Store role config and image URLs here
        self.werewolf_roles_config = {} # {channel_id: {'roles': {'Werewolf': 1}, 'image_urls': {}, 'audio_urls': {}}} 
        self.werewolf_roles_data = load_json_from_root('data/werewolf_roles.json') # Master role data (name, description, team, color, icon)

        # Horse Race Game States
        self.horse_race_games = {} # {channel_id: {'status': 'betting'/'racing', 'bets': [], 'horses': {}, 'race_message': None, 'winner_horse': None, 'game_task': None}} # Added 'game_task' for Horse Race

        # Wheel of Mad Fate States
        self.wheel_of_fate_config = {} # {channel_id: {'cost': int, 'segments': [], 'spinning_gif_url': '', 'outcome_image_urls': {}}}
        self.wheel_of_fate_data = load_json_from_root('data/wheel_of_mad_fate.json') # Store stats, default segment configs etc.

        # --- Game Data ---
        self.siapakah_aku_data = load_json_from_root('data/siapakah_aku.json')
        self.pernah_gak_pernah_data = load_json_from_root('data/pernah_gak_pernah.json')
        self.hitung_cepat_data = load_json_from_root('data/hitung_cepat.json')
        self.mata_mata_locations = load_json_from_root('data/mata_mata_locations.json')
        self.deskripsi_data = load_json_from_root('data/deskripsi_tebak.json')
        self.perang_otak_data = load_json_from_root('data/perang_otak.json').get('questions', [])
        self.cerita_pembuka_data = load_json_from_root('data/cerita_pembuka.json')
        self.tekateki_harian_data = load_json_from_root('data/teka_teki_harian.json')

        # Base reward amounts for non-Werewolf games
        self.reward = {"rsw": 50, "exp": 100} 
        # Specific Werewolf rewards
        self.werewolf_win_rewards = {"rsw": 550, "exp": 550}
        # Default Wheel of Mad Fate cost
        self.wheel_spin_cost = 200

        self.daily_puzzle = None
        self.daily_puzzle_solvers = set()
        self.daily_puzzle_channel_id = 765140300145360896 
        self.post_daily_puzzle.start()

        self.music_cog = None # Akan diisi setelah bot siap

    @commands.Cog.listener()
    async def on_ready(self):
        await self.bot.wait_until_ready()
        self.music_cog = self.bot.get_cog('Music')
        if not self.music_cog:
            print(f"{datetime.now()}: Peringatan: Cog 'Music' tidak ditemukan. Fungsi audio Werewolf mungkin tidak berfungsi.")
        # Reinstate views for Werewolf Role Setup
        for channel_id, config in self.werewolf_roles_config.items():
            if 'last_role_setup_message' in config:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        message = await channel.fetch_message(config['last_role_setup_message'])
                        # Re-instantiate the view with the correct parameters
                        view = WerewolfRoleSetupView(self, channel_id, config.get('total_players', 0), config)
                        self.bot.add_view(view, message=message)
                        print(f"[{datetime.now()}] WerewolfRoleSetupView reinstated for channel {channel_id}")
                    except discord.NotFound:
                        print(f"[{datetime.now()}] Could not find Werewolf setup message for channel {channel_id}. Clearing config.")
                        del self.werewolf_roles_config[channel_id]
                    except Exception as e:
                        print(f"[{datetime.now()}] Error reinstating WerewolfRoleSetupView for channel {channel_id}: {e}")


    def cog_unload(self):
        self.post_daily_puzzle.cancel()
        
        # Cancel all active game tasks
        for channel_id in list(self.spyfall_game_states.keys()):
            game_state = self.spyfall_game_states.get(channel_id)
            if game_state and 'game_task' in game_state and not game_state['game_task'].done():
                game_state['game_task'].cancel()
            self.end_game_cleanup(channel_id, game_type='spyfall') # Ensure cleanup
            
        for channel_id in list(self.werewolf_game_states.keys()):
            game_state = self.werewolf_game_states.get(channel_id)
            if game_state and game_state.get('voice_client'):
                self.bot.loop.create_task(game_state['voice_client'].disconnect())
            if game_state and 'game_task' in game_state and not game_state['game_task'].done():
                game_state['game_task'].cancel()
            self.end_game_cleanup(channel_id, game_type='werewolf')

        for channel_id in list(self.horse_race_games.keys()):
            game_state = self.horse_race_games.get(channel_id)
            if game_state and 'game_task' in game_state and not game_state['game_task'].done():
                game_state['game_task'].cancel()
            self.end_game_cleanup(channel_id, game_type='horse_race')
        
        # Wheel of fate config does not need explicit cleanup on unload, as it's static per channel config


    def get_anomaly_multiplier(self):
        dunia_cog = self.bot.get_cog('DuniaHidup')
        if dunia_cog and hasattr(dunia_cog, 'active_anomaly') and dunia_cog.active_anomaly and dunia_cog.active_anomaly.get('type') == 'exp_boost':
            return dunia_cog.active_anomaly.get('effect', {}).get('multiplier', 1)
        return 1

    async def give_rewards_with_bonus_check(self, user: discord.Member, guild_id: int, channel: discord.TextChannel = None, custom_rsw: int = None, custom_exp: int = None):
        anomaly_multiplier = self.get_anomaly_multiplier()
        
        rsw_to_give = custom_rsw if custom_rsw is not None else self.reward['rsw']
        exp_to_give = custom_exp if custom_exp is not None else self.reward['exp']

        final_rsw = int(rsw_to_give * anomaly_multiplier)
        final_exp = int(exp_to_give * anomaly_multiplier)
        
        self.give_rewards_base(user, guild_id, final_rsw, final_exp)

        if anomaly_multiplier > 1 and channel:
            await channel.send(f"✨ **BONUS ANOMALI!** {user.mention} mendapatkan hadiah yang dilipatgandakan!", delete_after=15)

    def give_rewards_base(self, user: discord.Member, guild_id: int, rsw_amount: int, exp_amount: int):
        user_id_str, guild_id_str = str(user.id), str(guild_id)
        
        bank_data = load_json_from_root('data/bank_data.json')
        bank_data.setdefault(user_id_str, {'balance': 0, 'debt': 0})['balance'] += rsw_amount
        save_json_to_root(bank_data, 'data/bank_data.json')
        
        level_data = load_json_from_root('data/level_data.json')
        guild_data = level_data.setdefault(guild_id_str, {})
        user_data = guild_data.setdefault(user_id_str, {'exp': 0, 'level': 1})
        user_data.setdefault('exp', 0) 
        user_data['exp'] += exp_amount
        save_json_to_root(level_data, 'data/level_data.json')

    async def start_game_check(self, ctx):
        if ctx.channel.id in self.active_games:
            await ctx.send("Maaf, sudah ada permainan lain di channel ini. Tunggu selesai ya!", ephemeral=True)
            return False
        self.active_games.add(ctx.channel.id)
        return True

    def end_game_cleanup(self, channel_id, game_type=None): # Added game_type for more specific cleanup
        self.active_games.discard(channel_id)
        print(f"[{datetime.now()}] end_game_cleanup called for channel {channel_id}, type {game_type}. Active games: {self.active_games}")

        if game_type == 'spyfall' and channel_id in self.spyfall_game_states:
            game_state = self.spyfall_game_states[channel_id]
            if 'game_task' in game_state and not game_state['game_task'].done():
                game_state['game_task'].cancel() # Cancel the associated task
                print(f"[{datetime.now()}] Spyfall game_task cancelled for channel {channel_id}.")
            self.last_spy_id = self.spyfall_game_states[channel_id]['spy'].id
            del self.spyfall_game_states[channel_id]
        elif game_type == 'werewolf' and channel_id in self.werewolf_game_states:
            game_state = self.werewolf_game_states.get(channel_id)
            if game_state and game_state.get('voice_client'):
                self.bot.loop.create_task(game_state['voice_client'].disconnect())
                game_state['voice_client'] = None
            if game_state and 'game_task' in game_state and not game_state['game_task'].done():
                game_state['game_task'].cancel()
                print(f"[{datetime.now()}] Werewolf game_task cancelled for channel {channel_id}.")
            del self.werewolf_game_states[channel_id]
        elif game_type == 'horse_race' and channel_id in self.horse_race_games:
            game_state = self.horse_race_games.get(channel_id)
            if game_state and 'game_task' in game_state and not game_state['game_task'].done():
                game_state['game_task'].cancel()
                print(f"[{datetime.now()}] Horse Race game_task cancelled for channel {channel_id}.")
            del self.horse_race_games[channel_id]
        # For TicTacToe, just remove from active_games (no specific state dict or task needed beyond the view timeout)
        # For other simple games like Siapakah Aku, Pernah Gak Pernah, etc., they naturally clean up their async ops.
        
        # Clean up join queues regardless of game_type
        if channel_id in self.werewolf_join_queues.get(channel_id, {}): # This logic seems a bit off, it should be guild_id then channel_id
            # Corrected lookup for join queues
            for guild_id in list(self.werewolf_join_queues.keys()):
                if channel_id in self.werewolf_join_queues[guild_id]:
                    del self.werewolf_join_queues[guild_id][channel_id]
                    if not self.werewolf_join_queues[guild_id]: # If guild has no more queues, remove guild entry
                        del self.werewolf_join_queues[guild_id]
                    break # Found and removed, no need to check other guilds
        
        # Spyfall specific cleanup (already done at the top of this function, but ensure consistency)
        if channel_id in self.spyfall_game_states: # This should ideally already be gone if game_type='spyfall' was used
            del self.spyfall_game_states[channel_id]


    # --- Fungsi untuk Mengirim Visual Werewolf (Hanya GIF/Gambar) ---
    async def _send_werewolf_visual(self, channel: discord.TextChannel, phase: str):
        config = self.werewolf_roles_config.get(channel.id, {})
        image_urls = config.get('image_urls', {})

        visual_url = None
        if phase == "game_start":
            visual_url = image_urls.get('game_start_image_url')
        elif phase == "night_phase":
            visual_url = image_urls.get('night_phase_image_url')
        elif phase == "day_phase":
            visual_url = image_urls.get('day_phase_image_url')
        elif phase == "night_resolution":
            visual_url = image_urls.get('night_resolution_image_url')

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


    # --- Fungsi untuk Memutar Audio Werewolf (MP3/WebM) ---
    async def _play_werewolf_audio(self, text_channel: discord.TextChannel, audio_type: str):
        game_state = self.werewolf_game_states.get(text_channel.id)
        if not game_state or not game_state.get('voice_client'):
            print(f"[{datetime.now()}] Tidak ada voice client untuk channel {text_channel.id} atau game tidak aktif.")
            return

        voice_client = game_state['voice_client']
        config = self.werewolf_roles_config.get(text_channel.id, {})
        audio_urls = config.get('audio_urls', {})

        audio_url = None
        if audio_type == "game_start_audio_url":
            audio_url = audio_urls.get('game_start_audio_url')
        elif audio_type == "night_phase_audio_url":
            audio_url = audio_urls.get('night_phase_audio_url')
        elif audio_type == "day_phase_audio_url":
            audio_url = audio_urls.get('day_phase_audio_url')
        elif audio_type == "vote_phase_audio_url":
            audio_url = audio_urls.get('vote_phase_audio_url')
        elif audio_type == "game_end_audio_url":
            audio_url = audio_urls.get('game_end_audio_url')

        if audio_url and self.music_cog:
            try:
                if voice_client.is_playing() or voice_client.is_paused():
                    voice_client.stop()
                
                source = await Music.YTDLSource.from_url(audio_url, loop=self.bot.loop, stream=True)
                voice_client.play(source, after=lambda e: print(f'[{datetime.now()}] Player error in Werewolf audio: {e}') if e else None)
                print(f"[{datetime.now()}] Memutar audio Werewolf '{audio_type}' di {voice_client.channel.name}: {source.title if hasattr(source, 'title') else 'Unknown Title'}")
            except Exception as e:
                print(f"[{datetime.now()}] Gagal memutar audio Werewolf '{audio_type}': {e}")
                await text_channel.send(f"⚠️ Maaf, gagal memutar audio untuk fase ini: `{e}`")
        elif not self.music_cog:
            print(f"[{datetime.now()}] Music cog tidak ditemukan, tidak dapat memutar audio Werewolf.")
        else:
            print(f"[{datetime.now()}] URL audio untuk '{audio_type}' tidak diatur.")

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


    # --- Contoh Perintah untuk Memulai Werewolf (placeholder) ---
    @commands.command(name="startwerewolf", help="Mulai game Werewolf (contoh, perlu integrasi lebih lanjut).")
    @commands.cooldown(1, 30, commands.BucketType.channel)
    async def start_werewolf_game_example(self, ctx):
        if not await self.start_game_check(ctx): return
        
        # Contoh inisialisasi state game (Anda perlu mengganti ini dengan logika join queue Anda)
        self.werewolf_game_states[ctx.channel.id] = {
            'host': ctx.author,
            'players': [ctx.author], # Tambahkan pemain lain yang sudah join di sini (ini hanya contoh minimal)
            'voice_client': None,
            'game_task': None # Inisialisasi game_task
            # ... tambahkan state game Werewolf lainnya
        }
        
        # --- Pengecekan Voice Channel ---
        if not ctx.author.voice or not ctx.author.voice.channel:
            self.end_game_cleanup(ctx.channel.id, game_type='werewolf')
            return await ctx.send("Untuk bermain Werewolf, kamu dan pemain lain harus berada di **voice channel** yang sama!", ephemeral=True)

        vc_channel = ctx.author.voice.channel
        game_players = self.werewolf_game_states.get(ctx.channel.id, {}).get('players', [])
        # Jika players masih kosong, anggap semua yang ada di VC adalah pemain untuk contoh ini
        if not game_players:
             game_players = [m for m in vc_channel.members if not m.bot]
             self.werewolf_game_states[ctx.channel.id]['players'] = game_players

        players_in_vc = [m for m in vc_channel.members if not m.bot and m in game_players]
        
        if len(players_in_vc) < 3:
            self.end_game_cleanup(ctx.channel.id, game_type='werewolf')
            return await ctx.send("Jumlah pemain di voice channel terlalu sedikit untuk memulai game Werewolf. Minimal 3 pemain aktif!", ephemeral=True)

        if not self.music_cog:
            self.end_game_cleanup(ctx.channel.id, game_type='werewolf')
            return await ctx.send("Cog musik bot tidak aktif. Tidak bisa memulai Werewolf dengan fitur audio.", ephemeral=True)
        
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
        
        # Memulai task untuk alur game Werewolf
        game_task = self.bot.loop.create_task(self._werewolf_game_flow(ctx, ctx.channel.id, players_in_vc))
        self.werewolf_game_states[ctx.channel.id]['game_task'] = game_task


    async def _werewolf_game_flow(self, ctx, channel_id, players):
        try:
            # Contoh Panggilan Visual dan Audio sesuai Fase Game
            await self._send_werewolf_visual(ctx.channel, "game_start")
            await self._play_werewolf_audio(ctx.channel, "game_start_audio_url")
            
            await asyncio.sleep(7) # Jeda untuk contoh
            await ctx.send("Malam telah tiba... Para Werewolf beraksi!")
            await self._send_werewolf_visual(ctx.channel, "night_phase")
            await self._play_werewolf_audio(ctx.channel, "night_phase_audio_url")

            # ... (Di sini akan ada logika peran malam, voting, dll.) ...
            # Contoh transisi ke siang:
            await asyncio.sleep(15) # Simulasi durasi malam
            await ctx.send("Pagi telah tiba! Siapa yang menjadi korban malam ini?")
            await self._send_werewolf_visual(ctx.channel, "night_resolution") # Visual korban
            
            await asyncio.sleep(3) # Jeda sebelum masuk fase siang
            await ctx.send("Mari kita diskusikan!")
            await self._send_werewolf_visual(ctx.channel, "day_phase")
            await self._play_werewolf_audio(ctx.channel, "day_phase_audio_url")
            
            await asyncio.sleep(10) # Simulasi diskusi
            await ctx.send("Waktunya voting!")
            await self._play_werewolf_audio(ctx.channel, "vote_phase_audio_url")

            # ... (Logika voting dan hasilnya) ...

            await asyncio.sleep(5) # Jeda
            await ctx.send("Game Werewolf berakhir. Selamat kepada para pemenang!")
            await self._play_werewolf_audio(ctx.channel, "game_end_audio_url") # Audio akhir game
            
        except asyncio.CancelledError:
            print(f"[{datetime.now()}] Werewolf game flow for channel {channel_id} was cancelled.")
            await ctx.send("Game Werewolf dihentikan lebih awal.")
        except Exception as e:
            print(f"[{datetime.now()}] Error in Werewolf game flow for channel {channel_id}: {e}")
            await ctx.send(f"Terjadi kesalahan fatal pada game Werewolf: `{e}`. Game dihentikan.")
        finally:
            self.end_game_cleanup(channel_id, game_type='werewolf') # Bersihkan game state dan putuskan dari VC


    # --- GAME 1: DESKRIPSIKAN & TEBAK ---
    @commands.command(name="deskripsi", help="Mulai game Gartic Phone versi teks.")
    @commands.cooldown(1, 30, commands.BucketType.channel)
    async def deskripsi(self, ctx):
        if not await self.start_game_check(ctx): return
        
        vc = ctx.author.voice.channel if ctx.author.voice else None
        if not vc or len(vc.members) < 2:
            self.end_game_cleanup(ctx.channel.id, game_type='deskripsi') # Added game_type
            return await ctx.send("Game ini butuh minimal 2 orang di voice channel yang sama.", ephemeral=True)

        players = [m for m in vc.members if not m.bot]
        if len(players) < 2:
            self.end_game_cleanup(ctx.channel.id, game_type='deskripsi') # Added game_type
            return await ctx.send("Kurang pemain nih, ajak temanmu!", ephemeral=True)

        deskriptor = random.choice(players)
        
        if not self.deskripsi_data or not isinstance(self.deskripsi_data, list):
            await ctx.send("Data untuk game deskripsi tidak ditemukan atau formatnya salah.", ephemeral=True)
            self.end_game_cleanup(ctx.channel.id, game_type='deskripsi') # Added game_type
            return

        item = random.choice(self.deskripsi_data)
        word = item['word']

        try:
            await deskriptor.send(f"✍️ Kamu adalah **Deskriptor**! Kata rahasiamu adalah: **{word}**. Deskripsikan kata ini tanpa menyebutkannya langsung!")
        except discord.Forbidden:
            self.end_game_cleanup(ctx.channel.id, game_type='deskripsi') # Added game_type
            return await ctx.send(f"Gagal memulai karena tidak bisa mengirim DM ke {deskriptor.mention}. Pastikan DM-nya terbuka.", ephemeral=True)

        embed = discord.Embed(title="💡 Deskripsikan & Tebak!", color=0x3498db)
        embed.description = f"{deskriptor.mention} telah menerima kata rahasia! Dia akan mendeskripsikannya sekarang. Yang lain, siap-siap menebak!"
        embed.set_footer(text="Penebak tercepat dan Deskriptor akan mendapat hadiah!")
        await ctx.send(embed=embed)

        def check(m):
            return m.channel == ctx.channel and not m.author.bot and m.author != deskriptor and m.content.lower() == word.lower()

        try:
            winner_msg = await self.bot.wait_for('message', timeout=180.0, check=check)
            winner = winner_msg.author
            
            await ctx.send(f"🎉 **Tepat Sekali!** {winner.mention} berhasil menebak **{word}**!")
            await self.give_rewards_with_bonus_check(winner, ctx.guild.id, ctx.channel)
            await self.give_rewards_with_bonus_check(deskriptor, ctx.guild.id, ctx.channel)
            await ctx.send(f"Selamat untuk {winner.mention} dan {deskriptor.mention}, kalian berdua mendapat hadiah!")

        except asyncio.TimeoutError:
            await ctx.send(f"Waktu habis! Jawaban yang benar adalah **{word}**.")
        
        self.end_game_cleanup(ctx.channel.id, game_type='deskripsi') # Added game_type

    # --- GAME 2: PERANG OTAK (Placeholder) ---
    @commands.command(name="perangotak", help="Mulai game Family Feud.")
    @commands.cooldown(1, 60, commands.BucketType.channel)
    async def perangotak(self, ctx):
        if not await self.start_game_check(ctx): return
        await ctx.send("Fitur **Perang Otak** sedang dalam pengembangan! Nantikan update selanjutnya. 🚧", ephemeral=True)
        self.end_game_cleanup(ctx.channel.id, game_type='perangotak') # Added game_type

    # --- GAME 3: CERITA BERSAMBUNG ---
    @commands.command(name="cerita", help="Mulai game membuat cerita bersama.")
    @commands.cooldown(1, 60, commands.BucketType.channel)
    async def cerita(self, ctx):
        if not await self.start_game_check(ctx): return

        vc = ctx.author.voice.channel if ctx.author.voice else None
        if not vc or len(vc.members) < 2:
            self.end_game_cleanup(ctx.channel.id, game_type='cerita') # Added game_type
            return await ctx.send("Ayo kumpul di voice channel dulu (minimal 2 orang) buat bikin cerita!", ephemeral=True)

        players = [m for m in vc.members if not m.bot]
        random.shuffle(players)
        
        if not self.cerita_pembuka_data or not isinstance(self.cerita_pembuka_data, list):
            await ctx.send("Data untuk cerita pembuka tidak ditemukan atau formatnya salah.", ephemeral=True)
            self.end_game_cleanup(ctx.channel.id, game_type='cerita') # Added game_type
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
        
        self.end_game_cleanup(ctx.channel.id, game_type='cerita') # Added game_type
        
    # --- GAME 4: TIC-TAC-TOE ---
    @commands.command(name="tictactoe", help="Tantang temanmu bermain Tic-Tac-Toe.")
    @commands.cooldown(1, 10, commands.BucketType.channel)
    async def tictactoe(self, ctx, opponent: discord.Member):
        if opponent.bot or opponent == ctx.author:
            return await ctx.send("Kamu tidak bisa bermain melawan bot atau dirimu sendiri.", ephemeral=True)
        if not await self.start_game_check(ctx): return
        
        view = TicTacToeView(self, ctx.author, opponent)
        embed = discord.Embed(title="❌⭕ Tic-Tac-Toe ❌⭕", description=f"Giliran: **{ctx.author.mention}**", color=discord.Color.blue())
        embed.add_field(name=f"Player 1 (X)", value=ctx.author.mention, inline=True)
        embed.add_field(name=f"Player 2 (O)", value=opponent.mention, inline=True)
        await ctx.send(content=f"{opponent.mention}, kamu ditantang oleh {ctx.author.mention}!", embed=embed, view=view)

    # --- GAME 5: TEKA-TEKI HARIAN ---
    @tasks.loop(time=time(hour=5, minute=0, tzinfo=None)) # Kirim setiap jam 05:00 WIB
    async def post_daily_puzzle(self):
        await self.bot.wait_until_ready()
        now = datetime.now()
        target_time = now.replace(hour=5, minute=0, second=0, microsecond=0)
        if now > target_time:
            target_time += timedelta(days=1)
        time_until_post = (target_time - now).total_seconds()
        if time_until_post > 0:
            await asyncio.sleep(time_until_post)

        if not self.tekateki_harian_data or not isinstance(self.tekateki_harian_data, list):
            print(f"[{datetime.now()}] Peringatan: Data teka-teki harian tidak ditemukan atau formatnya salah.")
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
        if not self.daily_puzzle:
            return await ctx.send("Belum ada teka-teki untuk hari ini. Sabar ya!", ephemeral=True)
        if ctx.author.id in self.daily_puzzle_solvers:
            return await ctx.send("Kamu sudah menjawab dengan benar hari ini!", ephemeral=True)
            
        if answer.lower() == self.daily_puzzle['answer'].lower():
            self.daily_puzzle_solvers.add(ctx.author.id)
            await self.give_rewards_with_bonus_check(ctx.author, ctx.guild.id, ctx.channel)
            await ctx.message.add_reaction("✅")
            await ctx.send(f"🎉 Selamat {ctx.author.mention}! Jawabanmu benar dan kamu mendapatkan hadiah!")
        else:
            await ctx.message.add_reaction("❌")

    # --- GAME 6: TARUHAN BALAP KUDA ---
    @commands.command(name="balapankuda", help="Mulai taruhan balap kuda.")
    @commands.cooldown(1, 120, commands.BucketType.channel) # Cooldown 2 menit
    async def balapankuda(self, ctx):
        if not await self.start_game_check(ctx): return
        
        channel_id = ctx.channel.id
        self.horse_race_games[channel_id] = {
            'status': 'betting',
            'bets': {}, 
            'horses': {name: {'emoji': self.horse_emojis[i], 'progress': 0} for i, name in enumerate(self.horse_names)},
            'race_message': None,
            'winner_horse': None,
            'players_who_bet': set(),
            'game_task': None # Inisialisasi game_task
        }
        game_state = self.horse_race_games[channel_id]

        embed = discord.Embed(title="🏇 Taruhan Balap Kuda Dimulai!", color=0xf1c40f)
        embed.description = "Pasang taruhanmu pada kuda jagoanmu! Waktu taruhan: **60 detik**.\n\n"
        horse_list = "\n".join([f"{data['emoji']} **Kuda {name.capitalize()}**" for name, data in game_state['horses'].items()])
        embed.add_field(name="Daftar Kuda", value=horse_list, inline=False)
        embed.set_footer(text="Gunakan !taruhan <jumlah> <warna_kuda>")
        
        await ctx.send(embed=embed)
        
        # Memulai task untuk alur game balapan kuda
        game_task = self.bot.loop.create_task(self._horse_race_game_flow(ctx, channel_id, game_state))
        self.horse_race_games[channel_id]['game_task'] = game_task


    async def _horse_race_game_flow(self, ctx, channel_id, game_state):
        try:
            await asyncio.sleep(60) # Waktu taruhan
        except asyncio.CancelledError:
            print(f"[{datetime.now()}] Horse race betting phase for channel {channel_id} was cancelled.")
            # Cleanup already handled by the calling command if needed
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
                user = ctx.guild.get_member(user_id) # Fetch user once
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


    # --- RODA TAKDIR GILA! ---
    @commands.command(name="putarroda", aliases=['putar'], help="Putar Roda Takdir Gila untuk takdir tak terduga!")
    @commands.cooldown(1, 10, commands.BucketType.user) # Cooldown per user
    async def putarroda(self, ctx):
        channel_id = ctx.channel.id
        guild = ctx.guild

        if not guild:
            return await ctx.send("Roda Takdir Gila hanya bisa diputar di server Discord!", ephemeral=True)

        # Initialize wheel config if not present
        if channel_id not in self.wheel_of_fate_config:
            self.wheel_of_fate_config[channel_id] = {
                'cost': self.wheel_spin_cost,
                'spinning_gif_url': 'https://media.giphy.com/media/l4FGFIg12vLw83XcA/giphy.gif', # Default gif
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
        
        # Deduct cost
        bank_data[user_id_str]['balance'] -= current_wheel_config['cost']
        save_json_to_root(bank_data, 'data/bank_data.json')

        wheel_stats = self.wheel_of_fate_data.setdefault('players_stats', {})
        wheel_stats.setdefault(user_id_str, {'spins': 0, 'wins_rsw': 0, 'losses_rsw': 0, 'weird_effects': 0})
        wheel_stats[user_id_str]['spins'] += 1
        save_json_to_root(self.wheel_of_fate_data, 'data/wheel_of_mad_fate.json')

        spin_embed = discord.Embed(
            title="🌀 Roda Takdir Gila Sedang Berputar! 🌀",
            description=f"{user.mention} telah membayar **{current_wheel_config['cost']} RSWN** dan memutar roda... Apa takdir yang menantinya?",
            color=discord.Color.gold()
        )
        if current_wheel_config['spinning_gif_url']: # Use configured GIF
            spin_embed.set_image(url=current_wheel_config['spinning_gif_url'])
        
        spin_message = await ctx.send(embed=spin_embed)
        
        await asyncio.sleep(random.uniform(3, 5))
        
        outcome = self._get_wheel_outcome(current_wheel_config['segments'])
        outcome_image_url = current_wheel_config.get('outcome_image_urls', {}).get(outcome['type'])

        result_embed = discord.Embed(
            title=f"✨ **Roda Berhenti!** ✨",
            description=f"Untuk {ctx.author.mention}: **{outcome['description']}**",
            color=discord.Color.from_rgb(*outcome['color'])
        )
        # Prioritize configured outcome image, then fallback to hardcoded
        if outcome_image_url:
            result_embed.set_image(url=outcome_image_url)
        else:
            if outcome['type'] == 'jackpot_rsw': result_embed.set_image(url="https://media.giphy.com/media/xT39D7PvWnJ14wD5c4/giphy.gif")
            elif outcome['type'] == 'boost_exp': result_embed.set_image(url="https://media.giphy.com/media/l0HlSZ0V5725j9M9W/giphy.gif")
            elif outcome['type'] == 'protection': result_embed.set_image(url="https://media.giphy.com/media/3o7WIJFA5r5d9n7jcA/giphy.gif")
            elif outcome['type'] == 'tax': result_embed.set_image(url="https://media.giphy.com/media/l3V0cE3tV6h6rC3m0/giphy.gif")
            elif outcome['type'] == 'nickname_transform': result_embed.set_image(url="https://media.giphy.com/media/rY9zudf2f2o8M/giphy.gif")
            elif outcome['type'] == 'message_mishap': result_embed.set_image(url="https://media.giphy.com/media/l3V0qXjXG2XW2tM/giphy.gif")
            elif outcome['type'] == 'bless_random_user': result_embed.set_image(url="https://media.giphy.com/media/l4FGJm7hXG1rE0J0I/giphy.gif")
            elif outcome['type'] == 'curse_mute_random': result_embed.set_image(url="https://media.giphy.com/media/l4FGJm7hXG1rE0J0I/giphy.gif")
            elif outcome['type'] == 'ping_random_user': result_embed.set_image(url="https://media.giphy.com/media/3ohhwpvL89Q8zN0n2g/giphy.gif")
            elif outcome['type'] == 'emoji_rain': result_embed.set_image(url="https://media.giphy.com/media/l0HlSZ0V5725j9M9W/giphy.gif")
            elif outcome['type'] == 'channel_rename': result_embed.set_image(url="https://media.giphy.com/media/l4FGJm7hXG1rE0J0I/giphy.gif")
            elif outcome['type'] == 'random_duck': result_embed.set_image(url="https://media.giphy.com/media/f3ekFq7v18B9lTzY/giphy.gif")
            elif outcome['type'] == 'absurd_fortune': result_embed.set_image(url="https://media.giphy.com/media/l3V0qXjXG2XW2tM/giphy.gif")

        await spin_message.edit(embed=result_embed)
        
        await self._apply_wheel_consequence(interaction.guild, channel, user, outcome)

        # Update stats based on outcome
        if outcome['type'] in ['jackpot_rsw', 'boost_exp', 'protection', 'bless_random_user']:
            player_stats['wins_rsw'] += (outcome['amount'] if 'amount' in outcome else 0)
        elif outcome['type'] in ['tax', 'nickname_transform', 'message_mishap', 'curse_mute_random', 'ping_random_user', 'emoji_rain', 'channel_rename']:
            player_stats['losses_rsw'] += (outcome['amount'] if 'amount' in outcome else 0)
            player_stats['weird_effects'] += 1
        save_json_to_root(self.wheel_of_fate_data, 'data/wheel_of_mad_fate.json')


    def _get_default_wheel_segments(self):
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
        total_weight = sum(s['weight'] for s in segments)
        rand_num = random.uniform(0, total_weight)
        
        current_weight = 0
        for segment in segments:
            current_weight += segment['weight']
            if rand_num <= current_weight:
                # Handle jackpot_rsw_big to jackpot_rsw conversion logic if it lands on it
                if segment['type'] == 'jackpot_rsw_big':
                    return {'type': 'jackpot_rsw', 'description': "MEGA JACKPOT! Kamu mendapatkan **1000 RSWN**!", 'color': (255,165,0), 'amount': 1000}
                # For other segments, return as is (deep copy to prevent modification issues if segment dicts are reused)
                return segment.copy() 
        # Fallback if somehow no segment is picked (shouldn't happen with correct weights)
        return random.choice(segments).copy()


    async def _apply_wheel_consequence(self, guild: discord.Guild, channel: discord.TextChannel, user: discord.Member, outcome: dict):
        user_id_str = str(user.id)
        wheel_stats = self.wheel_of_fate_data.setdefault('players_stats', {})
        player_stats = wheel_stats.setdefault(user_id_str, {'spins': 0, 'wins_rsw': 0, 'losses_rsw': 0, 'weird_effects': 0})
        
        if outcome['type'] == 'jackpot_rsw':
            amount = outcome['amount']
            await self.give_rewards_with_bonus_check(user, guild.id, channel, custom_rsw=amount, custom_exp=0)
            player_stats['wins_rsw'] += amount
            await channel.send(f"🎉 **SELAMAT!** {user.mention} mendapatkan **{amount} RSWN** dari Roda Takdir Gila!")

        elif outcome['type'] == 'boost_exp':
            await channel.send(f"⚡ **BOOST EXP!** {user.mention} mendapatkan 2x EXP dari pesan selama 1 jam! Maksimalkan diskusimu!")
            player_stats['weird_effects'] += 1

        elif outcome['type'] == 'protection':
            await channel.send(f"🛡️ **Perlindungan Aneh!** {user.mention} kebal dari 1 efek negatif Roda Takdir berikutnya! (Hanya berlaku sekali)")
            player_stats['weird_effects'] += 1

        elif outcome['type'] == 'tax':
            bank_data = load_json_from_root('data/bank_data.json')
            current_balance = bank_data.setdefault(user_id_str, {'balance': 0, 'debt': 0})['balance']
            tax_amount = min(int(current_balance * 0.10), 1500)
            if current_balance < 500: tax_amount = current_balance
            
            if tax_amount > 0:
                bank_data[user_id_str]['balance'] -= tax_amount
                save_json_to_root(bank_data, 'data/bank_data.json')
                player_stats['losses_rsw'] += tax_amount
                await channel.send(f"💸 **TERKENA PAJAK!** {user.mention} kehilangan **{tax_amount} RSWN** oleh Roda Takdir Gila!")
            else:
                await channel.send(f"💸 **TERKENA PAJAK!** Tapi {user.mention} sangat miskin, Roda Takdir kasihan. Tidak ada RSWN yang diambil.")
            player_stats['weird_effects'] += 1


        elif outcome['type'] == 'nickname_transform':
            absurd_nicknames = [
                "Raja Terong 🍆", "Ratu Bebek 🦆", "Kapten Kentang 🥔", "Pangeran Bawang Bombay 🧅",
                "Si Kucing Anggora Gila 🐈‍⬛", "Alien Penjelajah WC 🚽", "Badut Galau 🤡", "Batu Berkata-kata 🗿"
            ]
            original_nickname = user.display_name
            new_nickname = random.choice(absurd_nicknames)
            
            try:
                await user.edit(nick=new_nickname, reason="Roda Takdir Gila: Transfigurasi Sementara")
                await channel.send(f"✨ **TRANFIGURASI SEMENTARA!** Nickname server {user.mention} berubah jadi **{new_nickname}** selama 1 jam! (Nickname aslinya: {original_nickname})")
                
                await asyncio.sleep(3600)
                # Check if the user's nickname is still the absurd one before reverting
                current_member = guild.get_member(user.id) # Get fresh member data
                if current_member and current_member.nick == new_nickname:
                    await current_member.edit(nick=original_nickname, reason="Roda Takdir Gila: Kembali Normal")
                    await channel.send(f"✨ Nickname server {user.mention} kembali normal.")
                elif current_member:
                    await channel.send(f"Nickname {user.mention} sudah berubah, tidak dikembalikan otomatis.")

            except discord.Forbidden:
                await channel.send(f"❌ Bot tidak bisa mengubah nickname {user.mention}. Pastikan bot punya izin `Manage Nicknames`!")
            except Exception as e:
                print(f"Error changing nickname for {user.name}: {e}")
                await channel.send(f"Terjadi kesalahan saat mengubah nickname {user.mention}. {user.mention} seharusnya jadi **{new_nickname}**!")
            player_stats['weird_effects'] += 1


        elif outcome['type'] == 'message_mishap':
            await channel.send(f"🗣️ **TERSEDAK KATA!** Semua pesan {user.mention} di channel ini akan jadi aneh selama 30 menit! Semoga beruntung bicara!")
            player_stats['weird_effects'] += 1


        elif outcome['type'] == 'bless_random_user':
            online_members = [m for m in guild.members if m.status != discord.Status.offline and not m.bot and m.id != user.id]
            if online_members:
                blessed_user = random.choice(online_members)
                amount = outcome['amount'] if 'amount' in outcome else 500
                await self.give_rewards_with_bonus_check(blessed_user, guild.id, channel, custom_rsw=amount, custom_exp=0)
                await channel.send(f"🎁 **BERKAT RANDOM!** {blessed_user.mention} tiba-tiba mendapatkan **{amount} RSWN** dari Roda Takdir Gila! (Terima kasih {user.mention}!)")
            else:
                await channel.send("Tidak ada user lain yang online untuk diberkati Roda Takdir kali ini.")
            player_stats['weird_effects'] += 1


        elif outcome['type'] == 'curse_mute_random':
            active_members = [m for m m.guild.members if m.status != discord.Status.offline and not m.bot and m.id != user.id]
            if active_members:
                cursed_user = random.choice(active_members)
                try:
                    await cursed_user.timeout(timedelta(seconds=60), reason="Roda Takdir Gila: Kutukan Mute Kilat")
                    await channel.send(f"🔇 **KUTUKAN MUTE KILAT!** {cursed_user.mention} tidak bisa bicara selama 60 detik! (Awas, {user.mention}!)")
                except discord.Forbidden:
                    await channel.send(f"❌ Bot tidak bisa memberi timeout {cursed_user.mention}. Pastikan bot punya izin `Timeout Members`!")
                except Exception as e:
                    print(f"Error timing out {cursed_user.name}: {e}")
                    await channel.send(f"Terjadi kesalahan saat menerapkan Kutukan Mute Kilat pada {cursed_user.mention}.")
            else:
                await channel.send("Tidak ada user lain yang aktif untuk menerima Kutukan Mute Kilat.")
            player_stats['weird_effects'] += 1


        elif outcome['type'] == 'ping_random_user':
            all_users = [m for m in guild.members if not m.bot and m.id != user.id]
            if all_users:
                target_user = random.choice(all_users)
                for _ in range(3):
                    await channel.send(f"🔔 **PANGGILAN DARURAT!** Roda Takdir Gila memanggilmu, wahai jiwa yang tersesat, {target_user.mention}!")
                    await asyncio.sleep(random.uniform(2, 4))
            else:
                await channel.send("Roda Takdir Gila mencoba memanggil, tapi tidak ada jiwa lain untuk dipanggil.")
            player_stats['weird_effects'] += 1


        elif outcome['type'] == 'emoji_rain':
            # Filter out custom emojis that might not be available to the bot or guild
            available_emojis = [str(e) for e in guild.emojis]
            if available_emojis:
                await channel.send(f"🎉 **HUJAN EMOJI!** Bersiaplah, {user.mention} telah memicu badai emoji!")
                for _ in range(3):
                    # Ensure we don't try to sample more than available emojis
                    await channel.send(" ".join(random.sample(available_emojis, min(5, len(available_emojis)))))
                    await asyncio.sleep(0.5)
            else:
                await channel.send("Tidak ada emoji kustom di server ini untuk dihujani.")
            player_stats['weird_effects'] += 1


        elif outcome['type'] == 'channel_rename':
            original_channel_name = channel.name
            absurd_channel_names = [
                "kebun-binatang-virtual", "gudang-kaus-kaki-hilang", "lemari-baju-terbalik", 
                "dapur-mie-instan", "sumur-harapan-palsu", "gong-gila-berbunyi"
            ]
            new_channel_name = random.choice(absurd_channel_names)
            try:
                await channel.edit(name=new_channel_name, reason="Roda Takdir Gila: Perubahan Nama Channel Absurd")
                await channel.send(f"📛 **NAMA CHANNEL BERUBAH ABSURD!** Channel ini sekarang jadi `# {new_channel_name}` selama 15 menit! (Dipicu oleh {user.mention})")
                await asyncio.sleep(900)
                # Check if the channel name is still the absurd one before reverting
                current_channel = guild.get_channel(channel.id)
                if current_channel and current_channel.name == new_channel_name:
                    await current_channel.edit(name=original_channel_name, reason="Roda Takdir Gila: Kembali Normal")
                    await channel.send(f"Channel ini kembali ke nama normalnya: `#{original_channel_name}`.")
                elif current_channel:
                    await channel.send(f"Nama channel sudah berubah, tidak dikembalikan otomatis.")

            except discord.Forbidden:
                await channel.send(f"❌ Bot tidak bisa mengubah nama channel. Pastikan bot punya izin `Manage Channels`!")
            except Exception as e:
                print(f"Error renaming channel {channel.name}: {e}")
                await channel.send(f"Terjadi kesalahan saat mengubah nama channel. Channel seharusnya jadi **#{new_channel_name}**! (Dipicu oleh {user.mention})")
            player_stats['weird_effects'] += 1


        elif outcome['type'] == 'random_duck':
            # Assuming you have this GIF locally or it's a direct URL
            await channel.send(f"🦆 **KEJUTAN BEBEK!** Seekor bebek kartun muncul entah dari mana! (Dipicu oleh {user.mention})", file=discord.File('./assets/duck_gif.gif')) # Changed to local path assuming you have it
            player_stats['weird_effects'] += 1


        elif outcome['type'] == 'absurd_fortune':
            fortunes = [
                "Kamu akan menemukan kaus kaki hilangmu di bawah kulkas besok.",
                "Takdirmu adalah menjadi koki spesialis mie instan rasa durian.",
                "Besok, kamu akan bertemu dengan alien yang sangat gemar alpukat.",
                "Nomor keberuntunganmu adalah jumlah bulu kucing hitam tetangga sebelah."
            ]
            await channel.send(f"🔮 **RAMALAN HALU!** Untuk {user.mention}: \"{random.choice(fortunes)}\"")
            player_stats['weird_effects'] += 1
        
        save_json_to_root(self.wheel_of_fate_data, 'data/wheel_of_mad_fate.json')


    # --- SPYFALL (MATA-MATA) GAME LOGIC ---
    @commands.command(name="matamata", help="Mulai game Mata-Mata. Temukan siapa mata-matanya!")
    @commands.cooldown(1, 300, commands.BucketType.channel)
    async def matamata(self, ctx):
        # Initial checks and setup
        if not await self.start_game_check(ctx): # Checks self.active_games
            return
        
        if not ctx.author.voice or not ctx.author.voice.channel: 
            self.end_game_cleanup(ctx.channel.id, game_type='spyfall') # Cleanup if conditions not met
            return await ctx.send("Kamu harus berada di voice channel untuk memulai game ini.", delete_after=10)
        
        vc = ctx.author.voice.channel
        members = [m for m in vc.members if not m.bot]
        if len(members) < 3: 
            self.end_game_cleanup(ctx.channel.id, game_type='spyfall') # Cleanup if conditions not met
            return await ctx.send("Game ini butuh minimal 3 orang di voice channel.", delete_after=10)
        
        location = random.choice(self.mata_mata_locations)
        
        # Logic to avoid repeating the last spy
        eligible_spies = [m for m in members if m.id != self.last_spy_id]
        spy = random.choice(eligible_spies) if eligible_spies else random.choice(members)
        
        # Initialize game state for Spyfall
        self.spyfall_game_states[ctx.channel.id] = {
            'spy': spy,
            'location': location,
            'players': members,
            'discussion_start_time': datetime.now(), 
            'vote_in_progress': False,
            'game_task': None # Placeholder for the game flow task
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

        # Create and store the game flow task
        game_task = self.bot.loop.create_task(self._spyfall_game_flow(ctx, ctx.channel.id, spy, location, members))
        self.spyfall_game_states[ctx.channel.id]['game_task'] = game_task


    async def _spyfall_game_flow(self, ctx, channel_id, spy, location, players):
        try:
            # Phase 1: Discussion (5 minutes)
            await asyncio.sleep(300) # Wait for 5 minutes of discussion
            
            # Check if the game is still active after the discussion period
            if channel_id not in self.spyfall_game_states:
                # Game has already been ended by a successful !tuduh or !ungkap_lokasi command
                return 

            await ctx.send(f"⏰ **Waktu diskusi 5 menit habis!** Sekarang adalah fase penuduhan akhir. "
                           f"Pemain biasa bisa menggunakan `!tuduh @nama_pemain` untuk memulai voting.\n"
                           f"Mata-mata bisa menggunakan `!ungkap_lokasi <lokasi>` untuk mencoba menebak lokasi.\n\n"
                           f"Jika mata-mata berhasil menebak lokasi dengan benar dan belum dituduh, mata-mata menang! Jika tidak ada yang menuduh atau mata-mata tidak menebak lokasi dalam waktu 2 menit, maka **mata-mata menang secara otomatis.**")
            
            # Phase 2: Final Accusation/Revelation (2 minutes)
            await asyncio.sleep(120) # Wait for 2 minutes for final actions
            
            # Check again if the game is still active after the final accusation phase
            if channel_id in self.spyfall_game_states:
                # If it's still in state, it means no successful accusation or revelation occurred
                await ctx.send(f"Waktu penuduhan habis! Mata-mata ({spy.mention}) menang karena tidak ada yang berhasil menuduh atau mata-mata tidak mengungkapkan lokasi! Lokasi sebenarnya adalah **{location}**.")
                await self.give_rewards_with_bonus_check(spy, ctx.guild.id, ctx.channel)
                self.end_game_cleanup(channel_id, game_type='spyfall') # Clean up game state


        except asyncio.CancelledError:
            # This exception is caught if self.spyfall_game_states[channel_id]['game_task'].cancel() is called.
            # The cleanup will be handled by the command that triggered the cancellation.
            print(f"[{datetime.now()}] Spyfall game flow for channel {channel_id} was cancelled.")
        except Exception as e:
            print(f"[{datetime.now()}] Error in _spyfall_game_flow for channel {channel_id}: {e}")
            await ctx.send(f"Terjadi kesalahan fatal pada game Mata-Mata: `{e}`. Game dihentikan.")
            self.end_game_cleanup(channel_id, game_type='spyfall') # Ensure cleanup even on unexpected errors


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
        
        await asyncio.sleep(30) # Wait for votes
        
        # Re-fetch game state, as it might have been cleaned up if another command ended it during sleep
        if ctx.channel.id not in self.spyfall_game_states:
            print(f"[{datetime.now()}] Spyfall game state not found during vote tally for channel {ctx.channel.id}.")
            return # Game already ended by another action or cleanup

        game = self.spyfall_game_states[ctx.channel.id] # Re-fetch current game state
        game['vote_in_progress'] = False # Reset vote status

        try:
            cached_vote_msg = await ctx.channel.fetch_message(vote_msg.id)
            yes_votes = 0
            no_votes = 0
            actual_voters = set() 

            for reaction in cached_vote_msg.reactions:
                if str(reaction.emoji) == "✅":
                    async for user_reaction in reaction.users():
                        if not user_reaction.bot and user_reaction in players and user_reaction.id not in actual_voters:
                            yes_votes += 1
                            actual_voters.add(user_reaction.id)
                elif str(reaction.emoji) == "❌":
                    async for user_reaction in reaction.users():
                        if not user_reaction.bot and user_reaction in players and user_reaction.id not in actual_voters:
                            no_votes += 1
                            actual_voters.add(user_reaction.id)
            
            # The calculation for total_eligible_voters was slightly off. It should be based on the players who *can* vote.
            # A simpler way is to compare actual votes to total players.
            # A vote requires more than half of the *living* players to be successful.
            
            # Exclude the accuser and accused from the voting pool for simplicity, as they implicitly vote by action
            # However, if they *can* vote (e.g., if accused isn't spy and can still vote), keep them in the pool for count.
            # For simplicity here, let's just count total players in the game for the majority check.
            
            # Define majority as strictly more than half of all current players
            majority_needed = len(players) / 2 

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
                self.end_game_cleanup(ctx.channel.id, game_type='spyfall') # Game ends here
            else:
                await ctx.send(f"❌ **Voting Gagal.** Tidak cukup suara untuk menuduh {member.mention}. Permainan dilanjutkan!")
                # Game continues, no cleanup here
        
        except discord.NotFound:
            await ctx.send("Pesan voting tidak ditemukan.")
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

        # Re-check if the game is still active just before revealing (edge case if cleanup happened very fast)
        if ctx.channel.id not in self.spyfall_game_states:
            return # Game already ended by another action

        if guessed_location.lower() == location.lower():
            await ctx.send(f"🎉 **Mata-Mata Ungkap Lokasi Dengan Benar!** {spy.mention} berhasil menebak lokasi rahasia yaitu **{location}**! Mata-mata menang!")
            await self.give_rewards_with_bonus_check(spy, ctx.guild.id, ctx.channel)
        else:
            await ctx.send(f"❌ **Mata-Mata Gagal Mengungkap Lokasi!** Tebakan `{guessed_location}` salah. Lokasi sebenarnya adalah **{location}**. Warga menang!")
            for p in game['players']:
                if p.id != spy.id:
                    await self.give_rewards_with_bonus_check(p, ctx.guild.id, ctx.channel)

        self.end_game_cleanup(ctx.channel.id, game_type='spyfall') # Game ends here

    # --- TEKA-TEKI HARIAN ---
    @tasks.loop(time=time(hour=5, minute=0, tzinfo=None)) # Kirim setiap jam 05:00 WIB
    async def post_daily_puzzle(self):
        await self.bot.wait_until_ready()
        now = datetime.now()
        target_time = now.replace(hour=5, minute=0, second=0, microsecond=0)
        if now > target_time:
            target_time += timedelta(days=1)
        time_until_post = (target_time - now).total_seconds()
        if time_until_post > 0:
            await asyncio.sleep(time_until_post)

        if not self.tekateki_harian_data or not isinstance(self.tekateki_harian_data, list):
            print(f"[{datetime.now()}] Peringatan: Data teka-teki harian tidak ditemukan atau formatnya salah.")
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
        if not self.daily_puzzle:
            return await ctx.send("Belum ada teka-teki untuk hari ini. Sabar ya!", ephemeral=True)
        if ctx.author.id in self.daily_puzzle_solvers:
            return await ctx.send("Kamu sudah menjawab dengan benar hari ini!", ephemeral=True)
            
        if answer.lower() == self.daily_puzzle['answer'].lower():
            self.daily_puzzle_solvers.add(ctx.author.id)
            await self.give_rewards_with_bonus_check(ctx.author, ctx.guild.id, ctx.channel)
            await ctx.message.add_reaction("✅")
            await ctx.send(f"🎉 Selamat {ctx.author.mention}! Jawabanmu benar dan kamu mendapatkan hadiah!")
        else:
            await ctx.message.add_reaction("❌")

async def setup(bot):
    await bot.add_cog(UltimateGameArena(bot))
