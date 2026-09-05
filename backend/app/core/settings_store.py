"""In-memory runtime settings — survives the request lifecycle but not a
server restart. Lets admins tune operational knobs (e.g. the HITL confidence
threshold) without a code deploy or DB migration."""

_store: dict[str, object] = {
    "hitl_confidence_threshold": 0.5,
}


def get_hitl_threshold() -> float:
    return float(_store["hitl_confidence_threshold"])


def set_hitl_threshold(value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError("Threshold must be between 0.0 and 1.0")
    _store["hitl_confidence_threshold"] = value


def get_all_settings() -> dict[str, object]:
    return dict(_store)
