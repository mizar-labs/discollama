import io
import os
import json
import asyncio
import argparse
from datetime import datetime, timedelta
import ollama
import discord
import requests
from logging import getLogger


# piggy back on the logger discord.py set up
logging = getLogger('discord.discollama')
# Set APP_ENV to 'prod' to run in production mode, this should be automatically set by Dapr
APP_ENV = os.getenv('APP_ENV', 'dev')
# Set DEBUG to 'true' to enable debug logging, this should be automatically set by Dapr
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true' or APP_ENV == 'dev'
if DEBUG:
  logging.info("APP_ENV: %s", APP_ENV)
# Set APP_ID to the application ID, this should be automatically set by Dapr
APP_ID = os.getenv('APP_ID', 'dev-discollama')
if DEBUG:
  logging.info("APP_ID: %s", APP_ID)
# Set DEBUG to 'true' to enable debug logging, this should be automatically set by 1password
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true' or APP_ENV == 'dev'
# Set DAPR_STATE_STORE to the state store name, this should be automatically set by Dapr
DAPR_STATE_STORE = f'{APP_ID}'
if DEBUG:
  logging.info("DAPR_STATE_STORE: %s", DAPR_STATE_STORE)
#Set BASE_URL to the base URL of the Dapr sidecar
BASE_URL = os.getenv('BASE_URL', 'http://localhost') + ':' + os.getenv(
                    'DAPR_HTTP_PORT', '3500')
if DEBUG:
  logging.info("BASE_URL: %s", BASE_URL)
# Set STATE_STORE_URL to the state store URL
STATE_STORE_URL = f"{BASE_URL}/v1.0/state/{DAPR_STATE_STORE}"
if DEBUG:
  logging.info("STATE_STORE_URL: %s", STATE_STORE_URL)

class Response:
  def __init__(self, message):
    self.message = message
    self.channel = message.channel

    self.r = None
    self.sb = io.StringIO()

  async def write(self, s, end=''):
    if self.sb.seek(0, io.SEEK_END) + len(s) + len(end) > 2000:
      self.r = None
      self.sb.seek(0, io.SEEK_SET)
      self.sb.truncate()

    self.sb.write(s)

    value = self.sb.getvalue().strip()
    if not value:
      return

    if self.r:
      await self.r.edit(content=value + end)
      return

    if self.channel.type == discord.ChannelType.text:
      self.channel = await self.channel.create_thread(name='Discollama Says', message=self.message, auto_archive_duration=60)

    self.r = await self.channel.send(value)

class Discollama:
  def __init__(self, ollama, discord, model):
    self.ollama = ollama
    self.discord = discord
    self.model = model

    # register event handlers
    self.discord.event(self.on_ready)
    self.discord.event(self.on_message)
  #set the status of the bot
  async def on_ready(self):
    activity = discord.Activity(name='Discollama', state='Ask me anything!', type=discord.ActivityType.custom)
    await self.discord.change_presence(activity=activity)

    logging.info(
      'Ready! Invite URL: %s',
      discord.utils.oauth_url(
        self.discord.application_id,
        permissions=discord.Permissions(
          read_messages=True,
          send_messages=True,
          create_public_threads=True,
        ),
        scopes=['bot'],
      ),
    )

  async def on_message(self, message):
    print(message)
    if self.discord.user == message.author:
      # don't respond to ourselves
      return

    if not self.discord.user.mentioned_in(message):
      # don't respond to messages that don't mention us
      return

    content = message.content.replace(f'<@{self.discord.user.id}>', '').strip()
    if not content:
      content = 'Hi!'

    channel = message.channel

    context = []
    if reference := message.reference:
      context = await self.load(message_id=reference.message_id)
      if not context:
        reference_message = await message.channel.fetch_message(reference.message_id)
        content = '\n'.join(
          [
            content,
            'Use this to answer the question if it is relevant, otherwise ignore it:',
            reference_message.content,
          ]
        )

    if not context:
      context = await self.load(channel_id=channel.id)

    r = Response(message)
    task = asyncio.create_task(self.thinking(message))
    async for part in self.generate(content, context):
      task.cancel()

      await r.write(part['response'], end='...')

    await r.write('')
    await self.save(r.channel.id, message.id, part['context'])

  async def thinking(self, message, timeout=999):
    try:
      await message.add_reaction('🤔')
      async with message.channel.typing():
        await asyncio.sleep(timeout)
    except Exception:
      pass
    finally:
      await message.remove_reaction('🤔', self.discord.user)
  # Generate response from the model
  async def generate(self, content, context):
    sb = io.StringIO()

    t = datetime.now()
    async for part in await self.ollama.generate(model=self.model, prompt=content, context=context, keep_alive=-1, stream=True):
      sb.write(part['response'])

      if part['done'] or datetime.now() - t > timedelta(seconds=1):
        part['response'] = sb.getvalue()
        yield part
        t = datetime.now()
        sb.seek(0, io.SEEK_SET)
        sb.truncate()

  async def save(self, channel_id, message_id, ctx: list[int]):
   if DEBUG:
     logging.info("Saving state for channel %s and message %s", channel_id, message_id)
   # Template for saving state for a channel and message
   channel_state = [{
      "key": f"discollama:channel:{channel_id}",
      "value": json.dumps(message_id)
   }]
   if DEBUG:
     logging.info("channel_state: %s", channel_state)
   message_state = [{
     "key": f"discollama:message:{message_id}",
     "value": json.dumps(ctx)
   }]
   if DEBUG:
     logging.info("message_state: %s", message_state)
   # Save the state for the channel and message
   save_channel_state = requests.post(
        url=STATE_STORE_URL,
        json=channel_state,
   )
   if DEBUG:
     logging.info("Channel state saved: %s", save_channel_state.status_code)
   save_message_state = requests.post(
        url=STATE_STORE_URL,
        json=message_state,
    )
   if DEBUG:
     logging.info("Message state saved: %s", save_message_state.status_code)
  # Load the state for the channel and message
  async def load(self, channel_id=None, message_id=None) -> list[int]:
    if channel_id:
      if DEBUG:
        logging.info("Channel ID:  %s ", channel_id)
        logging.info("Attempting to load state for channel %s", channel_id)
      message_id_response = requests.get(
        url=STATE_STORE_URL + "/" + f"discollama:channel:{channel_id}" + "?metadata.contentType=application/json"
      )
      if DEBUG:
        logging.info("Response: %s", message_id_response.text)
      message_id = message_id_response.json()
      if DEBUG:
        logging.info("Response: %s", message_id_response.status_code)
    if DEBUG:
      logging.info("Attempting to load state for message %s", message_id_response.text)
    ctx_response = requests.get(
      url=STATE_STORE_URL + "/" + f"discollama:message:{message_id}" + "?metadata.contentType=application/json"
    )
    if DEBUG:
      logging.info("Response: %s", ctx_response.status_code)
    ctx = ctx_response.json()
    if DEBUG:
      logging.info("Context: %s", ctx)
    return json.loads(ctx) if ctx else []


  # Run the bot
  def run(self, token):
    self.discord.run(token)

# Main function
def main():
  # Parse command line arguments
  parser = argparse.ArgumentParser()
  parser.add_argument('--ollama-model', default=os.getenv('OLLAMA_MODEL', 'llama2'), type=str)
  parser.add_argument('--buffer-size', default=32, type=int)
  args = parser.parse_args()
  # Set up the discord intents
  intents = discord.Intents.default()
  intents.message_content = True
  # Initialize the bot
  Discollama(
    ollama.AsyncClient(),
    discord.Client(intents=intents),
    model=args.ollama_model,
  ).run(os.environ['DISCORD_TOKEN'])

# Run the main function
if __name__ == '__main__':
  main()
