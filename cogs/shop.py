import discord
from discord.ext import commands
import json
import os
import io
from datetime import datetime, timedelta
import aiohttp

SHOP_FILE = 'data/shop_items.json'
LEVEL_FILE = 'data/level_data.json'
BANK_FILE = 'data/bank_data.json'
SHOP_STATUS_FILE = 'data/shop_status.json'
COLLAGE_FILE = 'data/shop_collage.json'
INVENTORY_FILE = 'data/inventory.json'


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
            label = f"{item.get('name')} — 💰{item['price']}"
            if item.get('stock', 'unlimited') != 'unlimited':
                label += f" | Stock: {item['stock']}"
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

        if item.get("stock", "unlimited") != "unlimited" and item["stock"] <= 0:
            await interaction.response.send_message("Stock item ini sudah habis!", ephemeral=True)
            return

        level_data = load_json(LEVEL_FILE)
        bank_data = load_json(BANK_FILE)
        inventory_data = load_json(INVENTORY_FILE)

        user_data = level_data.setdefault(self.guild_id, {}).setdefault(self.user_id, {})
        bank_user = bank_data.setdefault(self.user_id, {"balance": 0, "debt": 0})
        inventory_user = inventory_data.setdefault(self.user_id, [])

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

        bank_user['balance'] -= item['price']

        if self.category == "badges":
            user_data.setdefault("badges", []).append(item['emoji'])
            if item.get("image_url"):
                user_data["image_url"] = item["image_url"]
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(item["image_url"]) as resp:
                            if resp.status == 200:
                                avatar_bytes = await resp.read()
                                file = discord.File(fp=io.BytesIO(avatar_bytes), filename="avatar.png")

                                await interaction.user.send(
                                    content="Selamat pembelian avatar kamu berhasil, jika kamu mau pasang sebagai profil Discord nih aku kasih file nya ya",
                                    file=file
                                )
                except Exception as e:
                    print(f"Gagal kirim DM avatar: {e}")

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

        inventory_user.append(item)

        if item.get("stock", "unlimited") != "unlimited":
            item["stock"] -= 1

        save_json(LEVEL_FILE, level_data)
        save_json(BANK_FILE, bank_data)
        save_json(INVENTORY_FILE, inventory_data)

        shop_data = load_json(SHOP_FILE)
        for cat in shop_data:
            for i in shop_data[cat]:
                if i['name'] == item['name']:
                    i.update(item)
        save_json(SHOP_FILE, shop_data)

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
            title=f"🛒 {category.title()} Shop",
            description=f"Pilih item dari kategori **{category}** untuk dibeli.",
            color=discord.Color.orange()
        )
        if not items:
            embed.description = "Tidak ada item dalam kategori ini."
        else:
            for item in items:
                stock_str = "∞" if item.get("stock", "unlimited") == "unlimited" else str(item["stock"])
                name = item['name']
                price = item['price']
                desc = item.get('description', '*Tidak ada deskripsi*')
                field_name = f"{name} — 💰{price} | Stok: {stock_str}"
                embed.add_field(name=field_name, value=desc, inline=False)

        if category == "badges":
            if os.path.exists(COLLAGE_FILE):
                collage_data = load_json(COLLAGE_FILE)
                collage_url = collage_data.get("collage_url")
                if collage_url:
                    embed.set_image(url=collage_url)

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
            title="💼 reSwan Shop",
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
        status = load_shop_status()
        if not status.get("is_open", True):
            return await ctx.send("⚠️ Toko sedang *ditutup* oleh admin. Silakan kembali lagi nanti.")

        shop_data = load_json(SHOP_FILE)
        embed = discord.Embed(
            title="💼 reSwan Shop",
            description="Pilih kategori di bawah untuk melihat item yang tersedia.",
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Gunakan dropdown untuk melihat item.")

        view = ShopCategoryView(self.bot, shop_data, ctx.author.id, ctx.guild.id)

        try:
            await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

        await ctx.send(embed=embed, view=view)

    @commands.command(name="toggleshop")
    @commands.has_permissions(administrator=True)
    async def toggle_shop(self, ctx):
        status = load_shop_status()
        status["is_open"] = not status.get("is_open", True)
        save_shop_status(status)

        state = "🟢 TERBUKA" if status["is_open"] else "🔴 TERTUTUP"
        await ctx.send(f"Toko sekarang telah diatur ke: **{state}**")

    @commands.command(name="additem")
    @commands.has_permissions(administrator=True)
    async def add_item(self, ctx, category: str, name: str, price: int, description: str, *args):
        shop_data = load_json(SHOP_FILE)

        if category not in shop_data:
            await ctx.send("⚠️ Kategori tidak valid. Gunakan 'badges', 'exp', atau 'roles'.")
            return

        emoji_or_url = args[0] if len(args) > 0 else ""
        stock = args[1] if len(args) > 1 else "unlimited"
        optional = args[2] if len(args) > 2 else None

        item = {
            "name": name,
            "price": price,
            "description": description,
            "emoji": emoji_or_url,
            "stock": int(stock) if stock != "unlimited" else "unlimited"
        }

        if category == "roles":
            if optional is None:
                return await ctx.send("⚠️ Harap masukkan role_id untuk kategori roles.")
            item["role_id"] = int(optional)

        if category == "badges" and optional:
            item["image_url"] = optional

        shop_data[category].append(item)
        save_json(SHOP_FILE, shop_data)
        await ctx.send(f"✅ Item baru ditambahkan ke kategori **{category}**: **{name}** seharga **{price}** RSWN! 🎉")

    @commands.command(name="addcollage")
    @commands.has_permissions(administrator=True)
    async def add_collage(self, ctx, url: str):
        save_json(COLLAGE_FILE, {"collage_url": url})
        await ctx.send("✅ Gambar kolase berhasil diperbarui!")


async def setup(bot):
    await bot.add_cog(Shop(bot))
