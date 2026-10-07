VENV   := venv
PYTHON := $(VENV)/bin/python
PIP    := $(VENV)/bin/pip

.PHONY: help install env download console dev start clean

help:
	@echo "make install   - crée le venv et installe les dépendances"
	@echo "make env       - crée .env à partir de .env.example"
	@echo "make download  - télécharge les modèles locaux (VAD, etc.)"
	@echo "make console   - lance Miki dans le terminal (micro + haut-parleur)"
	@echo "make dev       - lance l'agent en mode dev (LiveKit)"
	@echo "make clean     - supprime venv, caches et sessions"

$(VENV)/bin/activate: requirements.txt
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	touch $(VENV)/bin/activate

install: $(VENV)/bin/activate

env:
	@test -f .env && echo ".env existe déjà" || (cp .env.example .env && echo ".env créé, remplis les clés")

download: install
	$(PYTHON) agent.py download-files

console: install
	$(PYTHON) agent.py console

dev: install
	$(PYTHON) agent.py dev

start: install
	$(PYTHON) agent.py start

clean:
	rm -rf $(VENV) __pycache__ sessions
