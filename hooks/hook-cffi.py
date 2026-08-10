from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("cffi")
hiddenimports += [
    "_cffi_backend",
    "cffi.api",
    "cffi.backend_ctypes",
    "cffi.cparser",
    "cffi.model",
]
hiddenimports = sorted(set(hiddenimports))
