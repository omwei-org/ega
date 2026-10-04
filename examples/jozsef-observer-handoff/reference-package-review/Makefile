.PHONY: test validate generate fixtures

test: validate

validate:
	python scripts/validate_all.py

generate:
	python scripts/generate_golden_evidence.py

fixtures:
	python scripts/generate_fixtures.py
