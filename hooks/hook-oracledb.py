from PyInstaller.utils.hooks import collect_all, copy_metadata

datas, binaries, hiddenimports = collect_all("oracledb")

hiddenimports += [
    "getpass",
    "ssl",
    "socket",
    "secrets",
    "cryptography",
    "cffi",
    "_cffi_backend",
]

try:
    datas += copy_metadata("oracledb")
except Exception:
    pass

hiddenimports = sorted(set(hiddenimports))
