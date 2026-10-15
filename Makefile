.PHONY: install test demo verify demo-docker
install:
	pip install -e ".[dev]"
test:
	pytest -q
verify:
	python scripts/verify_demo.py
demo:
	python scripts/run_demo.py
demo-docker:
	docker compose up --build
