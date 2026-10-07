UV_ENV = UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python

.PHONY: setup test lint prototype test-report verify-local powerbi-build powerbi-check powerbi-check-csv profile-dry-run profile-run dbt-build airflow-up

setup:
	$(UV_ENV) uv sync --locked

test:
	$(UV_ENV) uv run --locked pytest

prototype:
	PYTHONPATH=src $(UV_ENV) uv run --locked python -m analysis.prototype

test-report:
	node tests/js/prototype.test.cjs

powerbi-build:
	PYTHONMALLOC=malloc PYTHONPATH=src $(UV_ENV) uv run --locked python -m analysis.powerbi_project

powerbi-check:
	PYTHONMALLOC=malloc PYTHONPATH=src $(UV_ENV) uv run --locked python -m analysis.powerbi_validate

powerbi-check-csv:
	PYTHONMALLOC=malloc PYTHONPATH=src $(UV_ENV) uv run --locked python -m analysis.powerbi_validate --with-csv

verify-local:
	PYTHONPATH=src $(UV_ENV) uv run --locked python -m pipeline.local_validate

lint:
	$(UV_ENV) uv run --locked ruff check src tests airflow
	$(UV_ENV) uv run --locked ruff format --check src tests airflow
	$(UV_ENV) uv run --locked sqlfluff lint sql
	$(UV_ENV) uv run --locked sqlfluff lint --ignore-local-config --config .sqlfluff --templater raw dbt/tests/fixtures
	PYTHONPATH=src $(UV_ENV) uv run --locked python -m pipeline.local_dbt_lint

profile-dry-run:
	PYTHONPATH=src $(UV_ENV) uv run --locked python -m pipeline.profile $(QUERY)

profile-run:
	PYTHONPATH=src $(UV_ENV) uv run --locked python -m pipeline.profile $(QUERY) --execute

dbt-build:
	$(UV_ENV) uv run --locked dotenv run -- uv run dbt build --project-dir dbt --profiles-dir dbt

airflow-up:
	cd airflow && LOCAL_AIRFLOW_UID=$$(id -u) astro dev start --no-browser --no-proxy --env .env.replay --settings-file replay-settings.yaml
