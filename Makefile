.PHONY: fmt lint all fmt-check

fmt:
	isort .
	black .

fmt-check:
	isort --check .
	black --check .

lint:
	flake8 .
	mypy

all: fmt lint
