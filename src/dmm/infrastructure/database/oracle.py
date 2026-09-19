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

    def get_rmu_records_by_feeder_id(
        self,
        feeder_id: Any,
    ) -> List[Dict[str, Any]]:
        """Return all combined-device/RMU rows owned by one FEEDER_ID.

        Jazan drawings may use ``NO`` or ``NO-...`` as a placeholder rather
        than the database RMU NAME.  The caller uses this feeder-scoped pool
        to allocate each database parent to at most one graphical placeholder.
        """
        if feeder_id in (None, ""):
            return []
        table_name = self.get_table_name(13501)
        rows = self._query(
            f"""
            SELECT *
            FROM {table_name}
            WHERE feeder_id = :feeder_id
            ORDER BY id
            """,
            {"feeder_id": int(feeder_id)},
        )
        for row in rows:
            row["_table_id"] = 13501
            row["_table_name"] = table_name
        return rows

    def get_combined_device_records(
        self,
        device_name: str,
        feeder_id: Any = None,
    ) -> List[Dict[str, Any]]:
        """Resolve a standalone device name in dms_combined_device (13501).

        Pole-switch drawings use the visible device name as the business
        identity. The normal lookup is an exact trimmed NAME lookup. Some
        DMS exports (including the supplied screenshot) expose the same
        display value in CODE instead, so CODE is checked only as a fallback
        when the NAME lookup returns no rows. The two lookups are deliberately
        performed one device at a time, never as a bulk IN query.
        """
        lookup_name = str(device_name or "").strip()
        if not lookup_name:
            return []
        table_name = self.get_table_name(13501)
        feeder_clause = ""
        binds = {"device_name": lookup_name}
        if feeder_id not in (None, ""):
            feeder_clause = " AND feeder_id = :feeder_id"
            binds["feeder_id"] = int(feeder_id)
        rows = self._query(
            f"""
            SELECT *
            FROM {table_name}
            WHERE TRIM(name) = :device_name{feeder_clause}
            """,
            binds,
        )
        matched_field = "NAME"
        if not rows:
            rows = self._query(
                f"""
                SELECT *
                FROM {table_name}
                WHERE TRIM(code) = :device_name{feeder_clause}
                """,
                binds,
            )
            matched_field = "CODE"
        for row in rows:
            row["_table_id"] = 13501
            row["_table_name"] = table_name
            row["_matched_field"] = matched_field
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

    def get_transformer_devices_by_feeder_id(
        self,
        feeder_id: Any,
        table_id: int = 13505,
    ) -> List[Dict[str, Any]]:
        """List all transformer rows belonging to one feeder.

        Jazan uses graphical ``NO`` as a placeholder.  The transformer
        module filters this feeder-scoped result to database names beginning
        with ``NO-`` and allocates each row at most once.
        """
        if feeder_id in (None, ""):
            return []
        table_name = self.get_table_name(int(table_id))
        rows = self._query(
            f"""
            SELECT id, code, name, feeder_id
            FROM {table_name}
            WHERE feeder_id = :feeder_id
            ORDER BY id
            """,
            {"feeder_id": int(feeder_id)},
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
                SELECT id, name, bv_id
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
