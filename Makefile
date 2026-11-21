.PHONY: install test demo evals

install:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"

test:
	.venv/bin/python -m pytest -q

demo:
	.venv/bin/python -m agent_support_resolution.demo

evals:
	.venv/bin/python -m agent_support_resolution.evals
