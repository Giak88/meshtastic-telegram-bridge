"""Tests of bridge.py: pure functions in-process, then the real program end to end with a fake
node (tests/fakes/meshtastic) and a fake Telegram server.   Run: python -m unittest -v"""

import os
import sys
import json
import time
import signal
import tempfile
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT), str(HERE)]

import bridge                                     # noqa: E402
from fake_telegram import FakeTelegram, GOOD_TOKEN, CHAT_ID   # noqa: E402

CHANNELS = ",Group"                              # 0 = MediumFast (preset), 1 = Group
ALICE, CAROL, ADMIN = 0x22222222, 0x33333333, 0x44444444


def configure(tmp, **over):
    env = {"BRIDGE_LANG": "en", "MESH_CHANNEL": "group", "TG_TOKEN": GOOD_TOKEN, "TG_CHAT_ID": str(CHAT_ID),
           "BRIDGE_STATE": str(Path(tmp) / "state.json"), "BRIDGE_HISTORY_FILE": str(Path(tmp) / "history.json")}
    env.update(over)
    bridge.setup(bridge.Config(env))


class Pure(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        configure(self.tmp)

    def test_paginate_limits(self):
        for text in ["x" * 1000, "parola " * 200, "è" * 500, "🙂 " * 300]:
            pages = bridge.paginate(text, "TG Bob: ")
            self.assertGreater(len(pages), 1)
            for p in pages:
                self.assertLessEqual(len(p), bridge.MAX_CHARS)
                self.assertLessEqual(len(p.encode()), bridge.MAX_BYTES)
            self.assertTrue(pages[-1].endswith(f"[{len(pages)}/{len(pages)}]"))
        self.assertEqual(bridge.paginate("ciao", "TG Bob: "), ["TG Bob: ciao"])

    def test_paginate_limited(self):
        pages, cut = bridge.paginate_limited("parola " * 400, "TG Bob: ", 3)
        self.assertTrue(cut)
        self.assertLessEqual(len(pages), 3)
        self.assertIn("…", pages[-1])
        pages, cut = bridge.paginate_limited("short", "TG: ", 3)
        self.assertEqual((pages, cut), (["TG: short"], False))

    def test_repeat_parse_bang(self):
        p = bridge.parse_repeat
        self.assertEqual(p("!repeat 3"), 3)
        self.assertEqual(p("!ripeti 5"), 5)
        self.assertEqual(p("  !RIPETI 2. "), 2)
        self.assertEqual(p("/ripeti 4"), 4)
        self.assertEqual(p("/repeat@my_bot 4"), 4)
        self.assertEqual(p("!ripeti"), 0)
        self.assertEqual(p("!ripeti tre"), 0)
        self.assertEqual(p("!ripeti 999"), 20)
        self.assertIsNone(p("ripeti 3"))               # without prefix it is normal chat
        self.assertIsNone(p("!ripeti 3 per favore"))

    def test_repeat_parse_word_prefix(self):
        configure(self.tmp, BRIDGE_PREFIX="CLU", BRIDGE_LANG="it")
        p = bridge.parse_repeat
        self.assertEqual(p("CLU ripeti 3"), 3)
        self.assertEqual(p("clu, ripeti 3"), 3)
        self.assertIsNone(p("CLUripeti 3"))
        self.assertEqual(bridge.repeat_cmd(), "CLU ripeti")
        configure(self.tmp, BRIDGE_PREFIX="!", BRIDGE_LANG="en")
        self.assertEqual(bridge.repeat_cmd(), "!repeat")

    def test_history_dedup_and_limit(self):
        configure(self.tmp, BRIDGE_HISTORY="3")
        h = bridge.history
        self.assertTrue(h.add("TG", "Bob", "a", mid="tg1"))
        self.assertFalse(h.add("TG", "Bob", "a", mid="tg1"))
        for i in range(5):
            h.add("M", "Alice", f"m{i}", ts=1000 + i)
        self.assertEqual([m["t"] for m in h.last("M")], ["m2", "m3", "m4"])
        h2 = bridge.History(h.path, 3)                  # reloaded from disk
        self.assertEqual(len(h2.last("M")), 3)

    def test_admin_commands_both_languages(self):
        configure(self.tmp, BRIDGE_ADMINS="!44444444")
        bridge.CHANNELS, bridge.BRIDGE_IDX = {0: "MediumFast", 1: "Group"}, 1
        self.assertIn("Status: bridge on", bridge.handle_admin("!44444444", "status"))
        self.assertIn("off", bridge.handle_admin("!44444444", "bridge off"))
        self.assertFalse(bridge.state.bridge)
        self.assertIn("bannato", Tr_it(lambda: bridge.handle_admin("!44444444", "ban 22222222")))
        self.assertIn("!22222222", bridge.state.ban)
        self.assertIsNone(bridge.handle_admin("!44444444", "come va?"))

    def test_config_ids_normalised(self):
        c = bridge.Config({"BRIDGE_ADMINS": "1A2B3C4D, !aabbccdd"})
        self.assertEqual(c.admins, {"!1a2b3c4d", "!aabbccdd"})
        self.assertEqual(bridge.Config({}).missing(), ["MESH_CHANNEL", "TG_TOKEN", "TG_CHAT_ID"])

    def test_no_missing_translations(self):
        from i18n import STRINGS
        self.assertEqual(set(STRINGS["en"]), set(STRINGS["it"]))
        import setup_wizard
        self.assertEqual(set(setup_wizard.W["en"]) - {"choose_lang"}, set(setup_wizard.W["it"]))


def Tr_it(fn):
    old = bridge.t
    bridge.t = bridge.Tr("it")
    try:
        return fn()
    finally:
        bridge.t = old


class EndToEnd(unittest.TestCase):
    """Runs the real bridge.py as a process."""

    def setUp(self):
        self.tg = FakeTelegram()
        self.tmp = Path(tempfile.mkdtemp())
        self.proc = None
        self.pid = 1

    def tearDown(self):
        self.stop()
        self.tg.stop()

    def start(self, lang="en", channels=CHANNELS, **extra):
        env = dict(os.environ)
        env.update({"PYTHONPATH": str(HERE / "fakes"), "FAKE_MESH_DIR": str(self.tmp),
                    "FAKE_MESH_CHANNELS": channels, "BRIDGE_CONFIG": str(self.tmp / "none.env"),
                    "BRIDGE_LANG": lang, "MESH_PORT": "", "MESH_CHANNEL": "Group",
                    "TG_TOKEN": GOOD_TOKEN, "TG_CHAT_ID": str(CHAT_ID), "TG_API_BASE": self.tg.url,
                    "BRIDGE_ADMINS": "!44444444", "BRIDGE_PREFIX": "!", "MESH_TX_INTERVAL": "0.05",
                    "BRIDGE_REPEAT_PAUSE": "0",
                    "BRIDGE_STATE": str(self.tmp / "state.json"),
                    "BRIDGE_HISTORY_FILE": str(self.tmp / "history.json")})
        env.update(extra)
        self.log = open(self.tmp / "log.txt", "a")
        self.proc = subprocess.Popen([sys.executable, str(ROOT / "bridge.py")], env=env,
                                     stdout=self.log, stderr=subprocess.STDOUT)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            self.proc.wait(5)
        self.proc = None
        if getattr(self, "log", None):
            self.log.close()

    def logtext(self):
        return (self.tmp / "log.txt").read_text()

    def wait(self, cond, timeout=8):
        end = time.time() + timeout
        while time.time() < end:
            if cond():
                return True
            time.sleep(0.05)
        self.fail("timeout; log:\n" + self.logtext())

    def mesh_rx(self, text, frm=ALICE, ch=1, to=0xFFFFFFFF, pki=False):
        self.pid += 1
        pkt = {"id": self.pid, "from": frm, "fromId": f"!{frm:08x}", "to": to,
               "decoded": {"text": text}, "pkiEncrypted": pki}
        if ch:
            pkt["channel"] = ch
        with open(self.tmp / "inbox.jsonl", "a") as f:
            f.write(json.dumps(pkt) + "\n")

    def outbox(self):
        p = self.tmp / "outbox.jsonl"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []

    def ready(self):
        self.wait(lambda: "<-> Telegram chat" in self.logtext() or "<-> chat Telegram" in self.logtext())

    # --------------------------------------------------------------------------------------
    def test_full_flow_english(self):
        self.start()
        self.ready()
        self.assertIn("starting (language: English)", self.logtext())
        self.assertNotIn("privacy mode", self.logtext())            # the bot is admin: no warning
        # mesh -> Telegram
        self.mesh_rx("hello from the mesh")
        self.wait(lambda: "Alice: hello from the mesh" in self.tg.texts())
        # other channels are ignored
        self.mesh_rx("on MediumFast", ch=0)
        # Telegram -> mesh
        self.tg.push("hi from telegram", first_name="Bob")
        self.wait(lambda: any(o["text"] == "TG Bob: hi from telegram" and o["ch"] == 1 and o["dest"] is None
                              for o in self.outbox()))
        # repeat on the mesh: excludes the asker (Alice), includes Bob (TG) and Carol
        self.mesh_rx("carol here", frm=CAROL)
        self.wait(lambda: "Carol: carol here" in self.tg.texts())
        self.mesh_rx("!repeat 5", frm=ALICE)
        self.wait(lambda: any("Last 2 from Telegram and Group" in o["text"] for o in self.outbox()))
        rep = [o["text"] for o in self.outbox() if "Last 2" in o["text"]][0]
        self.assertIn("TG Bob: hi from telegram", rep)
        self.assertIn("Carol: carol here", rep)
        self.assertNotIn("hello from the mesh", rep)
        self.assertTrue(rep.endswith("[1/1]"))
        self.assertNotIn("!repeat 5", " ".join(self.tg.texts()))          # command not forwarded
        # repeat on Telegram
        self.tg.push("/repeat 3", first_name="Bob")
        self.wait(lambda: any(x.startswith("Last 2 from Meshtastic:") for x in self.tg.texts()))
        self.assertNotIn("/repeat 3", " ".join(o["text"] for o in self.outbox()))
        # usage message
        self.mesh_rx("!repeat")
        self.wait(lambda: any(o["text"].startswith("Usage: !repeat <number>") for o in self.outbox()))
        self.assertNotIn("on MediumFast", " ".join(self.tg.texts()))

    def test_admin_channel(self):
        self.start(FAKE_MESH_CHANNELS=",Group,Admin", BRIDGE_ADMIN_CHANNEL="Admin")
        self.ready()
        self.wait(lambda: "Admin channel: 'Admin' (index 2)" in self.logtext())
        self.mesh_rx("status", frm=ADMIN, ch=2)
        self.wait(lambda: any(o["ch"] == 2 and o["dest"] is None and o["text"].startswith("Status: bridge on")
                              for o in self.outbox()))
        self.mesh_rx("status", frm=ALICE, ch=2)                         # not in BRIDGE_ADMINS
        self.wait(lambda: "[ADMIN-CH !22222222] ignored" in self.logtext())
        self.mesh_rx("!bridge off", frm=ADMIN, ch=2)
        self.wait(lambda: any(o["ch"] == 2 and o["text"].startswith("Bridge: off") for o in self.outbox()))
        self.mesh_rx("random chatter", frm=ADMIN, ch=2)                 # unknown: no answer, never forwarded
        time.sleep(0.6)
        self.assertEqual(sum(o["ch"] == 2 for o in self.outbox()), 2)
        self.assertNotIn("random chatter", " ".join(self.tg.texts()))
        self.assertFalse(json.loads((self.tmp / "state.json").read_text())["bridge"])
        self.mesh_rx("hello", ch=1)                                     # bridged channel still handled (bridge off)
        self.wait(lambda: "bridge off, not forwarded" in self.logtext())

    def test_admin_channel_without_admin_ids_is_open_to_its_members(self):
        self.start(lang="it", FAKE_MESH_CHANNELS=",Group,Admin", BRIDGE_ADMIN_CHANNEL="admin", BRIDGE_ADMINS="")
        self.ready()
        self.wait(lambda: "comandi accettati da: qualsiasi nodo sul canale" in self.logtext())
        self.mesh_rx("stato", frm=ALICE, ch=2)
        self.wait(lambda: any(o["ch"] == 2 and o["text"].startswith("Stato: bridge on") for o in self.outbox()))

    def test_admin_channel_same_as_bridged_exits_78(self):
        self.start(BRIDGE_ADMIN_CHANNEL="group")
        self.assertEqual(self.proc.wait(8), bridge.EX_CONFIG)
        self.assertIn("must be different from MESH_CHANNEL", self.logtext())

    def test_admin_channel_missing_is_not_fatal(self):
        self.start(BRIDGE_ADMIN_CHANNEL="Nope")
        self.ready()
        self.wait(lambda: "Admin channel 'Nope' not found" in self.logtext())
        self.mesh_rx("still bridging")
        self.wait(lambda: "Alice: still bridging" in self.tg.texts())

    def test_privacy_warning(self):
        self.tg.bot_status = "member"                       # not admin, privacy on
        self.start()
        self.ready()
        self.wait(lambda: "privacy mode is ON" in self.logtext())
        self.stop()
        self.tg.can_read_all = True                         # privacy disabled: no warning
        open(self.tmp / "log.txt", "w").close()
        self.start()
        self.ready()
        time.sleep(1)
        self.assertNotIn("privacy mode", self.logtext())

    def test_italian_admin_and_bridge_off(self):
        self.start(lang="it")
        self.ready()
        self.assertIn("lingua: italiano", self.logtext())
        # DM not encrypted: ignored
        self.mesh_rx("bridge off", frm=ADMIN, ch=0, to=0x11111111, pki=False)
        self.wait(lambda: "ignorato" in self.logtext())
        # DM from a non-admin: ignored
        self.mesh_rx("bridge off", frm=ALICE, ch=0, to=0x11111111, pki=True)
        # encrypted admin DM
        self.mesh_rx("bridge off", frm=ADMIN, ch=0, to=0x11111111, pki=True)
        self.wait(lambda: any(o["dest"] == "!44444444" and o["text"].startswith("Bridge: off")
                              for o in self.outbox()))
        self.mesh_rx("questo non deve uscire")
        self.tg.push("neanche questo")
        self.wait(lambda: "bridge spento, non inoltrato" in self.logtext()
                  and self.logtext().count("bridge spento") >= 2)
        self.assertNotIn("Alice: questo non deve uscire", self.tg.texts())
        # still kept for repeat
        self.mesh_rx("!ripeti 2", frm=CAROL)
        self.wait(lambda: any("Ultimi 2 da Telegram e Group" in o["text"] for o in self.outbox()))
        self.mesh_rx("stato", frm=ADMIN, ch=0, to=0x11111111, pki=True)
        self.wait(lambda: any(o["text"].startswith("Stato: bridge off") for o in self.outbox()))
        state = json.loads((self.tmp / "state.json").read_text())
        self.assertFalse(state["bridge"])

    def test_restart_no_duplicates_and_offset(self):
        self.start()
        self.ready()
        self.tg.push("only once")
        self.wait(lambda: any(o["text"] == "TG Bob: only once" for o in self.outbox()))
        time.sleep(0.5)
        self.stop()
        off = json.loads((self.tmp / "state.json").read_text())["tg_offset"]
        self.assertEqual(off, self.tg.next_id + 1)
        # simulate Telegram re-delivering the same update after the restart
        with self.tg.lock:
            self.tg.next_id -= 1
        self.tg.push("only once")
        self.start()
        self.ready()
        time.sleep(1.5)
        self.assertEqual(sum(o["text"] == "TG Bob: only once" for o in self.outbox()), 1)

    def test_old_messages_and_other_chats(self):
        self.start()
        self.ready()
        self.tg.push("from yesterday", age=7200)
        self.tg.push("other chat", chat_id=-42, title="Elsewhere")
        self.tg.push("from a bot", is_bot=True)
        self.tg.push("/start")
        self.tg.push("fresh")
        self.wait(lambda: any(o["text"] == "TG Bob: fresh" for o in self.outbox()))
        texts = " ".join(o["text"] for o in self.outbox())
        for bad in ("from yesterday", "other chat", "from a bot", "/start"):
            self.assertNotIn(bad, texts)
        self.assertIn("older than 1 h", self.logtext())
        self.assertIn("'Elsewhere'", self.logtext())
        hist = json.loads((self.tmp / "history.json").read_text())
        self.assertIn("from yesterday", [m["t"] for m in hist["TG"]])      # still repeatable

    def test_rate_limit_retry_and_failure_notice(self):
        self.tg.fail_next_send = [(429, 1)]
        self.start()
        self.ready()
        self.mesh_rx("after a 429")
        self.wait(lambda: "Alice: after a 429" in self.tg.texts())
        self.assertIn("rate limited", self.logtext())
        self.tg.fail_next_send = [(400, None)]
        self.mesh_rx("this one fails")
        self.wait(lambda: any(o["text"].startswith("Telegram: send failed") for o in self.outbox()))

    def test_long_message_truncated(self):
        self.start(BRIDGE_MAX_PARTS="2")
        self.ready()
        self.tg.push("word " * 300)
        self.wait(lambda: any(o["text"].endswith("[2/2]") for o in self.outbox()))
        time.sleep(0.3)
        parts = [o for o in self.outbox() if o["text"].startswith("TG Bob:")]
        self.assertEqual(len(parts), 2)
        self.assertIn("…", parts[-1]["text"])

    def test_missing_channel_exits_78(self):
        self.start(channels=",Other")
        self.assertEqual(self.proc.wait(8), bridge.EX_CONFIG)
        self.assertIn("Mesh channel 'Group' not found", self.logtext())

    def test_missing_config_exits_78(self):
        self.start(lang="it", TG_TOKEN="")
        self.assertEqual(self.proc.wait(8), bridge.EX_CONFIG)
        self.assertIn("Manca l'impostazione TG_TOKEN", self.logtext())

    def test_conflict_409_logged(self):
        self.tg.conflict = True
        self.start()
        self.ready()
        self.wait(lambda: "409 Conflict" in self.logtext())

    def test_token_never_logged(self):
        self.start(TG_CHAT_ID="-999")
        self.ready()
        self.mesh_rx("x")
        time.sleep(0.5)
        self.tg.stop()                                    # network errors include the URL
        self.mesh_rx("y")
        self.wait(lambda: "send failed" in self.logtext(), timeout=25)
        self.assertNotIn(GOOD_TOKEN, self.logtext())
        self.tg = FakeTelegram()


if __name__ == "__main__":
    unittest.main()
