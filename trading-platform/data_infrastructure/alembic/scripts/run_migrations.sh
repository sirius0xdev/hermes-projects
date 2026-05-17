#!/bin/bash
# Run Alembic migrations for the trading platform.
# Usage: ./run_migrations.sh or alembic upgrade head

cd "$(dirname "$0")/.."

if [ -z "$DATABASE_URL" ]; then
    export DATABASE_URL="postgresql+asyncpg://trading:trading@localhost:5432/trading_db"
fi

# Update alembic.ini with the current DATABASE_URL
python -c "
from configparser import ConfigParser
c = ConfigParser()
c.read('alembic.ini')
c.set('alembic', 'sqlalchemy.url', '${DATABASE_URL:-postgresql+asyncpg://trading:trading@localhost:5432/trading_db}')
c.write(open('alembic.ini', 'w'))
"

alembic upgrade head
