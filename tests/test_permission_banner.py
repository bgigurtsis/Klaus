from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication

from klaus.ui.permission_banner import PermissionBanner


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_permission_banner_opens_requested_settings(qt_app) -> None:
    banner = PermissionBanner()
    settings_url = "x-apple.systempreferences:test"
    banner.show_issue("Allow Screen Recording", "Permission needed.", settings_url)

    assert not banner.isHidden()
    assert banner._title.text() == "Allow Screen Recording"

    with patch("klaus.ui.permission_banner.QDesktopServices.openUrl") as open_url:
        banner._settings_button.click()

    assert open_url.call_args.args[0].toString() == settings_url

    banner.clear_issue()
    assert banner.isHidden()
