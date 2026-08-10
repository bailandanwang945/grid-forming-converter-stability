from pathlib import Path
import os

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH).parent
frontend_dist = Path(os.environ["GFM_FRONTEND_DIST"])
fixture_root = project_root / "experiments" / "baseline" / "fixtures"
comparison_root = (
    project_root / "results" / "comparison" / "fig8-damping-grid-strength"
)
build_info = Path(os.environ["GFM_BUILD_INFO"])

datas = [
    (str(frontend_dist), "apps/web/dist"),
    (str(fixture_root), "experiments/baseline/fixtures"),
    (
        str(comparison_root),
        "results/comparison/fig8-damping-grid-strength",
    ),
    (str(build_info), "."),
]

hiddenimports = collect_submodules("uvicorn")

a = Analysis(
    [str(project_root / "backend" / "launcher.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "pandas", "pytest", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GFM-Stability-Platform",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="GFM-Stability-Platform",
)
