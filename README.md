
# PairingIQ Full-Stack MVP

A deployable airline pairing-ranking web application.

## Features

- Server-side PDF, HTML, TXT, and CSV upload
- Persistent preference profiles
- SQLite analysis history
- Generic pairing extraction
- Configurable city, aircraft, redeye, transfer, and deadhead scoring
- Ranked results
- CSV export
- Responsive mobile interface
- Docker deployment

## Run locally

### Python

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://localhost:8000`.

### Docker

```bash
docker compose up --build
```

Open `http://localhost:8000`.

## Deploy

This repository can be deployed to Render, Railway, Fly.io, DigitalOcean App Platform, Google Cloud Run, AWS, Azure, or any Docker-compatible host.

Set the web service command to:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Persist the `/app/data` directory if you want profile and analysis history to survive redeployments.

## Current limitations

The parser is intentionally generic. Airline bid packages differ substantially, so production quality requires airline-specific parsers.

A production roadmap would add:

- Delta, American, United, Southwest, and Alaska package adapters
- Reliable duty-day and layover extraction
- Hotel and layover-duration interpretation
- Productive vs. heavy-recovery redeye classification
- Calendar and legality checks
- Composite-bid and award-file parsing
- Awardability estimates by seniority
- User authentication
- Cloud object storage
- Encrypted private uploads
- AI-assisted format detection
