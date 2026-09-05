.PHONY: install check build test

install:
	python -m pip install -r requirements.lock
	python -m pip install --no-deps -e .

check:
	digital-sztu check --json

build:
	digital-sztu build --json

test:
	python -m unittest discover -s tests
