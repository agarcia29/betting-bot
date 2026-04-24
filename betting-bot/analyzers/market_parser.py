"""
Mapeo entre los mercados de Rushbet y las estadísticas de SofaScore.

Mercados activos:
  FÚTBOL (5 grandes ligas):
    Partido  → Total goles +1.5 / +2.5, BTTS, Córners Over
    Jugador  → Gol, Tiros a puerta, Tiros totales, Tarjeta amarilla,
               Asistencias, Faltas cometidas

  NBA:
    Jugador  → Puntos, Rebotes, Asistencias, Triples, PRA
    Partido  → Total puntos Over
"""

from typing import Optional, Callable


# ══════════════════════════════════════════════════════════════
#  EXTRACTORES — PARTIDO DE FÚTBOL
# ══════════════════════════════════════════════════════════════

def extract_total_goals(game: dict) -> Optional[float]:
    """Goles totales en un partido ya jugado."""
    h = game.get("homeScore", {}).get("current")
    a = game.get("awayScore", {}).get("current")
    if h is not None and a is not None:
        return float(h + a)
    return None


def extract_btts(game: dict) -> Optional[float]:
    """1.0 si ambos equipos anotaron, 0.0 si no."""
    h = game.get("homeScore", {}).get("current")
    a = game.get("awayScore", {}).get("current")
    if h is not None and a is not None:
        return 1.0 if h > 0 and a > 0 else 0.0
    return None


def extract_corners(game: dict) -> Optional[float]:
    """Córners totales del partido (home + away)."""
    stats = game.get("statistics", {})
    for period in stats.get("periods", []):
        if period.get("period") == "ALL":
            for group in period.get("groups", []):
                for item in group.get("statisticsItems", []):
                    if "corner" in item.get("name", "").lower():
                        try:
                            hv = float(str(item.get("homeValue", 0)).replace("%", "") or 0)
                            av = float(str(item.get("awayValue", 0)).replace("%", "") or 0)
                            return hv + av
                        except Exception:
                            pass
    return None


# ══════════════════════════════════════════════════════════════
#  EXTRACTORES — JUGADOR DE FÚTBOL
#  Claves de SofaScore usadas en estadísticas por partido
# ══════════════════════════════════════════════════════════════

FOOTBALL_PLAYER_STAT_KEYS = {
    # stat_key interno  →  clave SofaScore
    "goals":            "goals",
    "shots_on_target":  "onTargetScoringAttempt",   # tiros a puerta
    "shots_total":      "totalScoringAttempt",       # tiros totales (a puerta + fuera)
    "yellow_cards":     "yellowCard",
    "assists":          "goalAssist",
    "fouls":            "foulsCommitted",            # faltas cometidas
}


def make_football_player_extractor(stat_key: str) -> Callable[[dict], Optional[float]]:
    sofa_key = FOOTBALL_PLAYER_STAT_KEYS[stat_key]
    def extractor(game_stat: dict) -> Optional[float]:
        stats = game_stat.get("statistics", game_stat)
        val = stats.get(sofa_key)
        return float(val) if val is not None else None
    return extractor


# ══════════════════════════════════════════════════════════════
#  EXTRACTORES — NBA
# ══════════════════════════════════════════════════════════════

NBA_PLAYER_STAT_KEYS = {
    "points":               "points",
    "rebounds":             "rebounds",
    "assists":              "assists",
    "three_pointers_made":  "threePointsMade",
    "pra":                  None,   # calculado abajo
}


def make_nba_player_extractor(stat_key: str) -> Callable[[dict], Optional[float]]:
    sofa_key = NBA_PLAYER_STAT_KEYS[stat_key]
    def extractor(game_stat: dict) -> Optional[float]:
        stats = game_stat.get("statistics", game_stat)
        val = stats.get(sofa_key)
        return float(val) if val is not None else None
    return extractor


def extract_pra(game_stat: dict) -> Optional[float]:
    """Puntos + Rebotes + Asistencias."""
    stats = game_stat.get("statistics", game_stat)
    p = stats.get("points")
    r = stats.get("rebounds")
    a = stats.get("assists")
    if all(x is not None for x in [p, r, a]):
        return float(p + r + a)
    return None


def extract_nba_total_points(game: dict) -> Optional[float]:
    """Total de puntos anotados en un partido de NBA."""
    h = game.get("homeScore", {}).get("current")
    a = game.get("awayScore", {}).get("current")
    if h is not None and a is not None:
        return float(h + a)
    return None


# ══════════════════════════════════════════════════════════════
#  PARSER PRINCIPAL
# ══════════════════════════════════════════════════════════════

def parse_rushbet_market(
    market_label: str,
    outcome_label: str,
    line: Optional[float],
    participant: str,
) -> Optional[dict]:
    """
    Retorna un dict con:
      market_type  : 'player' | 'team'
      stat_key     : clave interna del stat
      extractor    : callable(game_dict) → float | None
      display_name : texto para el mensaje de Discord
      player_name  : nombre del jugador (solo si market_type == 'player')

    Retorna None si el mercado no está entre los activos.
    """
    ml = market_label.lower()
    has_participant = bool(participant and participant.strip())

    # ──────────────────────────────────────────────────────────
    #  NBA — jugador
    # ──────────────────────────────────────────────────────────
    if _match(ml, ["puntos", "points"]) and has_participant:
        return _player("points", make_nba_player_extractor("points"),
                       f"Puntos +{line}", participant)

    if _match(ml, ["rebotes", "rebounds"]) and has_participant:
        return _player("rebounds", make_nba_player_extractor("rebounds"),
                       f"Rebotes +{line}", participant)

    if _match(ml, ["asistencias", "assists"]) and has_participant:
        return _player("assists", make_nba_player_extractor("assists"),
                       f"Asistencias +{line}", participant)

    if _match(ml, ["triples", "three", "3 puntos", "3pts"]) and has_participant:
        return _player("three_pointers_made", make_nba_player_extractor("three_pointers_made"),
                       f"Triples +{line}", participant)

    if _match(ml, ["pra", "pts+reb+ast", "puntos+rebotes"]) and has_participant:
        return _player("pra", extract_pra, f"PRA +{line}", participant)

    # ──────────────────────────────────────────────────────────
    #  NBA — partido
    # ──────────────────────────────────────────────────────────
    if _match(ml, ["total puntos", "total points", "puntos totales"]) and not has_participant:
        return _team("nba_total_points", extract_nba_total_points, f"Total Puntos +{line}")

    # ──────────────────────────────────────────────────────────
    #  FÚTBOL — jugador
    # ──────────────────────────────────────────────────────────

    # Tiros a puerta (más específico → va primero)
    if _match(ml, ["tiro a puerta", "tiros a puerta", "shots on target",
                   "disparo a puerta", "remate a puerta"]) and has_participant:
        return _player("shots_on_target",
                       make_football_player_extractor("shots_on_target"),
                       f"Tiros a puerta +{line}", participant)

    # Tiros totales
    if _match(ml, ["tiros totales", "total shots", "total tiros",
                   "disparos totales", "tiros del jugador",
                   "remates totales"]) and has_participant:
        return _player("shots_total",
                       make_football_player_extractor("shots_total"),
                       f"Tiros totales +{line}", participant)

    # Gol del jugador
    if _match(ml, ["marcar", "anotar gol", "scorer", "gol en cualquier momento",
                   "goleador", "primer gol", "último gol"]) and has_participant:
        return _player("goals",
                       make_football_player_extractor("goals"),
                       "Anota gol", participant)

    # Tarjeta amarilla
    if _match(ml, ["tarjeta amarilla", "yellow card", "amarilla"]) and has_participant:
        return _player("yellow_cards",
                       make_football_player_extractor("yellow_cards"),
                       "Tarjeta amarilla", participant)

    # Asistencias
    if _match(ml, ["asistencia", "assist"]) and has_participant:
        return _player("assists",
                       make_football_player_extractor("assists"),
                       f"Asistencias +{line}", participant)

    # Faltas cometidas
    if _match(ml, ["falta", "foul", "falta cometida", "faltas"]) and has_participant:
        return _player("fouls",
                       make_football_player_extractor("fouls"),
                       f"Faltas +{line}", participant)

    # ──────────────────────────────────────────────────────────
    #  FÚTBOL — partido
    # ──────────────────────────────────────────────────────────

    # Total goles (+1.5 o +2.5 — la línea viene en el campo `line`)
    if _match(ml, ["total goles", "total de goles", "goles totales",
                   "over goals", "over/under goles", "más de"]) and not has_participant:
        if line is not None:
            return _team("total_goals", extract_total_goals, f"Total Goles +{line}")

    # BTTS
    if _match(ml, ["ambos equipos anotan", "ambos marcan", "btts",
                   "both teams to score", "ambos equipos marcan"]):
        return _team("btts", extract_btts, "Ambos Anotan (BTTS)")

    # Córners Over
    if _match(ml, ["corner", "córner", "corners", "tiros de esquina"]):
        if line is not None:
            return _team("corners", extract_corners, f"Córners +{line}")

    return None   # Mercado no activo → ignorar


# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════

def _player(stat_key: str, extractor: Callable, display_name: str, player_name: str) -> dict:
    return {
        "market_type": "player",
        "stat_key": stat_key,
        "extractor": extractor,
        "display_name": display_name,
        "player_name": player_name,
    }


def _team(stat_key: str, extractor: Callable, display_name: str) -> dict:
    return {
        "market_type": "team",
        "stat_key": stat_key,
        "extractor": extractor,
        "display_name": display_name,
    }


def _match(market_lower: str, keywords: list) -> bool:
    return any(kw in market_lower for kw in keywords)


# ══════════════════════════════════════════════════════════════
#  TABLA DE CLAVES PARA PROMEDIO DE TEMPORADA
#  Usada en orchestrator._get_season_avg()
# ══════════════════════════════════════════════════════════════

SEASON_AVG_KEYS = {
    # NBA
    "points":               "points",
    "rebounds":             "rebounds",
    "assists":              "assists",
    "three_pointers_made":  "threePointsMade",
    "pra":                  None,   # se calcula sumando points + rebounds + assists
    # Fútbol jugador
    "goals":                "goals",
    "shots_on_target":      "onTargetScoringAttempt",
    "shots_total":          "totalScoringAttempt",
    "yellow_cards":         "yellowCard",
    "assists_football":     "goalAssist",
    "fouls":                "foulsCommitted",
}
