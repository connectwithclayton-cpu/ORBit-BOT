"""
Compatibility wrapper for old duplicate filename.

Canonical research backtest file is `Fabio_orb_backtest.py`.
This wrapper prevents drift from maintaining duplicate strategy code.
"""

from Fabio_orb_backtest import *  # noqa: F401,F403
