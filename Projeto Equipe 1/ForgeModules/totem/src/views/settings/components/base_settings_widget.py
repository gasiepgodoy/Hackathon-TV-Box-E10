from PyQt5.QtWidgets import QWidget
from src.utils.logging_config import get_logger

class BaseSettingsWidget(QWidget):
    """
    Base class for settings widgets, providing common UI setter/getter helpers.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_logger(self.__class__.__name__)
        self.ui_controls = {}

    def _set_text_value(self, control_name: str, value: str):
        """
        Set text of a widget control.
        """
        control = self.ui_controls.get(control_name)
        if control and hasattr(control, "setText"):
            control.setText(str(value) if value is not None else "")

    def _get_text_value(self, control_name: str) -> str:
        """
        Get text of a widget control.
        """
        control = self.ui_controls.get(control_name)
        if control and hasattr(control, "text"):
            return control.text().strip()
        return ""

    def _set_check_value(self, control_name: str, value: bool):
        """
        Set checked state of a checkbox or radio button.
        """
        control = self.ui_controls.get(control_name)
        if control and hasattr(control, "setChecked"):
            control.setChecked(bool(value))

    def _get_check_value(self, control_name: str) -> bool:
        """
        Get checked state of a checkbox or radio button.
        """
        control = self.ui_controls.get(control_name)
        if control and hasattr(control, "isChecked"):
            return control.isChecked()
        return False

    def _set_spin_value(self, control_name: str, value: int):
        """
        Set value of a spinbox or slider.
        """
        control = self.ui_controls.get(control_name)
        if control and hasattr(control, "setValue"):
            control.setValue(int(value) if value is not None else 0)

    def _get_spin_value(self, control_name: str) -> int:
        """
        Get value of a spinbox or slider.
        """
        control = self.ui_controls.get(control_name)
        if control and hasattr(control, "value"):
            return control.value()
        return 0
