.PHONY: run migrate seed lint test

run:
docker compose up --build

migrate:
docker compose run --rm bot alembic upgrade head

seed:
docker compose run --rm bot python -m app.scripts.seed

lint:
docker compose run --rm bot python -m compileall app

test:
docker compose run --rm bot pytest
