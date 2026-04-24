"""
Motor de análisis estadístico.
Evalúa si una apuesta cumple los criterios y la clasifica en Tipo 1/2/3.
"""

    """
    Recibe estadísticas ya parseadas y devuelve:
    - ¿Cumple el criterio mínimo? (bool)
    - Tipo de apuesta (1, 2 o 3)
    - Porcentaje histórico de éxito
    - Monto sugerido a apostar
    - Resumen de stats para el mensaje Discord
    """

from typing import Optional
from config.settings import BET_TYPES, BANKROLL, SPORT_CONFIG

class BetAnalyzer:

    def _get_sport_config(self, sport: str) -> dict:
        return SPORT_CONFIG.get(sport, SPORT_CONFIG["football"])

    def analyze_player_line(
        self,
        line: float,
        stat_key: str,
        last_games_stats: list,
        season_average: float,
        h2h_stats: list = None,
        home_stats: list = None,
        away_stats: list = None,
        is_home: bool = True,
        sport: str = "football",
    ):
        if not last_games_stats:
            return None

        cfg = self._get_sport_config(sport)
        thresholds = cfg["type_thresholds"]

        if season_average < line:
            return None

        recent_hits = sum(1 for s in last_games_stats if s > line)
        recent_pct = recent_hits / len(last_games_stats)

        h2h_pct = None
        if h2h_stats and len(h2h_stats) >= 2:
            h2h_pct = sum(1 for s in h2h_stats if s > line) / len(h2h_stats)

        location_pct = None
        location_stats = home_stats if is_home else away_stats
        if location_stats and len(location_stats) >= 3:
            location_pct = sum(1 for s in location_stats if s > line) / len(location_stats)

        score = self._composite_score(recent_pct, h2h_pct, location_pct)
        bet_type = self._classify(score, thresholds)
        if bet_type is None:
            return None

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
            "stake": self._calculate_stake(bet_type),
            "stake_label": f"${self._calculate_stake(bet_type)} USD",
        }

    def analyze_team_market(
        self,
        line,
        market_name: str,
        home_last_games: list,
        away_last_games: list,
        h2h_games: list = None,
        stat_extractor=None,
        sport: str = "football",
    ):
        if stat_extractor is None:
            return None

        cfg = self._get_sport_config(sport)
        thresholds = cfg["type_thresholds"]

        home_vals = [v for v in (stat_extractor(g) for g in home_last_games) if v is not None]
        away_vals = [v for v in (stat_extractor(g) for g in away_last_games) if v is not None]
        h2h_vals  = [v for v in (stat_extractor(g) for g in (h2h_games or [])) if v is not None]

        if not home_vals or not away_vals:
            return None

        threshold = line if line is not None else 0

        def pct(vals):
            return sum(1 for v in vals if v >= threshold) / len(vals) if vals else None

        score = self._composite_score(
            (pct(home_vals) + pct(away_vals)) / 2,
            pct(h2h_vals) if h2h_vals else None,
            None,
        )
        bet_type = self._classify(score, thresholds)
        if bet_type is None:
            return None

        return {
            "bet_type": bet_type,
            "bet_type_label": BET_TYPES[bet_type]["label"],
            "score": round(score, 3),
            "home_pct": round(pct(home_vals) * 100, 1) if home_vals else None,
            "away_pct": round(pct(away_vals) * 100, 1) if away_vals else None,
            "h2h_pct": round(pct(h2h_vals) * 100, 1) if h2h_vals else None,
            "stake": self._calculate_stake(bet_type),
            "stake_label": f"${self._calculate_stake(bet_type)} USD",
        }

    def _composite_score(self, recent_pct, h2h_pct, location_pct):
        weights = {"recent": 0.60, "h2h": 0.25, "location": 0.15}
        values = {"recent": recent_pct, "h2h": h2h_pct, "location": location_pct}
        available = {k: v for k, v in values.items() if v is not None}
        if not available:
            return 0.0
        total_w = sum(weights[k] for k in available)
        return sum((weights[k] / total_w) * v for k, v in available.items())

    def _classify(self, score: float, thresholds: dict):
        for bet_type in (3, 2, 1):
            if score >= thresholds[bet_type]:
                return bet_type
        return None

    def _calculate_stake(self, bet_type: int) -> float:
        return round(BANKROLL * BET_TYPES[bet_type]["stake_pct"] / 100, 2)
