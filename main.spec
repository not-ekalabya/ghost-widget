# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect data files from various packages
datas = []

# Add icons folder
datas += [('icons', 'icons')]

# Add Firebase config if exists
if os.path.exists('firebase_config.json'):
    datas += [('firebase_config.json', '.')]

if os.path.exists('github_config.json'):
    datas += [('github_config.json', '.')]

# Collect google-generativeai data files
try:
    datas += collect_data_files('google.generativeai')
except:
    pass

# Collect firebase-admin data files
try:
    datas += collect_data_files('firebase_admin')
except:
    pass

# Collect anthropic data files
try:
    datas += collect_data_files('anthropic')
except:
    pass

# Hidden imports - all required modules
hiddenimports = [
    # Core modules
    'google.generativeai',
    'google.ai.generativelanguage',
    'google.api_core',
    'google.auth',

    # Firebase
    'firebase_admin',
    'firebase_admin.credentials',
    'firebase_admin.firestore',
    'pyrebase4',

    # PyQt6
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',

    # Image processing
    'PIL',
    'PIL.Image',
    'PIL.ImageGrab',

    # System monitoring
    'pynput',
    'pynput.keyboard',
    'psutil',
    'pyperclip',

    # Video processing
    'cv2',
    'mss',
    'numpy',

    # HTTP and requests
    'requests',
    'urllib3',

    # Markdown
    'markdown',

    # GitHub
    'github',
    'PyGithub',

    # Anthropic/Claude
    'anthropic',

    # Mem0
    'mem0',

    # Analytics
    'google.analytics.data',

    # Additional google modules
    'google.cloud',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',

    # gRPC
    'grpc',
    'grpc._cython.cygrpc',
]

# Try to collect all submodules
try:
    hiddenimports += collect_submodules('google.generativeai')
    hiddenimports += collect_submodules('firebase_admin')
    hiddenimports += collect_submodules('google.cloud.firestore')
except:
    pass

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude Qt5
        'PyQt5',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',

        # Exclude heavy ML libraries if not needed
        'torch',
        'tensorflow',
        'keras',

        # Exclude test modules
        'pytest',
        'unittest',
        'test',

        # Exclude development tools
        'IPython',
        'jupyter',
    ],
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
    name='Ghost',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to True for debugging, False for release
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icons/logo-main.png',  # App icon
)
