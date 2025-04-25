# build.spec
# -*- mode: python -*-

import datetime
from PyInstaller.utils.win32 import versioninfo

block_cipher = None

# Генерируем информацию о версии
build_date = datetime.datetime.now().strftime("%Y.%m.%d")
vs = versioninfo.VSVersionInfo(
    ffi=versioninfo.FixedFileInfo(
        filevers=(1, 0, 0, 0),
        prodvers=(1, 0, 0, 0),
        mask=0x3f,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0)
    ),
    kids=[
        versioninfo.StringFileInfo(
            [
                versioninfo.StringTable(
                    '040904b0',
                    [
                        versioninfo.StringStruct('CompanyName', 'Your Company'),
                        versioninfo.StringStruct('FileDescription', 'Coub Downloader'),
                        versioninfo.StringStruct('FileVersion', f'1.0.{build_date}'),
                        versioninfo.StringStruct('InternalName', 'CoubDownloader'),
                        versioninfo.StringStruct('LegalCopyright', 'Copyright © 2025'),
                        versioninfo.StringStruct('OriginalFilename', 'CoubDownloader.exe'),
                        versioninfo.StringStruct('ProductName', 'Coub Downloader'),
                        versioninfo.StringStruct('ProductVersion', f'1.0.{build_date}'),
                    ]
                )
            ]
        ),
        versioninfo.VarFileInfo([versioninfo.VarStruct('Translation', [0x409, 1200])])
    ]
)

# Добавляем путь к ffmpeg.exe
ffmpeg_binaries = []
try:
    import ffmpeg
    ffmpeg_path = ffmpeg._run.get_ffmpeg_version()[1]  # Получаем путь к ffmpeg
    ffmpeg_binaries += [(ffmpeg_path, '.')]
except:
    pass

# Добавляем явный путь к ffmpeg (замените на ваш реальный путь)
ffmpeg_binaries += [('C:\\Shell\\ffmpeg\\bin\\ffmpeg.exe', '.')]
ffmpeg_binaries += [('C:\\Shell\\ffmpeg\\bin\\ffprobe.exe', '.')]

a = Analysis(
    ['coub_downloader_gui.py'],
    pathex=[],
    binaries=ffmpeg_binaries,
    datas=[],
    hiddenimports=[
        'requests',
        'ffmpeg',
        'ffmpeg._probe',
        'PyQt5.QtCore',
        'PyQt5.QtWidgets',
        'subprocess',
        're',
        'json'
    ],
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
    name='CoubDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon='icon.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=vs
)