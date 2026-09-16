PY := .venv/Scripts/python.exe

.PHONY: test refresh

test:
	$(PY) -m pytest tests -q

refresh:
	$(PY) tools/refresh.py --all
