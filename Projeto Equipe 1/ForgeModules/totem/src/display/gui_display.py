# -*- coding: utf-8 -*-
"""
Módulo de display GUI - implementação QML.
"""

import asyncio
import os
import signal
from abc import ABCMeta
from pathlib import Path
from typing import Callable, Optional

from PyQt5.QtCore import QObject, Qt, QTimer, QUrl
from PyQt5.QtGui import QColor, QCursor, QFont
from PyQt5.QtQuickWidgets import QQuickWidget
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QWidget

from src.display.base_display import BaseDisplay
from src.display.gui_display_model import GuiDisplayModel
from src.display.layout_config_model import LayoutConfigModel
from src.utils.resource_finder import find_assets_dir


# Metaclasse combinada para compatibilidade QObject + ABC
class CombinedMeta(type(QObject), ABCMeta):
    pass


class GuiDisplay(BaseDisplay, QObject, metaclass=CombinedMeta):
    """Classe de display GUI - interface moderna baseada em QML."""

    # Constantes
    EMOTION_EXTENSIONS = (".gif", ".png", ".jpg", ".jpeg", ".webp")
    DEFAULT_WINDOW_SIZE = (1024, 600)
    MINIMUM_WINDOW_SIZE = (800, 500)
    DEFAULT_FONT_SIZE = 12
    QUIT_TIMEOUT_MS = 3000

    def __init__(self, studio_mode: bool = False, rotation_gravity: str = None):
        super().__init__()
        QObject.__init__(self)

        # Componentes Qt
        self.app = None
        self.root = None
        self.qml_widget = None

        # Rotation: "right" → 90°, "left" → -90°, None → 0°
        _gravity_map = {"right": 90, "left": -90}
        self._rotation_angle: int = _gravity_map.get(rotation_gravity, 0) if rotation_gravity else 0

        # Modelo de dados
        self.display_model = GuiDisplayModel()

        # Layout configuration model (exposes all layout properties to QML)
        self.layout_config = LayoutConfigModel()
        self.layout_config.studioAvailable = bool(studio_mode)
        if studio_mode:
            self.layout_config.studioMode = True
            self.display_model.update_text("Olá tudo bem, meu nome é Mina")

        # Gestão de emoções
        self._emotion_cache = {}
        self._last_emotion_name = None
        self._emotion_cache_ready = False

        # Gestão de estado
        self._running = True
        self._force_fullscreen = False
        self.current_status = ""
        self.is_connected = True

        # Estado de drag da janela
        self._dragging = False
        self._drag_start_pos = None
        self._window_start_pos = None

        # Mapeamento de callbacks
        self._callbacks = {
            "auto": None,
            "abort": None,
            "send_text": None,
        }

    # =========================================================================
    # API Pública - callbacks e atualizações
    # =========================================================================

    def set_force_fullscreen(self, force: bool):
        """Force the main window to open full screen."""
        self._force_fullscreen = bool(force)

    async def set_callbacks(
        self,
        auto_callback: Optional[Callable] = None,
        abort_callback: Optional[Callable] = None,
        send_text_callback: Optional[Callable] = None,
    ):
        """
        Configura callbacks.
        """
        self._callbacks.update(
            {
                "auto": auto_callback,
                "abort": abort_callback,
                "send_text": send_text_callback,
            }
        )

    async def update_status(self, status: str, connected: bool):
        """
        Atualiza texto de status.
        """
        self.display_model.update_status(status, connected)

        # Rastreia mudanças de estado
        status_changed = status != self.current_status
        connected_changed = bool(connected) != self.is_connected

        if status_changed:
            self.current_status = status
        if connected_changed:
            self.is_connected = bool(connected)

    async def update_text(self, text: str):
        """
        Atualiza texto TTS.
        """
        self.display_model.update_text(text)

    async def update_emotion(self, emotion_name: str):
        """
        Atualiza emoção exibida.
        """
        if emotion_name == self._last_emotion_name:
            return

        self._last_emotion_name = emotion_name
        asset_path = self._get_emotion_asset_path(emotion_name)

        # Converte caminho local para URL compatível com QML (file:///...),
        # mantendo emoji como texto.
        def to_qml_url(p: str) -> str:
            if not p:
                return ""
            if p.startswith(("qrc:/", "file:")):
                return p
            # Converte para file URL apenas se o caminho existir
            try:
                if os.path.exists(p):
                    return QUrl.fromLocalFile(p).toString()
            except Exception:
                pass
            return p

        url_or_text = to_qml_url(asset_path)
        self.display_model.update_emotion(url_or_text)

    async def update_button_status(self, text: str):
        """
        Atualiza texto do botão.
        """
        self.display_model.update_button_text(text)

    async def update_button_bar_visibility(self, visible: bool):
        """
        Atualiza visibilidade da barra de botões.
        """
        self.display_model.update_button_bar_visibility(visible)

    async def toggle_window_visibility(self):
        """
        Alterna visibilidade da janela.
        """
        if not self.root:
            return

        if self.root.isVisible():
            self.logger.debug("Janela ocultada via atalho")
            self.root.hide()
        else:
            self.logger.debug("Janela exibida via atalho")
            self._show_main_window()

    async def close(self):
        """
        Fecha a janela.
        """
        self._running = False
        if self.root:
            self.root.close()

    # =========================================================================
    # Fluxo de inicialização
    # =========================================================================

    async def start(self):
        """
        Inicia a GUI.
        """
        try:
            self._configure_environment()
            self._create_main_window()
            self._load_qml()
            self._setup_interactions()
            await self._finalize_startup()
        except Exception as e:
            self.logger.error(f"Falha ao iniciar GUI: {e}", exc_info=True)
            raise

    def _configure_environment(self):
        """
        Configura o ambiente.
        """
        os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts.debug=false")

        self.app = QApplication.instance()
        if self.app is None:
            raise RuntimeError("QApplication não encontrado — execute dentro do loop qasync")

        self.app.setQuitOnLastWindowClosed(False)
        self.app.setFont(QFont("PingFang SC", self.DEFAULT_FONT_SIZE))

        self._setup_signal_handlers()
        self._setup_activation_handler()

    def _create_main_window(self):
        """
        Cria a janela principal.
        """
        self.root = QWidget()
        self.root.setWindowTitle("")
        self.root.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)

        # Calcula tamanho da janela conforme configuração
        window_size, is_fullscreen = self._calculate_window_size()
        self.root.resize(*window_size)

        # Tamanho mínimo da janela (ajustado para rotação)
        min_w, min_h = self.MINIMUM_WINDOW_SIZE
        if self._rotation_angle % 180 != 0:
            min_w, min_h = min_h, min_w
        self.root.setMinimumSize(min_w, min_h)

        # Salva estado fullscreen para uso no show
        self._is_fullscreen = is_fullscreen

        self.root.closeEvent = self._closeEvent

    def _calculate_window_size(self) -> tuple:
        """
        Calcula tamanho da janela a partir da configuração. Retorna ((w, h), fullscreen).
        """
        try:
            from src.utils.config_manager import ConfigManager

            config_manager = ConfigManager.get_instance()
            window_size_mode = config_manager.get_config(
                "SYSTEM_OPTIONS.WINDOW_SIZE_MODE", "default"
            )

            desktop = QApplication.desktop()
            screen_geo = desktop.screenGeometry()
            avail_geo = desktop.availableGeometry()

            full_width = screen_geo.width()
            full_height = screen_geo.height()
            avail_width = avail_geo.width()
            avail_height = avail_geo.height()

            if self._force_fullscreen:
                return ((full_width, full_height), True)

            # Calcula tamanho conforme modo
            if window_size_mode == "default":
                # Padrão: 1024x600
                width, height = self.DEFAULT_WINDOW_SIZE
                is_fullscreen = False
            elif window_size_mode == "screen_75":
                width = int(avail_width * 0.75)
                height = int(avail_height * 0.75)
                is_fullscreen = False
            elif window_size_mode == "screen_100":
                # 100%: fullscreen real
                width = full_width
                height = full_height
                is_fullscreen = True
            else:
                # Modo desconhecido: 1024x600
                width, height = self.DEFAULT_WINDOW_SIZE
                is_fullscreen = False

            # Swap dimensions when rotated 90°/270°
            if self._rotation_angle % 180 != 0:
                width, height = height, width

            # Capping width and height to available screen boundaries AFTER rotation swap
            if not is_fullscreen:
                width = min(width, avail_width)
                height = min(height, avail_height)

            return ((width, height), is_fullscreen)

        except Exception as e:
            self.logger.error(f"Falha ao calcular tamanho da janela: {e}", exc_info=True)
            # Fallback: DEFAULT_WINDOW_SIZE limitado pela tela pós-rotação
            try:
                desktop = QApplication.desktop()
                avail_geo = desktop.availableGeometry()
                w, h = self.DEFAULT_WINDOW_SIZE
                if self._rotation_angle % 180 != 0:
                    w, h = h, w
                w = min(w, avail_geo.width())
                h = min(h, avail_geo.height())
                return ((w, h), False)
            except Exception:
                return (self.DEFAULT_WINDOW_SIZE, False)

    def _load_qml(self):
        """
        Carrega interface QML.
        """
        self.qml_widget = QQuickWidget()
        self.qml_widget.setResizeMode(QQuickWidget.SizeRootObjectToView)
        self.qml_widget.setClearColor(QColor("#060f18"))

        # Registra modelo de dados no contexto QML
        qml_context = self.qml_widget.rootContext()
        qml_context.setContextProperty("displayModel", self.display_model)
        qml_context.setContextProperty("lc", self.layout_config)
        qml_context.setContextProperty("appRotationAngle", self._rotation_angle)

        # Carrega arquivo QML
        qml_file = Path(__file__).parent / "gui_display.qml"
        self.qml_widget.setSource(QUrl.fromLocalFile(str(qml_file)))

        # Define como widget central da janela
        layout = QVBoxLayout(self.root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.qml_widget)

    def _setup_interactions(self):
        """
        Configura interações (sinais).
        """
        self._connect_qml_signals()

    async def _finalize_startup(self):
        """
        Finaliza o startup.
        """
        # Eagerly preload all emotion assets to avoid first-use latency
        self._preload_emotion_cache()

        await self.update_emotion("neutral")

        # Resolve NTP time offset in background
        async def sync_time():
            try:
                from src.utils.ntp_sync import resolve_ntp_offset
                offset_seconds = await resolve_ntp_offset()
                self.display_model.timeOffset = offset_seconds * 1000.0
                self.logger.info("Applied NTP time offset: %.3f ms", offset_seconds * 1000.0)
            except Exception as e:
                self.logger.error("Failed to sync NTP time: %s", e)

        asyncio.create_task(sync_time())

        # Decide modo de exibição conforme configuração
        if getattr(self, "_is_fullscreen", False):
            try:
                desktop = QApplication.desktop()
                self.root.setGeometry(desktop.screenGeometry())
            except Exception:
                pass
            self.root.showFullScreen()
        else:
            self.root.show()

    # =========================================================================
    # Conexão de sinais
    # =========================================================================

    def _connect_qml_signals(self):
        """
        Conecta sinais QML aos slots Python.
        """
        root_object = self.qml_widget.rootObject()
        if not root_object:
            self.logger.warning("Objeto raiz QML não encontrado — sinais não conectados")
            return

        # Mapeamento de sinais de botões
        button_signals = {
            "autoButtonClicked": self._on_auto_button_click,
            "abortButtonClicked": self._on_abort_button_click,
            "sendButtonClicked": self._on_send_button_click,
        }

        # Mapeamento de sinais da barra de título
        titlebar_signals = {
            "titleMinimize": self._minimize_window,
            "titleClose": self._quit_application,
            "titleDragStart": self._on_title_drag_start,
            "titleDragMoveTo": self._on_title_drag_move,
            "titleDragEnd": self._on_title_drag_end,
        }

        # Conecta sinais em lote
        for signal_name, handler in {**button_signals, **titlebar_signals}.items():
            try:
                getattr(root_object, signal_name).connect(handler)
            except AttributeError:
                self.logger.debug(f"Sinal {signal_name} não existe (recurso opcional)")

        self.logger.debug("Conexão de sinais QML concluída")

    # =========================================================================
    # Handlers de botões
    # =========================================================================

    def _on_auto_button_click(self):
        """
        Clique no botão auto.
        """
        self._dispatch_callback("auto")

    def _on_abort_button_click(self):
        """
        Clique no botão abortar.
        """
        self._dispatch_callback("abort")

    def _on_send_button_click(self, text: str):
        """
        Clique no botão enviar texto.
        """
        text = text.strip()
        if not text or not self._callbacks["send_text"]:
            return

        try:
            task = asyncio.create_task(self._callbacks["send_text"](text))
            task.add_done_callback(
                lambda t: t.cancelled()
                or not t.exception()
                or self.logger.error(
                    f"Erro na tarefa de envio de texto: {t.exception()}", exc_info=True
                )
            )
        except Exception as e:
            self.logger.error(f"Erro ao enviar texto: {e}")

    def _dispatch_callback(self, callback_name: str, *args):
        """
        Dispatcher genérico de callbacks.
        """
        callback = self._callbacks.get(callback_name)
        if callback:
            callback(*args)

    # =========================================================================
    # Drag de janela
    # =========================================================================

    def _on_title_drag_start(self, x=0, y=0):
        """
        Início do drag pela barra de título.
        """
        if getattr(self, "_is_fullscreen", False):
            return
        self._dragging = True
        self._drag_start_pos = QCursor.pos()
        self._window_start_pos = self.root.pos()

    def _on_title_drag_move(self, x=0, y=0):
        """
        Movimento do drag pela barra de título.
        """
        if not getattr(self, "_is_fullscreen", False) and self._dragging and self._drag_start_pos and self._window_start_pos:
            curr_pos = QCursor.pos()
            delta = curr_pos - self._drag_start_pos
            self.root.move(self._window_start_pos + delta)

    def _on_title_drag_end(self):
        """
        Fim do drag pela barra de título.
        """
        self._dragging = False
        self._drag_start_pos = None
        self._window_start_pos = None

    # =========================================================================
    # Gestão de emoções
    # =========================================================================

    def _get_emotion_asset_path(self, emotion_name: str) -> str:
        """
        Obtém caminho do asset de emoção, com fallback de extensão.
        """
        if emotion_name in self._emotion_cache:
            return self._emotion_cache[emotion_name]

        assets_dir = find_assets_dir()
        if not assets_dir:
            path = "😊"
        else:
            emotion_dir = assets_dir / "emojis"
            # Busca arquivo de emoção, fallback para neutral
            primary = self._find_emotion_file(emotion_dir, emotion_name)
            fallback = self._find_emotion_file(emotion_dir, "neutral")
            if primary:
                path = str(primary)
            elif fallback:
                path = str(fallback)
            else:
                path = "😊"

        self._emotion_cache[emotion_name] = path
        return path

    def _find_emotion_file(self, emotion_dir: Path, name: str) -> Optional[Path]:
        """
        Busca arquivo de emoção no diretório especificado.
        """
        for ext in self.EMOTION_EXTENSIONS:
            file_path = emotion_dir / f"{name}{ext}"
            if file_path.exists():
                return file_path
        return None

    def _preload_emotion_cache(self):
        """
        Eagerly preload all emotion assets into the cache at startup.

        This avoids file-system lookups on the first display of each emotion,
        reducing latency when switching emotions during runtime.
        """
        assets_dir = find_assets_dir()
        if not assets_dir:
            return

        emotion_dir = assets_dir / "emojis"
        if not emotion_dir.is_dir():
            return

        count = 0
        for ext in self.EMOTION_EXTENSIONS:
            for file_path in emotion_dir.glob(f"*{ext}"):
                name = file_path.stem
                if name not in self._emotion_cache:
                    self._emotion_cache[name] = str(file_path)
                    count += 1

        self._emotion_cache_ready = True
        self.logger.debug(f"Preloaded {count} emotion assets into cache")

    # =========================================================================
    # Configurações do sistema
    # =========================================================================

    def _setup_signal_handlers(self):
        """
        Configura handler de sinais (Ctrl+C).
        """
        try:
            signal.signal(
                signal.SIGINT,
                lambda *_: QTimer.singleShot(0, self._quit_application),
            )
        except Exception as e:
            self.logger.warning(f"Falha ao configurar handler de sinais: {e}")

    def _setup_activation_handler(self):
        """
        Handler de ativação do app (clique no Dock do macOS restaura janela).
        """
        try:
            import platform

            if platform.system() != "Darwin":
                return

            self.app.applicationStateChanged.connect(self._on_application_state_changed)
            self.logger.debug("Handler de ativação configurado (suporte Dock macOS)")
        except Exception as e:
            self.logger.warning(f"Falha ao configurar handler de ativação: {e}")

    def _on_application_state_changed(self, state):
        """
        Tratamento de mudança de estado do app (restaura janela via Dock macOS).
        """
        if state == Qt.ApplicationActive and self.root and not self.root.isVisible():
            QTimer.singleShot(0, self._show_main_window)

    def _setup_system_tray(self):
        """
        System tray — removido na versão GUI-only.
        """
        # System tray removed in GUI-only version
        pass

    # =========================================================================
    # Controle de janela
    # =========================================================================

    def _show_main_window(self):
        """
        Exibe a janela principal.
        """
        if not self.root:
            return

        if self.root.isMinimized():
            self.root.showNormal()
        if not self.root.isVisible():
            self.root.show()
        self.root.activateWindow()
        self.root.raise_()

    def _minimize_window(self):
        """
        Minimiza a janela.
        """
        if self.root:
            self.root.showMinimized()

    def _quit_application(self):
        """
        Encerra o aplicativo — versão GUI-only simplificada.
        """
        self.logger.info("Encerrando aplicativo...")
        self._running = False

        try:
            # GUI-only version: simple quit without Application class
            QApplication.quit()
        except Exception as e:
            self.logger.error(f"Falha ao encerrar aplicativo: {e}")
            QApplication.quit()

    def _closeEvent(self, event):
        """
        Evento de fechamento da janela — versão GUI-only encerra direto.
        """
        # System tray removed - always quit application
        self.logger.info("Janela fechada: encerrando aplicativo")
        QTimer.singleShot(0, self._quit_application)
        event.accept()
