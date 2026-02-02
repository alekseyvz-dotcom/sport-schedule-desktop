# app/services/db_conn.py
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Any

import psycopg

from app.services.db import get_database_url


@contextmanager
def db_conn() -> Iterator[psycopg.Connection[Any]]:
    conn = psycopg.connect(get_database_url())
    try:
        yield conn
    finally:
        conn.close()
