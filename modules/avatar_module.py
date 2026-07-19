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
    # Port already in use. Verify the existing server is serving our assets.
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

    def set_volume(self, vol):
        self.volumeChanged.emit(vol)
        
    def set_emotion(self, emotion):
        self.emotionChanged.emit(emotion)
        
    def set_background(self, bg_name):
        self.backgroundChanged.emit(bg_name)

    def set_viseme(self, viseme_json):
        self.visemeChanged.emit(viseme_json)

class AvatarController(QWidget):
    modeRequested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        # Frameless, stay on top. Removed Qt.Tool so taskbar icon is always visible.
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        
        from PyQt5.QtWebEngineWidgets import QWebEngineSettings
        self.browser = QWebEngineView(self)
        self.browser.settings().setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        self.browser.settings().setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        # Force GPU acceleration for WebGL rendering (Three.js) — without this,
        # QtWebEngine can silently fall back to software rendering, which is
        # what causes choppy/stuttering avatar animation.
        self.browser.settings().setAttribute(QWebEngineSettings.WebGLEnabled, True)
        self.browser.settings().setAttribute(QWebEngineSettings.Accelerated2dCanvasEnabled, True)
        self.browser.page().setBackgroundColor(Qt.transparent)
        self.browser.resize(400, 500)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.browser)
        
        self.resize(400, 500)
        
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 420, screen.height() - 520)
        
        self.bridge = WebBridge()
        self.channel = QWebChannel()
        self.channel.registerObject("bridge", self.bridge)
        self.browser.page().setWebChannel(self.channel)
        
        # Clear cache to force loading patched JS files
        self.browser.page().profile().clearHttpCache()
        
        # Load the WebGL engine via the local HTTP server to bypass file:/// CORS restrictions
        self.browser.setUrl(QUrl(f"http://127.0.0.1:{PORT}/vrm_engine.html"))
        
        self.current_state = "idle"
        
        # Default to Cinematic Mode
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(1000, self.set_cinematic_mode)
        
        self.modeRequested.connect(self._handle_mode_request)

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
        self.showNormal()
        self.browser.setFixedSize(400, 500)
        self.resize(400, 500)
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 420, screen.height() - 520)
        self.bridge.modeChanged.emit("widget")

    def set_state(self, state):
        self.current_state = state
        self.bridge.set_emotion(state)

    def set_volume(self, vol):
        self.bridge.set_volume(vol)

    def set_viseme(self, viseme_json):
        self.bridge.set_viseme(viseme_json)
