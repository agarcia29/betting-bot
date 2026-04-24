"""
Bot de Apuestas Deportivas — Modo Web Service (Render free tier).
Corre FastAPI + Bot de Discord en paralelo.
"""

import asyncio
import importlib
import threading
import uvicorn
from fastapi import FastAPI

_discord = importlib.import_module("discord")
commands = importlib.import_module("discord.ext.commands")

from config.settings import DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID, LEAGUES

# ── FastAPI (mantiene vivo el servicio en Render) ─────────────────────────────
app = FastAPI()

@app.get("/")
def health():
    return {"status": "ok", "bot": "betting-bot activo"}

@app.get("/health")
def ping():
    return {"status": "ok"}

# ── Discord Bot ───────────────────────────────────────────────────────────────
FOOTBALL_ALIASES = {
    "la_liga":        "la_liga",
    "laliga":         "la_liga",
    "premier":        "premier_league",
    "premier_league": "premier_league",
    "bundesliga":     "bundesliga",
    "serie_a":        "serie_a",
    "seriea":         "serie_a",
    "ligue_1":        "ligue_1",
    "ligue1":         "ligue_1",
    "todas":          "todas",
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

_running = False

intents = _discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None, case_insensitive=True)

@bot.event
async def on_connect():
    await bot.tree.sync()


@bot.event
async def on_ready():
    print(f"[Bot] Conectado como {bot.user} — esperando comandos...")


@bot.command(name="analizar")
async def analizar(ctx, liga_arg: str = None):
    global _running

    if ctx.channel.id != DISCORD_CHANNEL_ID:
        return

    if _running:
        await ctx.send("Ya hay un analisis en curso. Espera a que termine.")
        return

    selected_leagues = None
    arg = liga_arg.lower().strip() if liga_arg else None

    if arg is None:
        await ctx.send(
            "**Uso:**\n"
            "`!analizar nba`\n"
            "`!analizar futbol` — te pregunta la liga\n"
            "`!analizar todas` — las 5 ligas europeas\n"
            "`!ayuda` — ver todos los comandos"
        )
        return

    if arg == "nba":
        selected_leagues = {k: v for k, v in LEAGUES.items() if v["sport"] == "basketball"}

    elif arg == "futbol":
        await ctx.send(FOOTBALL_MENU)

        def check(m):
            return (
                m.author == ctx.author
                and m.channel == ctx.channel
                and m.content in MENU_MAP
            )

        try:
            reply = await bot.wait_for("message", timeout=30.0, check=check)
            arg = MENU_MAP[reply.content]
        except asyncio.TimeoutError:
            await ctx.send("Tiempo agotado. Escribe `!analizar futbol` para intentar de nuevo.")
            return

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
            "Liga no reconocida. Opciones: `nba`, `futbol`, `todas`, "
            "`premier`, `la_liga`, `bundesliga`, `serie_a`, `ligue_1`"
        )
        return

    _running = True
    try:
        from orchestrator import BettingBotOrchestrator
        orquestador = BettingBotOrchestrator(selected_leagues=selected_leagues)
        orquestador.discord_client = bot
        orquestador.discord_channel_id = DISCORD_CHANNEL_ID
        await orquestador.run_from_discord()
    except Exception as e:
        await ctx.send(f"Error durante el analisis: `{e}`")
        print(f"[Bot] Error: {e}")
    finally:
        _running = False


@bot.command(name="ayuda")
async def ayuda(ctx):
    if ctx.channel.id != DISCORD_CHANNEL_ID:
        return
    await ctx.send(
        "**Comandos disponibles:**\n"
        "`!analizar nba` — NBA en la proxima hora\n"
        "`!analizar futbol` — Selecciona liga\n"
        "`!analizar premier` — Premier League\n"
        "`!analizar la_liga` — La Liga\n"
        "`!analizar bundesliga` — Bundesliga\n"
        "`!analizar serie_a` — Serie A\n"
        "`!analizar ligue_1` — Ligue 1\n"
        "`!analizar todas` — Las 5 ligas europeas\n"
        "`!ayuda` — Este mensaje"
    )


# ── Arranque: FastAPI + Discord en paralelo ───────────────────────────────────

def run_web():
    port = int(__import__("os").environ.get("PORT", 10000))  # 10000 no 8000
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


async def run_bot():
    """Corre el bot de Discord."""
    await bot.start(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    # Arrancar FastAPI en un hilo y el bot en el event loop principal
    thread = threading.Thread(target=run_web, daemon=True)
    thread.start()
    print("[Bot] Servidor web iniciado.")
    asyncio.run(run_bot())
