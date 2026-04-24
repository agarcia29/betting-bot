"""
Scraper de cuotas desde Rushbet.co (plataforma Kambi).

Mejoras anti-429:
  - Cliente httpx persistente (reutiliza conexión TCP)
  - Delay aleatorio entre ligas (3–7 seg)
  - Reintentos con backoff exponencial (3 intentos)
  - Rotación de User-Agent por request
  - Header Referer y cookies básicas que simula el navegador
"""

import httpx
import asyncio
import random
import time
from typing import Optional
from config.settings import ODDS_MIN, ODDS_MAX, LEAGUES

RUSHBET_API = "https://eu-offering-api.kambicdn.com/offering/v2018/rushco"

# Pool de User-Agents reales de navegadores modernos
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
]

# Parámetros base que Kambi siempre espera
BASE_PARAMS = {
    "lang":        "es_CO",
    "market":      "CO",
    "client_id":   "2",
    "channel_id":  "1",
    "ncid":        "1",
    "useCombined": "true",
}

# Mapeo rushbet_key → grupo en Kambi
LEAGUE_GROUPS = {
    "premier-league": "football/england/premier_league",
    "la-liga":        "football/spain/la_liga",
    "bundesliga":     "football/germany/bundesliga",
    "serie-a":        "football/italy/serie_a",
    "ligue-1":        "football/france/ligue_1",
    "nba":            "basketball/usa/nba",
}


class RushbetScraper:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    # ─── Ciclo de vida del cliente ─────────────────────────────────────────────

    async def _ensure_client(self):
        """Crea el cliente persistente si no existe o fue cerrado."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(25.0, connect=10.0),
                follow_redirects=True,
                http2=False,
            )

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ─── GET con reintentos y backoff ─────────────────────────────────────────

    async def _get(
        self,
        path: str,
        params: dict = None,
        max_retries: int = 3,
    ) -> Optional[dict]:
        await self._ensure_client()
        url = f"{RUSHBET_API}{path}"
        headers = self._build_headers()

        for attempt in range(1, max_retries + 1):
            try:
                r = await self._client.get(url, headers=headers, params=params)

                if r.status_code == 429:
                    # Respetar Retry-After si el servidor lo manda
                    retry_after = int(r.headers.get("Retry-After", 0))
                    wait = max(retry_after, self._backoff(attempt))
                    print(f"[Rushbet] 429 en {path} — esperando {wait:.1f}s (intento {attempt}/{max_retries})")
                    await asyncio.sleep(wait)
                    headers = self._build_headers()   # rotar UA en el reintento
                    continue

                r.raise_for_status()
                return r.json()

            except httpx.HTTPStatusError as e:
                print(f"[Rushbet] HTTP {e.response.status_code} en {path} (intento {attempt})")
                if attempt < max_retries:
                    await asyncio.sleep(self._backoff(attempt))
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                print(f"[Rushbet] Conexión/timeout en {path} (intento {attempt}): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(self._backoff(attempt))
            except Exception as e:
                print(f"[Rushbet] Error inesperado en {path}: {e}")
                break

        print(f"[Rushbet] ❌ Falló después de {max_retries} intentos: {path}")
        return None

    def _backoff(self, attempt: int) -> float:
        """Backoff exponencial con jitter: 5s, 15s, 35s (+/- 2s aleatorio)."""
        base = 5 * (2 ** (attempt - 1))
        jitter = random.uniform(-2, 2)
        return base + jitter

    def _build_headers(self) -> dict:
        """Construye headers con User-Agent rotado aleatoriamente."""
        return {
            "User-Agent":      random.choice(USER_AGENTS),
            "Accept":          "application/json, text/plain, */*",
            "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer":         "https://rushbet.co/",
            "Origin":          "https://rushbet.co",
            "DNT":             "1",
            "Connection":      "keep-alive",
            "Sec-Fetch-Dest":  "empty",
            "Sec-Fetch-Mode":  "cors",
            "Sec-Fetch-Site":  "cross-site",
        }

    # ─── Scraping por liga ─────────────────────────────────────────────────────

    async def get_events_by_league(self, rushbet_key: str) -> list[dict]:
        """Retorna eventos del día con cuotas en rango [ODDS_MIN, ODDS_MAX]."""
        group = LEAGUE_GROUPS.get(rushbet_key)
        if not group:
            print(f"[Rushbet] Liga no mapeada: {rushbet_key}")
            return []

        params = {**BASE_PARAMS, "group": group}
        data = await self._get("/listView/sport/event/group/match.json", params=params)
        if not data:
            return []

        events = []
        for event_data in data.get("events", []):
            parsed = self._parse_event(event_data)
            if parsed:
                events.append(parsed)

        print(f"[Rushbet] {rushbet_key}: {len(events)} eventos con cuotas en rango")
        return events

    # ─── Scraping completo — ligas en secuencia con delay ─────────────────────

    async def scrape_all_leagues(self, leagues: dict = None) -> dict:
        """
        Itera las ligas UNA POR UNA con delay aleatorio entre cada una.
        Evita el 429 que ocurría al lanzarlas todas simultáneamente.
        """
        results = {}
        from config.settings import LEAGUES as ALL_LEAGUES
        target = leagues if leagues else ALL_LEAGUES
        league_keys = list(target.keys())

        for i, league_key in enumerate(league_keys):
            league_cfg = target[league_key]
            print(f"[Rushbet] Scraping {league_cfg['name']} ({i+1}/{len(league_keys)})...")

            events = await self.get_events_by_league(league_cfg["rushbet_key"])
            results[league_key] = events

            # Delay entre ligas (excepto después de la última)
            if i < len(league_keys) - 1:
                delay = random.uniform(4.0, 8.0)
                print(f"[Rushbet] Esperando {delay:.1f}s antes de la siguiente liga...")
                await asyncio.sleep(delay)

        return results

    # ─── Parser de evento ─────────────────────────────────────────────────────

    def _parse_event(self, raw: dict) -> Optional[dict]:
        event = raw.get("event", {})
        if not event:
            return None

        name     = event.get("name", "")
        event_id = event.get("id")
        start    = event.get("start")   # ISO string

        markets = {}
        for bet_offer in raw.get("betOffers", []):
            criterion    = bet_offer.get("criterion", {})
            market_label = criterion.get("label", "")

            for outcome in bet_offer.get("outcomes", []):
                odds = outcome.get("oddsDecimal")
                if not odds or not (ODDS_MIN <= odds <= ODDS_MAX):
                    continue

                label       = outcome.get("label", "")
                line_raw    = outcome.get("line")
                participant = outcome.get("participant", "")

                market_key = f"{market_label}|{label}|{participant}"
                markets[market_key] = {
                    "market":      market_label,
                    "label":       label,
                    "line":        line_raw / 1000 if line_raw else None,  # Kambi → decimal
                    "odds":        odds,
                    "participant": participant,
                    "bet_offer_id": bet_offer.get("id"),
                }

        if not markets:
            return None

        parts = name.split(" - ", 1)
        home  = parts[0].strip() if len(parts) == 2 else name
        away  = parts[1].strip() if len(parts) == 2 else ""

        return {
            "event_id":   event_id,
            "event_name": name,
            "home_team":  home,
            "away_team":  away,
            "start_time": start,
            "markets":    markets,
        }

    # ─── Mercados completos de un evento (para análisis profundo) ─────────────

    async def get_all_markets(self, event_id: int) -> dict:
        params = {**BASE_PARAMS}
        data = await self._get(f"/betoffer/event/{event_id}.json", params=params)
        if not data:
            return {}

        all_markets = {}
        for bet_offer in data.get("betOffers", []):
            criterion    = bet_offer.get("criterion", {})
            market_label = criterion.get("label", "")
            for outcome in bet_offer.get("outcomes", []):
                odds = outcome.get("oddsDecimal")
                if not odds or not (ODDS_MIN <= odds <= ODDS_MAX):
                    continue
                line_raw = outcome.get("line")
                key = f"{market_label}|{outcome.get('label','')}|{outcome.get('participant','')}"
                all_markets[key] = {
                    "market":        market_label,
                    "outcome_label": outcome.get("label", ""),
                    "line":          line_raw / 1000 if line_raw else None,
                    "odds":          odds,
                    "participant":   outcome.get("participant", ""),
                }
        return all_markets
