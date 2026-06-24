# PyInstaller spec for Image Culler — single-file Windows .exe.
#
# Build on Windows (PyInstaller is not a cross-compiler):
#     pip install -r requirements.txt -r requirements-build.txt
#     pyinstaller image-culler.spec
# Output: dist/ImageCuller.exe
#
# Notes:
# - We bundle our own face_landmarker.task model AND MediaPipe's own data files
#   (its .binarypb graphs + bundled .tflite models), which MediaPipe loads from
#   its package dir at runtime; without them the FaceLandmarker fails to build.
# - onefile + multiprocessing (Phase 1 pool) is why __main__ calls
#   freeze_support() first — otherwise each worker re-launches the GUI.
# - console=False: this is a windowed GUI app, no terminal.

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

datas = [("image_culler/assets/face_landmarker.task", "image_culler/assets")]
# MediaPipe ships graph configs (.binarypb) and models it loads at runtime.
datas += collect_data_files("mediapipe")

binaries = collect_dynamic_libs("mediapipe")

hiddenimports = [
    "mediapipe",
    "rawpy",
    "cv2",
]

a = Analysis(
    ["run_image_culler.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ImageCuller",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
