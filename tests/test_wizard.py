"""End-to-end tests of the setup menu: real setup_wizard.py driven through stdin, with a fake
node, a fake Telegram server and fake sudo/systemctl/journalctl (they only log what is asked).
The service file is written to a temporary folder and checked with systemd-analyze."""

import os
import sys
import json
import shutil
import tempfile
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from fake_telegram import FakeTelegram, GOOD_TOKEN, CHAT_ID   # noqa: E402


class Wizard(unittest.TestCase):
    def setUp(self):
        self.tg = FakeTelegram()
        self.tmp = Path(tempfile.mkdtemp())
        self.conf = self.tmp / "config.env"
        self.sysd = self.tmp / "systemd"
        self.sysd.mkdir()
        dev = self.tmp / "dev"
        (dev / "serial" / "by-id").mkdir(parents=True)
        (dev / "ttyACM0").touch()
        (dev / "serial" / "by-id" / "usb-Test_Node_ABC123-if00").symlink_to(dev / "ttyACM0")
        self.port = str(dev / "serial" / "by-id" / "usb-Test_Node_ABC123-if00")
        self.cmdlog = self.tmp / "cmd.log"
        self.env = dict(os.environ)
        self.env.update({"PYTHONPATH": str(HERE / "fakes"), "PATH": f"{HERE / 'fakes' / 'bin'}:{os.environ['PATH']}",
                         "BRIDGE_CONFIG": str(self.conf), "MTB_SYSTEMD_DIR": str(self.sysd),
                         "MTB_DEV_DIR": str(dev), "MTB_STATUS_DELAY": "0", "MTB_CHAT_WAIT": "3",
                         "TG_API_BASE": self.tg.url, "FAKE_CMD_LOG": str(self.cmdlog),
                         "FAKE_MESH_CHANNELS": ",Group,Secret", "LANG": "C"})
        self.env["MTB_SUDO"] = "sudo"                       # exercise the non-root path

    def tearDown(self):
        self.tg.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_wizard(self, inputs, *args):
        r = subprocess.run([sys.executable, str(ROOT / "setup_wizard.py"), *args], env=self.env,
                           input="\n".join(inputs) + "\n", capture_output=True, text=True, timeout=60)
        self.out = r.stdout + r.stderr
        return r.returncode

    def read_conf(self):
        return dict(l.split("=", 1) for l in self.conf.read_text().splitlines() if l and not l.startswith("#"))

    def cmds(self):
        return self.cmdlog.read_text() if self.cmdlog.exists() else ""

    # ------------------------------------------------------------------------------------------
    def test_first_run_italian_full_install(self):
        self.tg.push("ciao bot", chat_id=CHAT_ID, title="Gruppo Mesh")
        rc = self.run_wizard([
            "2",            # Italiano
            "",             # USB
            "1",            # first by-id port
            "",             # read channels: yes
            "1",            # channel 1 = Group
            GOOD_TOKEN,
            "",             # detect the group
            "",             # first chat found
            "44444444",     # admin
            "",             # PKI only: yes
            "CLU",          # prefix
            "",             # default service name
            "",             # install now: yes
            "6",            # show configuration
            "5",            # test message
            "0",            # exit
        ])
        self.assertEqual(rc, 0, self.out)
        for s in ("Passo 1/6", "Canali sul nodo:", "1) Group", "Token valido: bot @test_bridge_bot",
                  "Gruppo Mesh (supergroup) id -1001234567890", "Configurazione salvata",
                  "Servizio mesh-telegram-bridge abilitato e avviato", "Messaggio inviato", "Ciao."):
            self.assertIn(s, self.out)
        c = self.read_conf()
        self.assertEqual(c["BRIDGE_LANG"], "it")
        self.assertEqual(c["MESH_PORT"], self.port)
        self.assertEqual(c["MESH_CHANNEL"], "Group")
        self.assertEqual(c["TG_TOKEN"], GOOD_TOKEN)
        self.assertEqual(c["TG_CHAT_ID"], str(CHAT_ID))
        self.assertEqual(c["BRIDGE_ADMINS"], "!44444444")
        self.assertEqual(c["BRIDGE_ADMIN_PKI_ONLY"], "1")
        self.assertEqual(c["BRIDGE_PREFIX"], "CLU")
        self.assertEqual(c["BRIDGE_HISTORY"], "20")
        self.assertEqual(self.conf.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(GOOD_TOKEN, self.out)                             # token masked on screen
        # the message used to detect the group was confirmed: the bridge will not forward it
        self.assertEqual(self.tg.updates, [])
        self.assertIn("Messaggio di prova", self.tg.texts()[0])
        # service
        unit = self.sysd / "mesh-telegram-bridge.service"
        u = unit.read_text()
        self.assertIn(f"EnvironmentFile={self.conf}", u)
        self.assertIn(f"{ROOT / 'bridge.py'}", u)
        self.assertIn("Restart=always", u)
        self.assertIn("RestartPreventExitStatus=78", u)
        self.assertIn("WantedBy=multi-user.target", u)
        cm = self.cmds()
        for s in ("systemctl daemon-reload", "systemctl enable mesh-telegram-bridge",
                  "systemctl restart mesh-telegram-bridge", "sudo install -m 644"):
            self.assertIn(s, cm)
        # config.env must be loadable by the bridge itself
        sys.path.insert(0, str(ROOT))
        import bridge
        env = {}
        for line in self.conf.read_text().splitlines():
            if line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k] = v
        cfg = bridge.Config(env)
        self.assertEqual(cfg.missing(), [])
        self.assertEqual(cfg.admins, {"!44444444"})

    def test_unit_passes_systemd_analyze(self):
        if not shutil.which("systemd-analyze"):
            self.skipTest("systemd-analyze not available")
        self.conf.write_text(f"BRIDGE_LANG=en\nMESH_PORT={self.port}\nMESH_CHANNEL=Group\n"
                             f"TG_TOKEN={GOOD_TOKEN}\nTG_CHAT_ID=-1\n")
        self.assertEqual(self.run_wizard([], "install"), 0, self.out)
        unit = self.sysd / "mesh-telegram-bridge.service"
        r = subprocess.run(["systemd-analyze", "verify", "--man=no", str(unit)],
                           capture_output=True, text=True)
        relevant = [l for l in (r.stdout + r.stderr).splitlines() if unit.name in l]
        self.assertEqual(relevant, [], r.stdout + r.stderr)

    def test_english_manual_entries_and_validation(self):
        self.env["FAKE_MESH_FAIL"] = "1"                     # node busy: falls back to typing the name
        rc = self.run_wizard([
            "1",                        # English
            "2", "192.168.1.50",        # TCP node
            "",                         # try reading channels -> fails
            "MyGroup",
            "bad:token", "n",           # rejected, do not keep
            GOOD_TOKEN,
            "2", "abc", "-100777",      # manual chat id, first one invalid
            "!12", "!aabbccdd,1a2b3c4d", "n",
            "with space", "!",
            "my-bridge",
            "n",                        # do not install
            "0",
        ])
        self.assertEqual(rc, 0, self.out)
        for s in ("Step 1/6", "Could not read the channels", "Token rejected by Telegram",
                  "Invalid node id: !12", "The prefix cannot contain spaces", "Configuration saved"):
            self.assertIn(s, self.out)
        self.assertNotIn("bad:token", self.out)
        self.assertNotIn("WARNING", self.out)              # the bot is admin: no privacy warning
        c = self.read_conf()
        self.assertEqual((c["MESH_HOST"], c["MESH_PORT"]), ("192.168.1.50", ""))
        self.assertEqual(c["MESH_CHANNEL"], "MyGroup")
        self.assertEqual(c["TG_CHAT_ID"], "-100777")
        self.assertEqual(c["BRIDGE_ADMINS"], "!aabbccdd,!1a2b3c4d")
        self.assertEqual(c["BRIDGE_ADMIN_PKI_ONLY"], "0")
        self.assertEqual(c["BRIDGE_PREFIX"], "!")
        self.assertEqual(c["BRIDGE_SERVICE"], "my-bridge")
        self.assertFalse(any(self.sysd.iterdir()))
        self.assertNotIn("systemctl", self.cmds())

    def test_chat_detection_409(self):
        self.tg.conflict = True
        rc = self.run_wizard(["1", "", "1", "n", "Group", GOOD_TOKEN, "", "-100555", "", "", "", "n", "0"])
        self.assertEqual(rc, 0, self.out)
        self.assertIn("another program is reading this bot (409)", self.out)
        self.assertEqual(self.read_conf()["TG_CHAT_ID"], "-100555")

    def test_privacy_warning_when_bot_is_not_admin(self):
        self.tg.bot_status = "member"
        rc = self.run_wizard(["1", "", "1", "n", "Group", GOOD_TOKEN, "2", "-100555",
                              "",                      # Enter after the warning
                              "", "", "", "n", "0"])
        self.assertEqual(rc, 0, self.out)
        self.assertIn("WARNING: the bot is not an administrator of this group", self.out)
        self.assertIn("REMOVE the bot from the group", self.out)
        self.assertEqual(self.read_conf()["TG_CHAT_ID"], "-100555")      # configuration still saved

    def test_privacy_warning_italian_and_not_shown_when_privacy_off(self):
        self.tg.bot_status = "member"
        rc = self.run_wizard(["2", "", "1", "n", "Group", GOOD_TOKEN, "2", "-100555", "", "", "", "", "n", "0"])
        self.assertEqual(rc, 0, self.out)
        self.assertIn("ATTENZIONE: il bot non è amministratore di questo gruppo", self.out)
        self.tg.can_read_all = True                        # privacy disabled: no warning, no extra Enter
        self.conf.unlink()
        rc = self.run_wizard(["2", "", "1", "n", "Group", GOOD_TOKEN, "2", "-100555", "", "", "", "n", "0"])
        self.assertEqual(rc, 0, self.out)
        self.assertNotIn("ATTENZIONE", self.out)

    def test_install_refuses_incomplete_config(self):
        self.conf.write_text("BRIDGE_LANG=it\nMESH_CHANNEL=Group\n")
        self.assertEqual(self.run_wizard([], "install"), 1)
        self.assertIn("Configurazione incompleta", self.out)
        self.assertIn("TG_TOKEN", self.out)
        self.assertFalse(any(self.sysd.iterdir()))

    def test_service_menu_logs_language_and_uninstall(self):
        self.conf.write_text(f"BRIDGE_LANG=en\nMESH_PORT={self.port}\nMESH_CHANNEL=Group\n"
                             f"TG_TOKEN={GOOD_TOKEN}\nTG_CHAT_ID=-1\nBRIDGE_SERVICE=test-br\n")
        self.assertEqual(self.run_wizard([], "install"), 0, self.out)
        self.assertTrue((self.sysd / "test-br.service").exists())
        rc = self.run_wizard(["3", "1", "3", "4", "0",      # status, stop, restart
                              "4",                          # logs
                              "7", "2", "",                 # Italian, restart: yes
                              "8", "s", "n",                # uninstall, keep files
                              "0"])
        self.assertEqual(rc, 0, self.out)
        cm = self.cmds()
        for s in ("systemctl status test-br", "systemctl stop test-br", "systemctl restart test-br",
                  "journalctl -u test-br -f", "systemctl disable --now test-br"):
            self.assertIn(s, cm)
        self.assertIn("Lingua: Italiano", self.out)
        self.assertIn("Servizio rimosso", self.out)
        self.assertFalse((self.sysd / "test-br.service").exists())
        self.assertEqual(self.read_conf()["BRIDGE_LANG"], "it")
        self.assertEqual(self.read_conf()["BRIDGE_SERVICE"], "test-br")   # other settings kept

    def test_uninstall_with_files(self):
        self.conf.write_text(f"BRIDGE_LANG=en\nMESH_PORT={self.port}\nMESH_CHANNEL=Group\n"
                             f"TG_TOKEN={GOOD_TOKEN}\nTG_CHAT_ID=-1\nBRIDGE_SERVICE=test-br2\n")
        self.run_wizard([], "install")
        self.assertEqual(self.run_wizard(["y", "y"], "uninstall"), 0, self.out)
        self.assertFalse(self.conf.exists())
        self.assertFalse((self.sysd / "test-br2.service").exists())


if __name__ == "__main__":
    unittest.main()
