# Steg-för-steg-guide: Aktiescanner med Telegram-notiser

Detta är ett gratis, automatiserat Python-skript som:

1. Bygger en tickerlista - som standard **hela NASDAQ-100** (hämtas dynamiskt från Wikipedia, cachas lokalt i 24h), plus eventuella egna tickers du lägger till.
2. Hämtar OHLCV-data via `yfinance` för varje ticker, batchvis, på tidsramarna 1h, 2h, 4h och 1d.
3. Analyserar varje tidsram för **demand zones**, **stigande trendlinjer** (higher lows) och **Fair Value Gaps (FVG)**.
4. Väljer, per ticker, den tidsram/setup där nuvarande pris ligger närmast en relevant nivå.
5. Ritar en candlestick-graf i "chart analysis"-stil med setupen markerad och sparar den som PNG.
6. Skickar grafen + en kort 3-punktsanalys (inklusive nästa earnings-datum) till en Telegram-chatt - för **varje** ticker som har en tydlig setup, inte bara en handfull.

Filstruktur:

```
stock_scanner/
├── config.py          # Universum (NASDAQ-100/egen lista), tidsramar, Telegram, analysparametrar
├── universe.py         # Bygger tickerlistan (dynamisk NASDAQ-100 + cache + fallback)
├── data_fetcher.py     # Batch-hämtning av OHLCV-data + earnings-datum/bolagsnamn (yfinance)
├── analysis.py         # Demand zones, trendlinjer, FVG, scoring/urval
├── charting.py         # Ritar och sparar candlestick-grafer (mplfinance + matplotlib)
├── telegram_bot.py      # Skickar bild + text till Telegram
├── main.py              # Kör hela flödet, en gång eller i loop
├── requirements.txt
└── .env.example
```

---

## 1. Sätt upp virtuell miljö

Kräver Python 3.10+ (helst 3.11/3.12).

```bash
cd stock_scanner
python3 -m venv venv

# Aktivera miljön
source venv/bin/activate          # macOS/Linux
venv\Scripts\activate              # Windows (PowerShell/cmd)
```

## 2. Installera paket

```bash
pip install -r requirements.txt
```

Detta installerar `yfinance`, `pandas`, `numpy`, `mplfinance`, `python-telegram-bot` och `python-dotenv`.

## 3. Skapa en Telegram-bot

1. Öppna Telegram och sök upp **@BotFather**.
2. Skicka `/newbot` och följ instruktionerna (välj namn och ett unikt användarnamn som slutar på `bot`).
3. BotFather ger dig en **bot-token**, t.ex. `123456789:AAExampleToken...`. Spara den.

## 4. Hämta ditt chat-ID

Enklaste sättet:

1. Starta en konversation med din nya bot i Telegram (sök upp den och tryck **Start**).
2. Skicka ett valfritt meddelande till boten.
3. Öppna följande URL i en webbläsare (ersätt `<TOKEN>` med din bot-token):

   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```

4. Leta i JSON-svaret efter `"chat":{"id": ...}` — det numret är ditt `TELEGRAM_CHAT_ID`.

   Vill du skicka till en grupp istället för dig själv: lägg till boten i gruppen, skicka ett meddelande i gruppen, och `chat.id` blir då gruppens (oftast negativa) ID.

## 5. Skapa en `.env`-fil

Kopiera exempelfilen och fyll i dina uppgifter:

```bash
cp .env.example .env
```

Redigera `.env`:

```
TELEGRAM_BOT_TOKEN=123456789:AAExampleToken...
TELEGRAM_CHAT_ID=123456789
```

`config.py` läser automatiskt in dessa värden via `python-dotenv`.

## 6. Anpassa vilka aktier som bevakas

Som standard scannar skriptet **hela NASDAQ-100** — listan hämtas automatiskt från Wikipedia vid varje körning (cachad i 24h i `nasdaq100_cache.json` så du inte gör onödiga anrop) och innehåller normalt ~100 tickers. I `config.py`:

```python
UNIVERSE = "nasdaq100"   # eller "custom" för att bara använda TICKERS nedan
TICKERS = ["NVDA", "CRWD", "DAL", "NET", "MU"]   # används bara om UNIVERSE == "custom"
EXTRA_TICKERS = ["DAL"]   # läggs alltid till, oavsett UNIVERSE (t.ex. aktier utanför NASDAQ-100)
LIMIT_UNIVERSE = None      # sätt t.ex. till 15 för snabba testkörningar
```

Vill du bara bevaka dina egna aktier (som i den ursprungliga versionen): sätt `UNIVERSE = "custom"` och fyll i `TICKERS`.

Om Wikipedia inte går att nå faller skriptet automatiskt tillbaka på en inbyggd (ungefärlig) NASDAQ-100-lista i `universe.py`, så scannern fortsätter fungera även om hämtningen misslyckas.

Du kan också justera analysparametrarna längre ner i `config.py`, t.ex.:

- `ZONE_MIN_IMPULSE_PCT` — hur stor rörelsen upp från en bas minst måste vara för att räknas som en demand zone (default 3 %).
- `PROXIMITY_ATR_MULT` — hur nära (i ATR) priset måste vara en nivå för att en setup ska räknas som "aktuell" (default 1.5x ATR). Höj den om du vill se fler (men mindre precisa) notiser när du scannar hela NASDAQ-100.
- `FVG_MIN_GAP_PCT` — minsta gap-storlek för att en FVG ska räknas (filtrerar brus).
- `BATCH_CHUNK_SIZE` / `BATCH_SLEEP_SECONDS` — hur många tickers som hämtas per Yahoo-anrop och paustiden mellan dem. Sänk `BATCH_CHUNK_SIZE` eller höj pausen om du får rate limit-fel från Yahoo när du scannar en stor lista.

## 7. Kör skriptet

**En engångskörning** (rekommenderas första gången, för att verifiera att allt fungerar):

```bash
python main.py
```

Skriptet bygger tickerlistan (NASDAQ-100 som standard), hämtar data batchvis för alla tickers och alla tidsramar, skriver ut i terminalen vilken setup som hittades för varje aktie, och skickar en bild + text till Telegram för **varje** ticker där en tydlig setup finns. En full NASDAQ-100-scan tar normalt någon minut, mest beroende på hur snabbt Yahoo Finance svarar.

Tips för första testkörningen: sätt `LIMIT_UNIVERSE = 10` i `config.py` så går det snabbare att verifiera att allt fungerar innan du kör mot hela listan.

Om `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` saknas eller är fel skriver skriptet ut en varning i terminalen istället för att krascha, så du kan testa analysdelen separat.

**Kontinuerlig körning** (skriptet sköter sin egen loop, t.ex. varje timme):

```bash
python main.py --loop --interval-minutes 60
```

Avbryt med `Ctrl+C`.

## 8. Schemalägg körningen (alternativ till `--loop`)

### macOS/Linux (cron)

```bash
crontab -e
```

Lägg till en rad för att köra varje timme under handelstid (exempel, justera efter din tidszon):

```
0 * * * * cd /full/sokvag/till/stock_scanner && venv/bin/python main.py >> scanner.log 2>&1
```

### Windows (Task Scheduler)

1. Öppna **Task Scheduler** → **Create Basic Task**.
2. Ställ in trigger (t.ex. varje timme).
3. Action: **Start a program**, peka på `venv\Scripts\python.exe` i din `stock_scanner`-mapp, med argument `main.py` och "Start in" satt till mappens sökväg.

## 9. Felsökning

- **"Ingen data för tidsram..."** — yfinance kan tillfälligt ha problem eller tickern kan sakna data för viss upplösning (t.ex. har vissa mindre aktier ingen 60m-historik längre än ~1 månad tillbaka, vilket är en begränsning i Yahoo Finance, inte i skriptet).
- **Inget skickas till Telegram** — kontrollera att `.env`-filen finns i samma mapp som du kör `python main.py` ifrån, och att token/chat-ID är korrekta (testa `getUpdates`-URL:en igen).
- **Ingen setup hittas för någon ticker** — det är förväntat och normalt; skriptet är medvetet konservativt (kräver att priset är nära en nivå, inom `PROXIMITY_ATR_MULT * ATR`). Höj `PROXIMITY_ATR_MULT` i `config.py` om du vill ha fler (men mindre precisa) notiser.

## 10. Cooldown och deduplicering av notiser

Utan cooldown skickas en ny Telegram-notis varje gång scannern körs och
priset fortfarande är nära samma zon — vilket lätt blir spam om du kör
scannern varje timme. Mekanismen i `notification_state.py` löser detta:

**Hur det fungerar:**

- Efter att en notis skickats för en ticker+setup-typ (t.ex. `NVDA:demand_zone`)
  sparas tidpunkten och prisnivån i `notification_state.json`.
- Nästa gång samma ticker+setup-typ hittas kontrolleras tre saker:
  1. **Har cooldown-fönstret gått ut?** (standard 6 timmar) → skicka.
  2. **Har prisnivån ändrats signifikant?** (standard ±2 % på level_low/level_high)
     → skicka, priset lämnade zonen och en ny zon identifierats.
  3. Annars → skippa och logga i terminalen.
- Byter en ticker setup-typ (t.ex. från `demand_zone` till `fvg`) behandlas
  det som en ny setup och notisen skickas alltid.

**Inställningar i `config.py`:**

```python
NOTIFICATION_COOLDOWN_HOURS = 6          # timmar tystnad efter en notis
NOTIFICATION_STATE_FILE = "notification_state.json"  # var state sparas
NOTIFICATION_LEVEL_TOLERANCE_PCT = 0.02  # 2% nivåförändring = ny zon
```

**`notification_state.json`** skapas automatiskt i projektroten vid första
körningen. Radera filen om du vill "nollställa" alla cooldowns och få alla
notiser igen vid nästa scan.

Modulen är designad defensivt: ett läs- eller skrivfel i state-filen loggas
som en varning i terminalen men kraschar aldrig hela scannen.

## 11. Kör på GitHub Actions (gratis, alltid live)

Istället för att ha en dator eller egen server igång kan du låta GitHub
köra scannern automatiskt varje timme — helt gratis för publika repon.

### Varför publikt repo?

GitHub Actions ger **obegränsade minuter** för publika repon. Dina
Telegram-hemligheter (bot-token, chat-ID) lagras krypterade i GitHub
Secrets och syns aldrig i koden, loggar eller för andra besökare — det
är säkert även i ett publikt repo.

### Steg 1: Skapa ett GitHub-repo

1. Logga in på [github.com](https://github.com) och klicka **New repository**.
2. Välj ett namn, t.ex. `stock_scanner`, och sätt det till **Public**.
3. Skapa repot tomt (utan README eller .gitignore — de finns redan lokalt).

### Steg 2: Pusha upp koden

```bash
cd stock_scanner

# Ersätt URL:en med din egen (visas på repots startsida på GitHub)
git remote add origin https://github.com/<ditt-användarnamn>/stock_scanner.git

git add .
git commit -m "Initial commit"
git push -u origin main
```

### Steg 3: Lägg in dina hemligheter

1. Gå till ditt repo på GitHub → **Settings** → **Secrets and variables**
   → **Actions** → **New repository secret**.
2. Lägg till två secrets, en åt gången:
   - **Name:** `TELEGRAM_BOT_TOKEN` — **Secret:** din bot-token
   - **Name:** `TELEGRAM_CHAT_ID`   — **Secret:** ditt chat-ID

Scannern hämtar dem via `os.getenv()` i `config.py` — ingen `.env`-fil
behövs på GitHub (och `.env` är korrekt utesluten i `.gitignore`).

### Steg 4: Verifiera att workflowen syns

Gå till **Actions**-fliken i ditt repo. Du bör se "Aktiescanner" i
listan till vänster. Om fliken är tom: vänta en minut och ladda om sidan.

### Steg 5: Trigga en manuell testkörning

1. Klicka på **"Aktiescanner"** i Actions-fliken.
2. Klicka på **"Run workflow"** → **"Run workflow"** (grön knapp).
3. Klicka på den körningen som dyker upp för att se realtidsloggar.
4. Om allt fungerar ser du Telegram-notiser komma in och ett automatiskt
   commit tillbaka av `notification_state.json`.

### Schemat

Workflowen körs varje hel timme **13:00–22:00 UTC, måndag–fredag** — det
täcker pre-market till efter after-hours oavsett om USA kör EDT (UTC-4)
eller EST (UTC-5). Vill du justera:

```yaml
# I .github/workflows/scan.yml:
- cron: "0 13-22 * * 1-5"
  #       │  │       │
  #       │  │       └─ måndag-fredag (1=mån, 5=fre)
  #       │  └─ timmar 13–22 UTC (inklusivt)
  #       └─ minut 0 (dvs. precis i hel timme)
```

Byt ut `13-22` mot t.ex. `15-20` för färre körningar, eller `0-23` för
att köra dygnet runt. Alla tider är UTC.

### Tillståndsfiler och 60-dagarsregeln

GitHub inaktiverar automatiskt schemalagda workflows om ett repo inte haft
någon aktivitet på 60 dagar. Workflowen löser detta självt: varje gång
`notification_state.json` eller `nasdaq100_cache.json` uppdateras committas
de tillbaka till repot, vilket räknas som aktivitet. Så länge marknaden är
öppen och scannern hittar setups sköter den sin egen "keep-alive".

Om du vill nollställa cooldown-historiken: ta bort `notification_state.json`
från repot och pusha, så börjar nästa körning med tomt state.

## 12. Viktigt att komma ihåg

Detta skript är ett **bevaknings- och analysverktyg**, inte ett tradingråd eller en automatiserad handelsbot — det lägger inga ordrar. All teknisk analys (demand zones, trendlinjer, FVG) är regelbaserad mönsterigenkänning och kan ge falska signaler, särskilt kring volatila händelser som earnings. Använd det som ett filter för din egen analys, inte som facit.
