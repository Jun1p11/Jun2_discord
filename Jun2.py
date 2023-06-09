import discord
import datetime
from discord.ext import commands
import csv
import youtube_dl
import ffmpeg
import asyncio
import requests
from bs4 import BeautifulSoup
import openai
openai.api_key = 'EDapqTGbXBdMnqRBBG7RT3BlbkFJrEESI3OlrVhh1C9slINa'

intents = discord.Intents.default()
intents.members = True
intents.message_content = True  
bot = commands.Bot(command_prefix='?', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

@bot.command()
async def join(ctx, student_id: int, student_name: str):
    # Load student information from CSV file
    with open('student_info.csv', 'r') as file:
        reader = csv.reader(file)
        for row in reader:
            if int(row[0]) == student_id and row[1] == student_name:
                guild = ctx.guild
                member_role = discord.utils.get(guild.roles, name='Member')
                await ctx.author.add_roles(member_role)
                await ctx.send(f'{ctx.author.mention} has been added as a club member!')
                return

    await ctx.send('Invalid student ID or name. Please try again.')

async def set_birthday(ctx, month: int, day: int):
    # Get user's ID and name
    user_id = ctx.author.id
    user_name = ctx.author.name

    # Save birthday to CSV file
    with open('birthdays.csv', 'a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([user_id, user_name, month, day])

    await ctx.send('Your birthday has been saved!')

@bot.command()
async def check_birthdays(ctx):
    # Load birthdays from CSV file
    with open('birthdays.csv', 'r') as file:
        reader = csv.reader(file)
        today = datetime.date.today()
        for row in reader:
            member_id = int(row[0])
            member_name = row[1]
            birth_month = int(row[2])
            birth_day = int(row[3])

            if birth_month == today.month and birth_day == today.day:
                guild = ctx.guild
                member = guild.get_member(member_id)
                if member:
                    new_name = f'Birthday {member_name}'
                    await member.edit(nick=new_name)
                    await ctx.send(f'{member.mention} Happy Birthday!')
                else:
                    await ctx.send('Could not find member with matching ID.')

@bot.command()
async def check_roster(ctx):
    # Load roster from CSV file
    with open('roster.csv', 'r') as file:
        reader = csv.reader(file)
        guild = ctx.guild

        # Iterate through each row in the roster
        for row in reader:
            member_id = int(row[0])
            member_name = row[1]
            role = row[2]

            # Get the member from the guild
            member = guild.get_member(member_id)

            if member:
                # Check the role of the member in the roster
                if role == 'Management':
                    # Change role to management team
                    management_role = discord.utils.get(guild.roles, name='Management Team')
                    await member.edit(roles=[management_role])
                elif role == 'Soldier':
                    # Change role to duty-in-service role
                    duty_role = discord.utils.get(guild.roles, name='Duty-in-Service')
                    await member.edit(roles=[duty_role])
                elif role == 'Withdrawn':
                    # Expel member from the server
                    await member.kick(reason='Withdrawn from roster')

@bot.command()
async def create_voice_room(ctx, room_name: str):
    guild = ctx.guild
    existing_channel = discord.utils.get(guild.voice_channels, name=room_name)

    if existing_channel:
        await ctx.send('A voice channel with that name already exists.')
        return

    # Create the voice channel
    await guild.create_voice_channel(room_name)
    await ctx.send(f'Voice channel "{room_name}" has been created.')

@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel is not None and len(before.channel.members) == 0:
        # Delete the voice channel if it becomes empty
        await before.channel.delete()

class MusicPlayer:
    def __init__(self):
        self.queue = []
        self.repeat = False
        self.max_queue_size = 50
    def play_next(self, ctx):
        if self.repeat:
            voice_client = ctx.voice_client
            source = discord.FFmpegPCMAudio(self.queue[0]['url'])
            voice_client.play(source, after=lambda e: self.play_next(ctx))
            voice_client.source = discord.PCMVolumeTransformer(source)
            voice_client.source.volume = 0.5
            return

        if len(self.queue) == 0:
            asyncio.run_coroutine_threadsafe(ctx.send('Queue is empty.'), bot.loop)
            return

        voice_client = ctx.voice_client
        if voice_client.is_playing():
            voice_client.stop()

        url = self.queue[0]['url']
        source = discord.FFmpegPCMAudio(url)
        voice_client.play(source, after=lambda e: self.play_next(ctx))
        voice_client.source = discord.PCMVolumeTransformer(source)
        voice_client.source.volume = 0.5

        asyncio.run_coroutine_threadsafe(ctx.send(f'Now playing: {self.queue[0]["title"]}'), bot.loop)
        del self.queue[0]
    def add_to_queue(self, url, title):
        if len(self.queue) >= self.max_queue_size:
            return False

        self.queue.append({'url': url, 'title': title})
        return True
    def set_repeat_mode(self, mode):
        self.repeat_mode = mode

music_player = MusicPlayer()

@bot.command()
async def play(ctx, *, song_title: str):
    voice_channel = ctx.author.voice.channel
    if not voice_channel:
        await ctx.send('You must be in a voice channel to use this command.')
        return

    query = f'ytsearch:{song_title}'
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(query, download=False)['entries'][0]
            url = info['url']
            title = info['title']

            added = music_player.add_to_queue(url, title)
            if added:
                if not ctx.voice_client:
                    await voice_channel.connect()

                if not ctx.voice_client.is_playing():
                    music_player.play_next(ctx)
                else:
                    await ctx.send(f'{title} added to the queue.')
            else:
                await ctx.send('Queue is full. Please wait for the current songs to finish.')
        except Exception as e:
            await ctx.send('Error occurred while processing the request. Please try again later.')

@bot.command()
async def skip(ctx):
    voice_client = ctx.voice_client
    if voice_client.is_playing():
        voice_client.stop()

@bot.command()
async def queue(ctx):
    queue_str = '\n'.join([f'{index + 1}. {song["title"]}' for index, song in enumerate(music_player.queue)])
    await ctx.send(f'Queue:\n{queue_str}')

@bot.command()
async def clear(ctx):
    music_player.queue.clear()
    await ctx.send('Queue cleared.')

@bot.command()
async def repeat(ctx, mode: str = ''):
    if mode.lower() == 'one':
        music_player.set_repeat_mode("One")
        await ctx.send('Repeat mode set to "Repeat One".')
    elif mode.lower() == 'all':
        music_player.set_repeat_mode("All")
        music_player.queue_backup = music_player.queue.copy()
        await ctx.send('Repeat mode set to "Repeat All".')
    else:
        music_player.set_repeat_mode("None")
        await ctx.send('Repeat mode disabled.')

class Schedule:
    def __init__(self):
        self.schedule = {}

    def add_event(self, date, event):
        month = date.strftime("%m")
        day = date.strftime("%d")
        if month not in self.schedule:
            self.schedule[month] = {}
        self.schedule[month][day] = event

    def print_schedule(self):
        current_month = datetime.datetime.now().strftime("%m")
        if current_month not in self.schedule:
            return "No events scheduled for this month."

        schedule_str = f"Schedule for the current month:\n"
        for day, event in self.schedule[current_month].items():
            schedule_str += f"{current_month}.{day}: {event}\n"

        return schedule_str

    def save_schedule(self, user_roles):
        if "management" not in [role.name.lower() for role in user_roles]:
            return "You don't have permission to save the schedule."

        with open("schedule.txt", "w") as file:
            for month, events in self.schedule.items():
                for day, event in events.items():
                    file.write(f"{month}.{day}: {event}\n")

        return "Schedule saved successfully."

schedule = Schedule()

@bot.command()
async def add_event(ctx, date_str: str, *, event: str):
    try:
        date = datetime.datetime.strptime(date_str, "%m.%d")
    except ValueError:
        await ctx.send("Invalid date format. Please use MM.DD format.")
        return

    schedule.add_event(date, event)
    await ctx.send("Event added to the schedule.")

@bot.command()
async def print_schedule(ctx):
    await ctx.send(schedule.print_schedule())

@bot.command()
async def save_schedule(ctx):
    user_roles = ctx.author.rolesvo
    result = schedule.save_schedule(user_roles)
    await ctx.send(result)

@bot.command()
async def lolstats(ctx, summoner_name: str):
    # Construct the URL for op.gg search
    url = f"https://www.op.gg/summoner/userName={summoner_name.replace(' ', '+')}"

    # Send a GET request to op.gg and retrieve the HTML content
    response = requests.get(url)
    if response.status_code != 200:
        await ctx.send("Failed to retrieve summoner stats.")
        return

    # Parse the HTML content using BeautifulSoup
    soup = BeautifulSoup(response.content, 'html.parser')

    # Extract the required information from the parsed HTML
    try:
        rank = soup.find("div", class_="TierRank").text.strip()
        win_ratio = soup.find("span", class_="winratio").text.strip()
        total_games = soup.find("span", class_="total").text.strip()
        most_played_champ = soup.find("div", class_="ChampionName").text.strip()
        most_played_champ_win_ratio = soup.find("div", class_="ChampionWinRatio").text.strip()

        # Send the extracted information as a response
        await ctx.send(f"Summoner: {summoner_name}\nRank: {rank}\nWin Ratio: {win_ratio}\nTotal Games: {total_games}\nMost Played Champion: {most_played_champ}\nChampion Win Ratio: {most_played_champ_win_ratio}")
    except AttributeError:
        await ctx.send("Summoner not found.")

@bot.command()
@commands.has_role('management')
async def set_channel_permissions(ctx, channel_indices: commands.Greedy[int], role: discord.Role, permission: discord.Permissions):
    guild = ctx.guild
    for index in channel_indices:
        if index < len(guild.channels):
            channel = guild.channels[index]
            await channel.set_permissions(role, overwrite=permission)
            await ctx.send(f"Access rights set for channel {channel.name}.")
        else:
            await ctx.send(f"Channel index {index} is out of range.")

@bot.command()
async def ques(ctx, *, question):
    # Call the OpenAI GPT API to generate the answer
    response = openai.Completion.create(
        engine='text-davinci-003',
        prompt=question,
        max_tokens=50,
        n=1,
        stop=None,
        temperature=0.7,
        top_p=None,
        frequency_penalty=None,
        presence_penalty=None
    )

    # Extract the answer from the API response
    if 'choices' in response and len(response.choices) > 0:
        answer = response.choices[0].text.strip()
        await ctx.send(answer)
    else:
        await ctx.send('Failed to retrieve the answer. Please try again.')



bot.run('user bot token')