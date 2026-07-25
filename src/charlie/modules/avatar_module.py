import sys
import os
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout
from PyQt5.QtCore import Qt, QUrl, QObject, pyqtSignal
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel

ASSET_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "avatar")

import http.server
import socketserver
import threading
import functools

PORT = 8123
Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ASSET_DIR)
try:
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
except OSError:
    import urllib.request
    try:
        req = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/vrm_engine.html", timeout=2)
        if req.getcode() != 200:
            print(f"\n[WARNING] Port {PORT} is in use, but failed to serve Charlie's assets! You may have a crashed zombie Python process blocking the port.")
    except Exception as e:
        print(f"\n[WARNING] Port {PORT} is blocked by an unresponsive process: {e}")

class WebBridge(QObject):
    volumeChanged = pyqtSignal(float)
    emotionChanged = pyqtSignal(str)
    modeChanged = pyqtSignal(str)
    listeningStatusChanged = pyqtSignal(bool)
    backgroundChanged = pyqtSignal(str)
    visemeChanged = pyqtSignal(str)  # JSON string: {"aa":0.2,"ih":0.0,"ou":0.6,"ee":0.0,"oh":0.1}
    statusTextChanged = pyqtSignal(str)  # e.g. "🧠 Thinking...", "⚡ Executing...", "" to hide
    smilePulseRequested = pyqtSignal()  # brief post-response smile, no payload needed

    def set_volume(self, vol):
        self.volumeChanged.emit(vol)
        
    def set_emotion(self, emotion):
        self.emotionChanged.emit(emotion)
        
    def set_background(self, bg_name):
        self.backgroundChanged.emit(bg_name)

    def set_viseme(self, viseme_json):
        self.visemeChanged.emit(viseme_json)

    def set_status_text(self, text):
        self.statusTextChanged.emit(text)

    def flash_smile(self):
        self.smilePulseRequested.emit()

class AvatarController(QWidget):
    modeRequested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        # Frameless, stay on top. Removed Qt.Tool so taskbar icon is always visible.
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        
        from PyQt5.QtWebEngineWidgets import QWebEngineSettings
        self.browser = QWebEngineView(self)
        self.browser.setAttribute(Qt.WA_OpaquePaintEvent, False)
        self.browser.setAttribute(Qt.WA_TranslucentBackground, True)
        self.browser.setStyleSheet("background: transparent; border: none;")
        self.browser.settings().setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        self.browser.settings().setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        self.browser.settings().setAttribute(QWebEngineSettings.WebGLEnabled, True)
        self.browser.settings().setAttribute(QWebEngineSettings.Accelerated2dCanvasEnabled, True)
        self.browser.page().setBackgroundColor(Qt.transparent)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.browser)
        
        self.bridge = WebBridge()
        self.channel = QWebChannel()
        self.channel.registerObject("bridge", self.bridge)
        self.browser.page().setWebChannel(self.channel)
        
        self.browser.page().profile().clearHttpCache()
        self.browser.setUrl(QUrl(f"http://127.0.0.1:{PORT}/vrm_engine.html"))
        
        self.current_state = "idle"
        self.modeRequested.connect(self._handle_mode_request)
        
        # Start natively in cinematic mode
        self.set_cinematic_mode()

    def _handle_mode_request(self, mode):
        if mode == "cinematic" or mode == "fullscreen":
            self.set_cinematic_mode()
        elif mode == "widget":
            self.set_widget_mode()

    def set_cinematic_mode(self):
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.browser.setFixedSize(screen.width(), screen.height())
        self.showFullScreen()
        self.bridge.modeChanged.emit("cinematic")

    def set_widget_mode(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.showNormal()
        self.browser.setFixedSize(400, 500)
        self.resize(400, 500)
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 420, screen.height() - 520)
        self.show()
        self.bridge.modeChanged.emit("widget")

    def set_state(self, state):
        self.current_state = state
        self.bridge.set_emotion(state)

    def set_volume(self, vol):
        self.bridge.set_volume(vol)

    def set_viseme(self, viseme_json):
        self.bridge.set_viseme(viseme_json)

    def set_status_text(self, text):
        self.bridge.set_status_text(text)

    def flash_smile(self):
        self.bridge.flash_smile()
