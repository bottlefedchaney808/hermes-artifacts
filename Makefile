# Cross-platform: Windows spine uses .venv/Scripts, POSIX boxes .venv/bin.
UNAME_S := $(shell uname -s 2>/dev/null)
ifeq ($(UNAME_S),Windows_NT)
PY := .venv/Scripts/python.exe
else
PY := .venv/bin/python
endif

.PHONY: venv test refresh

venv:
ifeq ($(UNAME_S),Windows_NT)
	python -m venv .venv && .venv/Scripts/python.exe -m pip install -q pytest
else
	@if [ ! -x .venv/bin/python ]; then python3 -m venv .venv && .venv/bin/python -m pip install -q pytest; fi
endif

test: venv
	$(PY) -m pytest tests -q

refresh: venv
	$(PY) tools/refresh.py --all
