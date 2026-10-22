"""Single source of the app version (read by the app and by installer/build_installer.ps1)."""

APP_VERSION = "2.10.0"
VERSION = ".".join(APP_VERSION.split(".")[:2])  # short form shown in the UI, e.g. "2.5"
