"""Local development settings layered on top of the base configuration."""

from __future__ import annotations

from decouple import config

from .base import *

DEBUG = config("DEBUG", default=True, cast=bool)
