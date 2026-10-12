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

```bash
python main.py
```

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
