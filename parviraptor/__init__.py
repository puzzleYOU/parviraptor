import sys

__version__ = "3.0.2"

if sys.version_info < (3, 12):
    raise RuntimeError("parviraptor requires at least python 3.12")
