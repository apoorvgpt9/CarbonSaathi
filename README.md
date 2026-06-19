# CarbonSaathi 🌱

> Your carbon companion, not your carbon scolder.

A personal AI companion that helps Indian metro professionals track and reduce their everyday carbon footprint through natural-language activity logging, state-aware emission calculation, and visible AI reasoning.

## Status
🚧 Under active development for PromptWars Challenge 3.

## Stack
Python 3.13 · FastAPI · Firebase Auth · Firestore · Gemini 2.5 · Cloud Run

## Decisions
See [DECISIONS.md](./DECISIONS.md) for full project context.

## Local Development

### Prerequisites
- Python 3.13.7
- Docker (optional, for container builds)

### Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
cp .env.example .env
# Edit .env and add your real values
```

### Run
```bash
make run            # uvicorn dev server on :8080
make test           # tests + coverage
make all            # full quality sweep
make docker-build   # local container build
make docker-run     # run container locally
```

## License
MIT
