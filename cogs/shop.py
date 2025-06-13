import discord
from discord.ext import commands
import json
import os
from datetime import datetime, timedelta

SHOP_FILE = 'data/shop_items.json'
LEVEL_FILE = 'data/level_data.json'
BANK_FILE = 'data/bank_data.json'
SHOP_STATUS_FILE = 'data/shop_status.json'


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)


def load_shop_status():
    if not os.path.exists(SHOP_STATUS_FILE):
        return {"is_open": True}
    return load_json(SHOP_STATUS_FILE)


def save_shop_status(status: dict):
    save_json(SHOP_STATUS_FILE, status)


class PurchaseDropdown(discord.ui.Select):
    def __init__(self, category, items, user_id, guild_id):
        self.category = category
        self.items = items
        self.user_id = str(user_id)
        self.guild_id = str(guild_id)
        options = []
        for item in items:
            label = f"{item.get('emoji', '')} {item['name']} — 💰{item['price']}"
            options.append(discord.SelectOption(
                label=label[:100],
                value=item['name'],
                description=item.get('description', '')[:100]
            ))
        super().__init__(placeholder=f"Pilih item dari {category.title()}", options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_item_name = self.values[0]
        item = next((i for i in self.items if i['name'] == selected_item_name), None)
        if not item:
            await interaction.response.send_message("Item tidak ditemukan.", ephemeral=True)
            return

        level_data = load_json(LEVEL_FILE)
        bank_data = load_json(BANK_FILE)
        user_data = level_data.setdefault(self.guild_id, {}).setdefault(self.user_id, {})
        bank_user = bank_data.setdefault(self.user_id, {"balance": 0, "debt": 0})

        if self.category == "badges" and item['emoji'] in user_data.get("badges", []):
            await interaction.response.send_message("Kamu sudah memiliki badge ini.", ephemeral=True)
            return
        elif self.category == "roles" and item['name'] in user_data.get("purchased_roles", []):
            await interaction.response.send_message("Kamu sudah memiliki role ini.", ephemeral=True)
            return
        elif self.category == "exp":
            last_purchase_str = user_data.get("last_exp_purchase")
            if last_purchase_str:
                try:
                    last_purchase = datetime.fromisoformat(last_purchase_str)
                    if datetime.utcnow() - last_purchase < timedelta(days=1):
                        await interaction.response.send_message("EXP hanya bisa dibeli 1x setiap 24 jam.", ephemeral=True)
                        return
                except Exception:
                    pass

        if bank_user['balance'] < item['price']:
            await interaction.response.send_message("Saldo RSWN kamu tidak cukup!", ephemeral=True)
            return

        # Proses pembelian
        bank_user['balance'] -= item['price']
        if self.category == "badges":
            user_data.setdefault("badges", []).append(item['emoji'])
        elif self.category == "roles":
            user_data.setdefault("purchased_roles", []).append(item['name'])
            role_id = item.get("role_id")
            if role_id:
                role = interaction.guild.get_role(int(role_id))
                if role:
                    await interaction.user.add_roles(role, reason="Pembelian dari shop")
        elif self.category == "exp":
            user_data["booster"] = {
                "exp_multiplier": 2,
                "voice_multiplier": 2,
                "expires_at": (datetime.utcnow() + timedelta(minutes=30)).isoformat()
            }
            user_data["last_exp_purchase"] = datetime.utcnow().isoformat()

        save_json(LEVEL_FILE, level_data)
        save_json(BANK_FILE, bank_data)
        await interaction.response.send_message(f"✅ Kamu telah membeli `{item['name']}` seharga {item['price']} RSWN!", ephemeral=True)


class ShopCategoryView(discord.ui.View):
    def __init__(self, bot, shop_data, user_id, guild_id):
        super().__init__(timeout=120)
        self.bot = bot
        self.shop_data = shop_data
        self.user_id = user_id
        self.guild_id = guild_id
        self.add_item(ShopCategorySelect(shop_data, user_id, guild_id))


class ShopCategorySelect(discord.ui.Select):
    def __init__(self, shop_data, user_id, guild_id):
        self.shop_data = shop_data
        self.user_id = user_id
        self.guild_id = guild_id
        options = [
            discord.SelectOption(label="🎖️ Badges", value="badges", description="Lencana keren buat profilmu!"),
            discord.SelectOption(label="⚡ EXP", value="exp", description="Tambah EXP buat naik level!"),
            discord.SelectOption(label="🧷 Roles", value="roles", description="Dapatkan role spesial di server!"),
        ]
        super().__init__(placeholder="Pilih kategori item", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        items = self.shop_data.get(category, [])
        embed = discord.Embed(
            title=f"🛍️ {category.title()} Shop",
            description=f"Pilih item dari kategori **{category}** untuk dibeli.",
            color=discord.Color.orange()
        )
        if not items:
            embed.description = "Tidak ada item dalam kategori ini."
        else:
            for item in items:
                embed.add_field(
                    name=f"{item.get('emoji', '')} {item['name']} — 💰{item['price']}",
                    value=item.get('description', '*Tidak ada deskripsi*'),
                    inline=False
                )

        view = discord.ui.View(timeout=60)
        view.add_item(PurchaseDropdown(category, items, self.user_id, self.guild_id))
        view.add_item(BackToCategoryButton(self.shop_data, self.user_id, self.guild_id))
        await interaction.response.edit_message(embed=embed, view=view)


class BackToCategoryButton(discord.ui.Button):
    def __init__(self, shop_data, user_id, guild_id):
        super().__init__(label="⬅️ Kembali", style=discord.ButtonStyle.secondary)
        self.shop_data = shop_data
        self.user_id = user_id
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛒 reSwan Shop",
            description="Pilih kategori di bawah untuk melihat item yang tersedia.",
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Gunakan dropdown untuk melihat item.")
        view = ShopCategoryView(interaction.client, self.shop_data, self.user_id, self.guild_id)
        await interaction.response.edit_message(embed=embed, view=view)


class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="shop")
    async def shop(self, ctx):
        """Menampilkan toko dengan UI interaktif."""
        status = load_shop_status()
        if not status.get("is_open", True):
            return await ctx.send("⚠️ Toko sedang *ditutup* oleh admin. Silakan kembali lagi nanti.")

        shop_data = load_json(SHOP_FILE)
        embed = discord.Embed(
            title="🛒 reSwan Shop",
            description="Pilih kategori di bawah untuk melihat item yang tersedia.",
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Gunakan dropdown untuk melihat item.")

        view = ShopCategoryView(self.bot, shop_data, ctx.author.id, ctx.guild.id)

        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

        await ctx.send(embed=embed, view=view)

    @commands.command(name="toggleshop")
    @commands.has_permissions(administrator=True)
    async def toggle_shop(self, ctx):
        """Menutup atau membuka toko (Admin Only)."""
        status = load_shop_status()
        status["is_open"] = not status.get("is_open", True)
        save_shop_status(status)

        state = "🟢 TERBUKA" if status["is_open"] else "🔴 TERTUTUP"
        await ctx.send(f"Toko sekarang telah diatur ke: **{state}**")


async def setup(bot):
    await bot.add_cog(Shop(bot))
