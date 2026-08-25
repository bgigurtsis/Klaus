"""Global hotkey backend (pynput) for push-to-talk and mode toggling.

Klaus runs two hotkey backends in parallel: Qt key events on the main window
(no OS permissions, focused window only) and this pynput listener (global,
needs macOS Accessibility). On macOS 26+ pynput crashes the process, so this
module refuses to import it and the listener stays off; the Qt backend still
works.
"""

from __future__ import annotations

import logging
import os
import platform
from collections.abc import Callable

logger = logging.getLogger(__name__)


def should_disable_global_hotkeys() -> bool:
    """Return True when starting pynput global hotkeys is known to crash.

    macOS 26 has a crash path in pynput/Carbon keyboard APIs across supported
    Python versions (HIToolbox dispatch queue assertion). Keep the app alive
    by disabling global hotkeys and relying on in-app Qt hotkeys.

    Also used at import time to skip loading pynput altogether, since merely
    importing pynput loads pyobjc extensions that trigger intermittent
    segfaults in the ctypes layer on this platform combination.
    """
    if os.environ.get("KLAUS_FORCE_GLOBAL_HOTKEYS") == "1":
        return False

    mac_version = platform.mac_ver()[0]
    try:
        mac_major = int(mac_version.split(".", 1)[0])
    except (TypeError, ValueError):
        return False

    return mac_major >= 26


if not should_disable_global_hotkeys():
    from pynput.keyboard import Key, KeyCode, Listener as KeyboardListener
    PYNPUT_AVAILABLE = True
    _SHIFT_KEYS: set = {Key.shift, Key.shift_l, Key.shift_r}
else:
    Key = KeyCode = KeyboardListener = None  # type: ignore[assignment,misc]
    PYNPUT_AVAILABLE = False
    _SHIFT_KEYS = set()

_PYNPUT_SHIFTED_VARIANTS: dict[str, str] = {
    "±": "§",
}

_MACOS_FKEY_HINT = (
    "macOS: F-keys trigger system actions by default "
    "(F3 = Mission Control). Use Fn+key, enable 'Use F1, F2, etc. "
    "keys as standard function keys' in System Settings > Keyboard, "
    "or set a different key in ~/.klaus/config.toml (toggle_key)."
)


def resolve_pynput_key(key_name: str) -> object:
    """Convert a config key name (e.g. ``'F2'``) to a pynput key object.

    Only valid when ``PYNPUT_AVAILABLE`` is True.
    """
    try:
        return getattr(Key, key_name.lower())
    except AttributeError:
        if len(key_name) == 1:
            return KeyCode.from_char(key_name)
        raise ValueError(f"Unknown hotkey: {key_name!r}")


def _mark_key_pressed(pressed: set[object], key: object | None) -> bool:
    """Track key presses and suppress repeated press events for held keys."""
    if key is None:
        return False
    if key in pressed:
        return False
    pressed.add(key)
    return True


def _mark_key_released(pressed: set[object], key: object | None) -> None:
    if key is None:
        return
    pressed.discard(key)


def _is_shift_active(pressed: set[object]) -> bool:
    return any(key in pressed for key in _SHIFT_KEYS)


def _resolve_shifted_key(key: object | None, shift_active: bool) -> object | None:
    """Map a shifted character back to its unshifted base key (e.g. ± → §)."""
    if not shift_active or key is None:
        return key
    char = getattr(key, "char", None)
    if char and char in _PYNPUT_SHIFTED_VARIANTS:
        return KeyCode.from_char(_PYNPUT_SHIFTED_VARIANTS[char])
    return key


def _hotkey_action_for_press(
    *,
    key: object | None,
    ptt_key: object,
    toggle_key: object,
    shift_active: bool,
) -> str | None:
    """Classify a key press as ``ptt_down``, ``toggle``, or ``None``."""
    if key is None:
        return None

    effective = _resolve_shifted_key(key, shift_active)
    if effective != ptt_key and effective != toggle_key:
        return None

    if ptt_key == toggle_key and effective == ptt_key:
        return "toggle" if shift_active else "ptt_down"

    if effective == toggle_key:
        return "toggle"
    if effective == ptt_key:
        return "ptt_down"
    return None


class HotkeyListener:
    """Own the pynput global listener and its key-name configuration."""

    def __init__(
        self,
        ptt_key_name: str,
        toggle_key_name: str,
        *,
        on_ptt_down: Callable[[], None],
        on_ptt_up: Callable[[], None],
        on_toggle: Callable[[], None],
    ) -> None:
        self._on_ptt_down = on_ptt_down
        self._on_ptt_up = on_ptt_up
        self._on_toggle = on_toggle
        self._listener = None
        self.set_keys(ptt_key_name, toggle_key_name)

    @property
    def ptt_key_name(self) -> str:
        return self._ptt_key_name

    @property
    def toggle_key_name(self) -> str:
        return self._toggle_key_name

    def set_keys(self, ptt_key_name: str, toggle_key_name: str) -> None:
        """Update the configured key names (takes effect on the next start)."""
        self._ptt_key_name = ptt_key_name
        self._toggle_key_name = toggle_key_name
        if PYNPUT_AVAILABLE:
            self._ptt_key = resolve_pynput_key(ptt_key_name)
            self._toggle_key = resolve_pynput_key(toggle_key_name)
        else:
            self._ptt_key = None
            self._toggle_key = None

    def start(self) -> None:
        """Start the global listener; log and carry on when it cannot start.

        On macOS this requires Accessibility permission, which is hard to
        grant when running as a Python script. If the listener fails to start
        we log a warning but carry on -- the Qt in-app key events still work
        when the window is focused.
        """
        if should_disable_global_hotkeys():
            logger.warning(
                "Global hotkeys disabled on macOS %s with Python %s due a known "
                "pynput crash. In-app hotkeys still work when the Klaus window "
                "is focused. Set KLAUS_FORCE_GLOBAL_HOTKEYS=1 to force-enable "
                "them (may crash).",
                platform.mac_ver()[0] or "unknown",
                platform.python_version(),
            )
            logger.info(_MACOS_FKEY_HINT)
            return

        ptt_key = self._ptt_key
        toggle_key = self._toggle_key
        pressed_keys: set[object] = set()
        ptt_key_armed = False

        def on_press(key: object | None) -> None:
            nonlocal ptt_key_armed
            if not _mark_key_pressed(pressed_keys, key):
                return

            action = _hotkey_action_for_press(
                key=key,
                ptt_key=ptt_key,
                toggle_key=toggle_key,
                shift_active=_is_shift_active(pressed_keys),
            )
            if action == "toggle":
                self._on_toggle()
                return
            if action == "ptt_down" and not ptt_key_armed:
                ptt_key_armed = True
                self._on_ptt_down()

        def on_release(key: object | None) -> None:
            nonlocal ptt_key_armed
            _mark_key_released(pressed_keys, key)
            if key == ptt_key and ptt_key_armed:
                ptt_key_armed = False
                self._on_ptt_up()

        try:
            self._listener = KeyboardListener(
                on_press=on_press, on_release=on_release,
            )
            self._listener.daemon = True
            self._listener.start()
            logger.info(
                "Global hotkey listener started (ptt=%s, toggle=%s)",
                self._ptt_key_name,
                self._toggle_key_name,
            )
        except Exception as exc:
            logger.warning(
                "Global hotkey listener failed to start: %s. "
                "In-app hotkeys still work when the Klaus window is focused.",
                exc,
            )

        logger.info(_MACOS_FKEY_HINT)

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None

    def restart(self, ptt_key_name: str, toggle_key_name: str) -> None:
        """Apply new key names; restart only if the listener was running."""
        was_running = self._listener is not None
        self.stop()
        self.set_keys(ptt_key_name, toggle_key_name)
        if was_running:
            self.start()
