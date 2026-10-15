.PHONY: install test demo demo-docker
install:
	pip install -e ".[dev]"
test:
	pytest -q
demo:
	python scripts/run_demo.py
demo-docker:
	docker compose up --build
