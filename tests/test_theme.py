"""Tests for application theme choices."""

from klaus.ui import theme


def test_theme_uses_helvetica_neue() -> None:
    assert theme.FONT_FAMILY_NAME == "Helvetica Neue"
    assert 'font-family: "Helvetica Neue"' in theme.application_stylesheet()
