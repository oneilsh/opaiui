.PHONY: help install dev clean build check test publish

default: help

help:
	@echo "Common development commands:"
	@echo "  make install      - Install all dependencies"
	@echo "  make dev          - Install dev dependencies (including build tools)"
	@echo "  make clean        - Remove build artifacts"
	@echo "  make build        - Build sdist and wheel"
	@echo "  make check        - Check build with twine"
	@echo "  make publish      - Upload to PyPI (live, not test)"

install:
	poetry install

dev:
	poetry install
	poetry run pip install build twine

clean:
	rm -rf dist/ build/ *.egg-info

build:
	poetry run python -m build

check:
	poetry run twine check dist/*

publish-test: build check
	@echo "Publishing to TestPyPI..."
	# Export env vars so twine picks them up
	. .env && \
	TWINE_USERNAME=__token__ TWINE_PASSWORD=$$TEST_PYPI_TOKEN poetry run twine upload --repository testpypi dist/* --skip-existing

publish: build check
	@echo "Publishing to PyPI..."
	. .env && \
	TWINE_USERNAME=__token__ TWINE_PASSWORD=$$PYPI_TOKEN poetry run twine upload dist/* --skip-existing
