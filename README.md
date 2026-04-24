# 🎯 Bot de Apuestas Deportivas → Discord

Bot automatizado que escanea cuotas en Rushbet (1.50–1.70), valida con estadísticas de SofaScore, y envía señales a Discord **50 minutos antes** de cada partido.

## Ligas soportadas
- ⚽ Premier League, La Liga, Bundesliga, Serie A, Ligue 1
- 🏀 NBA

## Cómo funciona

```
Cada 10 minutos:
  1. Rushbet API  → Cuotas 1.50–1.70 de todas las ligas
  2. SofaScore API → Partidos del día + estadísticas
  3. Analiza cada mercado:
       - ¿El promedio de temporada supera la línea?
       - ¿% de últimos partidos donde cumplió? (últimos 10)
       - ¿H2H esta temporada?
       - ¿Rendimiento local/visitante?
  4. Clasifica → Tipo 1 / 2 / 3
  5. 50 min antes del partido → envía señal a Discord
     (agrupa todos los mercados del mismo partido en un solo mensaje)
```

## Clasificación de apuestas

| Tipo | Probabilidad histórica | Stake |
|------|----------------------|-------|
| 🟡 Tipo 1 | ≥ 40% | 1% del bankroll |
| 🟠 Tipo 2 | ≥ 55% | 2% del bankroll |
| 🟢 Tipo 3 | ≥ 70% | 3% del bankroll |

## Instalación

```bash
# 1. Clonar / descomprimir el proyecto
cd betting-bot

# 2. Crear entorno virtual
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar
nano config/settings.py
# → DISCORD_BOT_TOKEN = "tu_token_aqui"
# → DISCORD_CHANNEL_ID = tu_canal_id
# → BANKROLL = tu_capital_en_USD
```

## Crear bot de Discord

1. Ve a https://discord.com/developers/applications
2. **New Application** → dale nombre → **Bot** → **Add Bot**
3. Copia el **Token** → pégalo en `DISCORD_BOT_TOKEN`
4. En **OAuth2 → URL Generator**: selecciona `bot` + permiso `Send Messages`
5. Usa la URL generada para invitar el bot a tu servidor
6. Clic derecho en tu canal → **Copiar ID** → pégalo en `DISCORD_CHANNEL_ID`

## Ejecutar

```bash
python main.py
```

Para correr en background (Linux):
```bash
nohup python main.py > bot.log 2>&1 &
```

## Estructura del proyecto

```
betting-bot/
├── main.py                    ← Punto de entrada
├── orchestrator.py            ← Coordinador principal
├── requirements.txt
├── config/
│   └── settings.py            ← ⚙️ Configuración (token, bankroll, ligas)
├── scrapers/
│   ├── sofascore.py           ← Stats de jugadores y equipos
│   └── rushbet.py             ← Cuotas en rango 1.50–1.70
├── analyzers/
│   ├── bet_analyzer.py        ← Motor de clasificación Tipo 1/2/3
│   └── market_parser.py       ← Mapeo mercados Rushbet ↔ SofaScore
└── discord/
    ├── sender.py              ← Envío de mensajes
    └── formatter.py           ← Formato de señales
```

## Ejemplo de señal en Discord

```
╔══════════════════════════════╗
║  ⚽  SEÑAL DE APUESTA  ⚽         ║
╚══════════════════════════════╝

🏆 Liga: La Liga 🇪🇸
🆚 Evento: Real Madrid vs Barcelona
🕐 Hora: 02:45 PM (🇨🇴 COT)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 Señal #1
📊 Mercado: Total Goles +2.5
💰 Cuota: 1.65
  🟢 TIPO 3
💵 Apostar: $3.0 USD

📈 Estadísticas:
  🏠 Local cumplió: 70%
  ✈️  Visitante cumplió: 80%
  🔁 H2H directo: 75%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 Señal #2
📊 Mercado: Vinicius Jr - Tiros a puerta +1.5
💰 Cuota: 1.60
  🟠 TIPO 2
💵 Apostar: $2.0 USD

📈 Estadísticas:
  👤 Vinicius Jr
  📏 Línea: 1.5 Tiros a puerta +1.5
  📅 Promedio temporada: 2.3
  🔥 Promedio últimos 5 partidos: 2.1
  ✅ Éxito reciente: 60%
  🔁 H2H este año: 67%
  📋 Últimos: 2 | 3 | 1 | 2 | 3
```

## Notas importantes

- **Rushbet Kambi API**: Es pública pero puede cambiar. Si falla, revisa la URL en DevTools del navegador.
- **SofaScore**: API pública, sin key requerida. Límite de cortesía: el bot tiene delays entre requests.
- **Alineaciones**: SofaScore publica alineaciones ~60 min antes. El bot las verifica para filtrar jugadores no convocados.
- **Ajusta el BANKROLL** en `settings.py` según tu capital real.
