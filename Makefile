.PHONY: install test demo verify verify-quickstart demo-docker
install:
	pip install -e ".[dev]"
test:
	pytest -q
verify-quickstart:
	python scripts/verify_quickstart.py
verify:
	python scripts/verify_demo.py
demo:
	python scripts/run_demo.py
demo-docker:
	docker compose up --build
