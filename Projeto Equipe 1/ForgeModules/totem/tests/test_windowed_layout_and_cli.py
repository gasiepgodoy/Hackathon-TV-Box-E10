# -*- coding: utf-8 -*-
"""
Unit tests for Windowed Mode Layout, CLI Argument Parsing, High DPI Scaling, and Responsive Resizing.
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from src.display.gui_display import GuiDisplay
import main_gui
import main_cli


class TestWindowedLayoutAndCLI(unittest.TestCase):

    def test_default_and_minimum_window_sizes(self):
        """Test R1: GuiDisplay constants DEFAULT_WINDOW_SIZE and MINIMUM_WINDOW_SIZE."""
        self.assertEqual(GuiDisplay.DEFAULT_WINDOW_SIZE, (1024, 600))
        self.assertEqual(GuiDisplay.MINIMUM_WINDOW_SIZE, (800, 500))

    def test_layout_config_offsets_cleaned(self):
        """Test R1: Offset noise in config/layout_config.json is zeroed out."""
        config_path = Path(__file__).parent.parent / "config" / "layout_config.json"
        self.assertTrue(config_path.exists(), "layout_config.json missing")

        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        self.assertEqual(cfg["titleBar"]["offsetX"], 0.0)
        self.assertEqual(cfg["titleBar"]["offsetY"], 0.0)
        self.assertEqual(cfg["ttsArea"]["offsetY"], 0.0)
        self.assertEqual(cfg["buttonBar"]["offsetY"], 0.0)

    def test_main_gui_cli_args_parsing(self):
        """Test R2: main_gui._parse_cli_args with -w, --windowed, --gui, -f, -F, -g right/left."""
        # Test -w (windowed)
        with patch.object(sys, "argv", ["main_gui.py", "-w"]):
            fullscreen, studio, gravity, windowed = main_gui._parse_cli_args()
            self.assertFalse(fullscreen)
            self.assertTrue(windowed)

        # Test --windowed
        with patch.object(sys, "argv", ["main_gui.py", "--windowed"]):
            fullscreen, studio, gravity, windowed = main_gui._parse_cli_args()
            self.assertFalse(fullscreen)
            self.assertTrue(windowed)

        # Test --gui
        with patch.object(sys, "argv", ["main_gui.py", "--gui"]):
            fullscreen, studio, gravity, windowed = main_gui._parse_cli_args()
            self.assertFalse(fullscreen)
            self.assertTrue(windowed)

        # Test -f (fullscreen lowercase)
        with patch.object(sys, "argv", ["main_gui.py", "-f"]):
            fullscreen, studio, gravity, windowed = main_gui._parse_cli_args()
            self.assertTrue(fullscreen)
            self.assertFalse(windowed)

        # Test -F (fullscreen uppercase)
        with patch.object(sys, "argv", ["main_gui.py", "-F"]):
            fullscreen, studio, gravity, windowed = main_gui._parse_cli_args()
            self.assertTrue(fullscreen)
            self.assertFalse(windowed)

        # Test -f and -w combined (-w should override -f)
        with patch.object(sys, "argv", ["main_gui.py", "-f", "-w"]):
            fullscreen, studio, gravity, windowed = main_gui._parse_cli_args()
            self.assertFalse(fullscreen)
            self.assertTrue(windowed)

        # Test -g right (gravity)
        with patch.object(sys, "argv", ["main_gui.py", "-g", "right"]):
            fullscreen, studio, gravity, windowed = main_gui._parse_cli_args()
            self.assertEqual(gravity, "right")

        # Test -g left (gravity)
        with patch.object(sys, "argv", ["main_gui.py", "-g", "left"]):
            fullscreen, studio, gravity, windowed = main_gui._parse_cli_args()
            self.assertEqual(gravity, "left")

        # Test -r left (gravity short alias)
        with patch.object(sys, "argv", ["main_gui.py", "-r", "left"]):
            fullscreen, studio, gravity, windowed = main_gui._parse_cli_args()
            self.assertEqual(gravity, "left")

    def test_main_cli_gui_launch_detection(self):
        """Test R2: main_cli._check_gui_launch_args detects windowed/gui/gravity flags."""
        with patch.object(sys, "argv", ["main_cli.py", "-w"]):
            self.assertTrue(main_cli._check_gui_launch_args())

        with patch.object(sys, "argv", ["main_cli.py", "--windowed"]):
            self.assertTrue(main_cli._check_gui_launch_args())

        with patch.object(sys, "argv", ["main_cli.py", "--gui"]):
            self.assertTrue(main_cli._check_gui_launch_args())

        with patch.object(sys, "argv", ["main_cli.py", "-f"]):
            self.assertTrue(main_cli._check_gui_launch_args())

        with patch.object(sys, "argv", ["main_cli.py", "-F"]):
            self.assertTrue(main_cli._check_gui_launch_args())

        with patch.object(sys, "argv", ["main_cli.py", "-g", "right"]):
            self.assertTrue(main_cli._check_gui_launch_args())

        with patch.object(sys, "argv", ["main_cli.py", "-g", "left"]):
            self.assertTrue(main_cli._check_gui_launch_args())

        with patch.object(sys, "argv", ["main_cli.py", "--gravity", "left"]):
            self.assertTrue(main_cli._check_gui_launch_args())

        with patch.object(sys, "argv", ["main_cli.py", "--no-tts"]):
            self.assertFalse(main_cli._check_gui_launch_args())

    def test_rotation_dimension_swap(self):
        """Test R3: Rotation angle dimension swapping logic."""
        gui_normal = GuiDisplay(rotation_gravity=None)
        self.assertEqual(gui_normal._rotation_angle, 0)

        gui_right = GuiDisplay(rotation_gravity="right")
        self.assertEqual(gui_right._rotation_angle, 90)

        gui_left = GuiDisplay(rotation_gravity="left")
        self.assertEqual(gui_left._rotation_angle, -90)

    def test_calculate_window_size_clamping_after_rotation(self):
        """Test that window size clamping happens AFTER rotation dimension swapping."""
        gui = GuiDisplay(rotation_gravity="right")

        class MockRect:
            def width(self):
                return 1920
            def height(self):
                return 768

        class MockDesktop:
            def availableGeometry(self):
                return MockRect()
            def screenGeometry(self):
                return MockRect()

        with patch("PyQt5.QtWidgets.QApplication.desktop", return_value=MockDesktop()):
            (w, h), is_fs = gui._calculate_window_size()
            # Default window (1024, 600) swapped -> (600, 1024).
            # Screen is (1920, 768). Clamped: w=600, h=768.
            self.assertEqual((w, h), (600, 768))


if __name__ == "__main__":
    unittest.main()
