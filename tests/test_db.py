from sqlalchemy import create_engine, text

from app.db import configure_sqlite_foreign_keys


def test_sqlite_application_connections_enable_foreign_keys(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'foreign-keys.db'}")
    configure_sqlite_foreign_keys(engine)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
    finally:
        engine.dispose()
