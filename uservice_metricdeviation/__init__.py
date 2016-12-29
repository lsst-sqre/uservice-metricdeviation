#!/usr/bin/env python
# pylint: disable=invalid-name
# Yep, it's a long module name.
"""SQuaRE QA Microservice proxy (api.lsst.codes-compliant)"""
from .server import server, standalone
__all__ = ["server", "standalone"]
