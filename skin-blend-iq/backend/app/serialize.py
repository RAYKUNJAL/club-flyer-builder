from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import inspect


def to_dict(row, exclude: tuple[str, ...] = ()) -> dict:
    out = {}
    for col in inspect(row).mapper.column_attrs:
        if col.key in exclude:
            continue
        v = getattr(row, col.key)
        if isinstance(v, (datetime, date)):
            v = v.isoformat()
        out[col.key] = v
    return out
