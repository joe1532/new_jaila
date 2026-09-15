"""Transaktionslokale Postgres-indstillinger. Nødvendigt ved connection pooling."""

from __future__ import annotations

from collections.abc import Sequence


def execute_with_local_settings(
    conn,
    settings: Sequence[str],
    sql: str,
    params,
):
    """Kør SET LOCAL og SQL i samme transaktion, derefter COMMIT hvis vi selv åbnede den.

    SET LOCAL overlever ikke autocommit-statements. Ved pooling må ef_search
    derfor aldrig sættes på session-niveau.
    """
    owned = bool(getattr(conn, "autocommit", False))
    if owned:
        conn.autocommit = False
    try:
        with conn.cursor() as cur:
            for statement in settings:
                cur.execute(statement)
            cur.execute(sql, params)
            rows = cur.fetchall()
        if owned:
            conn.commit()
        return rows
    except Exception:
        if owned:
            conn.rollback()
        raise
    finally:
        if owned:
            conn.autocommit = True
