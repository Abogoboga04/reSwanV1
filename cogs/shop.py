import discord
from discord.ext import commands
import json

# Load data from JSON file
def load_data():
    try:
        with open('shop_data.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.shop_items = load_data()  # Load existing shop items
        print("Shop items loaded:", self.shop_items)  # Debugging: check loaded items

    @commands.command()
    async def shop(self, ctx):
        """Command to open the shop with categories."""
        buttons = [
            discord.ui.Button(label="Badges", style=discord.ButtonStyle.primary, custom_id="badges"),
            discord.ui.Button(label="Roles", style=discord.ButtonStyle.primary, custom_id="roles"),
            discord.ui.Button(label="Extra EXP", style=discord.ButtonStyle.primary, custom_id="extra_exp")
        ]

        view = discord.ui.View()
        for button in buttons:
            view.add_item(button)

        await ctx.send("Choose a category:", view=view)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        # Ensure the interaction is from a button click
        if interaction.data['custom_id'] in ['badges', 'roles', 'extra_exp']:
            await self.show_items(interaction, interaction.data['custom_id'])
        elif interaction.data['custom_id'] == "back":
            await self.shop(interaction)
        elif interaction.data['custom_id'] in self.shop_items:
            await self.handle_purchase(interaction)

    async def show_items(self, interaction, item_type):
        """Show items based on the selected type."""
        # Convert the item type to lowercase for consistency
        item_type = item_type.lower()

        items = {k: v for k, v in self.shop_items.items() if v.get('type') == item_type}

        # Check if items were found
        if not items:
            await interaction.response.send_message("No items found in this category.", ephemeral=True)
            return

        # Create buttons for each item
        buttons = [
            discord.ui.Button(label=f"{v['name']} - {v['price']}", style=discord.ButtonStyle.secondary, custom_id=k) 
            for k, v in items.items()
        ]

        view = discord.ui.View()
        for button in buttons:
            view.add_item(button)

        # Add back button to return to category selection
        back_button = discord.ui.Button(label="Back to Categories", style=discord.ButtonStyle.secondary, custom_id="back")
        view.add_item(back_button)

        # Respond to the interaction with the list of items
        await interaction.response.send_message(f"**{item_type.capitalize()}**:\n" + "\n".join([f"{v['name']} - {v['price']}" for v in items.values()]), view=view)

    async def handle_purchase(self, interaction):
        """Handle the purchase of an item."""
        item_id = interaction.data['custom_id']
        item = self.shop_items[item_id]
        user_balance = await self.get_user_balance(interaction.user.id)  # Get user's balance

        if user_balance < item['price']:
            await interaction.response.send_message("You do not have enough RSWN to purchase this item!", ephemeral=True)
            return

        # Deduct price from user's balance
        await self.update_user_balance(interaction.user.id, -item['price'])  # Update user's balance

        # Give role if applicable
        if item['type'] == 'role' and item['role_id']:
            role = interaction.guild.get_role(item['role_id'])
            if role:
                await interaction.user.add_roles(role)

        # Send DM to user about transaction
        dm_channel = await interaction.user.create_dm()
        await dm_channel.send(f"Transaction successful! You bought: {item['name']} - {item['description']}")

        # Give extra experience if applicable
        if item['type'] == 'exp':
            await self.give_experience(interaction.user.id, item['exp'])  # Give user experience

        await interaction.response.send_message(f"You purchased: {item['name']} for {item['price']}!", ephemeral=True)

    async def get_user_balance(self, user_id):
        # Logic to retrieve user's balance
        return 1000  # Example balance

    async def update_user_balance(self, user_id, amount):
        # Logic to update user's balance
        pass

    async def give_experience(self, user_id, exp):
        # Logic to give the user experience points
        pass

async def setup(bot):
    await bot.add_cog(Shop(bot))