# Present so pytest adds the repo root to sys.path (via prepend import mode),
# making the image_culler package importable when tests run under the plain
# `pytest` console script (which, unlike `python -m pytest`, does not add CWD).
