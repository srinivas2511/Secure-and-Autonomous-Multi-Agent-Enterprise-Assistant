"""DB-backed runtime settings.

Replaces the in-memory dict — changes survive restarts and work across
multiple backend instances.  Falls back to the hard-coded default if the
DB row doesn't exist yet (e.g. on first boot before the table is seeded).
"""

from sqlalchemy.orm import Session

from app.core.database import SessionLocal

_DEFAULTS: dict[str, str] = {
    "hitl_confidence_threshold": "0.5",
}


def _get_db_value(key: str) -> str | None:
    db: Session = SessionLocal()
    try:
        from app.models.system_setting import SystemSetting

        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        return row.value if row else None
    except Exception:
        return None
    finally:
        db.close()


def _set_db_value(key: str, value: str) -> None:
    db: Session = SessionLocal()
    try:
        from app.models.system_setting import SystemSetting

        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if row:
            row.value = value
        else:
            db.add(SystemSetting(key=key, value=value))
        db.commit()
    finally:
        db.close()


def get_hitl_threshold() -> float:
    raw = _get_db_value("hitl_confidence_threshold")
    if raw is None:
        raw = _DEFAULTS["hitl_confidence_threshold"]
    return float(raw)


def set_hitl_threshold(value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError("Threshold must be between 0.0 and 1.0")
    _set_db_value("hitl_confidence_threshold", str(value))


def get_all_settings() -> dict[str, object]:
    return {"hitl_confidence_threshold": get_hitl_threshold()}
