# Validation record — 25 August 2026

PayPilot AI was validated as a fake-money agentic payment simulation.

## Clean-install CI validation

GitHub Actions performs a clean dependency installation using Python 3.12 and Node.js 22.

Backend validation:

```bash
pip install -r backend/requirements-dev.txt
pip check
python -m compileall -q app tests
pytest -q