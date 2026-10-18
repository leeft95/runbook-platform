from importlib import import_module

try:
    __version__ = import_module(".version", package=__name__).version  # type: ignore
except (ModuleNotFoundError, AttributeError):
    __version__ = "local"
