import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable
from zoneinfo import ZoneInfo

from config.settings import LEAGUES, ODDS_MIN, ODDS_MAX, ODDS_SOURCE
from scrapers.sofascore import SofaScoreScraper
from scrapers.rushbet import RushbetScraper
from scrapers.odds_api import OddsApiScraper
from analyzers.bet_analyzer import BetAnalyzer
from analyzers.market_parser import parse_rushbet_market, SEASON_AVG_KEYS
from messaging.formatter import (
    format_match_signals,
    format_stats_summary_player,
    format_stats_summary_team,
)
from messaging.sender import DiscordSender

COT = ZoneInfo("America/Bogota")
SCAN_WINDOW_MINUTES = 60


class BettingBotOrchestrator:
    def __init__(self, selected_leagues: dict = None):
        self.sofascore = SofaScoreScraper()
        self.rushbet   = RushbetScraper()
        self.odds_api  = OddsApiScraper()
        self.analyzer  = BetAnalyzer()
        self.discord   = DiscordSender()
        self.leagues   = selected_leagues if selected_leagues else LEAGUES
        # Estos se setean desde main.py cuando se usa Discord
        self.discord_client     = None
        self.discord_channel_id = None

    # ══════════════════════════════════════════════════════════════════════════
    #  FUNCIÓN SEND UNIFICADA
    #  Dependiendo del modo (terminal vs Discord command) usa el canal correcto
    # ══════════════════════════════════════════════════════════════════════════

    def _make_sender(self, channel=None):
        """
        Retorna una función send() apropiada según el modo de ejecución.
        - Si hay channel (modo Discord command): envía directo al canal
        - Si no (modo terminal): usa self.discord
        """
        if channel:
            async def send(msg: str):
                if len(msg) <= 2000:
                    await channel.send(msg)
                else:
                    lines = msg.split("\n")
                    chunk = ""
                    for line in lines:
                        if len(chunk) + len(line) + 1 > 1990:
                            await channel.send(chunk)
                            await asyncio.sleep(0.3)
                            chunk = line
                        else:
                            chunk += ("\n" if chunk else "") + line
                    if chunk:
                        await channel.send(chunk)
        else:
            async def send(msg: str):
                await self.discord.send_message(msg)

        return send

    # ══════════════════════════════════════════════════════════════════════════
    #  ENTRADAS — modo terminal y modo Discord command
    # ══════════════════════════════════════════════════════════════════════════

    async def run(self):
        """Modo terminal — arranca su propio cliente Discord."""
        now_utc    = datetime.now(timezone.utc)
        window_end = now_utc + timedelta(minutes=SCAN_WINDOW_MINUTES)
        now_col    = now_utc.astimezone(COT)
        end_col    = window_end.astimezone(COT)

        print(f"\n{'='*50}")
        print(f"  Ventana: {now_col.strftime('%H:%M')} → {end_col.strftime('%H:%M')} COT")
        print(f"{'='*50}\n")

        await self.discord.start()
        send = self._make_sender()

        try:
            await self._run_analysis(now_utc, window_end, now_col, end_col, send)
        finally:
            await self.rushbet.close()
            await self.odds_api.close()
            await self.discord.close()

    async def run_from_discord(self):
        """Modo Discord command — usa el bot ya conectado."""
        now_utc    = datetime.now(timezone.utc)
        window_end = now_utc + timedelta(minutes=SCAN_WINDOW_MINUTES)
        now_col    = now_utc.astimezone(COT)
        end_col    = window_end.astimezone(COT)

        channel = self.discord_client.get_channel(self.discord_channel_id)
        send    = self._make_sender(channel)

        try:
            await self._run_analysis(now_utc, window_end, now_col, end_col, send)
        finally:
            await self.rushbet.close()
            await self.odds_api.close()

    # ══════════════════════════════════════════════════════════════════════════
    #  ANÁLISIS PRINCIPAL — único, compartido por ambos modos
    # ══════════════════════════════════════════════════════════════════════════

    async def _run_analysis(
        self,
        now_utc:    datetime,
        window_end: datetime,
        now_col:    datetime,
        end_col:    datetime,
        send:       Callable,
    ):
        source_label = "The Odds API" if ODDS_SOURCE == "odds_api" else "Rushbet/Kambi"
        ligas = ", ".join(cfg["name"] for cfg in self.leagues.values())

        await send(
            "```\n"
            "╔══════════════════════════════════════╗\n"
            "║       BOT DE SENALES INICIADO        ║\n"
            "╚══════════════════════════════════════╝\n"
            "```\n"
            f"Fecha: {now_col.strftime('%d/%m/%Y')}\n"
            f"Buscando partidos: `{now_col.strftime('%H:%M')}` → `{end_col.strftime('%H:%M')}` COT\n"
            f"Fuente: {source_label} | Rango: 1.50 - 1.80\n"
            f"Ligas: {ligas}\n\n"
            f"_Analizando..._"
        )

        # 1. Cuotas
        print(f"[Bot] Obteniendo cuotas ({ODDS_SOURCE})...")
        if ODDS_SOURCE == "odds_api":
            odds_by_league = await self.odds_api.scrape_all_leagues(self.leagues)
        else:
            odds_by_league = await self.rushbet.scrape_all_leagues(self.leagues)

        # 2. Partidos de SofaScore
        print("[Bot] Obteniendo partidos de SofaScore...")
        sofa_by_league = {}
        for league_key, league_cfg in self.leagues.items():
            events = await self.sofascore.get_todays_events(
                league_cfg["sofascore_id"], league_cfg["sport"]
            )
            sofa_by_league[league_key] = events
            await asyncio.sleep(0.5)

        # 3. Cruzar y filtrar ventana — con logs de debug
        matched = []
        for league_key, odds_events in odds_by_league.items():
            league_cfg  = self.leagues[league_key]
            sofa_events = sofa_by_league.get(league_key, [])

            print(f"\n[Debug] {league_cfg['name']} — OddsAPI: {len(odds_events)} eventos | SofaScore: {len(sofa_events)} eventos")

            for oe in odds_events:
                print(f"[Debug]   OddsAPI  : {oe.get('home_team')} vs {oe.get('away_team')} — {oe.get('start_time')}")
            for se in sofa_events:
                print(f"[Debug]   SofaScore: {se['home_team']} vs {se['away_team']} — {se['start_time']}")

            for odds_event in odds_events:
                sofa_event = self._match_event(odds_event, sofa_events)

                if sofa_event is None:
                    print(f"[Debug]   SIN MATCH: {odds_event.get('home_team')} vs {odds_event.get('away_team')}")
                    continue

                start_time = sofa_event["start_time"]
                in_window  = now_utc <= start_time <= window_end
                mins       = int((start_time - now_utc).total_seconds() / 60)

                print(f"[Debug]   MATCH: {sofa_event['event_name']}")
                print(f"[Debug]   start_time={start_time} | now_utc={now_utc} | window_end={window_end}")
                print(f"[Debug]   En ventana: {in_window} | Faltan: {mins} min")

                if not in_window:
                    continue

                hora_col = start_time.astimezone(COT).strftime("%H:%M")
                await send(
                    f"Partido encontrado: **{sofa_event['event_name']}**\n"
                    f"En {mins} min — `{hora_col}` COT — {league_cfg['name']}"
                )
                matched.append({
                    "league_key": league_key,
                    "league_cfg": league_cfg,
                    "sofa_event": sofa_event,
                    "odds_event": odds_event,
                })

        if not matched:
            print("[Bot] No se encontraron partidos en la proxima hora.")
            await send("No se encontraron partidos en la proxima hora.")
            await send(
                f"Sin senales — {datetime.now(COT).strftime('%H:%M')} COT\n"
                "No hubo apuestas que cumplieran los criterios."
            )
            return

        await send(f"**{len(matched)} partido(s)** encontrado(s). Analizando mercados...")
        print(f"\n[Bot] {len(matched)} partido(s). Analizando...\n")

        # 4. Analizar cada partido
        total = 0
        for item in matched:
            total += await self._analyze_and_send(
                item["league_key"], item["league_cfg"],
                item["sofa_event"], item["odds_event"], send
            )

        # 5. Resumen final
        now_col_fin = datetime.now(COT)
        if total == 0:
            await send(f"Sin senales validas — {now_col_fin.strftime('%H:%M')} COT")
        else:
            await send(f"Analisis completo — **{total}** senal(es) enviada(s) — {now_col_fin.strftime('%H:%M')} COT")

        print(f"[Bot] Finalizado. {total} senal(es) enviada(s).")

    # ══════════════════════════════════════════════════════════════════════════
    #  ANÁLISIS DE UN PARTIDO
    # ══════════════════════════════════════════════════════════════════════════

    async def _analyze_and_send(
        self,
        league_key: str,
        league_cfg: dict,
        sofa_event: dict,
        odds_event: dict,
        send: Callable,
    ) -> int:
        event_id   = sofa_event["id"]
        sport      = league_cfg["sport"]
        start_time = sofa_event["start_time"]
        event_name = sofa_event["event_name"]

        print(f"\n[Bot] Analizando: {event_name}")

        lineups = await self.sofascore.get_lineups(event_id)
        await asyncio.sleep(0.4)
        confirmed = {
            p["name"].lower(): p
            for side in ("home", "away")
            for p in lineups.get(side, [])
            if p.get("in_starting_eleven")
        }
        print(f"[Bot] Alineaciones: {len(confirmed)} jugadores confirmados")

        home_id  = sofa_event.get("home_team_id")
        away_id  = sofa_event.get("away_team_id")
        tourn_id = sofa_event.get("tournament_id")

        home_games = await self.sofascore.get_team_last_games(home_id, tourn_id) if home_id else []
        await asyncio.sleep(0.3)
        away_games = await self.sofascore.get_team_last_games(away_id, tourn_id) if away_id else []
        await asyncio.sleep(0.3)
        h2h_games = await self.sofascore.get_h2h(event_id)
        await asyncio.sleep(0.3)

        signals = []

        for market_key, market_info in odds_event.get("markets", {}).items():
            odds = market_info["odds"]
            if not (ODDS_MIN <= odds <= ODDS_MAX):
                continue

            line        = market_info.get("line")
            participant = market_info.get("participant", "")

            parsed = parse_rushbet_market(
                market_info["market"], market_info["label"], line, participant
            )
            if not parsed:
                continue

            signal = None

            if parsed["market_type"] == "player":
                player_name = parsed.get("player_name", "")
                if confirmed and player_name.lower() not in confirmed:
                    continue
                player_id = self._find_player_id(player_name, lineups)
                if not player_id:
                    continue
                last_games_raw = await self.sofascore.get_player_last_games(player_id, sport)
                season_stats   = await self.sofascore.get_player_statistics(player_id, sport)
                await asyncio.sleep(0.3)
                last_vals  = [v for v in (parsed["extractor"](g) for g in last_games_raw) if v is not None]
                season_avg = self._get_season_avg(season_stats, parsed["stat_key"])
                if season_avg is None or line is None:
                    continue
                is_home  = any(p["name"].lower() == player_name.lower() for p in lineups.get("home", []))
                analysis = self.analyzer.analyze_player_line(
                    line=line, stat_key=parsed["stat_key"],
                    last_games_stats=last_vals, season_average=season_avg,
                    is_home=is_home, sport=sport
                )
                if analysis:
                    signal = {
                        "market":         parsed["display_name"],
                        "odds":           odds,
                        "bet_type_label": analysis["bet_type_label"],
                        "stake_label":    analysis["stake_label"],
                        "stats_summary":  format_stats_summary_player(
                            analysis, player_name, line, parsed["display_name"]
                        ),
                    }

            elif parsed["market_type"] == "team":
                analysis = self.analyzer.analyze_team_market(
                    line=line, market_name=parsed["display_name"],
                    home_last_games=home_games, away_last_games=away_games,
                    h2h_games=h2h_games, stat_extractor=parsed["extractor"], sport=sport
                )
                if analysis:
                    signal = {
                        "market":         parsed["display_name"],
                        "odds":           odds,
                        "bet_type_label": analysis["bet_type_label"],
                        "stake_label":    analysis["stake_label"],
                        "stats_summary":  format_stats_summary_team(
                            analysis, parsed["display_name"]
                        ),
                    }

            if signal:
                signals.append(signal)

        order = {"TIPO 3": 0, "TIPO 2": 1, "TIPO 1": 2}
        signals.sort(key=lambda s: order.get(s["bet_type_label"], 99))

        if signals:
            msg = format_match_signals(
                league_key=league_key, event_name=event_name,
                start_time=start_time, sport=sport, signals=signals
            )
            await send(msg)
            print(f"[Bot] {len(signals)} senal(es) para {event_name}")
        else:
            print(f"[Bot] Sin senales para {event_name}")

        return len(signals)

    # ══════════════════════════════════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _match_event(self, odds_event: dict, sofa_events: list) -> Optional[dict]:
        rb_home = odds_event.get("home_team", "").lower().strip()
        rb_away = odds_event.get("away_team", "").lower().strip()
        best, best_score = None, 0
        for se in sofa_events:
            score = (
                self._name_overlap(rb_home, se["home_team"].lower()) +
                self._name_overlap(rb_away, se["away_team"].lower())
            )
            if score > best_score:
                best_score, best = score, se
        return best if best_score >= 0.5 else None

    def _name_overlap(self, a: str, b: str) -> float:
        wa, wb = set(a.split()), set(b.split())
        if not wa or not wb:
            return 0.0
        return len(wa & wb) / max(len(wa), len(wb))

    def _find_player_id(self, player_name: str, lineups: dict) -> Optional[int]:
        name_lower = player_name.lower()
        for side in ("home", "away"):
            for p in lineups.get(side, []):
                if name_lower in p["name"].lower() or p["name"].lower() in name_lower:
                    return p.get("id")
        return None

    def _get_season_avg(self, season_stats: dict, stat_key: str) -> Optional[float]:
        sofa_key = SEASON_AVG_KEYS.get(stat_key)
        if sofa_key is None:
            if stat_key == "pra":
                p = season_stats.get("points")
                r = season_stats.get("rebounds")
                a = season_stats.get("assists")
                if all(x is not None for x in [p, r, a]):
                    return float(p + r + a)
            return None
        val = season_stats.get(sofa_key) or season_stats.get(stat_key)
        return float(val) if val is not None else None
