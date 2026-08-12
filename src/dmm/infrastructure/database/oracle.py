#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

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

    def get_rmu_records(self, rmu_name: str) -> List[Dict[str, Any]]:
        """
        Resolve RMU records by the business NAME field.

        RMU NAME is a string identifier, not a numeric identifier.  Valid
        examples include:
            42646
            RMU-42646
            ABC_123
            JED-RMU-01

        Therefore the application must never convert RMU names to int and must
        never depend on TO_CHAR(name).  Oracle performs an exact trimmed string
        comparison against dms_combined_device.NAME.
        """
        lookup_name = str(rmu_name or "").strip()
        if not lookup_name:
            return []

        return self._query(
            """
            SELECT *
            FROM dms_combined_device
            WHERE TRIM(name) = :rmu_name
            """,
            {"rmu_name": lookup_name},
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


    def get_device_by_id(self, table_id: int, device_id: int) -> Optional[Dict[str, Any]]:
        """
        Resolve the database record referenced by a KeyID.

        Table name is resolved only through sys_table_info.  This is used to
        verify the current G-file model link, especially its COMBINED_ID.
        """
        table_name = self.get_table_name(int(table_id))
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

    def get_feeder_info(self, feeder_id: Any) -> Optional[Dict[str, Any]]:
        """
        Resolve dms_combined_device.FEEDER_ID through table 13500.

        FEEDER_ID is a numeric foreign-key value in Oracle.  DBI may render a
        human-readable value, but normal SQL returns the real numeric ID, so
        the application resolves the referenced dms_feeder_device row itself.
        """
        if feeder_id in (None, ""):
            return None

        table_name = self.get_table_name(int(table_id))
        rows = self._query(
            f"""
            SELECT id, code, name, st_id, graph_name
            FROM {table_name}
            WHERE id = :feeder_id
            """,
            {"feeder_id": int(feeder_id)},
        )

        if len(rows) != 1:
            return None

        row = dict(rows[0])
        row["_table_id"] = 13500
        row["_table_name"] = table_name
        return row

    def get_station_info(self, station_id: Any) -> Optional[Dict[str, Any]]:
        if station_id in (None, ""):
            return None
        try:
            table_name = self.get_table_name(405)
            rows = self._query(
                f"""
                SELECT id, name
                FROM {table_name}
                WHERE id = :station_id
                """,
                {"station_id": int(station_id)},
            )
            return rows[0] if len(rows) == 1 else None
        except Exception:
            return None


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


    def get_sections_by_feeder_id(
        self,
        feeder_id: int,
        table_id: int = 13503,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Return dms_section_device rows belonging to one feeder."""
        table_name = self.get_table_name(int(table_id))
        rows = self._query(
            f"""
            SELECT id, code, name, feeder_id, bv_id
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
