"""
Scraper de estadísticas desde SofaScore API pública.
Obtiene: promedio de jugador, últimos N partidos, H2H en temporada actual.
"""

import httpx
import asyncio
from datetime import datetime, timezone
from typing import Optional
from config.settings import SOFASCORE_API, HEADERS, RECENT_GAMES_WINDOW, HEAD_TO_HEAD_WINDOW


class SofaScoreScraper:
    def __init__(self):
        self.base = SOFASCORE_API
        self.headers = {
            **HEADERS,
            "Referer": "https://www.sofascore.com/",
        }

    async def _get(self, path: str) -> Optional[dict]:
        url = f"{self.base}{path}"
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                r = await client.get(url, headers=self.headers)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                print(f"[SofaScore] Error GET {path}: {e}")
                return None

    # ─── Partidos del día por liga ─────────────────────────────────────────────
    async def get_todays_events(self, league_id: int, sport: str = "football") -> list[dict]:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        data = await self._get(f"/sport/{sport}/scheduled-events/{today}")
        if not data:
            return []
        events = []
        for event in data.get("events", []):
            # Filtra por liga
            if event.get("tournament", {}).get("uniqueTournament", {}).get("id") == league_id:
                events.append(self._parse_event(event))
        return events

    def _parse_event(self, raw: dict) -> dict:
        home = raw.get("homeTeam", {})
        away = raw.get("awayTeam", {})
        start_ts = raw.get("startTimestamp", 0)
        return {
            "id": raw.get("id"),
            "home_team": home.get("name", "?"),
            "home_team_id": home.get("id"),
            "away_team": away.get("name", "?"),
            "away_team_id": away.get("id"),
            "start_time": datetime.fromtimestamp(start_ts, tz=timezone.utc),
            "event_name": f"{home.get('name', '?')} vs {away.get('name', '?')}",
            "sport": raw.get("sport", {}).get("slug", "football"),
            "tournament_id": raw.get("tournament", {}).get("uniqueTournament", {}).get("id"),
        }

    # ─── Alineaciones (disponible ~60 min antes) ──────────────────────────────
    async def get_lineups(self, event_id: int) -> dict:
        data = await self._get(f"/event/{event_id}/lineups")
        if not data:
            return {"home": [], "away": []}
        result = {}
        for side in ("home", "away"):
            players = []
            for p in data.get(side, {}).get("players", []):
                player = p.get("player", {})
                players.append({
                    "id": player.get("id"),
                    "name": player.get("name"),
                    "position": p.get("position"),
                    "in_starting_eleven": not p.get("substitute", True),
                })
            result[side] = players
        return result

    # ─── Estadísticas de un jugador en últimos N partidos ─────────────────────
    async def get_player_last_games(self, player_id: int, sport: str = "football") -> list[dict]:
        data = await self._get(f"/player/{player_id}/last-year-summary/{sport}")
        if not data:
            return []
        # sofascore retorna por temporada; tomamos los RECENT_GAMES_WINDOW últimos
        events = data.get("events", [])[-RECENT_GAMES_WINDOW:]
        return events

    async def get_player_statistics(self, player_id: int, sport: str = "football") -> dict:
        """Retorna estadísticas detalladas del jugador (promedio de la temporada)."""
        data = await self._get(f"/player/{player_id}/statistics/season")
        if not data:
            return {}
        stats = {}
        for entry in data.get("statistics", []):
            for k, v in entry.items():
                if isinstance(v, (int, float)):
                    stats[k] = v
        return stats

    # ─── Head-to-Head en temporada actual ─────────────────────────────────────
    async def get_h2h(self, event_id: int) -> list[dict]:
        data = await self._get(f"/event/{event_id}/h2h")
        if not data:
            return []

        # Toma todos los enfrentamientos historicos entre ambos equipos
        # (no solo temporada actual) y retorna los ultimos HEAD_TO_HEAD_WINDOW
        all_events = (
            data.get("teamDuel", {}).get("events", [])
            or data.get("managerDuel", {}).get("events", [])
            or []
        )

        # Ordenar por fecha descendente y tomar los ultimos N
        all_events.sort(key=lambda e: e.get("startTimestamp", 0), reverse=True)
        return all_events[:HEAD_TO_HEAD_WINDOW]

    # ─── Estadísticas de equipo por partido ───────────────────────────────────
    async def get_team_last_games(self, team_id: int, tournament_id: int) -> list[dict]:
        data = await self._get(f"/team/{team_id}/events/last/0")
        if not data:
            return []
        events = data.get("events", [])
        # Filtrar por torneo si es posible
        filtered = [
            e for e in events
            if e.get("tournament", {}).get("uniqueTournament", {}).get("id") == tournament_id
        ]
        return (filtered or events)[-RECENT_GAMES_WINDOW:]

    async def get_match_stats(self, event_id: int) -> dict:
        """Estadísticas detalladas de un partido ya jugado."""
        data = await self._get(f"/event/{event_id}/statistics")
        if not data:
            return {}
        return data.get("statistics", {})

    # ─── Información de jugador ────────────────────────────────────────────────
    async def get_player_info(self, player_id: int) -> dict:
        data = await self._get(f"/player/{player_id}")
        if not data:
            return {}
        p = data.get("player", {})
        return {
            "id": p.get("id"),
            "name": p.get("name"),
            "team": p.get("team", {}).get("name"),
            "position": p.get("position"),
        }
