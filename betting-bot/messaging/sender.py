"""
Envío de mensajes a Discord usando discord.py.

NOTA: La carpeta del proyecto se llama 'messaging/' (no 'discord/')
para evitar que Python importe este paquete local en lugar de discord.py.
"""

import sys
import asyncio

# Importar discord.py con protección contra colisión de nombres
try:
    import importlib
    _discord = importlib.import_module("discord")
    Client   = _discord.Client
    Intents  = _discord.Intents
    Embed    = _discord.Embed
except ImportError:
    raise ImportError(
        "discord.py no está instalado. Ejecuta: pip install discord.py"
    )

from config.settings import DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID


class DiscordSender:
    def __init__(self):
        intents = Intents.default()
        self.client = Client(intents=intents)
        self._ready = asyncio.Event()

        @self.client.event
        async def on_ready():
            print(f"[Discord] Bot conectado como {self.client.user}")
            self._ready.set()

    async def start(self):
        asyncio.create_task(self.client.start(DISCORD_BOT_TOKEN))
        await self._ready.wait()

    async def send_message(self, content: str):
        """Envía un mensaje de texto al canal configurado (respeta límite 2000 chars)."""
        channel = await self._get_channel()
        if not channel:
            return
        if len(content) <= 2000:
            await channel.send(content)
        else:
            for chunk in self._split_message(content):
                await channel.send(chunk)
                await asyncio.sleep(0.5)

    async def send_embed(self, embed: Embed):
        """Envía un embed al canal configurado."""
        channel = await self._get_channel()
        if channel:
            await channel.send(embed=embed)

    # ─── Helpers ──────────────────────────────────────────────────────────────

    async def _get_channel(self):
        channel = self.client.get_channel(DISCORD_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.client.fetch_channel(DISCORD_CHANNEL_ID)
            except Exception as e:
                print(f"[Discord] No se pudo obtener el canal {DISCORD_CHANNEL_ID}: {e}")
                return None
        return channel

    def _split_message(self, content: str, limit: int = 1990) -> list:
        lines = content.split("\n")
        chunks = []
        current = ""
        for line in lines:
            if len(current) + len(line) + 1 > limit:
                if current:
                    chunks.append(current)
                current = line
            else:
                current += ("\n" if current else "") + line
        if current:
            chunks.append(current)
        return chunks

    async def close(self):
        await self.client.close()
