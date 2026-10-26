"""Local fake of the Telegram Bot API (getMe, getUpdates, sendMessage, deleteWebhook)."""

import json
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GOOD_TOKEN = "123456:TESTTOKEN"
CHAT_ID = -1001234567890


class FakeTelegram:
    def __init__(self):
        self.lock = threading.Lock()
        self.updates = []          # queued updates
        self.next_id = 1000
        self.sent = []             # sendMessage payloads
        self.fail_next_send = []   # list of (code, retry_after) to return on next sends
        self.conflict = False
        self.bot_status = "administrator"   # what getChatMember says about the bot
        self.can_read_all = False          # getMe: privacy mode disabled?
        srv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                _, bot, method = self.path.split("/", 2)
                code, out = srv.handle(bot[3:], method, body)
                data = json.dumps(out).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):   # client gone (process stopped)
                    pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def push(self, text, first_name="Bob", chat_id=CHAT_ID, age=0, is_bot=False, title="Test group"):
        with self.lock:
            self.next_id += 1
            self.updates.append({"update_id": self.next_id, "message": {
                "message_id": self.next_id, "date": int(time.time() - age), "text": text,
                "from": {"id": 7, "is_bot": is_bot, "first_name": first_name},
                "chat": {"id": chat_id, "type": "supergroup", "title": title}}})

    def texts(self):
        with self.lock:
            return [s["text"] for s in self.sent]

    def handle(self, token, method, body):
        if token != GOOD_TOKEN:
            return 401, {"ok": False, "error_code": 401, "description": "Unauthorized"}
        if method == "getMe":
            return 200, {"ok": True, "result": {"id": 123456, "is_bot": True, "username": "test_bridge_bot",
                                                "can_read_all_group_messages": self.can_read_all}}
        if method == "getChatMember":
            return 200, {"ok": True, "result": {"status": self.bot_status, "user": {"id": body.get("user_id")}}}
        if method == "deleteWebhook":
            return 200, {"ok": True, "result": True}
        if method == "getUpdates":
            if self.conflict:
                return 409, {"ok": False, "error_code": 409, "description": "Conflict: terminated by other getUpdates request"}
            off = body.get("offset")
            end = time.time() + min(float(body.get("timeout", 0)), 1.0)
            while True:
                with self.lock:
                    if off is not None:
                        self.updates = [u for u in self.updates if u["update_id"] >= off]
                    ready = list(self.updates)
                if ready or time.time() >= end:
                    return 200, {"ok": True, "result": ready}
                time.sleep(0.05)
        if method == "sendMessage":
            with self.lock:
                if self.fail_next_send:
                    code, ra = self.fail_next_send.pop(0)
                    out = {"ok": False, "error_code": code, "description": "Too Many Requests"}
                    if ra:
                        out["parameters"] = {"retry_after": ra}
                    return code, out
                self.sent.append(body)
            return 200, {"ok": True, "result": {"message_id": 1}}
        return 404, {"ok": False, "error_code": 404, "description": "Not Found"}
