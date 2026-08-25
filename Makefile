.PHONY: test backend frontend

test:
	cd backend && pytest

backend:
	cd backend && uvicorn app.main:app --reload

frontend:
	cd frontend && npm run dev
