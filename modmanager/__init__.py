__version__ = "1.1.0"
APP_NAME = "Ronin Mod Manager"  # shown to the user and used for the folders the app creates
try:  # written by the test-build (nightly) workflow only: the short commit id this app was built from
    from ._build import BUILD
except ImportError:
    BUILD = ""
