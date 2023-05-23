import discord
from discord.ext import commands
import openai
import json
import mysql.connector

file = open('config.json', 'r')
config = json.load(file)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=config['prefix'], intents=intents)
openai.api_key = config['token_openai']

# Установка соединения с базой данных
conn = mysql.connector.connect(
    host='host',
    user='db',
    password='russia',
    database='db'
)
cursor = conn.cursor()

# Создание таблицы, если она не существует
cursor.execute('''
    CREATE TABLE IF NOT EXISTS verify_channels (
        guild_id VARCHAR(255),
        channel_id VARCHAR(255),
        PRIMARY KEY (guild_id, channel_id)
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS conversations (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id VARCHAR(255),
        guild_id VARCHAR(255),
        channel_id VARCHAR(255),
        query TEXT,
        response TEXT
    )
''')
conn.commit()

@bot.event
async def on_ready():
    print('Bot online')

@bot.slash_command(name='addverifychannel', description='Добавляет канал в список разрешенных', hidden=True)
@commands.has_permissions(administrator=True)
async def add_verify_channel(ctx, channel: discord.TextChannel):
    guild_id = str(ctx.guild.id)
    channel_id = str(channel.id)

    cursor.execute('''
        SELECT COUNT(*) FROM verify_channels
        WHERE guild_id = %s
    ''', (guild_id,))
    count = cursor.fetchone()[0]

    if count >= 2:
        await ctx.respond("Нельзя добавить больше двух разрешенных каналов.", ephemeral=True)
        return

    cursor.execute('''
        INSERT INTO verify_channels (guild_id, channel_id)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE channel_id = %s
    ''', (guild_id, channel_id, channel_id))
    conn.commit()

    await ctx.respond(f'Канал {channel.mention} добавлен в список разрешенных.', ephemeral=True)

@add_verify_channel.error
async def add_verify_channel_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.respond("У вас недостаточно прав для использования этой команды.", ephemeral=True)

@bot.slash_command(name='removeverifychannel', description='Удаляет канал из списка разрешенных', hidden=True)
@commands.has_permissions(administrator=True)
async def remove_verify_channel(ctx, channel: discord.TextChannel):
    guild_id = str(ctx.guild.id)
    channel_id = str(channel.id)

    cursor.execute('''
        DELETE FROM verify_channels
        WHERE guild_id = %s AND channel_id = %s
    ''', (guild_id, channel_id))
    conn.commit()

    await ctx.respond(f'Канал {channel.mention} удален из списка разрешенных.', ephemeral=True)

@remove_verify_channel.error
async def remove_verify_channel_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.respond("У вас недостаточно прав для использования этой команды.", ephemeral=True)

@bot.slash_command(name='listverify', description='Показывает список разрешенных каналов', hidden=True)
async def list_verify_channels(ctx):
    guild_id = str(ctx.guild.id)

    cursor.execute('''
        SELECT channel_id FROM verify_channels
        WHERE guild_id = %s
    ''', (guild_id,))
    results = cursor.fetchall()

    if len(results) == 0:
        await ctx.respond("На этом сервере нет разрешенных каналов.", ephemeral=True)
        return

    channels = [f"<#{result[0]}>" for result in results]
    channel_list = "\n".join(channels)

    embed = discord.Embed(title="Список разрешенных каналов", color=0x3CB371)
    embed.add_field(name="Каналы", value=channel_list, inline=False)
    await ctx.respond(embed=embed, ephemeral=True)

@bot.slash_command(name="help", description="Выводит список команд")
async def help_command(ctx):
    embed = discord.Embed(title="Список команд", color=0x3CB371)
    embed.add_field(name="/gpt", value='"ваш запрос" - отправить запрос боту', inline=False)
    embed.add_field(name="/addverifychannel", value='"канал" - выбрать канал для включения бота', inline=False)
    embed.add_field(name="/removeverifychannel", value='"канал" - удалить канал, где включен бот', inline=False)
    embed.add_field(name="/listverify **[NEW]**", value='список всех разрешённых для отправки сообщений бота каналов', inline=False)
    await ctx.respond(embed=embed, ephemeral=True)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.content.startswith(config['prefix'] + 'gpt'):
        guild_id = str(message.guild.id)
        cursor.execute('''
            SELECT channel_id FROM verify_channels
            WHERE guild_id = %s
        ''', (guild_id,))
        result = cursor.fetchone()

        # Добавлен вызов cursor.fetchone() для чтения результата
        if result is not None and message.channel.id == int(result[0]):
            if message.author.guild_permissions.administrator:
                content = message.content.removeprefix(config['prefix'] + 'gpt').strip()

                response = openai.Completion.create(
                    engine="text-davinci-003",
                    prompt=f"User: {content}\nAI:",
                    temperature=0.7,
                    max_tokens=600,
                    top_p=1.0,
                    frequency_penalty=0.0,
                    presence_penalty=0.6,
                    stop=None
                )

                reply = f"{message.author.mention}, вот мой ответ:\n\n{response.choices[0]['text']}"
                embed = discord.Embed(description=reply)
                await message.channel.send(embed=embed)

                # Сохранение запроса и ответа в базу данных
                query = content.replace('"', '""')  # Защита от SQL-инъекций
                response_text = response.choices[0]['text'].replace('"', '""')  # Защита от SQL-инъекций
                cursor.execute('''
                    INSERT INTO conversations (user_id, guild_id, channel_id, query, response)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (str(message.author.id), guild_id, str(message.channel.id), query, response_text))
                conn.commit()

    await bot.process_commands(message)

bot.run(config['token'])
