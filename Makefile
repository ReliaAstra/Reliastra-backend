.PHONY: help frontend backend test lint install

help:
	@echo "Reliastra monorepo"
	@echo ""
	@echo "  make install    Install frontend and backend dependencies"
	@echo "  make frontend   Run the Next.js app on :3000"
	@echo "  make backend    Run the FastAPI app on :8000"
	@echo "  make test       Run backend tests"
	@echo "  make lint       Lint frontend and backend"

install:
	cd frontend && npm install
	cd backend && pip install -r requirements.txt

frontend:
	cd frontend && npm run dev

backend:
	cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

test:
	cd backend && pytest -v

lint:
	cd frontend && npm run lint
	cd backend && python -c "import app.main; print('backend imports ok')"
