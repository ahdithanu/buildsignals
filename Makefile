.PHONY: bench fallback-demo agent-status

PYTHON ?= python3

agent-status:
	$(PYTHON) scripts/agent_status.py

bench:
	python eval/bench.py

fallback-demo:
	python eval/fallback_demo.py
