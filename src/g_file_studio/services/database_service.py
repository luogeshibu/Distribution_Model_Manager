from __future__ import annotations

import base64
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from g_file_studio.services.user_settings_service import UserSettingsService


_DEFAULT_USERNAME = "d5000"
_DEFAULT_PASSWORD = "OracleDV1Dec.25"
_DEFAULT_HOST = "172.16.21.45"
_DEFAULT_PORT = 1521
_DEFAULT_SERVICE = "jedup8000"


@dataclass(frozen=True)
class OracleConnectionConfig:
    """Central Oracle connection configuration used by future business modules."""

    username: str = _DEFAULT_USERNAME
    password: str = _DEFAULT_PASSWORD
    host: str = _DEFAULT_HOST
    port: int = _DEFAULT_PORT
    service_name: str = _DEFAULT_SERVICE

    @property
    def dsn(self) -> str:
        return f"{self.host}:{self.port}/{self.service_name}"

    def validate(self) -> None:
        if not self.username.strip():
            raise ValueError("数据库用户名不能为空。")
        if not self.password:
            raise ValueError("数据库密码不能为空。")
        if not self.host.strip():
            raise ValueError("数据库服务器地址不能为空。")
        if not (1 <= int(self.port) <= 65535):
            raise ValueError("数据库端口必须在 1~65535 之间。")
        if not self.service_name.strip():
            raise ValueError("Oracle Service Name 不能为空。")






@dataclass(frozen=True)
class TopologyFeederAnchorContext:
    """Database-backed feeder identity for one G topology anchor device.

    Only the three authoritative DBI equipment tables are used by G content
    inventory feeder analysis: BREAKER (407), DISCONNECTOR (408), and
    GROUNDDISCONNECTOR (409).  ``bay_id`` is the business source of station and
    feeder identity; no G-file facID/facName or spatial guess is involved.
    """

    table_name: str
    device_id: str
    device_name: str
    bay_id: str
    station_name: str
    feeder_name: str


@dataclass(frozen=True)
class GFileDatabaseContext:
    """Resolved business identity for one feeder G file."""

    fac_id: str
    feeder_id: str
    feeder_name: str
    station_id: str
    station_name: str
    subarea_id: str
    subcontrolarea_name: str
    station_full_name: str
    feeder_full_name: str


@dataclass(frozen=True)
class RmuDatabaseContext:
    """Resolved feeder/station business identity from one RMU cabinet name.

    Authoritative relation:
    DMS_COMBINED_DEVICE.NAME -> DMS_COMBINED_DEVICE.FEEDER_ID
    -> DMS_FEEDER_DEVICE.ID/NAME/ST_ID -> SUBSTATION -> SUBCONTROLAREA.
    GRAPH_NAME is intentionally absent.
    """

    rmu_name: str
    combined_device_id: str
    feeder_id: str
    feeder_name: str
    station_id: str
    station_name: str
    subarea_id: str
    subcontrolarea_name: str
    station_full_name: str
    feeder_full_name: str


@dataclass(frozen=True)
class StationDatabaseContext:
    """Resolved canonical station identity from SUBSTATION.NAME.

    GRAPH_NAME is intentionally absent: station Poke naming is based only on
    SUBSTATION.NAME and its SUBAREA_ID -> SUBCONTROLAREA.NAME relation.
    """

    station_id: str
    station_name: str
    subarea_id: str
    subcontrolarea_name: str
    station_full_name: str

class _WindowsDpapiSecretStore:
    """Protect the database password with Windows DPAPI for the current user.

    The encrypted blob may safely live in the ordinary user_settings.ini.  It can be
    decrypted only by the same Windows user profile.  On non-Windows systems the
    password is deliberately not persisted.
    """

    @staticmethod
    def available() -> bool:
        return os.name == "nt"

    @staticmethod
    def protect(text: str) -> str:
        if not text or not _WindowsDpapiSecretStore.available():
            return ""
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        raw = text.encode("utf-8")
        buffer = ctypes.create_string_buffer(raw)
        in_blob = DATA_BLOB(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        out_blob = DATA_BLOB()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        description = "G File Studio Oracle Password"
        if not crypt32.CryptProtectData(
            ctypes.byref(in_blob),
            description,
            None,
            None,
            None,
            0,
            ctypes.byref(out_blob),
        ):
            raise OSError("Windows DPAPI 无法加密数据库密码。")
        try:
            protected = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            return base64.b64encode(protected).decode("ascii")
        finally:
            kernel32.LocalFree(out_blob.pbData)

    @staticmethod
    def unprotect(encoded: str) -> str:
        if not encoded or not _WindowsDpapiSecretStore.available():
            return ""
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        protected = base64.b64decode(encoded.encode("ascii"), validate=True)
        buffer = ctypes.create_string_buffer(protected)
        in_blob = DATA_BLOB(len(protected), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        out_blob = DATA_BLOB()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        if not crypt32.CryptUnprotectData(
            ctypes.byref(in_blob),
            None,
            None,
            None,
            None,
            0,
            ctypes.byref(out_blob),
        ):
            raise OSError("Windows DPAPI 无法解密数据库密码。")
        try:
            raw = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            return raw.decode("utf-8")
        finally:
            kernel32.LocalFree(out_blob.pbData)


class OracleDatabaseService:
    """Shared Oracle access service.

    Current G File Studio policy is intentionally conservative: the public query API
    is read-only and accepts SELECT / WITH statements only.  Future modules should
    consume this service rather than create private connection settings or embed
    credentials independently.
    """

    _WRITE_SQL = re.compile(
        r"\b(?:INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE|COMMIT|ROLLBACK|CALL|BEGIN|DECLARE|EXEC(?:UTE)?)\b",
        re.IGNORECASE,
    )

    def __init__(self, settings: UserSettingsService) -> None:
        self.settings = settings
        # Last feeder-anchor lookup diagnostics.  This is intentionally runtime-only
        # (never persisted) so the G inventory page can show exactly how many
        # CBreaker/Disconnector/GroundDisconnector keyids were queried and matched.
        self.last_topology_feeder_lookup_stats: dict[str, dict[str, object]] = {}

    def _has_saved_user_config(self) -> bool:
        """Return True once the user has persisted any Oracle connection setting.

        v2.18.86/v2.18.87 did not write an explicit marker, so the field existence
        check also preserves settings saved by those versions during upgrade.
        """
        if self.settings.get_bool("database/oracle_config_saved", False):
            return True
        sentinel = "__GFS_DATABASE_SETTING_MISSING__"
        keys = (
            "database/oracle_username",
            "database/oracle_password_dpapi",
            "database/oracle_host",
            "database/oracle_port",
            "database/oracle_service",
        )
        return any(self.settings.get_value(key, sentinel) != sentinel for key in keys)

    def load_config(self) -> OracleConnectionConfig:
        # Factory values are used only when the user has never saved a database
        # configuration. Once a user configuration exists, it is authoritative.
        if not self._has_saved_user_config():
            return OracleConnectionConfig(
                username="",
                password="",
                host="",
                port=_DEFAULT_PORT,
                service_name="",
            )

        password = ""
        protected = self.settings.get_value("database/oracle_password_dpapi").strip()
        if protected and _WindowsDpapiSecretStore.available():
            try:
                password = _WindowsDpapiSecretStore.unprotect(protected)
            except Exception:
                # A copied profile or changed Windows user cannot decrypt the blob.
                # Never fall back to the factory password after a user configuration
                # has been saved, because that could silently use the wrong account.
                password = ""
        return OracleConnectionConfig(
            username=self.settings.get_value("database/oracle_username", _DEFAULT_USERNAME).strip() or _DEFAULT_USERNAME,
            password=password,
            host=self.settings.get_value("database/oracle_host", _DEFAULT_HOST).strip() or _DEFAULT_HOST,
            port=self.settings.get_int("database/oracle_port", _DEFAULT_PORT),
            service_name=self.settings.get_value("database/oracle_service", _DEFAULT_SERVICE).strip() or _DEFAULT_SERVICE,
        )

    def save_config(self, config: OracleConnectionConfig) -> bool:
        """Persist public fields and, on Windows, protect the password with DPAPI.

        Returns True when the password was persisted securely.  On non-Windows
        systems only non-secret fields are saved and the caller should inform the
        user that the password will need to be re-entered.
        """
        config.validate()
        self.settings.set_value("database/oracle_username", config.username.strip())
        self.settings.set_value("database/oracle_host", config.host.strip())
        self.settings.set_value("database/oracle_port", int(config.port))
        self.settings.set_value("database/oracle_service", config.service_name.strip())
        self.settings.set_value("database/oracle_config_saved", "true")
        if _WindowsDpapiSecretStore.available():
            protected = _WindowsDpapiSecretStore.protect(config.password)
            self.settings.set_value("database/oracle_password_dpapi", protected)
            return True
        self.settings.clear("database/oracle_password_dpapi")
        return False

    @staticmethod
    def _import_driver():
        try:
            import oracledb  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on runtime packaging
            raise RuntimeError(
                "未安装 Oracle 驱动 python-oracledb。请重新运行 setup_env.ps1 或安装 requirements.txt。"
            ) from exc
        return oracledb

    @staticmethod
    def _connect(config: OracleConnectionConfig):
        config.validate()
        oracledb = OracleDatabaseService._import_driver()
        params = oracledb.ConnectParams(
            host=config.host.strip(),
            port=int(config.port),
            service_name=config.service_name.strip(),
            tcp_connect_timeout=8.0,
        )
        return oracledb.connect(
            user=config.username.strip(),
            password=config.password,
            params=params,
        )

    def test_connection(self, config: OracleConnectionConfig) -> dict[str, Any]:
        """Open a short-lived connection and execute read-only health queries."""
        connection = self._connect(config)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM DUAL")
                cursor.fetchone()
                cursor.execute(
                    "SELECT USER, SYS_CONTEXT('USERENV','DB_NAME'), "
                    "SYS_CONTEXT('USERENV','SERVICE_NAME') FROM DUAL"
                )
                row = cursor.fetchone() or (config.username, "", config.service_name)
            return {
                "username": str(row[0] or config.username),
                "database": str(row[1] or ""),
                "service": str(row[2] or config.service_name),
                "dsn": config.dsn,
            }
        finally:
            connection.close()


    def resolve_g_file_context(
        self,
        fac_id: str | int,
        *,
        config: OracleConnectionConfig | None = None,
    ) -> GFileDatabaseContext:
        """Resolve station/feeder business names from a G root ``facID``.

        Authoritative relation:
        G.facID -> DMS_FEEDER_DEVICE.ID -> (NAME, ST_ID)
        -> SUBSTATION.ID -> (NAME, SUBAREA_ID)
        -> SUBCONTROLAREA.ID -> NAME.

        GRAPH_NAME is deliberately not used to construct business names.
        """
        raw_fac_id = str(fac_id or "").strip()
        if not raw_fac_id:
            raise ValueError(
                "当前 G 文件 facID 为空。请先关联馈线，再执行智能环网柜 Poke 跳转。"
            )
        if not raw_fac_id.isdigit():
            raise ValueError(f"当前 G 文件 facID 不是有效数字：{raw_fac_id!r}")

        sql = """
            SELECT
                f.ID,
                f.NAME,
                f.ST_ID,
                s.ID,
                s.NAME,
                s.SUBAREA_ID,
                a.ID,
                a.NAME
            FROM DMS_FEEDER_DEVICE f
            LEFT JOIN SUBSTATION s
                   ON s.ID = f.ST_ID
            LEFT JOIN SUBCONTROLAREA a
                   ON a.ID = s.SUBAREA_ID
            WHERE f.ID = :fac_id
        """
        _columns, rows = self.query(sql, {"fac_id": int(raw_fac_id)}, max_rows=2, config=config)
        if not rows:
            raise LookupError(
                f"数据库未找到 facID={raw_fac_id} 对应的 DMS_FEEDER_DEVICE 记录。"
            )
        if len(rows) > 1:
            raise LookupError(
                f"数据库中 facID={raw_fac_id} 返回多条馈线记录，无法唯一确定。"
            )

        row = rows[0]
        feeder_id = str(row[0] or "").strip()
        feeder_name = str(row[1] or "").strip()
        station_id = str(row[3] or row[2] or "").strip()
        station_name = str(row[4] or "").strip()
        subarea_id = str(row[5] or "").strip()
        subcontrolarea_name = str(row[7] or "").strip()

        missing = [
            label for label, value in (
                ("DMS_FEEDER_DEVICE.NAME", feeder_name),
                ("SUBSTATION.NAME", station_name),
                ("SUBSTATION.SUBAREA_ID", subarea_id),
                ("SUBCONTROLAREA.NAME", subcontrolarea_name),
            ) if not value
        ]
        if missing:
            raise LookupError(
                f"facID={raw_fac_id} 的数据库关联信息不完整：" + ", ".join(missing)
            )

        station_full_name = f"{subcontrolarea_name}-{station_name}"
        feeder_full_name = f"{station_full_name}-{feeder_name}"
        return GFileDatabaseContext(
            fac_id=raw_fac_id,
            feeder_id=feeder_id or raw_fac_id,
            feeder_name=feeder_name,
            station_id=station_id,
            station_name=station_name,
            subarea_id=subarea_id,
            subcontrolarea_name=subcontrolarea_name,
            station_full_name=station_full_name,
            feeder_full_name=feeder_full_name,
        )

    @staticmethod
    def _rmu_lookup_key(value: object) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip()).casefold()

    def resolve_rmu_contexts(
        self,
        rmu_names: Iterable[str],
        *,
        config: OracleConnectionConfig | None = None,
    ) -> tuple[dict[str, RmuDatabaseContext], dict[str, str]]:
        """Resolve many RMU names to their feeder/station context in one DB round trip.

        This is the authoritative Poke path for RMU detail jumps.  ``facID`` is
        deliberately not involved because a station overview drawing may contain
        RMUs from many feeders.  Each cabinet resolves independently through
        DMS_COMBINED_DEVICE.NAME -> FEEDER_ID.

        The returned dictionaries are keyed by normalized/case-folded RMU name.
        Missing, duplicated, or incomplete database rows are returned in
        ``issues`` instead of aborting the whole G file.
        """
        requested: list[str] = []
        seen: set[str] = set()
        for raw in rmu_names:
            name = re.sub(r"\s+", " ", str(raw or "").strip())
            key = self._rmu_lookup_key(name)
            if name and key not in seen:
                seen.add(key)
                requested.append(name)
        if not requested:
            return {}, {}

        # A single station overview can contain hundreds of cabinets.  Keep the
        # query below Oracle's 1000-expression IN limit while avoiding one TCP/DB
        # connection per RMU.
        rows_by_key: dict[str, list[tuple[Any, ...]]] = {self._rmu_lookup_key(n): [] for n in requested}
        chunk_size = 500
        for start in range(0, len(requested), chunk_size):
            chunk = requested[start:start + chunk_size]
            params = {f"rmu_{i}": name for i, name in enumerate(chunk)}
            bind_list = ", ".join(f":rmu_{i}" for i in range(len(chunk)))
            sql = f"""
                SELECT
                    c.ID,
                    c.NAME,
                    c.FEEDER_ID,
                    f.ID,
                    f.NAME,
                    f.ST_ID,
                    s.ID,
                    s.NAME,
                    s.SUBAREA_ID,
                    a.ID,
                    a.NAME
                FROM DMS_COMBINED_DEVICE c
                LEFT JOIN DMS_FEEDER_DEVICE f
                       ON f.ID = c.FEEDER_ID
                LEFT JOIN SUBSTATION s
                       ON s.ID = f.ST_ID
                LEFT JOIN SUBCONTROLAREA a
                       ON a.ID = s.SUBAREA_ID
                WHERE UPPER(TRIM(CAST(c.NAME AS VARCHAR2(128)))) IN (
                    {bind_list}
                )
            """
            upper_params = {key: str(value).upper() for key, value in params.items()}
            _columns, rows = self.query(sql, upper_params, max_rows=max(len(chunk) * 4, 100), config=config)
            for row in rows:
                row_key = self._rmu_lookup_key(row[1] if len(row) > 1 else "")
                if row_key in rows_by_key:
                    rows_by_key[row_key].append(row)

        contexts: dict[str, RmuDatabaseContext] = {}
        issues: dict[str, str] = {}
        for requested_name in requested:
            key = self._rmu_lookup_key(requested_name)
            rows = rows_by_key.get(key, [])
            if not rows:
                issues[key] = (
                    f"数据库未找到 DMS_COMBINED_DEVICE.NAME={requested_name!r} 的环网柜记录。"
                )
                continue
            if len(rows) > 1:
                issues[key] = (
                    f"数据库中 DMS_COMBINED_DEVICE.NAME={requested_name!r} 返回 {len(rows)} 条记录，"
                    "无法唯一确定所属馈线。"
                )
                continue

            row = rows[0]
            combined_device_id = str(row[0] or "").strip()
            resolved_rmu_name = str(row[1] or requested_name).strip()
            feeder_id = str(row[3] or row[2] or "").strip()
            feeder_name = str(row[4] or "").strip()
            station_id = str(row[6] or row[5] or "").strip()
            station_name = str(row[7] or "").strip()
            subarea_id = str(row[8] or "").strip()
            subcontrolarea_name = str(row[10] or "").strip()
            missing = [
                label for label, value in (
                    ("DMS_COMBINED_DEVICE.ID", combined_device_id),
                    ("DMS_COMBINED_DEVICE.FEEDER_ID", feeder_id),
                    ("DMS_FEEDER_DEVICE.NAME", feeder_name),
                    ("SUBSTATION.NAME", station_name),
                    ("SUBSTATION.SUBAREA_ID", subarea_id),
                    ("SUBCONTROLAREA.NAME", subcontrolarea_name),
                ) if not value
            ]
            if missing:
                issues[key] = (
                    f"RMU {requested_name!r} 的数据库关联信息不完整：" + ", ".join(missing)
                )
                continue

            station_full_name = f"{subcontrolarea_name}-{station_name}"
            feeder_full_name = f"{station_full_name}-{feeder_name}"
            contexts[key] = RmuDatabaseContext(
                rmu_name=resolved_rmu_name,
                combined_device_id=combined_device_id,
                feeder_id=feeder_id,
                feeder_name=feeder_name,
                station_id=station_id,
                station_name=station_name,
                subarea_id=subarea_id,
                subcontrolarea_name=subcontrolarea_name,
                station_full_name=station_full_name,
                feeder_full_name=feeder_full_name,
            )

        return contexts, issues

    def resolve_rmu_context(
        self,
        rmu_name: str,
        *,
        config: OracleConnectionConfig | None = None,
    ) -> RmuDatabaseContext:
        """Resolve one RMU name; convenience wrapper over the batch resolver."""
        name = re.sub(r"\s+", " ", str(rmu_name or "").strip())
        if not name:
            raise ValueError("RMU 名称不能为空。")
        contexts, issues = self.resolve_rmu_contexts([name], config=config)
        key = self._rmu_lookup_key(name)
        if key in issues:
            raise LookupError(issues[key])
        context = contexts.get(key)
        if context is None:
            raise LookupError(f"RMU {name!r} 未解析到所属馈线。")
        return context

    def resolve_station_context(
        self,
        station_name: str,
        *,
        config: OracleConnectionConfig | None = None,
    ) -> StationDatabaseContext:
        """Resolve a station's canonical name using business fields only.

        Authoritative relation:
        SUBSTATION.NAME -> SUBSTATION.SUBAREA_ID -> SUBCONTROLAREA.ID/NAME.
        GRAPH_NAME is deliberately not read or used.  Exact case-insensitive
        NAME matching is required; zero or multiple rows are considered unsafe.
        """
        name = re.sub(r"\s+", " ", str(station_name or "").strip())
        if not name:
            raise ValueError("变电站关键字不能为空。")

        sql = """
            SELECT
                s.ID,
                s.NAME,
                s.SUBAREA_ID,
                a.ID,
                a.NAME
            FROM SUBSTATION s
            LEFT JOIN SUBCONTROLAREA a
                   ON a.ID = s.SUBAREA_ID
            WHERE UPPER(TRIM(s.NAME)) = UPPER(TRIM(:station_name))
        """
        _columns, rows = self.query(sql, {"station_name": name}, max_rows=3, config=config)
        if not rows:
            raise LookupError(f"数据库未找到 SUBSTATION.NAME={name!r} 的变电站记录。")
        if len(rows) > 1:
            raise LookupError(
                f"数据库中 SUBSTATION.NAME={name!r} 返回多条记录，无法唯一确定完整变电站名称。"
            )

        row = rows[0]
        station_id = str(row[0] or "").strip()
        resolved_name = str(row[1] or "").strip()
        subarea_id = str(row[2] or "").strip()
        subcontrolarea_name = str(row[4] or "").strip()
        missing = [
            label for label, value in (
                ("SUBSTATION.ID", station_id),
                ("SUBSTATION.NAME", resolved_name),
                ("SUBSTATION.SUBAREA_ID", subarea_id),
                ("SUBCONTROLAREA.NAME", subcontrolarea_name),
            ) if not value
        ]
        if missing:
            raise LookupError(
                f"SUBSTATION.NAME={name!r} 的数据库关联信息不完整：" + ", ".join(missing)
            )

        station_full_name = f"{subcontrolarea_name}-{resolved_name}"
        return StationDatabaseContext(
            station_id=station_id,
            station_name=resolved_name,
            subarea_id=subarea_id,
            subcontrolarea_name=subcontrolarea_name,
            station_full_name=station_full_name,
        )


    @staticmethod
    def _parse_bay_id(value: object) -> tuple[str, str]:
        """Return ``(station, feeder)`` from DBI BAY_ID.

        Typical examples are ``JED-NTH ABH 13.8kV AH303`` and
        ``JED-NTH ABH 13.8kV AH309_TR1_05``.  The station token immediately
        precedes the voltage token; the feeder is the base bay token immediately
        after it, with bay-detail suffixes removed.
        """
        text = re.sub(r"\s+", " ", str(value or "").strip())
        if not text:
            return "", ""
        tokens = text.split(" ")
        voltage_index = -1
        for index, token in enumerate(tokens):
            if re.fullmatch(r"(?i)\d+(?:\.\d+)?\s*kV", token):
                voltage_index = index
                break
        if voltage_index <= 0 or voltage_index + 1 >= len(tokens):
            return "", ""
        station = tokens[voltage_index - 1].strip()
        bay_token = tokens[voltage_index + 1].strip()
        feeder = bay_token.split("_", 1)[0].strip()
        return station, feeder

    def resolve_topology_feeder_anchors(
        self,
        keyids_by_table: dict[str, Iterable[str]],
        *,
        config: OracleConnectionConfig | None = None,
    ) -> tuple[dict[tuple[str, str], TopologyFeederAnchorContext], dict[tuple[str, str], str]]:
        """Resolve feeder anchors through the authoritative DBI keyid chain.

        Feeder ownership is rooted by the G ``CBreaker`` element:

        - ``CBreaker`` -> DBI table 407 -> ``breaker``

        The 408/409 table specifications remain available for compatibility with
        older callers, but the current G inventory workflow does not use
        Disconnector/GroundDisconnector as feeder roots.

        The G ``keyid`` is *not* a table primary key.  It is first decoded with the
        same DBI functions used by the model-validation workflow::

            long2_to_long1(keyid) -> device_id
            get_tab_no(keyid)     -> table_id
            get_col_no(keyid)     -> column_id (audit only)

        ``SYS_TABLE_INFO`` then verifies the decoded table name.  The decoded
        ``device_id`` is queried from the equipment table, its numeric ``BAY_ID``
        is resolved through ``BAY``, and ``BAY.ST_ID`` is finally resolved through
        ``SUBSTATION``.  Therefore the final business identity is sourced directly
        from ``BAY.NAME`` (feeder) and ``SUBSTATION.NAME`` (station); no G-file
        facID/facName, header text, filename, FeedLine text, or spatial guess is
        involved.

        Returned dictionaries remain keyed by ``(expected_table, original_keyid)``
        because the topology layer works with the original G XML keyid.
        """
        table_specs: dict[str, tuple[int, str]] = {
            "BREAKER": (407, "BREAKER"),
            "DISCONNECTOR": (408, "DISCONNECTOR"),
            "GROUNDDISCONNECTOR": (409, "GROUNDDISCONNECTOR"),
        }
        cfg = config or self.load_config()
        resolved: dict[tuple[str, str], TopologyFeederAnchorContext] = {}
        issues: dict[tuple[str, str], str] = {}
        self.last_topology_feeder_lookup_stats = {}

        def id_text(value: object) -> str:
            if value is None:
                return ""
            text = str(value).strip()
            # Some Oracle/Decimal renderers may expose an integral NUMBER as
            # ``123.0``.  IDs are integer business keys, so normalize only that
            # harmless representation and preserve every other character.
            if re.fullmatch(r"[+-]?\d+\.0+", text):
                text = text.split(".", 1)[0]
            return text

        def chunks(values: list[str], size: int = 300):
            for start_index in range(0, len(values), size):
                yield values[start_index:start_index + size]

        requested_by_table: dict[str, list[str]] = {}
        all_keyids: list[str] = []
        seen_all: set[str] = set()
        for raw_table, raw_ids in keyids_by_table.items():
            table = str(raw_table or "").strip().upper()
            if table not in table_specs:
                raise ValueError(f"不允许用于馈线锚点查询的表：{raw_table!r}")
            requested: list[str] = []
            seen: set[str] = set()
            for raw_id in raw_ids:
                keyid = str(raw_id or "").strip()
                if not keyid or keyid in seen:
                    continue
                seen.add(keyid)
                requested.append(keyid)
                if keyid not in seen_all:
                    seen_all.add(keyid)
                    all_keyids.append(keyid)
            requested_by_table[table] = requested
            self.last_topology_feeder_lookup_stats[table] = {
                "requested": len(requested),
                "decoded": 0,
                "decode_failed": 0,
                "table_valid": 0,
                "table_mismatch": 0,
                "matched": 0,             # compatibility: equipment row matched
                "device_matched": 0,
                "unmatched": 0,           # compatibility: unresolved final keyids
                "valid_bay_id": 0,
                "bay_matched": 0,
                "station_matched": 0,
                "resolved": 0,
                "invalid_bay_id": 0,
                "sample_requested": requested[:3],
                "sample_unmatched": [],
                "sample_resolved": [],
                "dsn": cfg.dsn,
                "username": cfg.username,
            }

        # Phase 1: decode every G keyid through DBI's authoritative functions.
        decoded_by_keyid: dict[str, tuple[str, int, int]] = {}
        invalid_keyids: set[str] = set()
        for keyid in all_keyids:
            if not re.fullmatch(r"\d+", keyid):
                invalid_keyids.add(keyid)

        numeric_keyids = [item for item in all_keyids if item not in invalid_keyids]
        for chunk in chunks(numeric_keyids, 180):
            params: dict[str, Any] = {}
            selects: list[str] = []
            for index, keyid in enumerate(chunk):
                bind = f"key_{index}"
                params[bind] = int(keyid)
                selects.append(
                    f"SELECT :{bind} AS KEY_ID, "
                    f"long2_to_long1(:{bind}) AS DEVICE_ID, "
                    f"get_tab_no(:{bind}) AS TAB_NO, "
                    f"get_col_no(:{bind}) AS COL_NO FROM DUAL"
                )
            sql = " UNION ALL ".join(selects)
            _columns, rows = self.query(sql, params, max_rows=max(len(chunk) * 2, 100), config=cfg)
            for row in rows:
                keyid = id_text(row[0] if len(row) > 0 else "")
                device_id = id_text(row[1] if len(row) > 1 else "")
                try:
                    tab_no = int(row[2]) if len(row) > 2 and row[2] is not None else 0
                except (TypeError, ValueError):
                    tab_no = 0
                try:
                    col_no = int(row[3]) if len(row) > 3 and row[3] is not None else 0
                except (TypeError, ValueError):
                    col_no = 0
                if keyid and device_id and tab_no:
                    decoded_by_keyid[keyid] = (device_id, tab_no, col_no)

        # Phase 2: use the decoded table number to resolve/verify the DBI table name.
        table_ids = sorted({decoded[1] for decoded in decoded_by_keyid.values() if decoded[1]})
        table_name_by_id: dict[int, str] = {}
        if table_ids:
            for id_chunk in [table_ids[i:i + 500] for i in range(0, len(table_ids), 500)]:
                params = {f"tab_{i}": int(tab_id) for i, tab_id in enumerate(id_chunk)}
                bind_list = ", ".join(f":tab_{i}" for i in range(len(id_chunk)))
                sql = (
                    "SELECT TABLE_ID, TABLE_NAME_ENG FROM SYS_TABLE_INFO "
                    f"WHERE TABLE_ID IN ({bind_list})"
                )
                _columns, rows = self.query(sql, params, max_rows=max(len(id_chunk) * 2, 20), config=cfg)
                for row in rows:
                    try:
                        table_id = int(row[0])
                    except (TypeError, ValueError, IndexError):
                        continue
                    table_name_by_id[table_id] = str(row[1] or "").strip()

        def normalized_table_name(value: object) -> str:
            return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())

        validated_device_ids: dict[str, dict[str, str]] = {table: {} for table in table_specs}
        decoded_meta: dict[tuple[str, str], tuple[str, int, int]] = {}
        for table, requested in requested_by_table.items():
            expected_tab_no, expected_table_name = table_specs[table]
            stat = self.last_topology_feeder_lookup_stats[table]
            for keyid in requested:
                issue_key = (table, keyid)
                decoded = decoded_by_keyid.get(keyid)
                if decoded is None:
                    stat["decode_failed"] = int(stat["decode_failed"]) + 1
                    if keyid in invalid_keyids:
                        issues[issue_key] = f"G keyid={keyid!r} 不是有效数字，无法执行 long2_to_long1/get_tab_no。"
                    else:
                        issues[issue_key] = f"G keyid={keyid} 未能通过 long2_to_long1/get_tab_no 解码。"
                    continue
                stat["decoded"] = int(stat["decoded"]) + 1
                device_id, tab_no, col_no = decoded
                decoded_meta[issue_key] = decoded
                if tab_no != expected_tab_no:
                    stat["table_mismatch"] = int(stat["table_mismatch"]) + 1
                    issues[issue_key] = (
                        f"G keyid={keyid} 解码 device_id={device_id}, tab_no={tab_no}, col_no={col_no}；"
                        f"但 {table} 锚点要求 tab_no={expected_tab_no}。"
                    )
                    continue
                db_table_name = table_name_by_id.get(tab_no, "")
                if not db_table_name:
                    stat["table_mismatch"] = int(stat["table_mismatch"]) + 1
                    issues[issue_key] = (
                        f"G keyid={keyid} 解码 tab_no={tab_no}，但 SYS_TABLE_INFO 未找到对应表名。"
                    )
                    continue
                if normalized_table_name(db_table_name) != normalized_table_name(expected_table_name):
                    stat["table_mismatch"] = int(stat["table_mismatch"]) + 1
                    issues[issue_key] = (
                        f"G keyid={keyid} 解码 tab_no={tab_no} -> SYS_TABLE_INFO={db_table_name!r}，"
                        f"与期望表 {expected_table_name!r} 不一致。"
                    )
                    continue
                stat["table_valid"] = int(stat["table_valid"]) + 1
                validated_device_ids[table][keyid] = device_id

        # Phase 3: query the three equipment tables by decoded device_id.
        device_rows_by_table: dict[str, dict[str, list[tuple[Any, ...]]]] = {
            table: {} for table in table_specs
        }
        keyids_by_device: dict[str, dict[str, list[str]]] = {table: defaultdict(list) for table in table_specs}
        for table, mapping in validated_device_ids.items():
            for keyid, device_id in mapping.items():
                keyids_by_device[table][device_id].append(keyid)
            unique_device_ids = list(keyids_by_device[table].keys())
            rows_by_id: dict[str, list[tuple[Any, ...]]] = {item: [] for item in unique_device_ids}
            for chunk in chunks(unique_device_ids, 500):
                params = {f"dev_{i}": int(device_id) for i, device_id in enumerate(chunk)}
                bind_list = ", ".join(f":dev_{i}" for i in range(len(chunk)))
                sql = (
                    f"SELECT TO_CHAR(ID), NAME, TO_CHAR(ST_ID), TO_CHAR(BAY_ID) FROM {table} "
                    f"WHERE ID IN ({bind_list})"
                )
                _columns, rows = self.query(sql, params, max_rows=max(len(chunk) * 3, 100), config=cfg)
                for row in rows:
                    device_id = id_text(row[0] if len(row) > 0 else "")
                    if device_id in rows_by_id:
                        rows_by_id[device_id].append(row)
            device_rows_by_table[table] = rows_by_id
            matched_keyids = 0
            for device_id, keyids in keyids_by_device[table].items():
                if rows_by_id.get(device_id):
                    matched_keyids += len(keyids)
            stat = self.last_topology_feeder_lookup_stats[table]
            stat["matched"] = matched_keyids
            stat["device_matched"] = matched_keyids

        # Phase 4: resolve every equipment BAY_ID through BAY.ID -> BAY.NAME/ST_ID.
        all_bay_ids: list[str] = []
        seen_bays: set[str] = set()
        for rows_by_id in device_rows_by_table.values():
            for rows in rows_by_id.values():
                if len(rows) != 1:
                    continue
                bay_id = id_text(rows[0][3] if len(rows[0]) > 3 else "")
                if bay_id and bay_id not in seen_bays:
                    seen_bays.add(bay_id)
                    all_bay_ids.append(bay_id)
        bay_rows_by_id: dict[str, list[tuple[Any, ...]]] = {item: [] for item in all_bay_ids}
        for chunk in chunks(all_bay_ids, 500):
            params = {f"bay_{i}": int(bay_id) for i, bay_id in enumerate(chunk)}
            bind_list = ", ".join(f":bay_{i}" for i in range(len(chunk)))
            sql = (
                "SELECT TO_CHAR(ID), NAME, TO_CHAR(ST_ID) FROM BAY "
                f"WHERE ID IN ({bind_list})"
            )
            _columns, rows = self.query(sql, params, max_rows=max(len(chunk) * 3, 100), config=cfg)
            for row in rows:
                bay_id = id_text(row[0] if len(row) > 0 else "")
                if bay_id in bay_rows_by_id:
                    bay_rows_by_id[bay_id].append(row)

        # Phase 5: resolve BAY.ST_ID -> SUBSTATION.NAME.
        station_ids: list[str] = []
        seen_stations: set[str] = set()
        for rows in bay_rows_by_id.values():
            if len(rows) != 1:
                continue
            station_id = id_text(rows[0][2] if len(rows[0]) > 2 else "")
            if station_id and station_id not in seen_stations:
                seen_stations.add(station_id)
                station_ids.append(station_id)
        station_rows_by_id: dict[str, list[tuple[Any, ...]]] = {item: [] for item in station_ids}
        for chunk in chunks(station_ids, 500):
            params = {f"st_{i}": int(station_id) for i, station_id in enumerate(chunk)}
            bind_list = ", ".join(f":st_{i}" for i in range(len(chunk)))
            sql = (
                "SELECT TO_CHAR(ID), NAME FROM SUBSTATION "
                f"WHERE ID IN ({bind_list})"
            )
            _columns, rows = self.query(sql, params, max_rows=max(len(chunk) * 3, 100), config=cfg)
            for row in rows:
                station_id = id_text(row[0] if len(row) > 0 else "")
                if station_id in station_rows_by_id:
                    station_rows_by_id[station_id].append(row)

        # Phase 6: assemble one traceable feeder anchor per original G keyid.
        for table, requested in requested_by_table.items():
            stat = self.last_topology_feeder_lookup_stats[table]
            unresolved_samples: list[str] = []
            resolved_samples: list[str] = []
            valid_bay_count = 0
            bay_matched_count = 0
            station_matched_count = 0
            resolved_count = 0
            for keyid in requested:
                issue_key = (table, keyid)
                if issue_key in issues:
                    if len(unresolved_samples) < 3:
                        unresolved_samples.append(keyid)
                    continue
                decoded = decoded_meta.get(issue_key)
                if decoded is None:
                    if len(unresolved_samples) < 3:
                        unresolved_samples.append(keyid)
                    continue
                device_id, tab_no, col_no = decoded
                rows = device_rows_by_table.get(table, {}).get(device_id, [])
                if not rows:
                    issues[issue_key] = (
                        f"G keyid={keyid} -> device_id={device_id}, tab_no={tab_no}, col_no={col_no}；"
                        f"{table}.ID={device_id} 未找到设备记录。"
                    )
                    if len(unresolved_samples) < 3:
                        unresolved_samples.append(keyid)
                    continue
                if len(rows) > 1:
                    issues[issue_key] = (
                        f"G keyid={keyid} -> device_id={device_id}；{table}.ID 返回 {len(rows)} 条记录，无法唯一确定。"
                    )
                    if len(unresolved_samples) < 3:
                        unresolved_samples.append(keyid)
                    continue

                row = rows[0]
                device_name = str(row[1] or "").strip()
                bay_id = id_text(row[3] if len(row) > 3 else "")
                if not bay_id:
                    issues[issue_key] = (
                        f"G keyid={keyid} -> device_id={device_id}；{table}.BAY_ID 为空，请先完成设备 BAY 关联。"
                    )
                    if len(unresolved_samples) < 3:
                        unresolved_samples.append(keyid)
                    continue
                valid_bay_count += 1

                bay_rows = bay_rows_by_id.get(bay_id, [])
                if not bay_rows:
                    issues[issue_key] = (
                        f"G keyid={keyid} -> device_id={device_id} -> BAY_ID={bay_id}；BAY 表未找到对应记录。"
                    )
                    if len(unresolved_samples) < 3:
                        unresolved_samples.append(keyid)
                    continue
                if len(bay_rows) > 1:
                    issues[issue_key] = (
                        f"BAY.ID={bay_id} 返回 {len(bay_rows)} 条记录，无法唯一确定馈线。"
                    )
                    if len(unresolved_samples) < 3:
                        unresolved_samples.append(keyid)
                    continue
                bay_matched_count += 1
                bay_row = bay_rows[0]
                feeder_name = str(bay_row[1] or "").strip()
                station_id = id_text(bay_row[2] if len(bay_row) > 2 else "")
                if not feeder_name:
                    issues[issue_key] = f"BAY.ID={bay_id} 的 NAME 为空，无法确定馈线名称。"
                    if len(unresolved_samples) < 3:
                        unresolved_samples.append(keyid)
                    continue
                if not station_id:
                    issues[issue_key] = f"BAY.ID={bay_id} 的 ST_ID 为空，无法确定所属厂站。"
                    if len(unresolved_samples) < 3:
                        unresolved_samples.append(keyid)
                    continue

                station_rows = station_rows_by_id.get(station_id, [])
                if not station_rows:
                    issues[issue_key] = (
                        f"BAY.ID={bay_id} -> ST_ID={station_id}；SUBSTATION 表未找到对应记录。"
                    )
                    if len(unresolved_samples) < 3:
                        unresolved_samples.append(keyid)
                    continue
                if len(station_rows) > 1:
                    issues[issue_key] = (
                        f"SUBSTATION.ID={station_id} 返回 {len(station_rows)} 条记录，无法唯一确定厂站。"
                    )
                    if len(unresolved_samples) < 3:
                        unresolved_samples.append(keyid)
                    continue
                station_name = str(station_rows[0][1] or "").strip()
                if not station_name:
                    issues[issue_key] = f"SUBSTATION.ID={station_id} 的 NAME 为空，无法确定厂站名称。"
                    if len(unresolved_samples) < 3:
                        unresolved_samples.append(keyid)
                    continue
                station_matched_count += 1

                resolved[issue_key] = TopologyFeederAnchorContext(
                    table_name=table,
                    device_id=device_id,
                    device_name=device_name,
                    bay_id=bay_id,
                    station_name=station_name,
                    feeder_name=feeder_name,
                )
                resolved_count += 1
                if len(resolved_samples) < 3:
                    resolved_samples.append(
                        f"keyid={keyid} -> device_id={device_id} -> tab_no={tab_no} -> "
                        f"BAY_ID={bay_id} -> {station_name}/{feeder_name}"
                    )

            stat["valid_bay_id"] = valid_bay_count
            stat["bay_matched"] = bay_matched_count
            stat["station_matched"] = station_matched_count
            stat["resolved"] = resolved_count
            stat["unmatched"] = len(requested) - resolved_count
            stat["invalid_bay_id"] = max(0, int(stat["device_matched"]) - resolved_count)
            stat["sample_unmatched"] = unresolved_samples
            stat["sample_resolved"] = resolved_samples

        return resolved, issues

    @classmethod
    def validate_read_only_sql(cls, sql: str) -> str:
        statement = str(sql).strip().rstrip(";").strip()
        if not statement:
            raise ValueError("SQL 不能为空。")
        # Ignore leading SQL comments when deciding the first statement keyword.
        normalized = re.sub(r"^\s*(?:(?:--[^\n]*\n)|(?:/\*.*?\*/\s*))*", "", statement, flags=re.DOTALL)
        first = normalized.split(None, 1)[0].upper() if normalized else ""
        if first not in {"SELECT", "WITH"} or cls._WRITE_SQL.search(normalized):
            raise PermissionError("公共数据库服务当前只允许 SELECT / WITH 只读查询。")
        return statement

    def query(
        self,
        sql: str,
        params: dict[str, Any] | Iterable[Any] | None = None,
        *,
        max_rows: int = 10000,
        config: OracleConnectionConfig | None = None,
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        """Execute a bounded read-only query for future modules."""
        statement = self.validate_read_only_sql(sql)
        cfg = config or self.load_config()
        connection = self._connect(cfg)
        try:
            with connection.cursor() as cursor:
                cursor.execute(statement, params or {})
                columns = [str(item[0]) for item in (cursor.description or [])]
                rows = cursor.fetchmany(max(1, min(int(max_rows), 100000)))
                return columns, list(rows)
        finally:
            connection.close()
