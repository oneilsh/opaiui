# a generic Makefile for developing a python package with uv
# usage: make <target>
# default target is 


default: install test

install:
	uv pip install -e .

test:
	@echo "\n\n"
	@uv run python test.py
