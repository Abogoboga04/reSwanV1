import discord
from discord.ext import commands
import json
import random
import asyncio
import os

class GameLanjutan(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Game State Management
        self.active_scramble_games = {}
        self.active_sambung_games = {}
        
        # Load Data
        self.bank_data = self.load_json('data/bank_data.json')
        self.level_data = self.load_json('data/level_data.json')
        self.scramble_questions = self.load_json('data/questions_hangman.json')
        self.sambung_kata_words = self.load_json('data/sambung_kata_words.json')

        # Game Configuration
        self.game_channel_id = 765140300145360896 # ID channel yang diizinkan
        self.scramble_reward = {"rsw": 25, "exp": 15}
        self.sambung_kata_winner_reward = {"rsw": 150, "exp": 100}
        self.scramble_time_limit = 30 # Detik per soal acak kata
        self.sambung_kata_time_limit = 20 # Detik per giliran sambung kata

    def load_json(self, file_path):
        """Helper function to load a JSON file."""
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            full_path = os.path.join(base_dir, file_path)
            with open(full_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print(f"Warning: Could not load {file_path}. A new file might be created.")
            return {} if 'bank' in file_path or 'level' in file_path else []

    def save_json(self, data, file_path):
        """Helper function to save data to a JSON file."""
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        full_path = os.path.join(base_dir, file_path)
        with open(full_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)

    def give_rewards(self, user_id, guild_id, rewards):
        """Gives RSWN and EXP to a user based on the provided JSON structure."""
        user_id_str = str(user_id)
        guild_id_str = str(guild_id)
        
        if user_id_str not in self.bank_data:
            self.bank_data[user_id_str] = {'balance': 0, 'debt': 0}
        self.bank_data[user_id_str]['balance'] += rewards.get("rsw", 0)
        self.save_json(self.bank_data, 'data/bank_data.json')
        
        if guild_id_str not in self.level_data:
            self.level_data[guild_id_str] = {}
        
        guild_users = self.level_data[guild_id_str]
        if user_id_str not in guild_users:
            guild_users[user_id_str] = {'exp': 0, 'level': 1, 'badges': ['🐣']}
        if 'exp' not in guild_users[user_id_str]: guild_users[user_id_str]['exp'] = 0
        guild_users[user_id_str]['exp'] += rewards.get("exp", 0)
        self.save_json(self.level_data, 'data/level_data.json')

    # --- GAME 1: TEBAK KATA ACAK (WORD SCRAMBLE) ---
    @commands.command(name="resacak", help="Mulai permainan Tebak Kata Acak.")
    async def resacak(self, ctx):
        if ctx.channel.id != self.game_channel_id:
            return await ctx.send("Permainan ini hanya bisa dimainkan di channel yang ditentukan.", delete_after=10)
        if ctx.channel.id in self.active_scramble_games:
            return await ctx.send("Permainan Tebak Kata Acak sudah berlangsung. Mohon tunggu hingga selesai.", delete_after=10)
        
        embed = discord.Embed(title="🎲 Siap Bermain Tebak Kata Acak?", color=0x3498db)
        embed.description = (
            "Uji kecepatan berpikir dan kosakatamu dalam game seru ini!\n\n"
            "**Aturan Main:**\n"
            "1. Bot akan memberikan kata yang hurufnya diacak.\n"
            "2. Tebak kata aslinya secepat mungkin.\n"
            f"3. Jawaban benar pertama mendapat **{self.scramble_reward['rsw']} RSWN** & **{self.scramble_reward['exp']} EXP**.\n"
            "4. Permainan terdiri dari 10 ronde.\n\n"
            "Klik tombol di bawah untuk memulai petualangan katamu!"
        )
        embed.set_thumbnail(url="https://i.imgur.com/gJ9w0a1.png") # Puzzle icon
        embed.set_footer(text="Hanya pemanggil perintah yang bisa memulai permainan.")
        
        view = discord.ui.View(timeout=60)
        start_button = discord.ui.Button(label="MULAI SEKARANG", style=discord.ButtonStyle.primary, emoji="▶️")

        async def start_callback(interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message("Hanya pemanggil perintah yang bisa memulai permainan.", ephemeral=True)
            
            self.active_scramble_games[ctx.channel.id] = True
            await interaction.message.delete()
            await ctx.send(f"**Permainan Tebak Kata Acak Dimulai!** Diselenggarakan oleh {ctx.author.mention}", delete_after=10)
            await self.play_scramble_game(ctx)
            
        start_button.callback = start_callback
        view.add_item(start_button)
        await ctx.send(embed=embed, view=view)

    async def play_scramble_game(self, ctx):
        if not self.scramble_questions or len(self.scramble_questions) < 10:
            await ctx.send("Maaf, bank soal tidak cukup untuk memulai permainan.")
            self.active_scramble_games.pop(ctx.channel.id, None)
            return
            
        questions = random.sample(self.scramble_questions, 10)
        for i, question_data in enumerate(questions):
            word = question_data['word']
            clue = question_data['clue']
            scrambled_word = "".join(random.sample(word, len(word)))

            embed = discord.Embed(title=f"📝 Soal #{i+1}", color=0x2ecc71)
            embed.add_field(name="Kata Teracak", value=f"## `{scrambled_word.upper()}`", inline=False)
            embed.add_field(name="Petunjuk", value=f"_{clue}_", inline=False)
            
            question_msg = await ctx.send(embed=embed)

            # --- Timer and Waiter Logic ---
            winner = await self.wait_for_answer_with_timer(ctx, word, question_msg, self.scramble_time_limit)

            if winner:
                self.give_rewards(winner.id, ctx.guild.id, self.scramble_reward)
                await ctx.send(f"🎉 Selamat {winner.mention}! Jawabanmu benar. Kamu mendapatkan hadiah!")
            else: # Timeout
                await ctx.send(f"Waktu habis! Jawaban yang benar adalah: **{word}**.")

        await ctx.send("🏁 Permainan Tebak Kata Acak selesai! Terima kasih sudah bermain.")
        self.active_scramble_games.pop(ctx.channel.id, None)

    # --- GAME 2: SAMBUNG KATA ---
    @commands.command(name="ressambung", help="Mulai permainan Sambung Kata di Voice Channel.")
    async def ressambung(self, ctx):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("Kamu harus berada di dalam voice channel untuk memulai game ini.", delete_after=10)
        vc = ctx.author.voice.channel
        if vc.id in self.active_sambung_games:
            return await ctx.send(f"Sudah ada permainan Sambung Kata yang berlangsung di voice channel ini.", delete_after=10)

        members = [m for m in vc.members if not m.bot]
        if len(members) < 2:
            return await ctx.send("Permainan ini membutuhkan minimal 2 orang di dalam voice channel.", delete_after=10)

        game_state = {
            "players": {p.id: p for p in members}, "turn_index": 0, "current_word": "",
            "used_words": set(), "channel": ctx.channel, "guild_id": ctx.guild.id
        }
        self.active_sambung_games[vc.id] = game_state
        
        player_mentions = ", ".join([p.mention for p in game_state["players"].values()])
        embed = discord.Embed(title="🔗 Siap Bermain Sambung Kata?", color=0xe91e63)
        embed.description = (
            "Uji kosakatamu dan bertahanlah sampai akhir!\n\n"
            "**Aturan Main:**\n"
            "1. Pemain bergiliran menyambung kata berdasarkan **2 huruf terakhir**.\n"
            "2. Waktu menjawab **20 detik** per giliran.\n"
            "3. Pemain yang gagal atau salah kata akan tereliminasi.\n"
            f"4. Pemenang terakhir mendapat **{self.sambung_kata_winner_reward['rsw']} RSWN** & **{self.sambung_kata_winner_reward['exp']} EXP**.\n"
        )
        embed.add_field(name="👥 Pemain Bergabung", value=player_mentions)
        embed.set_thumbnail(url="https://i.imgur.com/wA2O6b4.png") # Chain icon
        
        await ctx.send(embed=embed)
        await asyncio.sleep(5)
        await self.play_sambung_kata_game(vc.id)

    async def play_sambung_kata_game(self, vc_id):
        game = self.active_sambung_games.get(vc_id)
        if not game: return

        player_ids = list(game["players"].keys())
        random.shuffle(player_ids)
        
        game["current_word"] = random.choice(self.sambung_kata_words).lower()
        game["used_words"].add(game["current_word"])
        
        await game["channel"].send(f"Kata pertama dari bot adalah: **{game['current_word'].upper()}**")

        while len(player_ids) > 1:
            current_player_id = player_ids[game["turn_index"]]
            current_player = game["players"][current_player_id]
            prefix = game["current_word"][-2:].lower()
            
            embed = discord.Embed(
                title=f"Giliran {current_player.display_name}!",
                description=f"Sebutkan kata yang diawali dengan **`{prefix.upper()}`**",
                color=current_player.color
            )
            prompt_msg = await game["channel"].send(embed=embed)

            try:
                # --- Timer and Waiter Logic ---
                async def timer_task():
                    for i in range(self.sambung_kata_time_limit, -1, -1):
                        new_embed = embed.copy()
                        new_embed.set_footer(text=f"Waktu tersisa: {i} detik ⏳")
                        await prompt_msg.edit(embed=new_embed)
                        await asyncio.sleep(1)
                
                def check(m):
                    return m.author.id == current_player_id and m.channel == game["channel"]
                
                wait_for_msg = self.bot.loop.create_task(self.bot.wait_for('message', check=check))
                timer = self.bot.loop.create_task(timer_task())

                done, pending = await asyncio.wait([wait_for_msg, timer], return_when=asyncio.FIRST_COMPLETED)
                timer.cancel()
                
                if wait_for_msg in done:
                    msg = wait_for_msg.result()
                    new_word = msg.content.strip().lower()
                    if not new_word.startswith(prefix):
                        await game["channel"].send(f"❌ Salah! {current_player.mention} tereliminasi!")
                        player_ids.pop(game["turn_index"])
                    elif new_word in game["used_words"]:
                        await game["channel"].send(f"❌ Kata sudah digunakan! {current_player.mention} tereliminasi!")
                        player_ids.pop(game["turn_index"])
                    else:
                        await msg.add_reaction("✅")
                        game["current_word"], game["used_words"] = new_word, game["used_words"] | {new_word}
                        game["turn_index"] = (game["turn_index"] + 1) % len(player_ids)
                else: # Timeout
                    raise asyncio.TimeoutError

            except asyncio.TimeoutError:
                await game["channel"].send(f"⌛ Waktu habis! {current_player.mention} tereliminasi!")
                player_ids.pop(game["turn_index"])
            
            if game["turn_index"] >= len(player_ids) and len(player_ids) > 0: game["turn_index"] = 0
            await asyncio.sleep(2)

        if len(player_ids) == 1:
            winner = game["players"][player_ids[0]]
            guild_id = game["guild_id"]
            self.give_rewards(winner.id, guild_id, self.sambung_kata_winner_reward)
            await game["channel"].send(f"🏆 Pemenangnya adalah {winner.mention}! Kamu mendapatkan hadiah!")
        else:
            await game["channel"].send("Permainan berakhir tanpa pemenang.")
        self.active_sambung_games.pop(vc_id, None)
    
    # --- HELPER FUNCTION FOR TIMER ---
    async def wait_for_answer_with_timer(self, ctx, correct_answer, question_msg, time_limit):
        """A helper that runs a countdown timer and waits for a correct message."""
        
        async def timer_task():
            """Updates the message embed with a countdown."""
            for i in range(time_limit, -1, -1):
                new_embed = question_msg.embeds[0].copy()
                new_embed.set_footer(text=f"Waktu tersisa: {i} detik ⏳")
                try:
                    await question_msg.edit(embed=new_embed)
                except discord.NotFound: # Message was deleted
                    break
                await asyncio.sleep(1)

        def check(m):
            return m.channel == ctx.channel and not m.author.bot and m.content.lower() == correct_answer.lower()

        # Create and run tasks concurrently
        wait_for_msg_task = self.bot.loop.create_task(self.bot.wait_for('message', check=check))
        timer = self.bot.loop.create_task(timer_task())

        done, pending = await asyncio.wait([wait_for_msg_task, timer], return_when=asyncio.FIRST_COMPLETED)

        # Cleanup: cancel the task that didn't finish
        timer.cancel()
        for task in pending:
            task.cancel()

        if wait_for_msg_task in done:
            return wait_for_msg_task.result().author # Return the winner
        else:
            return None # Return None on timeout

async def setup(bot):
    await bot.add_cog(GameLanjutan(bot))
