"""PyInstaller entry point — mirrors ``python -m image_culler``.

PyInstaller analyses a script file, not a ``-m`` module, so this is the frozen
build's entry. freeze_support() must run first so multiprocessing workers don't
re-launch the GUI under the onefile bootloader.
"""

from multiprocessing import freeze_support

from image_culler.gui import main

if __name__ == "__main__":
    freeze_support()
    main()
