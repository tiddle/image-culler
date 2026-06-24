from multiprocessing import freeze_support

from .gui import main

if __name__ == "__main__":
    # AIDEV-NOTE: freeze_support() must run first under a PyInstaller/Windows
    # frozen build, otherwise multiprocessing (Phase 1) re-launches the GUI.
    freeze_support()
    main()
