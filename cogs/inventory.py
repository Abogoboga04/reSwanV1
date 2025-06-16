import discord
from discord.ext import commands
import json
import os

LEVEL_FILE = 'data/level_data.json'
INVENTORY_FILE = 'data/inventory_data.json'


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)


class Inventory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_inventory(self, guild_id, user_id):
        inventory = load_json(INVENTORY_FILE)
        return inventory.setdefault(str(guild_id), {}).setdefault(str(user_id), [])

    def save_inventory_item(self, guild_id, user_id, item):
        inventory = load_json(INVENTORY_FILE)
        user_inv = inventory.setdefault(str(guild_id), {}).setdefault(str(user_id), [])
        if item not in user_inv:
            user_inv.append(item)
        save_json(INVENTORY_FILE, inventory)

    @commands.command(name="inventory")
    async def show_inventory(self, ctx):
        """Menampilkan inventory kamu."""
        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)
        inventory = load_json(INVENTORY_FILE)
        user_items = inventory.get(guild_id, {}).get(user_id, [])

        if not user_items:
            return await ctx.send("📦 Inventory kamu kosong.")

        embed = discord.Embed(
            title=f"🎒 Inventory {ctx.author.display_name}",
            color=discord.Color.blue()
        )

        avatars = [i for i in user_items if i.get("image_url")]
        badges = [i for i in user_items if not i.get("image_url")]

        if badges:
            badge_str = '\n'.join(f"{b['emoji']} **{b['name']}**" for b in badges)
            embed.add_field(name="🎖️ Badges", value=badge_str, inline=False)

        if avatars:
            avatar_str = '\n'.join(f"🖼️ **{a['name']}**" for a in avatars)
            embed.add_field(name="🖼️ Avatar", value=avatar_str, inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="setavatar")
    async def set_avatar(self, ctx, *, avatar_name):
        """Mengatur avatar dari inventory kamu."""
        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)
        inventory = load_json(INVENTORY_FILE)
        level_data = load_json(LEVEL_FILE)

        user_items = inventory.get(guild_id, {}).get(user_id, [])
        avatars = [i for i in user_items if i.get("image_url")]

        selected = next((a for a in avatars if a['name'].lower() == avatar_name.lower()), None)
        if not selected:
            return await ctx.send("❌ Avatar tidak ditemukan di inventory kamu.")

        level_data.setdefault(guild_id, {}).setdefault(user_id, {})["image_url"] = selected['image_url']
        save_json(LEVEL_FILE, level_data)

        await ctx.send(f"✅ Avatar kamu telah diperbarui menjadi **{selected['name']}**!")


async def setup(bot):
    await bot.add_cog(Inventory(bot))
