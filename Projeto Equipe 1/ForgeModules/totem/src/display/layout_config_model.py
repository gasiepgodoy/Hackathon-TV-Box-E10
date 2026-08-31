# -*- coding: utf-8 -*-
"""
Layout configuration model for QML data binding.

Loads layout_config.json and exposes every property to QML so that the
gui_display.qml can use configurable values instead of hard-coded ones.
When studio/layout-editor mode is active the values can be changed at
runtime and persisted back to the JSON file.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict

from PyQt5.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

_logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "layout_config.json"

# Default layout (mirrors the initial gui_display.qml hard-coded values)
_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "root": {"color": "#f5f5f5"},
    "titleBar": {
        "height": 36,
        "color": "#f7f8fa",
        "x": None,
        "y": None,
        "width": None,
        "height_canvas": None,
        "offsetX": 0,
        "offsetY": 0,
    },
    "statusDot": {
        "width": 8,
        "height": 8,
        "radius": 4,
        "colorReady": "#00b42a", "colorListening": "#ff7d00",
        "colorThinking": "#165dff", "colorError": "#f53f3f",
        "colorDefault": "#c9cdd4",
        "offsetX": 0,
        "offsetY": 0,
    },
    "statusText": {"fontSize": 11, "color": "#86909c", "maxWidth": 200, "offsetX": 0, "offsetY": 0},
    "btnMin": {
        "width": 24, "height": 24, "radius": 6,
        "colorPressed": "#e5e6eb", "colorHover": "#f2f3f5",
        "colorNormal": "transparent", "iconColor": "#4e5969", "iconSize": 14,
        "offsetX": 0,
        "offsetY": 0,
    },
    "btnClose": {
        "width": 24, "height": 24, "radius": 6,
        "colorPressed": "#f53f3f", "colorHover": "#ff7875",
        "colorNormal": "transparent", "iconColor": "#86909c",
        "iconColorHover": "white", "iconSize": 14,
        "offsetX": 0,
        "offsetY": 0,
    },
    "contentArea": {
        "margins": 12,
        "spacing": 12,
        "x": None,
        "y": None,
        "width": None,
        "height": None,
        "offsetX": 0,
        "offsetY": 0,
    },
    "emotionArea": {"minimumHeight": 80, "sizeFactor": 0.7, "minSize": 60, "offsetX": 0, "offsetY": 0},
    "emotionGlow": {
        "scaleFactor": 1.2, "colorInner": "#20165dff", "colorOuter": "transparent",
        "offsetX": 0,
        "offsetY": 0,
    },
    "ttsArea": {
        "height": 60, "color": "transparent", "textMargins": 10,
        "fontSize": 13, "textColor": "#555555",
        "offsetX": 0,
        "offsetY": 0,
    },
    "buttonBar": {
        "height": 72, "color": "#f7f8fa", "margins": 12,
        "bottomMargin": 10, "spacing": 6,
        "x": None, "y": None, "width": None, "height_canvas": None,
        "offsetX": 0,
        "offsetY": 0,
    },
    "autoButton": {
        "preferredWidth": 100, "maxWidth": 140, "height": 38, "radius": 8,
        "colorNormal": "#165dff", "colorHover": "#4080ff",
        "colorPressed": "#0e42d2", "textColor": "white", "fontSize": 12,
        "offsetX": 0,
        "offsetY": 0,
    },
    "abortButton": {
        "preferredWidth": 80, "maxWidth": 120, "height": 38, "radius": 8,
        "colorNormal": "#eceff3", "colorHover": "#f2f3f5",
        "colorPressed": "#e5e6eb", "textColor": "#1d2129", "fontSize": 12,
        "offsetX": 0,
        "offsetY": 0,
    },
    "textInput": {
        "height": 38, "radius": 8, "bgColor": "white",
        "borderColorFocused": "#165dff", "borderColorNormal": "#e5e6eb",
        "borderWidthFocused": 2, "borderWidthNormal": 1,
        "textColor": "#333333", "placeholderColor": "#c9cdd4",
        "fontSize": 12, "leftMargin": 10, "rightMargin": 10,
        "offsetX": 0,
        "offsetY": 0,
    },
    "sendButton": {
        "preferredWidth": 60, "maxWidth": 84, "height": 38, "radius": 8,
        "colorNormal": "#165dff", "colorHover": "#4080ff",
        "colorPressed": "#0e42d2", "colorDisabled": "#a0bfff",
        "textColor": "white", "fontSize": 12,
        "offsetX": 0,
        "offsetY": 0,
    },
}

_THEME_KEYS: Dict[str, list] = {
    "root": ["color"],
    "titleBar": ["color"],
    "statusDot": ["colorReady", "colorListening", "colorThinking", "colorError", "colorDefault"],
    "statusText": ["color"],
    "btnMin": ["colorPressed", "colorHover", "colorNormal", "iconColor"],
    "btnClose": ["colorPressed", "colorHover", "colorNormal", "iconColor", "iconColorHover"],
    "emotionGlow": ["colorInner", "colorOuter"],
    "ttsArea": ["color", "textColor"],
    "buttonBar": ["color"],
    "autoButton": ["colorNormal", "colorHover", "colorPressed", "textColor"],
    "abortButton": ["colorNormal", "colorHover", "colorPressed", "textColor"],
    "textInput": [
        "bgColor",
        "borderColorFocused",
        "borderColorNormal",
        "textColor",
        "placeholderColor",
    ],
    "sendButton": ["colorNormal", "colorHover", "colorPressed", "colorDisabled", "textColor"],
}

_DARK_THEME: Dict[str, Dict[str, Any]] = {
    "root": {"color": "#060f18"},
    "titleBar": {"color": "#0d1826"},
    "statusDot": {
        "colorReady": "#4de28f",
        "colorListening": "#ffbf69",
        "colorThinking": "#66c2ff",
        "colorError": "#ff7285",
        "colorDefault": "#5e7087",
    },
    "statusText": {"color": "#8ea5c4"},
    "btnMin": {
        "colorPressed": "#182536",
        "colorHover": "#122031",
        "colorNormal": "transparent",
        "iconColor": "#9cb7d7",
    },
    "btnClose": {
        "colorPressed": "#ff5d72",
        "colorHover": "#ff7c8c",
        "colorNormal": "transparent",
        "iconColor": "#8fa6c5",
        "iconColorHover": "white",
    },
    "emotionGlow": {
        "colorInner": "#2b9dff",
        "colorOuter": "transparent",
    },
    "ttsArea": {"color": "#0c1724", "textColor": "#edf5ff"},
    "buttonBar": {"color": "#0d1826"},
    "autoButton": {
        "colorNormal": "#2f9fff",
        "colorHover": "#5db7ff",
        "colorPressed": "#227fd1",
        "textColor": "white",
    },
    "abortButton": {
        "colorNormal": "#132232",
        "colorHover": "#1a2c40",
        "colorPressed": "#0f1b2a",
        "textColor": "#d8e6f8",
    },
    "textInput": {
        "bgColor": "#0b1520",
        "borderColorFocused": "#6dc9ff",
        "borderColorNormal": "#223952",
        "textColor": "#eff6ff",
        "placeholderColor": "#6f86a3",
    },
    "sendButton": {
        "colorNormal": "#2f9fff",
        "colorHover": "#5db7ff",
        "colorPressed": "#227fd1",
        "colorDisabled": "#1d3953",
        "textColor": "white",
    },
}


def _build_light_theme() -> Dict[str, Dict[str, Any]]:
    theme: Dict[str, Dict[str, Any]] = {}
    for section, keys in _THEME_KEYS.items():
        defaults = _DEFAULTS.get(section, {})
        if not defaults:
            continue
        theme[section] = {key: defaults.get(key) for key in keys if key in defaults}
    return theme


def _deep_merge(base: dict, override: dict) -> dict:
    """Return *base* with values from *override* applied on top."""
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class LayoutConfigModel(QObject):
    """Exposes layout configuration to QML and supports runtime editing."""

    configChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config: Dict[str, Dict[str, Any]] = _deep_merge(_DEFAULTS, {})
        self._studio_mode = False
        self._studio_available = False
        self._config_version = 0
        self._load()

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _load(self):
        """Load layout_config.json, falling back to built-in defaults."""
        try:
            if _CONFIG_PATH.exists():
                with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._config = _deep_merge(_DEFAULTS, data)
        except Exception as exc:
            _logger.warning("Failed to load layout config (%s), using defaults", exc)
            self._config = _deep_merge(_DEFAULTS, {})

    def _save(self):
        """Persist current config to layout_config.json."""
        try:
            _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(_CONFIG_PATH, "w", encoding="utf-8") as fh:
                json.dump(self._config, fh, indent=4, ensure_ascii=False)
        except Exception as exc:
            _logger.warning("Failed to save layout config: %s", exc)

    # ------------------------------------------------------------------
    # QML-facing API
    # ------------------------------------------------------------------

    @pyqtProperty(bool, notify=configChanged)
    def studioMode(self):
        return self._studio_mode

    @studioMode.setter  # type: ignore[attr-defined]
    def studioMode(self, value):
        if self._studio_mode != value:
            self._studio_mode = value
            self.configChanged.emit()

    @pyqtProperty(bool, notify=configChanged)
    def studioAvailable(self):
        return self._studio_available

    @studioAvailable.setter  # type: ignore[attr-defined]
    def studioAvailable(self, value):
        if self._studio_available != value:
            self._studio_available = value
            self.configChanged.emit()

    @pyqtProperty(int, notify=configChanged)
    def configVersion(self):
        """Incremented on every layout change so QML can observe updates."""
        return self._config_version

    @pyqtSlot(str, str, result="QVariant")
    def get(self, section: str, key: str):
        """Return a single layout value.  ``layoutConfig.get("root", "color")``"""
        return self._config.get(section, {}).get(key)

    @pyqtSlot(str, str, "QVariant")
    def set(self, section: str, key: str, value):
        """Set a layout value at runtime and persist."""
        if section not in self._config:
            self._config[section] = {}
        self._config[section][key] = value
        self._config_version += 1
        self._save()
        self.configChanged.emit()

    @pyqtSlot()
    def resetAll(self):
        """Restore every property to built-in defaults and persist."""
        self._config = _deep_merge(_DEFAULTS, {})
        self._config_version += 1
        self._save()
        self.configChanged.emit()

    @pyqtSlot(str)
    def applyTheme(self, name: str):
        """Apply a named theme by overriding color-related keys."""
        theme_name = (name or "").strip().lower()
        if theme_name == "light":
            theme = _build_light_theme()
        elif theme_name == "dark":
            theme = _DARK_THEME
        else:
            return

        for section, values in theme.items():
            if section not in self._config:
                self._config[section] = {}
            self._config[section].update(values)

        self._config_version += 1
        self._save()
        self.configChanged.emit()

    @pyqtSlot(str)
    def resetSection(self, section: str):
        """Restore one section to defaults and persist."""
        if section in _DEFAULTS:
            self._config[section] = dict(_DEFAULTS[section])
            self._config_version += 1
            self._save()
            self.configChanged.emit()

    @pyqtSlot(result="QVariant")
    def allSections(self):
        """Return a list of section names."""
        return list(self._config.keys())

    @pyqtSlot(str, result="QVariant")
    def sectionKeys(self, section: str):
        """Return key names for a section."""
        return list(self._config.get(section, {}).keys())

    @pyqtSlot(str, result="QVariant")
    def sectionData(self, section: str):
        """Return all key-value pairs for a section as a JS object."""
        return dict(self._config.get(section, {}))

    @pyqtSlot(str, str, result=bool)
    def isDefault(self, section: str, key: str):
        """Return True if the current value matches the built-in default."""
        default_val = _DEFAULTS.get(section, {}).get(key)
        current_val = self._config.get(section, {}).get(key)
        return current_val == default_val

    @pyqtSlot(str, result="QVariant")
    def sectionLabel(self, section: str):
        """Return a human-friendly label for a section."""
        labels = {
            "root": "🎨 Background",
            "titleBar": "📌 Title Bar",
            "statusDot": "🟢 Status Indicator",
            "statusText": "📝 Status Text",
            "btnMin": "➖ Minimize Button",
            "btnClose": "✖ Close Button",
            "contentArea": "📦 Content Area",
            "emotionArea": "😊 Emotion Display",
            "emotionGlow": "✨ Emotion Glow",
            "ttsArea": "💬 TTS Text Area",
            "buttonBar": "🔲 Button Bar",
            "autoButton": "🎙 Talk Button",
            "abortButton": "🛑 Interrupt Button",
            "textInput": "⌨ Text Input",
            "sendButton": "📨 Send Button",
        }
        return labels.get(section, section)
