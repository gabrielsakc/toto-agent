"""
Gmail IMAP monitor — emits `new_mail(subject)` whenever a new message arrives
in INBOX. Uses IDLE when available, falls back to periodic polling.

Runs in a background thread; the Qt signal is delivered to the main thread
via Qt's queued connection machinery.
"""
import threading
from PyQt6.QtCore import QObject, pyqtSignal
from imapclient import IMAPClient


class MailMonitor(QObject):
    new_mail = pyqtSignal(str)

    def __init__(self, cfg: dict):
        super().__init__()
        self.host = cfg.get("imap_host", "imap.gmail.com")
        self.port = int(cfg.get("imap_port", 993))
        self.user = cfg["username"]
        self.app_password = cfg["app_password"].replace(" ", "")
        self.poll_seconds = int(cfg.get("poll_seconds", 30))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_uid: int | None = None

    def start(self):
        self._thread = threading.Thread(target=self._run, name="MailMonitor", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                with IMAPClient(self.host, port=self.port, ssl=True) as c:
                    c.login(self.user, self.app_password)
                    c.select_folder("INBOX", readonly=True)

                    if self._last_uid is None:
                        uids = c.search(["ALL"])
                        self._last_uid = max(uids) if uids else 0
                        print(f"[mail] connected, baseline UID={self._last_uid}")

                    # Inner loop: IDLE (or poll) repeatedly on this connection
                    while not self._stop.is_set():
                        try:
                            c.idle()
                            # Wake every poll_seconds to refresh idle (Gmail
                            # drops IDLE after ~29 min; we refresh much sooner)
                            c.idle_check(timeout=self.poll_seconds)
                            c.idle_done()
                        except Exception:
                            # IDLE unsupported or failed — fall through to search
                            self._stop.wait(self.poll_seconds)

                        uids = c.search(["UID", f"{self._last_uid + 1}:*"])
                        new = sorted(u for u in uids if u > self._last_uid)
                        if new:
                            self._emit_new(c, new)
            except Exception as e:
                if not self._stop.is_set():
                    print(f"[mail] error: {e}; reconnect in {self.poll_seconds}s")
                    self._stop.wait(self.poll_seconds)

    def _emit_new(self, client, uids):
        try:
            data = client.fetch(uids, ["ENVELOPE"])
        except Exception:
            data = {}
        for uid in uids:
            subj = "(new mail)"
            env = data.get(uid, {}).get(b"ENVELOPE") if data else None
            if env is not None and env.subject:
                try:
                    subj = env.subject.decode("utf-8", errors="replace")
                except Exception:
                    subj = str(env.subject)
            print(f"[mail] new UID={uid}  subject={subj!r}")
            self.new_mail.emit(subj)
            self._last_uid = uid
