"""
Formateador de señales para Discord.
Genera los mensajes en el formato requerido, agrupados por partido.
"""

from datetime import datetime, timezone
from typing import Optional
from config.settings import LEAGUES, BET_TYPES


SPORT_EMOJI = {
    "football": "⚽",
    "basketball": "🏀",
}

LEAGUE_EMOJI = {
    "premier_league": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "la_liga": "🇪🇸",
    "bundesliga": "🇩🇪",
    "serie_a": "🇮🇹",
    "ligue_1": "🇫🇷",
    "nba": "🏀",
}

# Separadores visuales
DIVIDER     = "━" * 32
THIN_DIV    = "─" * 32
BLOCK_START = "╔" + "═" * 30 + "╗"
BLOCK_END   = "╚" + "═" * 30 + "╝"


def format_match_signals(
    league_key: str,
    event_name: str,
    start_time: datetime,
    sport: str,
    signals: list[dict],
) -> str:
    """
    Genera el mensaje completo de Discord para UN partido con sus señales.
    signals: lista de dicts con claves market, line, odds, bet_type_label, stake_label, stats_summary
    """
    league_cfg = LEAGUES.get(league_key, {})
    league_name = league_cfg.get("name", league_key)
    sport_emoji = SPORT_EMOJI.get(sport, "🎮")

    # Hora en formato legible (UTC-5 Colombia)
    try:
        from zoneinfo import ZoneInfo
        local_tz = ZoneInfo("America/Bogota")
        local_time = start_time.astimezone(local_tz)
    except Exception:
        local_time = start_time

    time_str = local_time.strftime("%I:%M %p")

    lines = []
    lines.append(BLOCK_START)
    lines.append(f"║  {sport_emoji}  SEÑAL DE APUESTA  {sport_emoji}         ║")
    lines.append(BLOCK_END)
    lines.append("")
    lines.append(f"🏆 **Liga:** {league_name}")
    lines.append(f"🆚 **Evento:** {event_name}")
    lines.append(f"🕐 **Hora:** {time_str} (🇨🇴 COT)")
    lines.append("")
    lines.append(DIVIDER)

    for i, signal in enumerate(signals, 1):
        lines.append(f"")
        lines.append(f"**📌 Señal #{i}**")
        lines.append(f"📊 **Mercado:** {signal['market']}")
        lines.append(f"💰 **Cuota:** `{signal['odds']}`")
        lines.append(f"  {signal['bet_type_label']}")
        lines.append(f"💵 **Apostar:** {signal['stake_label']}")
        lines.append("")

        # Estadísticas de soporte
        stats = signal.get("stats_summary")
        if stats:
            lines.append("📈 **Estadísticas:**")
            for stat_line in stats:
                lines.append(f"  {stat_line}")

        if i < len(signals):
            lines.append(THIN_DIV)

    lines.append("")
    lines.append(DIVIDER)
    lines.append("⚠️ *Apuesta con responsabilidad. Solo información.*")

    return "\n".join(lines)


def format_stats_summary_player(analysis: dict, player_name: str, line: float, stat_name: str) -> list[str]:
    """Genera líneas de estadísticas para mercados de jugador."""
    lines = []
    lines.append(f"👤 {player_name}")
    lines.append(f"📏 Línea: **{line}** {stat_name}")
    lines.append(f"📅 Promedio temporada: **{analysis['season_average']}**")
    lines.append(f"🔥 Promedio últimos {len(analysis['last_games'])} partidos: **{analysis['recent_average']}**")
    lines.append(f"✅ Éxito reciente: **{analysis['recent_pct']}%**")
    if analysis.get("h2h_pct") is not None:
        lines.append(f"🔁 H2H este año: **{analysis['h2h_pct']}%**")
    if analysis.get("location_pct") is not None:
        lines.append(f"🏠 Local/Visitante: **{analysis['location_pct']}%**")
    last = " | ".join(str(v) for v in analysis["last_games"])
    lines.append(f"📋 Últimos: `{last}`")
    return lines


def format_stats_summary_team(analysis: dict, market_name: str) -> list[str]:
    """Genera líneas de estadísticas para mercados de equipo."""
    lines = []
    if analysis.get("home_pct") is not None:
        lines.append(f"🏠 Local cumplió: **{analysis['home_pct']}%**")
    if analysis.get("away_pct") is not None:
        lines.append(f"✈️  Visitante cumplió: **{analysis['away_pct']}%**")
    if analysis.get("h2h_pct") is not None:
        lines.append(f"🔁 H2H directo: **{analysis['h2h_pct']}%**")
    return lines


def format_no_signals_day() -> str:
    """Mensaje cuando no hay señales en todo el día."""
    return (
        "📭 **Sin señales hoy**\n"
        "No se encontraron apuestas con cuota 1.50–1.70 que cumplan "
        "los criterios estadísticos mínimos.\n"
        "Sigue el siguiente escaneo mañana. 🔄"
    )
