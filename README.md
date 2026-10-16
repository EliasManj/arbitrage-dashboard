# ligamx-arbitrage

## Setup

### 1. Create virtual environment

```bash
python3 -m venv .venv
```

### 2. Activate virtual environment

```bash
source .venv/bin/activate
```

### 3. Upgrade pip

```bash
pip install --upgrade pip
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

## Running

### CLI (console output)

```bash
python main.py
```

### Web Dashboard (API + UI)

Start the API server:

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8080
```

Then open [http://localhost:8080](http://localhost:8080) in your browser.

The API fetches all bookmakers and runs analysis automatically on startup, then refreshes every 5 minutes. You can also trigger a manual refresh from the dashboard UI.

**Additional options:**

| Flag | Description |
|------|-------------|
| `--reload` | Auto-restart on code changes (development only) |
| `--port 8080` | Change the port |

**API endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/results` | Latest analysis results (JSON) |
| `POST` | `/api/refresh` | Trigger an immediate refresh |
| `GET` | `/docs` | Interactive API docs (Swagger UI) |

## Correlation betting

The project now includes a conservative correlation-bet pass that:

- groups bookmaker data by fixture,
- builds the best available odds for each compatible market outcome,
- combines logically related markets such as home win + over goals or home win + BTTS,
- computes a no-vig joint fair probability with a modest positive-correlation adjustment,
- keeps only combinations with a positive expected edge.

This is a heuristic layer on top of the existing arbitrage and +EV scans, intended for positive-edge correlated multi-leg bets rather than pure arbitrage.

## Deactivate virtual environment

```bash
deactivate
```

Skill	Purpose
design-taste-frontend	Main design taste skill (v2)
design-taste-frontend-v1	Pinned v1 version
gpt-taste	GPT-style taste guidance
high-end-visual-design	High-end UI design
minimalist-ui	Minimalist UI style
industrial-brutalist-ui	Brutalist UI style
image-to-code	Convert images to code
imagegen-frontend-web	Web image generation
imagegen-frontend-mobile	Mobile image generation
brandkit	Brand kit generation
redesign-existing-projects	UI redesign
stitch-design-taste	Stitching design patterns
full-output-enforcement	Full output mode
