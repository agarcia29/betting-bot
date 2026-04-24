"""
Bot de Apuestas Deportivas — Modo servidor (Render / VPS).
Se mantiene escuchando comandos de Discord y corre el analisis cuando se lo pides.

Comandos:
  !analizar nba
  !analizar futbol        (te pregunta la liga)
  !analizar la_liga
  !analizar premier
  !analizar bundesliga
  !analizar serie_a
  !analizar ligue_1
  !analizar todas
"""

import asyncio
import importlib
import sys

_discord = importlib.import_module("discord")
commands = importlib.import_module("discord.ext.commands")

from config.settings import DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID, LEAGUES

FOOTBALL_ALIASES = {
    "la_liga":    "la_liga",
    "laliga":     "la_liga",
    "premier":    "premier_league",
    "premier_league": "premier_league",
    "bundesliga": "bundesliga",
    "serie_a":    "serie_a",
    "seriea":     "serie_a",
    "ligue_1":    "ligue_1",
    "ligue1":     "ligue_1",
    "todas":      "todas",
}

FOOTBALL_MENU = (
    "Escribe el numero de la liga:\n"
    "`1` Premier League\n"
    "`2` La Liga\n"
    "`3` Bundesliga\n"
    "`4` Serie A\n"
    "`5` Ligue 1\n"
    "`6` Todas las ligas"
)

MENU_MAP = {
    "1": "premier_league",
    "2": "la_liga",
    "3": "bundesliga",
    "4": "serie_a",
    "5": "ligue_1",
    "6": "todas",
}

# Sesiones activas: evita que dos analisis corran al mismo tiempo
_running = False

intents = _discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


@bot.event
async def on_ready():
    print(f"[Bot] Conectado como {bot.user} — esperando comandos...")


@bot.command(name="analizar")
async def analizar(ctx, liga_arg: str = None):
    global _running

    # Solo responder en el canal configurado
    if ctx.channel.id != DISCORD_CHANNEL_ID:
        return

    if _running:
        await ctx.send("⚠️ Ya hay un analisis en curso. Espera a que termine.")
        return

    # Determinar deporte y ligas seleccionadas
    selected_leagues = None

    if liga_arg is None:
        await ctx.send(
            "**Selecciona deporte:**\n"
            "`!analizar nba` — NBA\n"
            "`!analizar futbol` — Futbol (te pregunta la liga)\n"
            "`!analizar todas` — Todas las ligas de futbol"
        )
        return

    arg = liga_arg.lower().strip()

    # NBA
    if arg == "nba":
        selected_leagues = {k: v for k, v in LEAGUES.items() if v["sport"] == "basketball"}

    # Futbol sin liga especifica → preguntar
    elif arg == "futbol":
        await ctx.send(FOOTBALL_MENU)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content in MENU_MAP

        try:
            reply = await bot.wait_for("message", timeout=30.0, check=check)
            arg = MENU_MAP[reply.content]
        except asyncio.TimeoutError:
            await ctx.send("⏱ Tiempo agotado. Vuelve a escribir `!analizar futbol`.")
            return

    # Liga especifica o "todas"
    if arg == "todas":
        selected_leagues = {k: v for k, v in LEAGUES.items() if v["sport"] == "football"}
    elif arg in FOOTBALL_ALIASES:
        key = FOOTBALL_ALIASES[arg]
        if key == "todas":
            selected_leagues = {k: v for k, v in LEAGUES.items() if v["sport"] == "football"}
        else:
            selected_leagues = {key: LEAGUES[key]}

    if selected_leagues is None:
        await ctx.send(
            "Liga no reconocida. Opciones validas:\n"
            "`nba`, `futbol`, `todas`, `premier`, `la_liga`, `bundesliga`, `serie_a`, `ligue_1`"
        )
        return

    # Correr el analisis
    _running = True
    try:
        from orchestrator import BettingBotOrchestrator
        orquestador = BettingBotOrchestrator(selected_leagues=selected_leagues)
        # El orquestador usa el cliente del bot directamente
        orquestador.discord_client = bot
        orquestador.discord_channel_id = DISCORD_CHANNEL_ID
        await orquestador.run_from_discord()
    except Exception as e:
        await ctx.send(f"❌ Error durante el analisis: `{e}`")
        print(f"[Bot] Error: {e}")
    finally:
        _running = False


@bot.command(name="ayuda")
async def ayuda(ctx):
    if ctx.channel.id != DISCORD_CHANNEL_ID:
        return
    await ctx.send(
        "**Comandos disponibles:**\n"
        "`!analizar nba` — Analiza partidos de NBA en la proxima hora\n"
        "`!analizar futbol` — Selecciona liga de futbol\n"
        "`!analizar premier` — Premier League\n"
        "`!analizar la_liga` — La Liga\n"
        "`!analizar bundesliga` — Bundesliga\n"
        "`!analizar serie_a` — Serie A\n"
        "`!analizar ligue_1` — Ligue 1\n"
        "`!analizar todas` — Las 5 ligas europeas\n"
        "`!ayuda` — Muestra este mensaje"
    )


if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)