# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
hiddenimports += collect_submodules("app")
hiddenimports += collect_submodules("app.services")
hiddenimports += collect_submodules("app.ui")

a = Analysis(
    ["app/main.py"],
    pathex=["."],          # КЛЮЧЕВО: корень проекта в путях
    hiddenimports=hiddenimports,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    a.zipfiles,
    a.hiddenimports,
    name="SportSchedule",
    console=False,
)
