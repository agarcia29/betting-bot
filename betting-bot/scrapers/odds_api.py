"""
Scraper de cuotas usando The Odds API (the-odds-api.com).

Por qué esto en vez de scraping directo de Rushbet:
  - API oficial → sin 429, sin bloqueos
  - Cubre Bet365, William Hill, Unibet, Pinnacle y ~40 casas europeas
  - Las cuotas de esas casas son prácticamente iguales a Rushbet en estos mercados
  - Tier GRATUITO: 500 requests/mes (suficiente para 6 ligas cada 10 min)

Registro gratuito en: https://the-odds-api.com
Una vez registrado, copia tu API key en config/settings.py → ODDS_API_KEY
"""

import httpx
import asyncio
from typing import Optional
from datetime import datetime, timezone

from config.settings import ODDS_API_KEY, ODDS_MIN, ODDS_MAX, LEAGUES

BASE_URL = "https://api.the-odds-api.com/v4"

# Mapeo league_key → sport_key de The Odds API
LEAGUE_TO_SPORT = {
    "premier_league": "soccer_epl",
    "la_liga":        "soccer_spain_la_liga",
    "bundesliga":     "soccer_germany_bundesliga",
    "serie_a":        "soccer_italy_serie_a",
    "ligue_1":        "soccer_france_ligue_one",
    "nba":            "basketball_nba",
}

# Mercados disponibles en The Odds API por deporte
# h2h = resultado, totals = over/under, player_props = props de jugador
FOOTBALL_API_MARKETS = ["h2h", "totals", "btts", "player_pass_tbs",
                         "player_shots", "player_shots_on_target",
                         "player_goal_scorer_anytime", "player_cards",
                         "player_assists", "player_fouls_committed"]

NBA_API_MARKETS = ["h2h", "totals", "player_points", "player_rebounds",
                   "player_assists", "player_threes", "player_pra"]

# Bookmakers europeos de referencia (cuotas similares a Rushbet)
EU_BOOKMAKERS = "bet365,unibet,williamhill,betfair_ex_eu,betsson,nordicbet"


class OddsApiScraper:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._requests_used = 0
        self._requests_remaining = 500

    async def _ensure_client(self):
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(20.0),
                follow_redirects=True,
            )

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _get(self, path: str, params: dict) -> Optional[dict | list]:
        await self._ensure_client()
        params["apiKey"] = ODDS_API_KEY
        url = f"{BASE_URL}{path}"
        try:
            r = await self._client.get(url, params=params)

            # Leer headers de cuota antes de raise
            self._requests_remaining = int(r.headers.get("x-requests-remaining", self._requests_remaining))
            self._requests_used = int(r.headers.get("x-requests-used", self._requests_used))

            if r.status_code == 401:
                print("[OddsAPI] ❌ API key inválida. Verifica ODDS_API_KEY en settings.py")
                return None
            if r.status_code == 429:
                print("[OddsAPI] ⚠️ Límite de requests alcanzado este mes.")
                return None

            r.raise_for_status()
            print(f"[OddsAPI] Requests restantes este mes: {self._requests_remaining}")
            return r.json()

        except httpx.HTTPStatusError as e:
            print(f"[OddsAPI] HTTP {e.response.status_code}: {path}")
            return None
        except Exception as e:
            print(f"[OddsAPI] Error: {e}")
            return None

    # ─── Eventos con cuotas de hoy ────────────────────────────────────────────

    async def get_events_by_league(self, league_key: str) -> list[dict]:
        """Retorna eventos con cuotas en rango [ODDS_MIN, ODDS_MAX] para una liga."""
        sport_key = LEAGUE_TO_SPORT.get(league_key)
        if not sport_key:
            return []

        league_cfg = LEAGUES[league_key]
        is_football = league_cfg["sport"] == "football"

        # Mercados principales (totals + h2h) — 1 request por liga
        markets = "totals,h2h"
        data = await self._get(f"/sports/{sport_key}/odds", params={
            "regions":     "eu",
            "markets":     markets,
            "oddsFormat":  "decimal",
            "bookmakers":  EU_BOOKMAKERS,
        })

        if not data:
            return []

        events = []
        for raw_event in data:
            parsed = self._parse_event(raw_event, league_key)
            if parsed:
                events.append(parsed)

        print(f"[OddsAPI] {league_cfg['name']}: {len(events)} eventos con cuotas en rango")
        return events

    # ─── Player props (request separado por evento) ───────────────────────────

    async def get_player_props(self, league_key: str, event_id: str) -> list[dict]:
        """
        Obtiene props de jugador para un evento específico.
        COSTO: 1 request por llamada — úsalo solo para eventos próximos (~50 min).
        """
        sport_key = LEAGUE_TO_SPORT.get(league_key)
        if not sport_key:
            return []

        league_cfg = LEAGUES[league_key]
        is_football = league_cfg["sport"] == "football"

        if is_football:
            prop_markets = ("player_goal_scorer_anytime,player_shots_on_target,"
                            "player_cards,player_assists,player_fouls_committed,"
                            "player_shots")
        else:
            prop_markets = ("player_points,player_rebounds,player_assists,"
                            "player_threes,player_pra")

        data = await self._get(f"/sports/{sport_key}/events/{event_id}/odds", params={
            "regions":    "eu",
            "markets":    prop_markets,
            "oddsFormat": "decimal",
            "bookmakers": EU_BOOKMAKERS,
        })

        if not data:
            return []

        props = []
        for bookmaker in data.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                for outcome in market.get("outcomes", []):
                    odds = outcome.get("price")
                    if odds and ODDS_MIN <= odds <= ODDS_MAX:
                        props.append({
                            "market":      market.get("key", ""),
                            "player_name": outcome.get("description", outcome.get("name", "")),
                            "label":       outcome.get("name", ""),
                            "line":        outcome.get("point"),
                            "odds":        odds,
                            "bookmaker":   bookmaker.get("key"),
                        })
        return props

    # ─── Scraping completo ─────────────────────────────────────────────────────

    async def scrape_all_leagues(self, leagues: dict = None) -> dict:
        """Itera las ligas seleccionadas con delay entre cada una."""
        from config.settings import LEAGUES as ALL_LEAGUES
        target = leagues if leagues else ALL_LEAGUES
        results = {}
        league_keys = list(target.keys())

        for i, league_key in enumerate(league_keys):
            events = await self.get_events_by_league(league_key)
            results[league_key] = events

            if i < len(league_keys) - 1:
                await asyncio.sleep(1.5)   # La API es amigable, 1.5s es suficiente

        return results

    # ─── Parser de evento ─────────────────────────────────────────────────────

    def _parse_event(self, raw: dict, league_key: str) -> Optional[dict]:
        commence_time_str = raw.get("commence_time", "")
        try:
            start_time = datetime.fromisoformat(commence_time_str.replace("Z", "+00:00"))
        except Exception:
            return None

        home = raw.get("home_team", "")
        away = raw.get("away_team", "")
        event_id = raw.get("id", "")

        markets = {}
        for bookmaker in raw.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                market_key_api = market.get("key", "")
                for outcome in market.get("outcomes", []):
                    odds = outcome.get("price")
                    if not odds or not (ODDS_MIN <= odds <= ODDS_MAX):
                        continue

                    name  = outcome.get("name", "")
                    point = outcome.get("point")  # línea (ej: 2.5)

                    # Solo nos interesan los Over en totals
                    if market_key_api == "totals" and "over" not in name.lower():
                        continue

                    key = f"{market_key_api}|{name}|{point}"
                    if key not in markets:   # primer bookmaker que lo tenga en rango
                        markets[key] = {
                            "market":      market_key_api,
                            "label":       name,
                            "line":        point,
                            "odds":        odds,
                            "participant": "",
                            "bookmaker":   bookmaker.get("key"),
                        }

        if not markets:
            return None

        return {
            "event_id":    event_id,         # ID de The Odds API (string)
            "event_name":  f"{home} vs {away}",
            "home_team":   home,
            "away_team":   away,
            "start_time":  start_time.isoformat(),
            "markets":     markets,
        }
