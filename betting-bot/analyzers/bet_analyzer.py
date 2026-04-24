"""
Motor de análisis estadístico.
Evalúa si una apuesta cumple los criterios y la clasifica en Tipo 1/2/3.
"""

from typing import Optional
from config.settings import TYPE_THRESHOLDS, RECENT_GAMES_WINDOW, BET_TYPES, BANKROLL


class BetAnalyzer:
    """
    Recibe estadísticas ya parseadas y devuelve:
    - ¿Cumple el criterio mínimo? (bool)
    - Tipo de apuesta (1, 2 o 3)
    - Porcentaje histórico de éxito
    - Monto sugerido a apostar
    - Resumen de stats para el mensaje Discord
    """

    # ─── Análisis de línea de jugador (NBA/fútbol) ─────────────────────────────
    def analyze_player_line(
        self,
        line: float,
        stat_key: str,
        last_games_stats: list[float],   # valores del stat en últimos N partidos
        season_average: float,
        h2h_stats: list[float] = None,   # valores contra este rival esta temporada
        home_stats: list[float] = None,  # de local
        away_stats: list[float] = None,  # de visitante
        is_home: bool = True,
    ) -> Optional[dict]:
        """
        Analiza si apostar Over <line> en un stat de jugador.
        Retorna None si no cumple el mínimo.
        """
        if not last_games_stats:
            return None

        # Criterio 1: promedio de temporada supera la línea
        if season_average < line:
            return None

        # Criterio 2: % de partidos recientes donde superó la línea
        recent_hits = sum(1 for s in last_games_stats if s > line)
        recent_pct = recent_hits / len(last_games_stats)

        # Criterio 3 (opcional): rendimiento H2H esta temporada
        h2h_pct = None
        if h2h_stats and len(h2h_stats) >= 2:
            h2h_hits = sum(1 for s in h2h_stats if s > line)
            h2h_pct = h2h_hits / len(h2h_stats)

        # Criterio 4 (opcional): local/visitante
        location_pct = None
        location_stats = home_stats if is_home else away_stats
        if location_stats and len(location_stats) >= 3:
            loc_hits = sum(1 for s in location_stats if s > line)
            location_pct = loc_hits / len(location_stats)

        # Score compuesto
        score = self._composite_score(recent_pct, h2h_pct, location_pct)

        # Clasificar
        bet_type = self._classify(score)
        if bet_type is None:
            return None  # No cumple ni el mínimo

        stake = self._calculate_stake(bet_type)

        # Promedio últimos partidos
        avg_recent = sum(last_games_stats) / len(last_games_stats)

        return {
            "bet_type": bet_type,
            "bet_type_label": BET_TYPES[bet_type]["label"],
            "score": round(score, 3),
            "recent_pct": round(recent_pct * 100, 1),
            "h2h_pct": round(h2h_pct * 100, 1) if h2h_pct is not None else None,
            "location_pct": round(location_pct * 100, 1) if location_pct is not None else None,
            "season_average": round(season_average, 1),
            "recent_average": round(avg_recent, 1),
            "last_games": [round(s, 1) for s in last_games_stats[-5:]],
            "stake": stake,
            "stake_label": f"${stake} COP",
        }

    # ─── Análisis de mercado de equipo (totales, BTTS, corners) ───────────────
    def analyze_team_market(
        self,
        line: Optional[float],
        market_name: str,
        home_last_games: list,   # estadísticas del equipo local en últimos N
        away_last_games: list,   # estadísticas del equipo visitante en últimos N
        h2h_games: list = None,  # H2H entre ambos
        stat_extractor=None,     # función que extrae el valor relevante de cada partido
    ) -> Optional[dict]:
        """
        Analiza mercados de equipo: totales de goles, corners, BTTS, etc.
        stat_extractor: callable(game_dict) → float
        """
        if stat_extractor is None:
            return None

        # Combinar rendimiento de local + visitante
        home_vals = [stat_extractor(g) for g in home_last_games if stat_extractor(g) is not None]
        away_vals = [stat_extractor(g) for g in away_last_games if stat_extractor(g) is not None]
        h2h_vals = [stat_extractor(g) for g in (h2h_games or []) if stat_extractor(g) is not None]

        if not home_vals or not away_vals:
            return None

        def pct_over(vals, threshold):
            if not vals:
                return None
            return sum(1 for v in vals if v >= threshold) / len(vals)

        threshold = line if line is not None else 0

        home_pct = pct_over(home_vals, threshold)
        away_pct = pct_over(away_vals, threshold)
        combined_pct = (home_pct + away_pct) / 2 if home_pct and away_pct else None
        h2h_pct = pct_over(h2h_vals, threshold) if h2h_vals else None

        score = self._composite_score(combined_pct, h2h_pct, None)
        bet_type = self._classify(score)
        if bet_type is None:
            return None

        stake = self._calculate_stake(bet_type)

        return {
            "bet_type": bet_type,
            "bet_type_label": BET_TYPES[bet_type]["label"],
            "score": round(score, 3),
            "home_pct": round(home_pct * 100, 1) if home_pct else None,
            "away_pct": round(away_pct * 100, 1) if away_pct else None,
            "h2h_pct": round(h2h_pct * 100, 1) if h2h_pct else None,
            "stake": stake,
            "stake_label": f"${stake} COP",
        }

    # ─── Helpers internos ─────────────────────────────────────────────────────
    def _composite_score(
        self,
        recent_pct: Optional[float],
        h2h_pct: Optional[float],
        location_pct: Optional[float],
    ) -> float:
        """
        Ponderación: reciente 60%, H2H 25%, local/visitante 15%.
        Si falta algún dato, redistribuye el peso.
        """
        weights = {"recent": 0.60, "h2h": 0.25, "location": 0.15}
        values = {
            "recent": recent_pct,
            "h2h": h2h_pct,
            "location": location_pct,
        }
        # Redistribuir peso de valores faltantes
        available = {k: v for k, v in values.items() if v is not None}
        if not available:
            return 0.0

        total_weight = sum(weights[k] for k in available)
        score = sum((weights[k] / total_weight) * v for k, v in available.items())
        return score

    def _classify(self, score: float) -> Optional[int]:
        for bet_type in (3, 2, 1):
            if score >= TYPE_THRESHOLDS[bet_type]:
                return bet_type
        return None  # No cumple el mínimo

    def _calculate_stake(self, bet_type: int) -> float:
        pct = BET_TYPES[bet_type]["stake_pct"]
        return round(BANKROLL * pct / 100, 2)
