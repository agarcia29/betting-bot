"""
Configuración central del bot de apuestas deportivas.
"""

# ─── Discord ──────────────────────────────────────────────────────────────────
# ─── Fuente de cuotas ───────────────────────────────────────────────────────────
# "odds_api"  → The Odds API (recomendado, sin 429, registro gratis en the-odds-api.com)

ODDS_SOURCE = "odds_api"

# API key de The Odds API (gratis en https://the-odds-api.com)
DISCORD_BOT_TOKEN = "MTQ5NzAwODg3MTQ4MTI4MjY3MQ.GG2duI.PJl9agOyUZ4HgYm6R0uMFtr6WBQRbdI49TVbFo"
DISCORD_CHANNEL_ID = 1497012356360700035
# ─── Cuotas objetivo ──────────────────────────────────────────────────────────
ODDS_MIN = 1.50
ODDS_MAX = 1.80

# ─── Clasificación de apuestas ────────────────────────────────────────────────
# Basada en probabilidad implícita + estadísticas históricas del jugador/equipo
BET_TYPES = {
    1: {"label": "🟡 TIPO 1", "description": "Menor probabilidad (apostar poco)",  "stake_pct": 1},
    2: {"label": "🟠 TIPO 2", "description": "Probabilidad media",                  "stake_pct": 2},
    3: {"label": "🟢 TIPO 3", "description": "Alta probabilidad (apuesta fuerte)",  "stake_pct": 3},
}

# Bankroll base en USD (ajusta según tu capital)
BANKROLL = 250000

# ─── Ligas soportadas ─────────────────────────────────────────────────────────
LEAGUES = {
    # Fútbol - 5 grandes ligas europeas
    "premier_league": {
        "name": "Premier League 🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "sofascore_id": 17,
        "sport": "football",
        "rushbet_key": "premier-league",
    },
    "la_liga": {
        "name": "La Liga 🇪🇸",
        "sofascore_id": 8,
        "sport": "football",
        "rushbet_key": "la-liga",
    },
    "bundesliga": {
        "name": "Bundesliga 🇩🇪",
        "sofascore_id": 35,
        "sport": "football",
        "rushbet_key": "bundesliga",
    },
    "serie_a": {
        "name": "Serie A 🇮🇹",
        "sofascore_id": 23,
        "sport": "football",
        "rushbet_key": "serie-a",
    },
    "ligue_1": {
        "name": "Ligue 1 🇫🇷",
        "sofascore_id": 34,
        "sport": "football",
        "rushbet_key": "ligue-1",
    },
    # Baloncesto
    "nba": {
        "name": "NBA 🏀",
        "sofascore_id": 132,
        "sport": "basketball",
        "rushbet_key": "nba",
    },
}

# ─── Mercados de fútbol a analizar ────────────────────────────────────────────
FOOTBALL_MARKETS = [
    # -- Mercados de partido --
    "total_goals_over_1.5",       # Total goles +1.5
    "total_goals_over_2.5",       # Total goles +2.5
    "both_teams_to_score",        # Ambos anotan (BTTS)
    "total_corners_over",         # Córners Over (línea variable)
    # -- Mercados de jugador --
    "player_goals",               # Gol de jugador específico
    "player_shots_on_target",     # Tiros a puerta del jugador
    "player_shots_total",         # Tiros totales del jugador (a puerta + fuera)
    "player_yellow_cards",        # Tarjeta amarilla
    "player_assists",             # Asistencias
    "player_fouls",               # Faltas cometidas
]

# ─── Mercados de NBA a analizar ────────────────────────────────────────────────
NBA_MARKETS = [
    "player_points_over",         # Puntos Over
    "player_rebounds_over",       # Rebotes Over
    "player_assists_over",        # Asistencias Over
    "player_three_pointers_over", # Triples anotados Over
    "player_pra_over",            # Puntos + Rebotes + Asistencias Over
    "total_points_over",          # Total puntos del partido Over
]

# ─── Umbrales estadísticos para clasificar tipo de apuesta ───────────────────
# % de últimos partidos donde el jugador/equipo superó la línea
TYPE_THRESHOLDS = {
    3: 0.70,   # ≥70% de veces cumplió → Tipo 3
    2: 0.55,   # ≥55% → Tipo 2
    1: 0.40,   # ≥40% → Tipo 1 (mínimo para enviar señal)
}

# Ventana de análisis (últimos N partidos)
RECENT_GAMES_WINDOW = 5
HEAD_TO_HEAD_WINDOW = 2   # últimos H2H en temporada actual

# Tiempo antes del partido para enviar señal (minutos)
SIGNAL_LEAD_TIME_MINUTES = 50

# ─── Headers para requests ────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
}

SOFASCORE_API = "https://api.sofascore.com/api/v1"
