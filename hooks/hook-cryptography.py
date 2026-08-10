from PyInstaller.utils.hooks import collect_all, copy_metadata

datas, binaries, hiddenimports = collect_all("cryptography")

hiddenimports += [
    "_cffi_backend",
    "cffi",
]

try:
    datas += copy_metadata("cryptography")
except Exception:
    pass

hiddenimports = sorted(set(hiddenimports))
