from collections.abc import Generator

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from config import DATA_DIR, DB_PATH, DEFAULT_SETTINGS, DIGESTS_DIR
from models import AppSetting, SourceConfig

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DIGESTS_DIR.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)
    _ensure_defaults()


def _ensure_defaults() -> None:
    from sources import SOURCES

    with Session(engine) as session:
        for key, value in DEFAULT_SETTINGS.items():
            existing = session.get(AppSetting, key)
            if existing is None:
                session.add(AppSetting(key=key, value=value))

        for source_id in SOURCES:
            row = session.exec(
                select(SourceConfig).where(SourceConfig.source_id == source_id)
            ).first()
            if row is None:
                session.add(
                    SourceConfig(
                        source_id=source_id,
                        is_active=source_id == DEFAULT_SETTINGS["active_source_id"],
                        config_json="{}",
                    )
                )
        session.commit()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def get_settings_map(session: Session) -> dict[str, str]:
    rows = session.exec(select(AppSetting)).all()
    merged = dict(DEFAULT_SETTINGS)
    merged.update({row.key: row.value for row in rows})
    return merged
