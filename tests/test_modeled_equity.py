"""Tests for modeled paper equity mapping (fabio_live + config)."""

from __future__ import annotations

from unittest.mock import patch

import config
import fabio_live.market_data as market_data


def test_modeled_equity_from_raw_pass_through_when_disabled():
    with patch.object(market_data, "FABIO_MODELED_EQUITY_ENABLED", False):
        assert market_data.modeled_equity_from_raw(1_000_000.0) == 1_000_000.0
        assert market_data.modeled_equity_from_raw(10_523.41) == 10_523.41


def test_modeled_equity_from_raw_default_affine_map():
    with patch.object(market_data, "FABIO_MODELED_EQUITY_ENABLED", True):
        with patch.object(market_data, "FABIO_MOOMOO_REFERENCE_EQUITY", 1_000_000.0):
            with patch.object(market_data, "FABIO_DISPLAY_EQUITY_START", 10_000.0):
                assert market_data.modeled_equity_from_raw(1_000_000.0) == 10_000.0
                assert market_data.modeled_equity_from_raw(1_000_581.0) == 10_581.0


def test_modeled_equity_annotation_suffix():
    with patch.object(config, "FABIO_MODELED_EQUITY_ENABLED", False):
        assert config.modeled_equity_annotation_suffix() == ""
    with patch.object(config, "FABIO_MODELED_EQUITY_ENABLED", True):
        with patch.object(config, "FABIO_DISPLAY_EQUITY_START", 10_000.0):
            with patch.object(config, "FABIO_MOOMOO_REFERENCE_EQUITY", 1_000_000.0):
                s = config.modeled_equity_annotation_suffix()
                assert "Modeled book" in s
                assert "10,000" in s
                assert "1,000,000" in s


def test_modeled_equity_dashboard_subtitle():
    with patch.object(config, "FABIO_MODELED_EQUITY_ENABLED", False):
        assert config.modeled_equity_dashboard_subtitle() is None
    with patch.object(config, "FABIO_MODELED_EQUITY_ENABLED", True):
        with patch.object(config, "FABIO_DISPLAY_EQUITY_START", 10_000.0):
            with patch.object(config, "FABIO_MOOMOO_REFERENCE_EQUITY", 1_000_000.0):
                sub = config.modeled_equity_dashboard_subtitle()
                assert sub is not None
                assert "10,000" in sub
                assert "1,000,000" in sub


def test_get_portfolio_value_failure_fallback_modeled():
    class _Ctx:
        def accinfo_query(self, trd_env):
            return -1, None

    with patch.object(market_data, "FABIO_MODELED_EQUITY_ENABLED", True):
        with patch.object(market_data, "FABIO_DISPLAY_EQUITY_START", 10_000.0):
            assert market_data.get_portfolio_value(_Ctx()) == 10_000.0

    with patch.object(market_data, "FABIO_MODELED_EQUITY_ENABLED", False):
        assert market_data.get_portfolio_value(_Ctx()) == 100_000.0
