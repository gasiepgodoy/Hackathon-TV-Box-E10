# -*- coding: utf-8 -*-
"""
GUI 显示窗口数据模型 - 用于 QML 数据绑定.
"""

from PyQt5.QtCore import QObject, pyqtProperty, pyqtSignal


class GuiDisplayModel(QObject):
    """
    GUI 主窗口的数据模型，用于 Python 和 QML 之间的数据绑定.
    """

    # 属性变化信号
    statusTextChanged = pyqtSignal()
    emotionPathChanged = pyqtSignal()
    ttsTextChanged = pyqtSignal()
    buttonTextChanged = pyqtSignal()
    buttonBarVisibleChanged = pyqtSignal()
    timeOffsetChanged = pyqtSignal()

    # 用户操作信号
    autoButtonClicked = pyqtSignal()
    abortButtonClicked = pyqtSignal()
    sendButtonClicked = pyqtSignal(str)  # 携带输入的文本

    def __init__(self, parent=None):
        super().__init__(parent)

        # 私有属性
        self._status_text = "Status: Desconectado"
        self._emotion_path = ""  # 表情资源路径（GIF/图片）或 emoji 字符
        self._tts_text = ""
        self._button_text = "Falar"  # 自动模式按钮文本
        self._is_connected = False
        self._button_bar_visible = True
        self._time_offset = 0.0  # offset in milliseconds

    # 状态文本属性
    @pyqtProperty(str, notify=statusTextChanged)
    def statusText(self):
        return self._status_text

    @statusText.setter
    def statusText(self, value):
        if self._status_text != value:
            self._status_text = value
            self.statusTextChanged.emit()

    # 表情路径属性
    @pyqtProperty(str, notify=emotionPathChanged)
    def emotionPath(self):
        return self._emotion_path

    @emotionPath.setter
    def emotionPath(self, value):
        if self._emotion_path != value:
            self._emotion_path = value
            self.emotionPathChanged.emit()

    # TTS 文本属性
    @pyqtProperty(str, notify=ttsTextChanged)
    def ttsText(self):
        return self._tts_text

    @ttsText.setter
    def ttsText(self, value):
        if self._tts_text != value:
            self._tts_text = value
            self.ttsTextChanged.emit()

    # 自动模式按钮文本属性
    @pyqtProperty(str, notify=buttonTextChanged)
    def buttonText(self):
        return self._button_text

    @buttonText.setter
    def buttonText(self, value):
        if self._button_text != value:
            self._button_text = value
            self.buttonTextChanged.emit()

    # 按钮栏可见性
    @pyqtProperty(bool, notify=buttonBarVisibleChanged)
    def buttonBarVisible(self):
        return self._button_bar_visible

    @buttonBarVisible.setter
    def buttonBarVisible(self, value):
        value = bool(value)
        if self._button_bar_visible != value:
            self._button_bar_visible = value
            self.buttonBarVisibleChanged.emit()

    # NTP time offset property (in milliseconds)
    @pyqtProperty(float, notify=timeOffsetChanged)
    def timeOffset(self):
        return self._time_offset

    @timeOffset.setter
    def timeOffset(self, value):
        if self._time_offset != value:
            self._time_offset = float(value)
            self.timeOffsetChanged.emit()

    # 便捷方法
    def update_status(self, status: str, connected: bool):
        """
        更新状态文本和连接状态.
        """
        if status.startswith("状态:") or status.startswith("Status:"):
            self.statusText = status
        else:
            self.statusText = f"Status: {status}"
        self._is_connected = connected

    def update_text(self, text: str):
        """
        更新 TTS 文本.
        """
        self.ttsText = text

    def update_emotion(self, emotion_path: str):
        """
        更新表情路径.
        """
        self.emotionPath = emotion_path

    def update_button_text(self, text: str):
        """
        更新自动模式按钮文本.
        """
        self.buttonText = text

    def update_button_bar_visibility(self, visible: bool):
        """
        更新底部按钮栏可见性.
        """
        self.buttonBarVisible = visible
