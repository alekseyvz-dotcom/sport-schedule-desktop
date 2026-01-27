# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ["app/main.py"],
    pathex=["."],
    hiddenimports=[
        "app.services.tenants_service",
        "app.services.orgs_service",
        "app.services.venues_service",
        "app.services.bookings_service",
        "app.services.users_service",
        "app.services.ref_service",
        "app.services.diagnostics_service",
    ],
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
    console=True,  # временно включите консоль для диагностики
)
