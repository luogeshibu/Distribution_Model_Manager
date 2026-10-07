#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from dmm.config.constants import RMU_CHANNEL_STATUS_KEYID_OFFSET

ORACLEDB_IMPORT_ERROR = None
try:
    import oracledb
except Exception as exc:
    oracledb = None
    ORACLEDB_IMPORT_ERROR = exc


class OracleError(RuntimeError):
    pass


@dataclass
class OracleConfig:
    user: str
    password: str
    host: str
    port: int
    service_name: str


class OracleClient:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = OracleConfig(
            user=str(cfg["user"]),
            password=str(cfg["password"]),
            host=str(cfg["host"]),
            port=int(cfg.get("port", 1521)),
            service_name=str(cfg["service_name"]),
        )
        self.conn = None
        self._table_name_cache: Dict[int, str] = {}

    @property
    def dsn(self) -> str:
        return f"{self.cfg.host}:{self.cfg.port}/{self.cfg.service_name}"

    def connect(self):
        if oracledb is None:
            detail = repr(ORACLEDB_IMPORT_ERROR) if ORACLEDB_IMPORT_ERROR else "unknown import error"
            raise OracleError(
                "Oracle Python driver could not be loaded. "
                "If this is a packaged EXE, the Oracle driver dependency was not bundled correctly. "
                f"Import error: {detail}"
            )
        try:
            self.conn = oracledb.connect(
                user=self.cfg.user,
                password=self.cfg.password,
                dsn=self.dsn,
            )
            return self.conn
        except Exception as exc:
            raise OracleError(f"Oracle connection failed: {exc}") from exc

    def close(self):
        if self.conn is not None:
            try:
                self.conn.close()
            finally:
                self.conn = None

    def ensure_connected(self):
        if self.conn is None:
            self.connect()

    def _query(self, sql: str, binds=None) -> List[Dict[str, Any]]:
        self.ensure_connected()
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, binds or {})
                cols = [d[0].lower() for d in cur.description] if cur.description else []
                rows = []
                for row in cur:
                    rows.append({cols[i]: row[i] for i in range(len(cols))})
                return rows
        except Exception as exc:
            raise OracleError(f"Oracle query failed:\n{sql}\n\n{exc}") from exc

    def test_connection(self) -> str:
        rows = self._query("SELECT SYSDATE AS db_time FROM dual")
        db_time = rows[0]["db_time"] if rows else ""
        return f"Connected: {self.dsn} | DB time: {db_time}"

    def get_table_name(self, table_id: int) -> str:
        table_id = int(table_id)
        if table_id in self._table_name_cache:
            return self._table_name_cache[table_id]
        rows = self._query(
            """
            SELECT table_name_eng
            FROM sys_table_info
            WHERE table_id = :table_id
            """,
            {"table_id": table_id},
        )
        if len(rows) != 1 or not rows[0].get("table_name_eng"):
            raise OracleError(
                f"Unable to uniquely resolve table name for table_id={table_id}. "
                f"Returned rows={len(rows)}"
            )
        name = str(rows[0]["table_name_eng"]).strip()
        self._table_name_cache[table_id] = name
        return name

    def get_rmu_by_id(self, rmu_id: Any) -> Optional[Dict[str, Any]]:
        """
        Resolve dms_combined_device by ID (table 13501).

        Used when validating an already-written KeyID:
        KeyID -> device -> combined_id -> dms_combined_device -> RMU NAME.
        """
        if rmu_id in (None, ""):
            return None

        rows = self._query(
            """
            SELECT id, code, name, feeder_id, graph_name, combined_type, run_state
            FROM dms_combined_device
            WHERE id = :rmu_id
            """,
            {"rmu_id": int(rmu_id)},
        )
        if len(rows) != 1:
            return None

        row = dict(rows[0])
        row["_table_id"] = 13501
        row["_table_name"] = "dms_combined_device"
        return row

    def get_rmu_records(
        self,
        rmu_name: str,
        feeder_id: Any = None,
    ) -> List[Dict[str, Any]]:
        """Resolve RMU rows by exact NAME and, when supplied, FEEDER_ID.

        Makkah RMU association now treats the graph-topology feeder as an
        ownership boundary.  For an unlinked RMU, callers pass ``feeder_id`` so
        a same-name cabinet on another feeder can never become a candidate.
        The optional argument preserves the historical name-only lookup for
        diagnostics and existing-link inspection.
        """
        lookup_name = str(rmu_name or "").strip()
        if not lookup_name:
            return []

        where = "TRIM(name) = :rmu_name"
        binds: Dict[str, Any] = {"rmu_name": lookup_name}
        if feeder_id not in (None, ""):
            where += " AND feeder_id = :feeder_id"
            binds["feeder_id"] = int(feeder_id)

        return self._query(
            f"""
            SELECT *
            FROM dms_combined_device
            WHERE {where}
            ORDER BY id
            """,
            binds,
        )

    def update_rmu_feeder_id(
        self,
        rmu_id: Any,
        old_feeder_id: Any,
        new_feeder_id: Any,
    ) -> Dict[str, Any]:
        """Safely update one 13501 RMU FEEDER_ID using optimistic locking.

        Only ``dms_combined_device.FEEDER_ID`` is changed.  The old value must
        still equal the previewed value (including NULL), exactly one row must
        be affected, and the new value is verified before commit.
        """
        self.ensure_connected()
        rid = int(rmu_id)
        target = int(new_feeder_id)
        old = None if old_feeder_id in (None, "") else int(old_feeder_id)
        try:
            with self.conn.cursor() as cur:
                if old is None:
                    cur.execute(
                        """
                        UPDATE dms_combined_device
                        SET feeder_id = :new_feeder_id
                        WHERE id = :rmu_id
                          AND feeder_id IS NULL
                        """,
                        {"new_feeder_id": target, "rmu_id": rid},
                    )
                else:
                    cur.execute(
                        """
                        UPDATE dms_combined_device
                        SET feeder_id = :new_feeder_id
                        WHERE id = :rmu_id
                          AND feeder_id = :old_feeder_id
                        """,
                        {
                            "new_feeder_id": target,
                            "rmu_id": rid,
                            "old_feeder_id": old,
                        },
                    )
                if int(cur.rowcount or 0) != 1:
                    raise OracleError(
                        f"RMU FEEDER_ID 更新被阻断：ID={rid}；"
                        f"预期旧值={old if old is not None else 'NULL'}；"
                        "数据库记录可能已被其它操作修改。"
                    )
                cur.execute(
                    """
                    SELECT id, code, name, feeder_id
                    FROM dms_combined_device
                    WHERE id = :rmu_id
                    """,
                    {"rmu_id": rid},
                )
                raw = cur.fetchone()
                if not raw or int(raw[3]) != target:
                    raise OracleError(
                        f"RMU FEEDER_ID 更新后验证失败：ID={rid}，目标={target}"
                    )
                result = {
                    "id": raw[0], "code": raw[1], "name": raw[2],
                    "feeder_id": raw[3], "old_feeder_id": old,
                }
            self.conn.commit()
            return result
        except Exception as exc:
            try:
                self.conn.rollback()
            except Exception:
                pass
            if isinstance(exc, OracleError):
                raise
            raise OracleError(
                f"修改 dms_combined_device.FEEDER_ID 失败，事务已回滚：{exc}"
            ) from exc

    def get_combined_device_records(self, device_name: str) -> List[Dict[str, Any]]:
        """Resolve a standalone pole-switch parent by exact NAME only.

        Makkah pole-switch association treats the graphical device label as
        the authoritative business NAME in dms_combined_device (13501). The
        value is passed to Oracle unchanged: no TRIM, whitespace collapse,
        punctuation removal, or case conversion. Do not fall back to CODE and
        do not add a FEEDER_ID constraint. A caller may associate only when
        this exact NAME lookup returns one row.
        """
        # Makkah rule: query with the G-file name exactly as supplied.
        # Do not strip/collapse whitespace and do not remove punctuation.
        lookup_name = str(device_name or "")
        if lookup_name == "":
            return []
        table_name = self.get_table_name(13501)
        rows = self._query(
            f"""
            SELECT *
            FROM {table_name}
            WHERE name = :device_name
            """,
            {"device_name": lookup_name},
        )
        for row in rows:
            row["_table_id"] = 13501
            row["_table_name"] = table_name
            row["_matched_field"] = "NAME"
        return rows

    def get_cb_devices_by_combined_name(
        self,
        combined_name: str,
        table_id: int = 13502,
    ) -> List[Dict[str, Any]]:
        """Resolve dms_cb_device rows whose combined_id is a device NAME.

        In the pole-switch model, ``dms_cb_device.combined_id`` is a string
        such as ``SEC-2046`` rather than the numeric 13501 row ID used by RMU
        device associations.  The exact trimmed comparison prevents a nearby
        device with a similar display name from being selected.
        """
        lookup_name = str(combined_name or "").strip()
        if not lookup_name:
            return []
        table_name = self.get_table_name(int(table_id))
        rows = self._query(
            f"""
            SELECT *
            FROM {table_name}
            WHERE TRIM(combined_id) = :combined_name
            """,
            {"combined_name": lookup_name},
        )
        for row in rows:
            row["_table_id"] = int(table_id)
            row["_table_name"] = table_name
        return rows

    def get_cb_devices_by_combined_device_id(
        self,
        combined_device_id: Any,
        table_id: int = 13502,
    ) -> List[Dict[str, Any]]:
        """Resolve child switch rows by the parent 13501 device ID.

        In the live DMS data, ``dms_cb_device.COMBINED_ID`` is the numeric
        ``dms_combined_device.ID``. For example, the 13501 row whose CODE is
        ``SEC-2046`` has ID ``3800193660570626905`` and the corresponding
        13502 row stores that number in COMBINED_ID.
        """
        if combined_device_id in (None, ""):
            return []
        try:
            lookup_id = int(combined_device_id)
        except (TypeError, ValueError):
            return []
        table_name = self.get_table_name(int(table_id))
        rows = self._query(
            f"""
            SELECT *
            FROM {table_name}
            WHERE combined_id = :combined_device_id
            """,
            {"combined_device_id": lookup_id},
        )
        for row in rows:
            row["_table_id"] = int(table_id)
            row["_table_name"] = table_name
        return rows

    def get_channel_status_keyids_by_combined_id(self, combined_id: int) -> List[Dict[str, Any]]:
        """Return Channel Status KeyID candidates for one resolved RMU.

        This is the same read-only database rule used by the Jazan edition:
        resolve dms_terminal_info by the RMU COMBINED_ID, join
        dms_channel_info by TERMINAL_ID, exclude DR channels, and construct
        the G-file KeyID from dms_channel_info.ID with domain 40.
        """
        if combined_id in (None, ""):
            return []
        sql = """
            SELECT
                ci.id + :channel_keyid_offset AS new_id,
                ci.id AS channel_id,
                ci.chan_name AS chan_name,
                ti.id AS terminal_id,
                ti.combined_id AS combined_id
            FROM d5000.dms_terminal_info ti
            JOIN d5000.dms_channel_info ci
                ON ci.terminal_id = ti.id
            WHERE ti.combined_id = :combined_id
              AND (
                    ci.chan_name IS NULL
                    OR UPPER(TRIM(ci.chan_name)) NOT LIKE '%DR'
                  )
        """
        return self._query(
            sql,
            {
                "combined_id": int(combined_id),
                "channel_keyid_offset": int(RMU_CHANNEL_STATUS_KEYID_OFFSET),
            },
        )

    def get_devices_by_combined_id(self, table_id: int, combined_id: int) -> Tuple[str, List[Dict[str, Any]]]:
        table_name = self.get_table_name(table_id)
        # Table name comes only from sys_table_info, never from user input.
        sql = f"""
            SELECT id, code, name, feeder_id, combined_id, bv_id
            FROM {table_name}
            WHERE combined_id = :combined_id
        """
        rows = self._query(sql, {"combined_id": int(combined_id)})
        return table_name, rows

    def get_devices_by_code(
        self,
        table_id: int,
        code: str,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Resolve a model device by exact CODE.

        The table name is still resolved through ``sys_table_info``.  This is
        used by the fixed main-station association rules (407/408/409), where
        the G key_name carries the model CODE.
        """
        table_name = self.get_table_name(int(table_id))
        lookup_code = str(code or "").strip()
        if not lookup_code:
            return table_name, []
        rows = self._query(
            f"""
            SELECT *
            FROM {table_name}
            WHERE TRIM(code) = :code
            """,
            {"code": lookup_code},
        )
        for row in rows:
            row["_table_id"] = int(table_id)
            row["_table_name"] = table_name
        return table_name, rows

    def get_relay_signals_by_combined_id(
        self,
        combined_id: int,
        code: str = "EFI INDICATOR",
        table_id: int = 13533,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Read the fixed EFI signal row for one RMU.

        ``dms_relay_sig`` is intentionally queried with ``SELECT *`` because
        the relay table's auxiliary columns are not part of the generic
        device-table contract.  The association rule itself only requires
        ID, CODE and COMBINED_ID (plus whatever optional BV_ID is present).
        """
        table_name = self.get_table_name(int(table_id))
        rows = self._query(
            f"""
            SELECT *
            FROM {table_name}
            WHERE combined_id = :combined_id
              AND TRIM(code) = :code
            """,
            {
                "combined_id": int(combined_id),
                "code": str(code or "").strip(),
            },
        )
        for row in rows:
            row["_table_id"] = int(table_id)
            row["_table_name"] = table_name
        return table_name, rows


    def get_device_by_id(self, table_id: int, device_id: int) -> Optional[Dict[str, Any]]:
        """
        Resolve the database record referenced by a KeyID.

        Table name is resolved only through sys_table_info.  This is used to
        verify the current G-file model link, especially its COMBINED_ID.
        """
        table_name = self.get_table_name(int(table_id))
        if int(table_id) == 13533:
            rows = self._query(
                f"""
                SELECT *
                FROM {table_name}
                WHERE id = :device_id
                """,
                {"device_id": int(device_id)},
            )
        else:
            rows = self._query(
                f"""
                SELECT id, code, name, feeder_id, combined_id, bv_id
                FROM {table_name}
                WHERE id = :device_id
                """,
                {"device_id": int(device_id)},
            )
        if len(rows) == 1:
            row = dict(rows[0])
            row["_table_name"] = table_name
            return row
        return None

    def get_raw_device_by_id(
        self,
        table_id: int,
        device_id: int,
    ) -> Optional[Dict[str, Any]]:
        """Read one model row without assuming a shared column contract."""
        table_name = self.get_table_name(int(table_id))
        rows = self._query(
            f"""
            SELECT *
            FROM {table_name}
            WHERE id = :device_id
            """,
            {"device_id": int(device_id)},
        )
        if len(rows) != 1:
            return None
        row = dict(rows[0])
        row["_table_id"] = int(table_id)
        row["_table_name"] = table_name
        return row

    def get_feeders_by_station(
        self,
        station_id: Any,
        table_id: int = 13500,
    ) -> List[Dict[str, Any]]:
        """List feeder master records owned by one substation."""
        if station_id in (None, ""):
            return []
        table_name = self.get_table_name(int(table_id))
        rows = self._query(
            f"""
            SELECT id, code, name, st_id, graph_name
            FROM {table_name}
            WHERE st_id = :station_id
            ORDER BY id
            """,
            {"station_id": int(station_id)},
        )
        for row in rows:
            row["_table_id"] = int(table_id)
            row["_table_name"] = table_name
        return rows

    def get_transformer_devices_by_name(
        self,
        device_name: str,
        feeder_id: Any = None,
        table_id: int = 13505,
    ) -> List[Dict[str, Any]]:
        """Resolve transformer rows by exact NAME and optional FEEDER_ID.

        dms_tr_device does not expose the RMU-style BV_ID/COMBINED_ID contract,
        so transformer lookup intentionally selects only columns known to exist
        in the transformer table.  NAME is the graphical Text business key;
        feeder_id is applied as an independent ownership constraint.
        """
        lookup_name = str(device_name or "").strip()
        if not lookup_name:
            return []
        table_name = self.get_table_name(int(table_id))
        where = "TRIM(name) = :device_name"
        binds = {"device_name": lookup_name}
        if feeder_id not in (None, ""):
            where += " AND feeder_id = :feeder_id"
            binds["feeder_id"] = int(feeder_id)
        rows = self._query(
            f"""
            SELECT id, code, name, feeder_id
            FROM {table_name}
            WHERE {where}
            ORDER BY id
            """,
            binds,
        )
        for row in rows:
            row["_table_id"] = int(table_id)
            row["_table_name"] = table_name
        return rows

    def get_disconnector_devices_by_name(
        self,
        device_name: str,
        feeder_id: Any = None,
        table_id: int = 13513,
    ) -> List[Dict[str, Any]]:
        """Resolve disconnector/fuse rows by exact NAME.

        Makkah FUSE association intentionally passes ``feeder_id=None`` so
        FEEDER_ID never participates in target selection.  The optional
        parameter is retained only for API compatibility with other site
        variants.
        """
        lookup_name = str(device_name or "").strip()
        if not lookup_name:
            return []
        table_name = self.get_table_name(int(table_id))
        where = "TRIM(name) = :device_name"
        binds = {"device_name": lookup_name}
        if feeder_id not in (None, ""):
            where += " AND feeder_id = :feeder_id"
            binds["feeder_id"] = int(feeder_id)
        rows = self._query(
            f"""
            SELECT id, code, name, feeder_id, bv_id
            FROM {table_name}
            WHERE {where}
            ORDER BY id
            """,
            binds,
        )
        for row in rows:
            row["_table_id"] = int(table_id)
            row["_table_name"] = table_name
        return rows

    def get_transformer_device_by_id(
        self,
        table_id: int,
        device_id: int,
    ) -> Optional[Dict[str, Any]]:
        """Resolve one dms_tr_device row without assuming a BV_ID column."""
        table_name = self.get_table_name(int(table_id))
        rows = self._query(
            f"""
            SELECT id, code, name, feeder_id
            FROM {table_name}
            WHERE id = :device_id
            """,
            {"device_id": int(device_id)},
        )
        if len(rows) != 1:
            return None
        row = dict(rows[0])
        row["_table_name"] = table_name
        row["_table_id"] = int(table_id)
        return row

    def find_stations_by_name_hint(
        self,
        station_hint: str,
        table_id: int = 405,
    ) -> List[Dict[str, Any]]:
        """Resolve a Makkah station caption such as ARF / MNA4.

        The visible drawing title can be shorter than the database station
        name (for example regional prefixes may be present in 405).  Matching
        therefore uses a normalized alphanumeric suffix, while exact
        normalized equality naturally ranks as the same unique result.
        """
        hint = "".join(
            ch for ch in str(station_hint or "").upper() if ch.isalnum()
        )
        if not hint:
            return []
        table_name = self.get_table_name(int(table_id))
        rows = self._query(
            f"""
            SELECT id, code, name, bv_id, subarea_id, graph_name
            FROM {table_name}
            WHERE REGEXP_REPLACE(UPPER(TRIM(name)), '[^A-Z0-9]', '') = :hint
               OR REGEXP_REPLACE(UPPER(TRIM(name)), '[^A-Z0-9]', '') LIKE :suffix_hint
            ORDER BY id
            """,
            {"hint": hint, "suffix_hint": f"%{hint}"},
        )
        for row in rows:
            row["_table_id"] = int(table_id)
            row["_table_name"] = table_name
        return rows

    def get_bays_by_station(
        self,
        station_id: Any,
        table_id: int = 406,
    ) -> List[Dict[str, Any]]:
        """List Bay records for one substation."""
        if station_id in (None, ""):
            return []
        table_name = self.get_table_name(int(table_id))
        rows = self._query(
            f"""
            SELECT id, code, name, st_id, bv_id, vl_id
            FROM {table_name}
            WHERE st_id = :station_id
            ORDER BY id
            """,
            {"station_id": int(station_id)},
        )
        for row in rows:
            row["_table_id"] = int(table_id)
            row["_table_name"] = table_name
        return rows

    def get_devices_by_station(
        self,
        table_id: int,
        station_id: Any,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Read model devices owned by one ST_ID.

        Used by Makkah main-network Bus association.  Busbarsection is a
        station-level pool for this workflow; BAY_ID is intentionally not
        used when choosing table 410 records.
        """
        table_name = self.get_table_name(int(table_id))
        if station_id in (None, ""):
            return table_name, []
        rows = self._query(
            f"""
            SELECT *
            FROM {table_name}
            WHERE st_id = :station_id
            ORDER BY id
            """,
            {"station_id": int(station_id)},
        )
        for row in rows:
            row["_table_id"] = int(table_id)
            row["_table_name"] = table_name
        return table_name, rows

    def get_devices_by_bay(
        self,
        table_id: int,
        bay_id: Any,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Read model devices owned by one BAY_ID.

        Main-network tables 407/408/409 all expose BAY_ID.  SELECT * is used
        intentionally because those station tables do not share the DMS
        FEEDER_ID/COMBINED_ID column contract.
        """
        table_name = self.get_table_name(int(table_id))
        if bay_id in (None, ""):
            return table_name, []
        rows = self._query(
            f"""
            SELECT *
            FROM {table_name}
            WHERE bay_id = :bay_id
            ORDER BY id
            """,
            {"bay_id": int(bay_id)},
        )
        for row in rows:
            row["_table_id"] = int(table_id)
            row["_table_name"] = table_name
        return table_name, rows

    def get_breaker_by_id(
        self,
        breaker_id: int,
        table_id: int = 407,
    ) -> Optional[Dict[str, Any]]:
        """Resolve the source CBreaker row and its BAY_ID."""
        table_name = self.get_table_name(int(table_id))
        rows = self._query(
            f"""
            SELECT id, code, name, st_id, bay_id, bv_id
            FROM {table_name}
            WHERE id = :breaker_id
            """,
            {"breaker_id": int(breaker_id)},
        )
        if len(rows) != 1:
            return None
        row = dict(rows[0])
        row["_table_id"] = int(table_id)
        row["_table_name"] = table_name
        return row

    def get_bay_by_id(
        self,
        bay_id: int,
        table_id: int = 406,
    ) -> Optional[Dict[str, Any]]:
        """Resolve BAY_ID to the bay code and station ownership."""
        table_name = self.get_table_name(int(table_id))
        rows = self._query(
            f"""
            SELECT id, code, name, st_id, bv_id, vl_id
            FROM {table_name}
            WHERE id = :bay_id
            """,
            {"bay_id": int(bay_id)},
        )
        if len(rows) != 1:
            return None
        row = dict(rows[0])
        row["_table_id"] = int(table_id)
        row["_table_name"] = table_name
        return row

    def find_feeders_by_bay(
        self,
        bay_code: str,
        station_id: Any,
        table_id: int = 13500,
    ) -> List[Dict[str, Any]]:
        """Find feeder master rows owned by a bay's station and code.

        Bay.CODE is normally the feeder code (for example AH303).  The exact
        CODE + ST_ID query is authoritative. GRAPH_NAME/NAME are only checked
        when CODE has no result, and every result must still be unique.
        """
        lookup_code = str(bay_code or "").strip()
        if not lookup_code or station_id in (None, ""):
            return []
        feeder_table = self.get_table_name(int(table_id))
        base = f"""
            SELECT id, code, name, st_id, graph_name
            FROM {feeder_table}
            WHERE st_id = :station_id
              AND TRIM({{field}}) = :bay_code
            ORDER BY id
        """
        binds = {"station_id": int(station_id), "bay_code": lookup_code}
        rows = self._query(base.format(field="code"), binds)
        match_field = "CODE"
        if not rows:
            rows = self._query(base.format(field="graph_name"), binds)
            match_field = "GRAPH_NAME"
        if not rows:
            rows = self._query(base.format(field="name"), binds)
            match_field = "NAME"
        for row in rows:
            row["_table_id"] = int(table_id)
            row["_table_name"] = feeder_table
            row["_matched_field"] = match_field
        return rows

    def get_feeder_info(
        self,
        feeder_id: Any,
        table_id: int = 13500,
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve one feeder master record by numeric feeder ID.

        Return the same station+feeder display_name used by
        find_feeders_by_name_hint(), so an existing FeedLine KeyID can be used
        to confirm a G title such as ABH-03 against JED NTH ABH 03.
        """
        if feeder_id in (None, ""):
            return None

        table_name = self.get_table_name(int(table_id))
        station_table = self.get_table_name(405)
        rows = self._query(
            f"""
            SELECT
                f.id,
                f.code,
                f.name,
                f.st_id,
                f.graph_name,
                s.name AS station_name,
                s.bv_id AS station_bv_id,
                TRIM(
                    NVL(s.name, '') || ' ' ||
                    NVL(f.name, '')
                ) AS display_name
            FROM {table_name} f
            LEFT JOIN {station_table} s
              ON s.id = f.st_id
            WHERE f.id = :feeder_id
            """,
            {"feeder_id": int(feeder_id)},
        )

        if len(rows) != 1:
            return None

        row = dict(rows[0])
        row["_table_id"] = int(table_id)
        row["_table_name"] = table_name
        if not str(row.get("display_name") or "").strip():
            row["display_name"] = str(row.get("name") or "").strip()
        return row

    def get_station_info(self, station_id: Any) -> Optional[Dict[str, Any]]:
        if station_id in (None, ""):
            return None
        try:
            table_name = self.get_table_name(405)
            rows = self._query(
                f"""
                SELECT id, code, name, bv_id, subarea_id, graph_name
                FROM {table_name}
                WHERE id = :station_id
                """,
                {"station_id": int(station_id)},
            )
            return rows[0] if len(rows) == 1 else None
        except Exception:
            return None


    def get_preferred_feeder_section_voltage(self, station_id: Any) -> Optional[Dict[str, Any]]:
        """Select the lowest eligible station voltage for new feeder sections.

        Eligible nominal voltages: 13.8kV, 33kV, 110kV.
        Table 402 voltagelevel provides the station-specific BV_ID; table 401
        basevoltage provides the nominal voltage represented by that BV_ID.
        """
        if station_id in (None, ""):
            return None

        voltagelevel_table = self.get_table_name(402)
        basevoltage_table = self.get_table_name(401)
        rows = self._query(
            f"""
            SELECT
                vl.id AS voltagelevel_id,
                vl.name AS voltagelevel_name,
                vl.st_id,
                vl.bv_id,
                bv.name AS basevoltage_name,
                bv.nomvol
            FROM {voltagelevel_table} vl
            JOIN {basevoltage_table} bv
              ON bv.id = vl.bv_id
            WHERE vl.st_id = :station_id
              AND (
                    ABS(bv.nomvol - 13.8) < 0.000001
                 OR ABS(bv.nomvol - 33.0) < 0.000001
                 OR ABS(bv.nomvol - 110.0) < 0.000001
              )
            ORDER BY bv.nomvol ASC, vl.id ASC
            """,
            {"station_id": int(station_id)},
        )
        if not rows:
            return None

        row = dict(rows[0])
        row["_voltagelevel_table_id"] = 402
        row["_basevoltage_table_id"] = 401
        return row


    def find_feeders_by_name_hint(
        self,
        normalized_hint: str,
        table_id: int = 13500,
    ) -> List[Dict[str, Any]]:
        """
        Resolve feeder master records using the human-readable feeder name.

        In the Oracle model, dms_feeder_device.NAME may contain only the local
        feeder suffix (for example "07"), while DBI renders FEEDER_ID as a
        readable value such as "JED CTL AJWD 07" by combining the station name
        and feeder name.

        Therefore matching is performed against:

            station.name + feeder.name

        after removing punctuation/spaces and upper-casing.

        Example:
            G label:          AJWD-07  -> AJWD07
            station.name:     JED CTL AJWD
            feeder.name:      07
            database display: JED CTL AJWD 07
            normalized:       JEDCTLAJWD07

        AJWD07 is contained in JEDCTLAJWD07 -> match.
        """
        hint = "".join(
            ch for ch in str(normalized_hint or "").upper()
            if ch.isalnum()
        )
        if not hint:
            return []

        feeder_table = self.get_table_name(int(table_id))
        station_table = self.get_table_name(405)

        rows = self._query(
            f"""
            SELECT
                f.id,
                f.code,
                f.name,
                f.st_id,
                f.graph_name,
                s.name AS station_name,
                TRIM(
                    NVL(s.name, '') || ' ' ||
                    NVL(f.name, '')
                ) AS display_name
            FROM {feeder_table} f
            LEFT JOIN {station_table} s
              ON s.id = f.st_id
            WHERE REGEXP_REPLACE(
                    UPPER(
                        TRIM(
                            NVL(s.name, '') || ' ' ||
                            NVL(f.name, '')
                        )
                    ),
                    '[^A-Z0-9]',
                    ''
                  ) LIKE :name_pattern
            ORDER BY s.name, f.name, f.id
            """,
            {"name_pattern": f"%{hint}%"},
        )

        for row in rows:
            row["_table_id"] = int(table_id)
            row["_table_name"] = feeder_table
            if not str(row.get("display_name") or "").strip():
                row["display_name"] = str(row.get("name") or "").strip()

        return rows


    @staticmethod
    def _rmu_poke_lookup_key(value: Any) -> str:
        return " ".join(str(value or "").strip().split()).casefold()

    def resolve_rmu_poke_contexts(
        self,
        rmu_names,
    ) -> tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
        """Resolve smart RMU names for Poke target generation.

        This is a SELECT-only helper copied from the proven GFileStudio Poke
        workflow.  Each RMU is resolved independently through:

            13501 dms_combined_device.NAME
              -> FEEDER_ID
              -> 13500 dms_feeder_device
              -> 405 substation
              -> subcontrolarea

        The returned ``feeder_full_name`` is used only to build the target
        ``<subarea>-<station>-<feeder>-<RMU>.com.pic.g`` filename.  Missing or
        duplicated rows are returned in ``issues`` instead of aborting the
        complete G file.
        """
        requested = []
        seen = set()
        for raw in rmu_names or []:
            name = " ".join(str(raw or "").strip().split())
            key = self._rmu_poke_lookup_key(name)
            if name and key not in seen:
                seen.add(key)
                requested.append(name)
        if not requested:
            return {}, {}

        combined_table = self.get_table_name(13501)
        feeder_table = self.get_table_name(13500)
        station_table = self.get_table_name(405)
        rows_by_key: Dict[str, List[Dict[str, Any]]] = {
            self._rmu_poke_lookup_key(name): [] for name in requested
        }

        # Keep well under Oracle's 1000-expression IN limit.
        chunk_size = 500
        for start in range(0, len(requested), chunk_size):
            chunk = requested[start:start + chunk_size]
            binds = {f"rmu_{i}": name.upper() for i, name in enumerate(chunk)}
            placeholders = ", ".join(f":rmu_{i}" for i in range(len(chunk)))
            rows = self._query(
                f"""
                SELECT
                    c.id AS combined_device_id,
                    c.name AS rmu_name,
                    c.feeder_id AS combined_feeder_id,
                    f.id AS feeder_id,
                    f.name AS feeder_name,
                    f.code AS feeder_code,
                    f.st_id AS station_id,
                    s.name AS station_name,
                    s.subarea_id AS subarea_id,
                    a.name AS subcontrolarea_name
                FROM {combined_table} c
                LEFT JOIN {feeder_table} f
                  ON f.id = c.feeder_id
                LEFT JOIN {station_table} s
                  ON s.id = f.st_id
                LEFT JOIN subcontrolarea a
                  ON a.id = s.subarea_id
                WHERE UPPER(TRIM(CAST(c.name AS VARCHAR2(128)))) IN ({placeholders})
                """,
                binds,
            )
            for row in rows:
                key = self._rmu_poke_lookup_key(row.get("rmu_name"))
                if key in rows_by_key:
                    rows_by_key[key].append(dict(row))

        contexts: Dict[str, Dict[str, Any]] = {}
        issues: Dict[str, str] = {}
        for requested_name in requested:
            key = self._rmu_poke_lookup_key(requested_name)
            rows = rows_by_key.get(key, [])
            if not rows:
                issues[key] = (
                    f"数据库未找到 DMS_COMBINED_DEVICE.NAME={requested_name!r} 的环网柜记录。"
                )
                continue
            unique_by_id = {
                str(row.get("combined_device_id")): row
                for row in rows
                if row.get("combined_device_id") not in (None, "")
            }
            if len(unique_by_id) != 1:
                issues[key] = (
                    f"数据库中 DMS_COMBINED_DEVICE.NAME={requested_name!r} 返回 "
                    f"{len(unique_by_id) or len(rows)} 条有效记录，无法唯一确定所属馈线。"
                )
                continue
            row = dict(next(iter(unique_by_id.values())))
            required = {
                "combined_device_id": row.get("combined_device_id"),
                "feeder_id": row.get("feeder_id") or row.get("combined_feeder_id"),
                "feeder_name": row.get("feeder_name"),
                "station_name": row.get("station_name"),
                "subcontrolarea_name": row.get("subcontrolarea_name"),
            }
            missing = [name for name, value in required.items() if value in (None, "")]
            if missing:
                issues[key] = (
                    f"RMU {requested_name!r} 的数据库关联信息不完整："
                    + ", ".join(missing)
                )
                continue
            station_full_name = (
                f"{str(row.get('subcontrolarea_name')).strip()}-"
                f"{str(row.get('station_name')).strip()}"
            )
            feeder_full_name = (
                f"{station_full_name}-"
                f"{str(row.get('feeder_name')).strip()}"
            )
            row["station_full_name"] = station_full_name
            row["feeder_full_name"] = feeder_full_name
            contexts[key] = row

        return contexts, issues


    def get_sections_by_feeder_id(
        self,
        feeder_id: int,
        table_id: int = 13503,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Return dms_section_device rows belonging to one feeder."""
        table_name = self.get_table_name(int(table_id))
        rows = self._query(
            f"""
            SELECT id, code, name, feeder_id, bv_id, section_type
            FROM {table_name}
            WHERE feeder_id = :feeder_id
            ORDER BY name, id
            """,
            {"feeder_id": int(feeder_id)},
        )
        for row in rows:
            row["_table_id"] = int(table_id)
            row["_table_name"] = table_name
        return table_name, rows

    def create_missing_sections(
        self,
        feeder_id: int,
        section_defs: List[Dict[str, Any]],
        *,
        table_id: int = 13503,
        area_id: int = 0,
    ) -> List[Dict[str, Any]]:
        """Create only missing dms_section_device rows in one transaction.

        ID allocation intentionally follows the D5000 GET_VLLE_ID pattern:
          1. lock target table for this short allocation transaction;
          2. derive the legal ID range with KEYID_TO_LONG3(table,0,area,*);
          3. compare current MAX(id) with deleted_record MAX(id);
          4. allocate sequential IDs above the larger value;
          5. INSERT all missing rows, verify, then COMMIT.

        Existing rows are never UPDATEd or DELETEd here.
        """
        if not section_defs:
            return []

        self.ensure_connected()
        table_id = int(table_id)
        feeder_id = int(feeder_id)
        area_id = int(area_id)

        if table_id != 13503:
            raise OracleError(
                "自动创建馈线段仅允许 DMS_SECTION_DEVICE / table_id=13503。"
            )

        table_name = self.get_table_name(table_id)
        requested = []
        seen_names = set()
        for item in section_defs:
            name = str(item.get("name") or "").strip()
            if not name:
                raise OracleError("待创建馈线段 NAME 不能为空。")
            key = name.upper()
            if key in seen_names:
                continue
            seen_names.add(key)
            bv_id = item.get("bv_id")
            if bv_id in (None, ""):
                raise OracleError(f"{name}: BV_ID 为空，禁止创建。")
            section_type = int(item.get("section_type"))
            if section_type not in {0, 1, 3}:
                raise OracleError(
                    f"{name}: SECTION_TYPE={section_type} 不在允许值 0/1/3。"
                )
            requested.append({
                "name": name,
                "bv_id": int(bv_id),
                "section_type": section_type,
            })

        created = []
        try:
            with self.conn.cursor() as cur:
                # Keep ID allocation + inserts atomic and avoid two instances
                # allocating the same MAX+1 value at the same time.
                cur.execute(f"LOCK TABLE {table_name} IN EXCLUSIVE MODE")

                # Re-check names AFTER the lock. Existing rows are reused and
                # are never inserted a second time.
                existing_by_name = {}
                cur.execute(
                    f"""
                    SELECT id, name, feeder_id, bv_id, section_type
                    FROM {table_name}
                    WHERE feeder_id = :feeder_id
                    """,
                    {"feeder_id": feeder_id},
                )
                cols = [d[0].lower() for d in cur.description]
                for raw in cur:
                    row = {
                        cols[i]: raw[i]
                        for i in range(len(cols))
                    }
                    key = str(row.get("name") or "").strip().upper()
                    existing_by_name.setdefault(key, []).append(row)

                for item in requested:
                    matches = existing_by_name.get(item["name"].upper(), [])
                    if len(matches) > 1:
                        raise OracleError(
                            f"{item['name']}: 数据库存在 {len(matches)} 条同名馈线段，"
                            "禁止自动创建/分配。"
                        )

                missing = [
                    item for item in requested
                    if not existing_by_name.get(item["name"].upper())
                ]
                if not missing:
                    return []

                cur.execute(
                    """
                    SELECT
                        keyid_to_long3(:table_id, 0, :area_id, 0) AS min_id,
                        keyid_to_long3(
                            :table_id,
                            0,
                            :area_id,
                            TO_NUMBER('FFFFFF','XXXXXX')
                        ) AS max_id
                    FROM dual
                    """,
                    {
                        "table_id": table_id,
                        "area_id": area_id,
                    },
                )
                min_id, max_id = cur.fetchone()
                min_id = int(min_id)
                max_id = int(max_id)

                cur.execute(
                    f"""
                    SELECT MAX(id)
                    FROM {table_name}
                    WHERE id > :min_id
                      AND id < :max_id
                    """,
                    {"min_id": min_id, "max_id": max_id},
                )
                current_max = cur.fetchone()[0]

                cur.execute(
                    """
                    SELECT MAX(id)
                    FROM deleted_record
                    WHERE table_id = :table_id
                      AND region_id = :area_id
                    """,
                    {
                        "table_id": table_id,
                        "area_id": area_id,
                    },
                )
                deleted_max = cur.fetchone()[0]

                allocator = max(
                    int(current_max) if current_max is not None else min_id,
                    int(deleted_max) if deleted_max is not None else min_id,
                )

                for item in missing:
                    allocator += 1
                    if allocator >= max_id:
                        raise OracleError(
                            "DMS_SECTION_DEVICE 当前 ID 区间已无可用编号。"
                        )

                    # Last-line uniqueness defense, still inside the lock.
                    cur.execute(
                        f"SELECT COUNT(*) FROM {table_name} WHERE id = :id",
                        {"id": allocator},
                    )
                    if int(cur.fetchone()[0]) != 0:
                        raise OracleError(
                            f"新 ID 已被占用：{allocator}"
                        )

                    cur.execute(
                        f"""
                        INSERT INTO {table_name}
                        (
                            id,
                            name,
                            feeder_id,
                            bv_id,
                            section_type,
                            record_app,
                            record_app2,
                            record_app3,
                            record_app4
                        )
                        VALUES
                        (
                            :id,
                            :name,
                            :feeder_id,
                            :bv_id,
                            :section_type,
                            65545,
                            65545,
                            65545,
                            65545
                        )
                        """,
                        {
                            "id": allocator,
                            "name": item["name"],
                            "feeder_id": feeder_id,
                            "bv_id": item["bv_id"],
                            "section_type": item["section_type"],
                        },
                    )
                    created.append({
                        "id": allocator,
                        "name": item["name"],
                        "feeder_id": feeder_id,
                        "bv_id": item["bv_id"],
                        "section_type": item["section_type"],
                    })

                # Verify exactly what this transaction created before COMMIT.
                for item in created:
                    cur.execute(
                        f"""
                        SELECT id, name, feeder_id, bv_id, section_type
                        FROM {table_name}
                        WHERE id = :id
                        """,
                        {"id": item["id"]},
                    )
                    row = cur.fetchone()
                    if not row:
                        raise OracleError(
                            f"创建后验证失败：{item['name']}"
                        )

            self.conn.commit()
            return created
        except Exception as exc:
            try:
                self.conn.rollback()
            except Exception:
                pass
            if isinstance(exc, OracleError):
                raise
            raise OracleError(
                f"创建 DMS_SECTION_DEVICE 失败，事务已回滚：{exc}"
            ) from exc

    def verify_keyid(self, keyid: int) -> Dict[str, Any]:
        rows = self._query(
            """
            SELECT
                :keyid AS key_id,
                long2_to_long1(:keyid) AS device_id,
                get_tab_no(:keyid) AS tab_no,
                get_col_no(:keyid) AS col_no
            FROM dual
            """,
            {"keyid": int(keyid)},
        )
        return rows[0] if rows else {}

    def get_column_info(self, table_id: int, col_no: int) -> Optional[Dict[str, Any]]:
        rows = self._query(
            """
            SELECT table_id, column_id, field_id, column_name_eng, column_name_chn
            FROM sys_column_info
            WHERE table_id = :table_id
              AND column_id = :col_no
            """,
            {"table_id": int(table_id), "col_no": int(col_no)},
        )
        return rows[0] if len(rows) == 1 else None
