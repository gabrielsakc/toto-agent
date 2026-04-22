"""
Desktop bulldog pet — transparent always-on-top widget driven by sprite
sequences extracted from short Veo videos.

State flow on a new mail:
  SLEEP (seq_breath loop) -> seq_wake -> seq_bark
    -> seq_run left across screen -> seq_run right back
    -> seq_yawn -> SLEEP (seq_breath loop)

All sequences live as numbered PNGs in assets_processed/seq_*/ — generated
by running extract_frames.py.
"""
from __future__ import annotations
import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

import numpy as np
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QUrl,
    pyqtSignal, pyqtSlot,
)
from PyQt6.QtGui import (
    QPixmap, QBitmap, QImage, QIcon, QAction, QTransform,
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMenu,
    QMessageBox, QPushButton, QSpinBox, QSystemTrayIcon, QVBoxLayout, QWidget,
    QApplication,
)


# ---------------------------------------------------------------------------
# Win32 DWM tweak: kill the 1-px accent border + rounded corners that W11
# draws around every top-level frameless window.
# ---------------------------------------------------------------------------
def _disable_win11_frame(hwnd: int):
    if sys.platform != "win32":
        return
    import ctypes
    DWMWA_WINDOW_CORNER_PREFERENCE = 33
    DWMWA_BORDER_COLOR = 34
    DWMWCP_DONOTROUND = 1
    DWMWA_COLOR_NONE = 0xFFFFFFFE
    try:
        dwm = ctypes.windll.dwmapi
    except OSError:
        return
    pref = ctypes.c_int(DWMWCP_DONOTROUND)
    dwm.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                              ctypes.byref(pref), ctypes.sizeof(pref))
    col = ctypes.c_uint(DWMWA_COLOR_NONE)
    dwm.DwmSetWindowAttribute(hwnd, DWMWA_BORDER_COLOR,
                              ctypes.byref(col), ctypes.sizeof(col))


# ---------------------------------------------------------------------------
# Per-sequence playback config.
# ---------------------------------------------------------------------------
@dataclass
class SeqCfg:
    folder: str
    fps: int
    start: int = 0
    end: int | None = None      # None = last
    target_h: int = 180         # height in pixels when displayed (width auto)
    loops: int = 1              # 0 = infinite

SEQ = {
    # target_h is calibrated per-clip so the dog's APPARENT size is consistent
    # across sequences. The bark/yawn video clips were filmed too close so we
    # drive those phases with static full-body stills instead.
    "breath": SeqCfg("seq_breath", fps=8,  target_h=110, loops=0),
    "wake":   SeqCfg("seq_wake",   fps=14, target_h=220, loops=1),
    "run":    SeqCfg("seq_run",    fps=14, target_h=160, loops=1),
}

# Static full-body poses used to drive the BARK phase (the Veo bark video
# was a head-only close-up so it looked oversized against the other clips).
STATIC_POSE_H = 220  # matches the wake sequence standing height

# (pose_name, duration_ms, vertical_hop_px)
BARK_POSE_STEPS = [
    ("bark",        200, -10),
    ("stand_front", 180,   0),
    ("bark_wide",   230, -16),
    ("stand_front", 440,   0),   # pause between volleys
    ("bark",        200, -10),
    ("stand_front", 320,   0),   # settle before running
]


class State(Enum):
    SLEEP = auto()
    PLAYBACK = auto()   # one-shot sequence in progress
    RUN_LEFT = auto()
    RUN_RIGHT = auto()


# ---------------------------------------------------------------------------
# Sprite player — loads PNGs from a folder and steps through them with a
# QTimer. One player per window; frames of the previous sequence are dropped
# when a new one starts, to bound memory.
# ---------------------------------------------------------------------------
class SpritePlayer:
    def __init__(self, window: "PetWindow"):
        self.w = window
        self.timer = QTimer(window)
        self.timer.timeout.connect(self._tick)
        self.frames: list[QPixmap] = []
        self.flipped_cache: dict[int, QPixmap] = {}
        self.idx = 0
        self.loops_remaining = 0
        self.on_done = None
        self.flip_h = False
        self.cfg: SeqCfg | None = None

    def stop(self):
        self.timer.stop()

    def play(self, cfg: SeqCfg, assets_dir: Path, *,
             flip_h: bool = False, reverse: bool = False, on_done=None):
        self.timer.stop()
        folder = assets_dir / cfg.folder
        files = sorted(folder.glob("*.png"))
        end = cfg.end if cfg.end is not None else len(files)
        files = files[cfg.start:end]
        if reverse:
            files = list(reversed(files))
        self.frames = []
        for f in files:
            pix = QPixmap(str(f))
            if pix.isNull():
                continue
            if pix.height() != cfg.target_h:
                pix = pix.scaledToHeight(cfg.target_h,
                                         Qt.TransformationMode.SmoothTransformation)
            self.frames.append(pix)
        self.flipped_cache.clear()
        self.idx = 0
        self.loops_remaining = cfg.loops if cfg.loops > 0 else 10**9
        self.flip_h = flip_h
        self.on_done = on_done
        self.cfg = cfg
        if not self.frames:
            print(f"[warn] no frames for {cfg.folder}")
            if on_done:
                on_done()
            return
        interval = max(10, int(1000 / cfg.fps))
        self._tick()
        self.timer.start(interval)

    def _tick(self):
        if self.idx >= len(self.frames):
            self.loops_remaining -= 1
            if self.loops_remaining <= 0:
                self.timer.stop()
                if self.on_done:
                    cb = self.on_done
                    self.on_done = None
                    cb()
                return
            self.idx = 0
        pix = self._current_pix()
        self.w.render_frame(pix)
        self.idx += 1

    def _current_pix(self) -> QPixmap:
        if not self.flip_h:
            return self.frames[self.idx]
        cached = self.flipped_cache.get(self.idx)
        if cached is None:
            cached = self.frames[self.idx].transformed(
                QTransform().scale(-1, 1),
                Qt.TransformationMode.SmoothTransformation)
            self.flipped_cache[self.idx] = cached
        return cached


# ---------------------------------------------------------------------------
class GmailConfigDialog(QDialog):
    """Small form to capture Gmail username + App password. Emits `saved`
    with the resulting gmail dict when the user clicks Save."""
    saved = pyqtSignal(dict)

    def __init__(self, current: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurar Gmail")
        self.setModal(True)
        self.resize(500, 300)

        g = current or {}

        self.enabled = QCheckBox("Activar monitor de mail")
        self.enabled.setChecked(bool(g.get("enabled", False)))

        self.username = QLineEdit(g.get("username", ""))
        self.username.setPlaceholderText("usuario@gmail.com")

        self.pwd = QLineEdit(g.get("app_password", ""))
        self.pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd.setPlaceholderText("16 caracteres (sin espacios)")

        self.poll = QSpinBox()
        self.poll.setRange(10, 600)
        self.poll.setValue(int(g.get("poll_seconds", 30)))
        self.poll.setSuffix(" seg")

        form = QFormLayout()
        form.addRow(self.enabled)
        form.addRow("Usuario:", self.username)
        form.addRow("App password:", self.pwd)
        form.addRow("Polling:", self.poll)

        help_lbl = QLabel(
            'Generá una <b>App Password</b> en '
            '<a href="https://myaccount.google.com/apppasswords">'
            'myaccount.google.com/apppasswords</a>. Requiere que tengas '
            'verificación en dos pasos activada en tu cuenta de Google.'
        )
        help_lbl.setOpenExternalLinks(True)
        help_lbl.setWordWrap(True)

        test_btn = QPushButton("Probar conexión")
        test_btn.clicked.connect(self._test)
        save_btn = QPushButton("Guardar")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)

        btns = QHBoxLayout()
        btns.addWidget(test_btn)
        btns.addStretch(1)
        btns.addWidget(cancel_btn)
        btns.addWidget(save_btn)

        main = QVBoxLayout()
        main.addWidget(help_lbl)
        main.addLayout(form)
        main.addLayout(btns)
        self.setLayout(main)

    def _values(self) -> dict:
        return {
            "enabled": self.enabled.isChecked(),
            "username": self.username.text().strip(),
            "app_password": self.pwd.text().strip().replace(" ", ""),
            "poll_seconds": int(self.poll.value()),
            "imap_host": "imap.gmail.com",
            "imap_port": 993,
        }

    def _test(self):
        v = self._values()
        if not v["username"] or not v["app_password"]:
            QMessageBox.warning(self, "Faltan datos",
                                "Completá usuario y app password.")
            return
        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            from imapclient import IMAPClient
            with IMAPClient("imap.gmail.com", port=993, ssl=True) as c:
                c.login(v["username"], v["app_password"])
                info = c.select_folder("INBOX", readonly=True)
                count = info.get(b"EXISTS", 0)
            QMessageBox.information(
                self, "Conexión exitosa",
                f"Login OK como {v['username']}.\nINBOX tiene {count} mensajes.")
        except Exception as e:
            QMessageBox.critical(self, "Error de conexión", str(e))
        finally:
            self.unsetCursor()

    def _save(self):
        v = self._values()
        if v["enabled"] and (not v["username"] or not v["app_password"]):
            QMessageBox.warning(self, "Faltan datos",
                                "Si el monitor está activado, completá "
                                "usuario y app password.")
            return
        self.saved.emit(v)
        self.accept()


# ---------------------------------------------------------------------------
class PetWindow(QWidget):
    RUN_LEG_MS = 3600

    configSaved = pyqtSignal(dict)   # emits full cfg after user saves Gmail form

    def __init__(self, assets_dir: Path, cfg: dict, config_dir: Path | None = None):
        super().__init__()
        self.assets_dir = Path(assets_dir)
        self.cfg = cfg
        self.config_dir = Path(config_dir) if config_dir else None
        self.margin = int(cfg.get("margin_px", 40))

        # Allow config to override target heights per sequence.
        heights = cfg.get("pet_heights", {})
        for key, override in heights.items():
            if key in SEQ:
                SEQ[key].target_h = int(override)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        # NOTE: WA_TransparentForMouseEvents is INTENTIONALLY not set — we
        # want right-click on the dog to open the context menu. The per-frame
        # alpha mask in render_frame() ensures clicks outside the dog's
        # silhouette still pass through to the desktop beneath.
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent;")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

        self.label = QLabel(self)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.label.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.label.setAutoFillBackground(False)
        self.label.setStyleSheet("background: transparent;")

        screen = QApplication.primaryScreen().availableGeometry()
        self.screen_rect = screen
        self.baseline_y = screen.bottom() - self.margin
        self.anchor_right = screen.right() - self.margin

        self.state = State.SLEEP
        self.player = SpritePlayer(self)
        self._render_mode = "anchor"  # anchor / fixed (during run)
        self._fixed_pos: QPoint | None = None

        self._static_cache: dict[str, QPixmap] = {}
        self._pose_queue: list[tuple[str, int, int]] = []
        self._pose_done_cb = None
        self._pose_timer = QTimer(self)
        self._pose_timer.setSingleShot(True)
        self._pose_timer.timeout.connect(self._pose_tick)

        try:
            self._init_audio()
        except Exception as exc:
            print(f"[warn] audio init failed ({exc}); continuing without sound")
            self.snore_player = None
            self.bark_player  = None
            self.snore_audio  = None
            self.bark_audio   = None
            self._sound_enabled = False
        self._start_sleep()
        self._build_tray()

    # ---------------------------------------------------------------- audio
    def _init_audio(self):
        """Wire up two QMediaPlayer instances (MP3/WAV capable): a looping
        snore while the dog sleeps, and a one-shot bark fired on each bark
        pose. Files are looked up by several extensions so you can drop in
        either an MP3 or a WAV."""
        sound_dir = self.assets_dir / "sound"

        def find(*names) -> Path | None:
            for n in names:
                p = sound_dir / n
                if p.exists():
                    return p
            return None

        self.snore_audio = QAudioOutput(self)
        self.snore_player = QMediaPlayer(self)
        self.snore_player.setAudioOutput(self.snore_audio)
        snore = find("snore.mp3", "snore.wav")
        if snore is not None:
            self.snore_player.setSource(QUrl.fromLocalFile(str(snore)))
            # Use -1 (QMediaPlayer.Infinite) directly; Loops enum may not exist
            # in all PyQt6 builds.
            self.snore_player.setLoops(-1)

        self.bark_audio = QAudioOutput(self)
        self.bark_player = QMediaPlayer(self)
        self.bark_player.setAudioOutput(self.bark_audio)
        bark = find("bark.mp3", "bark.wav")
        if bark is not None:
            self.bark_player.setSource(QUrl.fromLocalFile(str(bark)))

        self._sound_enabled = bool(self.cfg.get("sound_enabled", True))
        self._apply_sound_volumes()

    def _apply_sound_volumes(self):
        """Re-apply audio-output volumes based on `_sound_enabled`."""
        if self.snore_audio is None or self.bark_audio is None:
            return
        if self._sound_enabled:
            self.snore_audio.setVolume(float(self.cfg.get("snore_volume", 0.22)))
            self.bark_audio.setVolume(float(self.cfg.get("bark_volume", 0.80)))
        else:
            self.snore_audio.setVolume(0.0)
            self.bark_audio.setVolume(0.0)

    def _has_source(self, player: "QMediaPlayer | None") -> bool:
        if player is None:
            return False
        src = player.source()
        return src is not None and not src.isEmpty()

    def _start_snore(self):
        if not self._sound_enabled or self.snore_player is None:
            return
        if self._has_source(self.snore_player):
            self.snore_player.setPosition(0)
            self.snore_player.play()

    def _stop_snore(self):
        if self.snore_player is not None:
            self.snore_player.stop()

    def _play_bark_sfx(self):
        if not self._sound_enabled or self.bark_player is None:
            return
        if self._has_source(self.bark_player):
            # Rewind + replay so rapid fires cut in cleanly.
            self.bark_player.stop()
            self.bark_player.setPosition(0)
            self.bark_player.play()

    def _toggle_sound(self, on: bool):
        self._sound_enabled = bool(on)
        self._apply_sound_volumes()
        # Persist the choice so it sticks across restarts.
        self.cfg["sound_enabled"] = self._sound_enabled
        self._persist_cfg()
        # If we just turned sound ON while already sleeping, start the snore;
        # if we turned it OFF, stop it.
        if self._sound_enabled and self.state == State.SLEEP:
            self._start_snore()
        elif not self._sound_enabled:
            self._stop_snore()
        # Keep the tray checkbox in sync if audio was unavailable at startup.
        if getattr(self, "_act_sound", None) is not None:
            self._act_sound.setChecked(self._sound_enabled)

    def _persist_cfg(self):
        if self.config_dir is None:
            return
        import json
        try:
            (self.config_dir / "config.json").write_text(
                json.dumps(self.cfg, indent=2, ensure_ascii=False),
                encoding="utf-8")
        except Exception as e:
            print(f"[warn] could not persist config: {e}")

    def showEvent(self, event):
        super().showEvent(event)
        _disable_win11_frame(int(self.winId()))

    # ------------------------------------------------------------- render
    @staticmethod
    def _alpha_mask(pix: QPixmap, threshold: int = 5) -> QBitmap:
        """Build a widget-shaped mask from the pixmap's alpha channel.

        `QPixmap.mask()` uses a hard threshold of ~128, which eats pixels
        on soft-feathered edges (our bg removal applies a 1-px Gaussian
        blur) and can even hollow out the interior of the sprite. Here we
        drop the threshold to 5 so anything remotely opaque stays in the
        mask — clicks only pass through fully-transparent pixels.
        """
        img = pix.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        w, h = img.width(), img.height()
        ptr = img.constBits()
        ptr.setsize(img.sizeInBytes())
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape(h, w, 4)
        # Qt ARGB32 on little-endian stores bytes as B, G, R, A
        alpha = arr[..., 3]
        mono = np.where(alpha > threshold, 255, 0).astype(np.uint8)
        mono = np.ascontiguousarray(mono)
        # We must keep `mono` alive for the lifetime of the QImage → .copy()
        mono_img = QImage(mono.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
        return QBitmap.fromImage(mono_img)

    def render_frame(self, pix: QPixmap):
        """Called by SpritePlayer for every frame.

        Note: we used to call `self.setMask(...)` here so clicks on
        transparent pixels would pass through to the desktop. Both approaches
        tried (QPixmap.mask() and a numpy-based low-threshold mask) ended up
        clipping parts of the dog on this Windows build, so masking is off
        for now. Trade-off: the widget's bounding rectangle captures clicks,
        but the rectangle is small (just around the dog) so it's not
        practically disruptive. Right-click on the widget opens the menu."""
        if pix.isNull():
            return
        if self._render_mode == "anchor":
            self.resize(pix.size())
            self.label.setPixmap(pix)
            self.label.resize(pix.size())
            self.move(self.anchor_right - pix.width(),
                      self.baseline_y - pix.height())
        else:
            # Fixed mode: window size + position managed externally (run).
            self.label.setPixmap(pix)
        self.clearMask()

    # -------------------------------------------------------------- sleep
    def _start_sleep(self):
        self.state = State.SLEEP
        self._render_mode = "anchor"
        self.player.play(SEQ["breath"], self.assets_dir)
        self._start_snore()

    # ---------------------------------------------------------- reactions
    @pyqtSlot(str)
    def on_new_mail(self, subject: str = ""):
        if self.state != State.SLEEP:
            return  # already mid-sequence; ignore
        print(f"[mail] new -> wake sequence   subject={subject!r}")
        self._stop_snore()
        self.state = State.PLAYBACK
        self._render_mode = "anchor"
        self.player.play(SEQ["wake"], self.assets_dir,
                         on_done=self._play_bark)

    def _play_bark(self):
        """Drive the bark phase with static full-body PNGs rather than the
        head-only Veo clip. Keeps the dog at a consistent size on screen."""
        self.player.stop()
        self.state = State.PLAYBACK
        self._render_mode = "anchor"
        self._pose_queue = list(BARK_POSE_STEPS)
        self._pose_done_cb = self._start_run
        self._pose_tick()

    def _load_static(self, name: str) -> QPixmap:
        pix = self._static_cache.get(name)
        if pix is not None:
            return pix
        path = self.assets_dir / f"{name}.png"
        loaded = QPixmap(str(path))
        if not loaded.isNull() and loaded.height() != STATIC_POSE_H:
            loaded = loaded.scaledToHeight(
                STATIC_POSE_H, Qt.TransformationMode.SmoothTransformation)
        self._static_cache[name] = loaded
        return loaded

    def _pose_tick(self):
        if not self._pose_queue:
            cb, self._pose_done_cb = self._pose_done_cb, None
            if cb:
                cb()
            return
        pose_name, ms, y_off = self._pose_queue.pop(0)
        pix = self._load_static(pose_name)
        if not pix.isNull():
            self.resize(pix.size())
            self.label.setPixmap(pix)
            self.label.resize(pix.size())
            self.move(self.anchor_right - pix.width(),
                      self.baseline_y - pix.height() + y_off)
        # Fire a bark SFX whenever we hit an open-mouth pose.
        if pose_name in ("bark", "bark_wide"):
            self._play_bark_sfx()
        self._pose_timer.start(ms)

    # ---------------------------------------------------------------- run
    def _start_run(self):
        self.state = State.RUN_LEFT
        self._prepare_run_window()

        start_left = self.anchor_right - self.run_w
        end_left = self.screen_rect.left() + self.margin
        y = self.baseline_y - self.run_h
        self.move(start_left, y)

        self.player.play(SEQ["run"], self.assets_dir)   # infinite until we swap
        self.player.loops_remaining = 10**9

        self.run_anim = QPropertyAnimation(self, b"pos")
        self.run_anim.setDuration(self.RUN_LEG_MS)
        self.run_anim.setStartValue(QPoint(start_left, y))
        self.run_anim.setEndValue(QPoint(end_left, y))
        self.run_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.run_anim.finished.connect(self._start_run_back)
        self.run_anim.start()

    def _start_run_back(self):
        self.state = State.RUN_RIGHT
        # Same frames, flipped.
        self.player.play(SEQ["run"], self.assets_dir, flip_h=True)
        self.player.loops_remaining = 10**9

        start_left = self.screen_rect.left() + self.margin
        end_left = self.anchor_right - self.run_w
        y = self.baseline_y - self.run_h

        self.run_anim = QPropertyAnimation(self, b"pos")
        self.run_anim.setDuration(self.RUN_LEG_MS)
        self.run_anim.setStartValue(QPoint(start_left, y))
        self.run_anim.setEndValue(QPoint(end_left, y))
        self.run_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.run_anim.finished.connect(self._play_yawn)
        self.run_anim.start()

    def _prepare_run_window(self):
        """Pre-measure the first run frame to set a fixed window size that all
        frames will be drawn into — so QPropertyAnimation on `pos` doesn't
        fight with per-frame resizes."""
        folder = self.assets_dir / SEQ["run"].folder
        files = sorted(folder.glob("*.png"))
        if not files:
            self.run_w = self.run_h = 200
            return
        pix = QPixmap(str(files[0])).scaledToHeight(
            SEQ["run"].target_h, Qt.TransformationMode.SmoothTransformation)
        self.run_w = pix.width()
        self.run_h = pix.height()
        self.resize(self.run_w, self.run_h)
        self.label.resize(self.run_w, self.run_h)
        self._render_mode = "fixed"

    # ------------------------------------------------------------ returning
    def _play_yawn(self):
        """Called after the second run leg. Instead of the yawn video (which
        was a tight head-and-chest crop that looked oversized), we replay the
        wake sequence IN REVERSE: standing -> sitting -> lying down. It's a
        clean, natural return to sleep using footage we already have."""
        self.player.stop()
        self.state = State.PLAYBACK
        self._render_mode = "anchor"
        self.player.play(SEQ["wake"], self.assets_dir,
                         reverse=True, on_done=self._start_sleep)

    # ------------------------------------------------------ context menu
    def contextMenuEvent(self, event):
        """Right-click ANYWHERE on the dog opens the same menu the tray uses."""
        if getattr(self, "_context_menu", None) is not None:
            self._context_menu.exec(event.globalPos())

    # ---------------------------------------------------------------- tray
    def _build_tray(self):
        self.tray = QSystemTrayIcon(self)
        # Use first breath frame as icon.
        breath = sorted((self.assets_dir / "seq_breath").glob("*.png"))
        if breath:
            icon_pix = QPixmap(str(breath[0])).scaled(
                64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self.tray.setIcon(QIcon(icon_pix))
        self.tray.setToolTip("Toto agent")

        menu = QMenu()
        act_test = QAction("Test: bark + run", self)
        act_test.triggered.connect(lambda: self.on_new_mail("Test"))
        menu.addAction(act_test)

        menu.addSeparator()

        act_sound = QAction("Sonido", self, checkable=True)
        act_sound.setChecked(self._sound_enabled)
        # Disable the toggle if audio backend unavailable.
        act_sound.setEnabled(
            self.snore_player is not None or self.bark_player is not None)
        act_sound.toggled.connect(self._toggle_sound)
        menu.addAction(act_sound)
        self._act_sound = act_sound

        menu.addSeparator()

        act_cfg = QAction("Configurar Gmail...", self)
        act_cfg.triggered.connect(self._open_gmail_dialog)
        menu.addAction(act_cfg)

        if self.config_dir is not None:
            act_folder = QAction("Abrir carpeta de config", self)
            act_folder.triggered.connect(self._open_config_dir)
            menu.addAction(act_folder)

        act_startup = QAction("Start with Windows", self, checkable=True)
        act_startup.setChecked(self._is_startup_enabled())
        act_startup.toggled.connect(self._set_startup)
        menu.addAction(act_startup)

        menu.addSeparator()
        act_quit = QAction("Quit", self)
        act_quit.triggered.connect(QApplication.quit)
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self.tray.show()
        # Save reference so right-click on the pet can reopen the same menu.
        self._context_menu = menu

    def _open_config_dir(self):
        import shutil, subprocess
        if self.config_dir is None:
            return
        cfg = self.config_dir / "config.json"
        if not cfg.exists():
            example = self.config_dir / "config.example.json"
            if example.exists():
                shutil.copy(example, cfg)
        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(self.config_dir)])
        else:
            subprocess.Popen(["xdg-open", str(self.config_dir)])

    def _open_gmail_dialog(self):
        current = self.cfg.get("gmail", {}) if self.cfg else {}
        dlg = GmailConfigDialog(current, parent=None)
        dlg.saved.connect(self._on_gmail_saved)
        dlg.exec()

    def _on_gmail_saved(self, gmail_cfg: dict):
        self.cfg = self.cfg or {}
        self.cfg["gmail"] = gmail_cfg
        if self.config_dir is not None:
            import json
            path = self.config_dir / "config.json"
            try:
                path.write_text(
                    json.dumps(self.cfg, indent=2, ensure_ascii=False),
                    encoding="utf-8")
                print(f"[info] config saved to {path}")
            except Exception as e:
                print(f"[error] could not save config: {e}")
        self.configSaved.emit(self.cfg)

    @staticmethod
    def _startup_shortcut_path() -> Path:
        import os
        appdata = os.environ.get("APPDATA", "")
        return Path(appdata) / "Microsoft/Windows/Start Menu/Programs/Startup/TotoAgent.lnk"

    def _is_startup_enabled(self) -> bool:
        if sys.platform != "win32":
            return False
        return self._startup_shortcut_path().exists()

    def _set_startup(self, enabled: bool):
        if sys.platform != "win32":
            return
        link = self._startup_shortcut_path()
        if enabled:
            target = sys.executable
            args = ""
            if not getattr(sys, "frozen", False):
                pyw = Path(sys.executable).with_name("pythonw.exe")
                if pyw.exists():
                    target = str(pyw)
                args = f'"{Path(__file__).parent / "main.py"}"'
            self._create_shortcut(link, target, args)
        else:
            try:
                link.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _create_shortcut(link: Path, target: str, args: str = ""):
        link.parent.mkdir(parents=True, exist_ok=True)
        import subprocess
        ps = (
            f'$s = (New-Object -ComObject WScript.Shell).CreateShortcut("{link}");'
            f'$s.TargetPath = "{target}";'
            f'$s.Arguments = \'{args}\';'
            f'$s.WorkingDirectory = "{Path(target).parent}";'
            f'$s.Save()'
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       check=False, creationflags=0x08000000)
