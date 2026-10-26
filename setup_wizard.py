#!/usr/bin/env python3
"""Interactive setup for the Meshtastic <-> Telegram bridge. Start it with ./setup.sh

    ./setup.sh             menu
    ./setup.sh config      guided configuration
    ./setup.sh install     install / update the systemd service (starts at boot)
    ./setup.sh uninstall   remove the service
    ./setup.sh status      service status
    ./setup.sh logs        live log
    ./setup.sh test        send a test message to Telegram
"""

import os
import re
import sys
import time
import getpass
import shutil
import tempfile
import subprocess
from datetime import date
from pathlib import Path

import requests

import bridge
from i18n import Tr, LANGS

ROOT = Path(__file__).resolve().parent
CONF = Path(os.environ.get("BRIDGE_CONFIG", ROOT / "config.env"))
SYSTEMD_DIR = Path(os.environ.get("MTB_SYSTEMD_DIR", "/etc/systemd/system"))
DEV_DIR = Path(os.environ.get("MTB_DEV_DIR", "/dev"))
# command used for root actions: "sudo" for normal users, nothing for root; MTB_SUDO overrides (e.g. "doas")
SUDO = (os.environ["MTB_SUDO"].split() if "MTB_SUDO" in os.environ
        else [] if os.geteuid() == 0 else ["sudo"])
DEFAULT_SERVICE = "mesh-telegram-bridge"

MAIN_KEYS = ["BRIDGE_LANG", "MESH_PORT", "MESH_HOST", "MESH_CHANNEL", "TG_TOKEN", "TG_CHAT_ID",
             "BRIDGE_PREFIX", "BRIDGE_ADMINS", "BRIDGE_ADMIN_PKI_ONLY", "BRIDGE_SERVICE"]
ADVANCED = {"BRIDGE_HISTORY": "20", "BRIDGE_REPEAT_PAUSE": "30", "BRIDGE_MAX_PARTS": "4",
            "MESH_TX_INTERVAL": "1.5", "TG_MAX_AGE": "3600"}

W = {
    "en": {
        "title": "Meshtastic <-> Telegram bridge - setup",
        "choose_lang": "Language / Lingua:\n  1) English\n  2) Italiano\nChoice [1]: ",
        "menu": ("\n  1) Guided configuration\n  2) Install / update the service (starts at boot)\n"
                 "  3) Service: status, start, stop, restart\n  4) Live log\n"
                 "  5) Test: send a message to Telegram\n  6) Show configuration\n"
                 "  7) Language / Lingua\n  8) Uninstall the service\n  0) Exit\n"),
        "choice": "Choice: ",
        "invalid": "Invalid choice.",
        "bye": "Bye.",
        "yes": ("y", "yes"),
        "yn": "[Y/n]",
        "ny": "[y/N]",
        "press_enter": "Press Enter to continue...",
        "step": "\n--- Step {n}/6: {what} ---",
        "s_conn": "connection to the node",
        "s_chan": "mesh channel",
        "s_token": "Telegram bot",
        "s_chat": "Telegram group",
        "s_admin": "administrators",
        "s_prefix": "command prefix",
        "conn_how": "How is the node connected?\n  1) USB cable (recommended)\n  2) Network (Wi-Fi/Ethernet, TCP 4403)\nChoice [1]: ",
        "ports_found": "Serial devices found (stable names, they do not change on reconnect):",
        "ports_fallback": ("No /dev/serial/by-id entries. Devices found (these names can change "
                           "when replugged):"),
        "ports_none": "No serial device found. Is the node plugged in?",
        "port_pick": "Number, or full path [{d}]: ",
        "host_ask": "Node IP address or hostname [{d}]: ",
        "chan_read": ("Read the channel list from the node now? The node must not be in use by another "
                      "program (stop it first, e.g. sudo systemctl stop <service>)."),
        "chan_reading": "Connecting to the node...",
        "chan_err": "Could not read the channels: {err}",
        "chan_list": "Channels on the node:",
        "chan_pick": "Number of the channel to bridge with Telegram, or its name [{d}]: ",
        "chan_name": "Exact name of the mesh channel to bridge (e.g. MyGroup) [{d}]: ",
        "chan_note": ("Tip: use a private channel (own PSK) shared only with the people of the group: "
                      "everything written there goes to Telegram."),
        "token_help": ("Create a bot with @BotFather (/newbot) and paste its token. Then add the bot to "
                       "your group and make it an administrator (or, in BotFather, /setprivacy -> "
                       "Disable), otherwise it cannot read the group messages."),
        "token_ask": "Bot token [{d}]: ",
        "token_ok": "Token valid: bot @{u}",
        "token_bad": "Token rejected by Telegram: {err}",
        "token_keep": "Keep it anyway?",
        "chat_how": ("How do you want to set the group?\n  1) Detect it: I wait for a message in the "
                     "group\n  2) Type the chat id\nChoice [1]: "),
        "chat_wait": "Write any message in the Telegram group now (waiting up to {s} s, Ctrl+C to stop)...",
        "chat_found": "Chats seen by the bot:",
        "chat_pick": "Number of the group [1]: ",
        "chat_none": "No message received.",
        "chat_409": ("Telegram says another program is reading this bot (409). Stop the bridge "
                     "service first (menu 3), then retry."),
        "chat_ask": "Chat id (groups are negative, e.g. -1001234567890) [{d}]: ",
        "admin_help": ("Administrators can switch the bridge on/off and ban nodes with a direct message "
                       "to the bridge node (commands: status, bridge on|off, ban <id>, unban <id>)."),
        "admin_ask": "Node IDs of the administrators, comma-separated (e.g. !1a2b3c4d), empty = none [{d}]: ",
        "admin_bad": "Invalid node id: {x} (expected ! followed by 8 hex digits)",
        "admin_pki": "Accept admin commands only in PKI-encrypted direct messages (recommended)?",
        "prefix_help": ("Anyone on the channel or in the group can ask for missed messages with "
                        "<prefix>repeat <n> (in Italian <prefix>ripeti <n>); on Telegram /repeat <n> "
                        "also works. Examples: prefix ! -> !repeat 3; prefix BOT -> BOT repeat 3."),
        "prefix_ask": "Prefix [{d}]: ",
        "prefix_bad": "The prefix cannot contain spaces.",
        "service_ask": "Name of the systemd service [{d}]: ",
        "saved": "Configuration saved in {f} (readable only by you).",
        "install_now": "Install / update the service now, so the bridge starts at boot?",
        "incomplete": "Configuration incomplete ({k}): run the guided configuration first.",
        "port_busy": "Warning: the serial port is in use by another process:\n{who}\nOnly one program at a time can use the node.",
        "installing": "Installing {f} (sudo may ask your password)...",
        "installed": "Service {s} enabled and started: it will start automatically at every boot.",
        "cmd_failed": "Command failed: {c}",
        "svc_menu": "  1) Status\n  2) Start\n  3) Stop\n  4) Restart\n  0) Back\nChoice: ",
        "logs_hint": "Live log, Ctrl+C to go back.",
        "test_text": "Test message from the Meshtastic bridge setup.",
        "test_ok": "Message sent: check the Telegram group.",
        "test_bad": "Send failed: {err}",
        "no_conf": "No configuration yet.",
        "uninstall_ask": "Stop and remove the service {s}?",
        "uninstall_files": "Also delete config.env, state.json and history.json?",
        "uninstalled": "Service removed. To remove everything, delete the folder {d}.",
        "not_installed": "The service {s} is not installed.",
        "restart_ask": "Restart the service to apply the change?",
        "lang_set": "Language: {l}.",
    },
    "it": {
        "title": "Bridge Meshtastic <-> Telegram - configurazione",
        "menu": ("\n  1) Configurazione guidata\n  2) Installa / aggiorna il servizio (avvio automatico)\n"
                 "  3) Servizio: stato, avvia, ferma, riavvia\n  4) Log in tempo reale\n"
                 "  5) Prova: invia un messaggio a Telegram\n  6) Mostra la configurazione\n"
                 "  7) Lingua / Language\n  8) Disinstalla il servizio\n  0) Esci\n"),
        "choice": "Scelta: ",
        "invalid": "Scelta non valida.",
        "bye": "Ciao.",
        "yes": ("s", "si", "sì", "y", "yes"),
        "yn": "[S/n]",
        "ny": "[s/N]",
        "press_enter": "Premi Invio per continuare...",
        "step": "\n--- Passo {n}/6: {what} ---",
        "s_conn": "collegamento al nodo",
        "s_chan": "canale mesh",
        "s_token": "bot Telegram",
        "s_chat": "gruppo Telegram",
        "s_admin": "amministratori",
        "s_prefix": "prefisso dei comandi",
        "conn_how": "Come è collegato il nodo?\n  1) Cavo USB (consigliato)\n  2) Rete (Wi-Fi/Ethernet, TCP 4403)\nScelta [1]: ",
        "ports_found": "Dispositivi seriali trovati (nomi stabili, non cambiano se ricolleghi):",
        "ports_fallback": ("Nessuna voce in /dev/serial/by-id. Dispositivi trovati (questi nomi possono "
                           "cambiare quando li ricolleghi):"),
        "ports_none": "Nessun dispositivo seriale trovato. Il nodo è collegato?",
        "port_pick": "Numero, o percorso completo [{d}]: ",
        "host_ask": "Indirizzo IP o nome del nodo [{d}]: ",
        "chan_read": ("Leggo adesso l'elenco dei canali dal nodo? Il nodo non deve essere usato da un altro "
                      "programma (fermalo prima, es. sudo systemctl stop <servizio>)."),
        "chan_reading": "Collegamento al nodo...",
        "chan_err": "Impossibile leggere i canali: {err}",
        "chan_list": "Canali sul nodo:",
        "chan_pick": "Numero del canale da collegare a Telegram, o il suo nome [{d}]: ",
        "chan_name": "Nome esatto del canale mesh da collegare (es. MioGruppo) [{d}]: ",
        "chan_note": ("Consiglio: usa un canale privato (PSK propria) condiviso solo con le persone del "
                      "gruppo: tutto ciò che vi si scrive va su Telegram."),
        "token_help": ("Crea un bot con @BotFather (/newbot) e incolla il token. Poi aggiungi il bot al "
                       "gruppo e rendilo amministratore (oppure, in BotFather, /setprivacy -> Disable), "
                       "altrimenti non può leggere i messaggi del gruppo."),
        "token_ask": "Token del bot [{d}]: ",
        "token_ok": "Token valido: bot @{u}",
        "token_bad": "Token rifiutato da Telegram: {err}",
        "token_keep": "Lo tengo comunque?",
        "chat_how": ("Come vuoi impostare il gruppo?\n  1) Rilevalo: aspetto un messaggio nel gruppo\n"
                     "  2) Scrivo l'id della chat\nScelta [1]: "),
        "chat_wait": "Scrivi un messaggio qualsiasi nel gruppo Telegram adesso (attendo fino a {s} s, Ctrl+C per smettere)...",
        "chat_found": "Chat viste dal bot:",
        "chat_pick": "Numero del gruppo [1]: ",
        "chat_none": "Nessun messaggio ricevuto.",
        "chat_409": ("Telegram dice che un altro programma sta leggendo questo bot (409). Ferma prima il "
                     "servizio del bridge (menu 3), poi riprova."),
        "chat_ask": "Id della chat (i gruppi sono negativi, es. -1001234567890) [{d}]: ",
        "admin_help": ("Gli amministratori accendono/spengono il bridge e bannano nodi con un messaggio "
                       "diretto al nodo del bridge (comandi: stato, bridge on|off, ban <id>, unban <id>)."),
        "admin_ask": "ID dei nodi amministratori, separati da virgola (es. !1a2b3c4d), vuoto = nessuno [{d}]: ",
        "admin_bad": "ID nodo non valido: {x} (serve ! seguito da 8 cifre esadecimali)",
        "admin_pki": "Accetto i comandi admin solo nei messaggi diretti cifrati PKI (consigliato)?",
        "prefix_help": ("Chiunque sul canale o nel gruppo può chiedere i messaggi persi con "
                        "<prefisso>ripeti <n> (in inglese <prefisso>repeat <n>); su Telegram funziona "
                        "anche /ripeti <n>. Esempi: prefisso ! -> !ripeti 3; prefisso BOT -> BOT ripeti 3."),
        "prefix_ask": "Prefisso [{d}]: ",
        "prefix_bad": "Il prefisso non può contenere spazi.",
        "service_ask": "Nome del servizio systemd [{d}]: ",
        "saved": "Configurazione salvata in {f} (leggibile solo da te).",
        "install_now": "Installo / aggiorno adesso il servizio, così il bridge parte all'avvio?",
        "incomplete": "Configurazione incompleta ({k}): esegui prima la configurazione guidata.",
        "port_busy": "Attenzione: la porta seriale è usata da un altro processo:\n{who}\nIl nodo può essere usato da un solo programma alla volta.",
        "installing": "Installo {f} (sudo può chiedere la password)...",
        "installed": "Servizio {s} abilitato e avviato: partirà da solo a ogni avvio.",
        "cmd_failed": "Comando fallito: {c}",
        "svc_menu": "  1) Stato\n  2) Avvia\n  3) Ferma\n  4) Riavvia\n  0) Indietro\nScelta: ",
        "logs_hint": "Log in tempo reale, Ctrl+C per tornare indietro.",
        "test_text": "Messaggio di prova dalla configurazione del bridge Meshtastic.",
        "test_ok": "Messaggio inviato: controlla il gruppo Telegram.",
        "test_bad": "Invio fallito: {err}",
        "no_conf": "Nessuna configurazione ancora.",
        "uninstall_ask": "Fermo e rimuovo il servizio {s}?",
        "uninstall_files": "Cancello anche config.env, state.json e history.json?",
        "uninstalled": "Servizio rimosso. Per togliere tutto, cancella la cartella {d}.",
        "not_installed": "Il servizio {s} non è installato.",
        "restart_ask": "Riavvio il servizio per applicare la modifica?",
        "lang_set": "Lingua: {l}.",
    },
}

w = Tr("en", table=W)


# ================================================================== input helpers
def ask(prompt):
    try:
        return input(prompt).strip()
    except EOFError:
        print()
        print(w("bye"))
        sys.exit(0)


def ask_default(key, default="", **kw):
    v = ask(w(key, d=default, **kw))
    return v if v else default


def yes(question, default=True):
    v = ask(f"{question} {w('yn') if default else w('ny')} ").lower()
    return default if not v else v in w("yes")


def pause():
    ask(w("press_enter"))


# ================================================================== config file
def read_conf():
    d = {}
    if CONF.exists():
        for line in CONF.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    return d


def write_conf(d):
    service = d.get("BRIDGE_SERVICE") or DEFAULT_SERVICE
    lines = [f"# Meshtastic <-> Telegram bridge - written by setup.sh on {date.today()}",
             f"# Change it with ./setup.sh or by hand, then: sudo systemctl restart {service}",
             "# Every setting is described in config.env.example.", ""]
    lines += [f"{k}={d.get(k, '')}" for k in MAIN_KEYS]
    lines += ["", "# Advanced"]
    lines += [f"{k}={d.get(k, v)}" for k, v in ADVANCED.items()]
    extra = [k for k in d if k not in MAIN_KEYS and k not in ADVANCED]
    if extra:
        lines += [""] + [f"{k}={d[k]}" for k in extra]
    old = os.umask(0o077)
    try:
        tmp = CONF.with_suffix(".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(CONF)
    finally:
        os.umask(old)


def set_lang(lang):
    global w
    w = Tr(lang, table=W)


def service_name(d=None):
    return (d or read_conf()).get("BRIDGE_SERVICE") or DEFAULT_SERVICE


def missing(d):
    m = [k for k in ("MESH_CHANNEL", "TG_TOKEN", "TG_CHAT_ID") if not d.get(k)]
    if not d.get("MESH_PORT") and not d.get("MESH_HOST"):
        m.insert(0, "MESH_PORT/MESH_HOST")
    return m


# ================================================================== commands
def run(cmd, check=True, **kw):
    r = subprocess.run(cmd, **kw)
    if check and r.returncode != 0:
        print(w("cmd_failed", c=" ".join(map(str, cmd))))
    return r.returncode == 0


def tg(token, method, params=None, timeout=15):
    base = os.environ.get("TG_API_BASE", "https://api.telegram.org").rstrip("/")
    r = requests.post(f"{base}/bot{token}/{method}", json=params or {}, timeout=timeout)
    try:
        d = r.json()
    except ValueError:
        d = {}
    if not d.get("ok"):
        raise bridge.TgError(r.status_code, d.get("description", ""))
    return d["result"]


# ================================================================== guided configuration
def choose_language(d=None):
    v = ask(W["en"]["choose_lang"])
    lang = "it" if v == "2" else "en"
    set_lang(lang)
    if d is not None:
        d["BRIDGE_LANG"] = lang
    return lang


def serial_ports():
    """[(path, description)] - by-id names first; ttyACM/ttyUSB only if there are none."""
    byid = DEV_DIR / "serial" / "by-id"
    if byid.is_dir():
        out = [(str(p), os.path.realpath(p)) for p in sorted(byid.iterdir())]
        if out:
            return out, True
    out = [(str(p), "") for pat in ("ttyACM*", "ttyUSB*", "ttyCH343USB*") for p in sorted(DEV_DIR.glob(pat))]
    return out, False


def step_connection(d):
    if ask(w("conn_how")) == "2":
        d["MESH_HOST"] = ask_default("host_ask", d.get("MESH_HOST", ""))
        d["MESH_PORT"] = ""
        return
    d["MESH_HOST"] = ""
    ports, stable = serial_ports()
    if not ports:
        print(w("ports_none"))
    else:
        print(w("ports_found") if stable else w("ports_fallback"))
        for i, (p, real) in enumerate(ports, 1):
            print(f"  {i}) {p}" + (f"  -> {real}" if real else ""))
    default = d.get("MESH_PORT") or (ports[0][0] if ports else "")
    v = ask_default("port_pick", default)
    d["MESH_PORT"] = ports[int(v) - 1][0] if v.isdigit() and 1 <= int(v) <= len(ports) else v


def read_node_channels(d):
    print(w("chan_reading"))
    try:
        if d.get("MESH_HOST"):
            import meshtastic.tcp_interface
            node = meshtastic.tcp_interface.TCPInterface(hostname=d["MESH_HOST"])
        else:
            import meshtastic.serial_interface
            node = meshtastic.serial_interface.SerialInterface(devPath=d.get("MESH_PORT") or None)
        try:
            return bridge.read_channels(node)
        finally:
            node.close()
    except Exception as ex:
        print(w("chan_err", err=f"{type(ex).__name__}: {ex}"))
        return None


def step_channel(d):
    print(w("chan_note"))
    chans = read_node_channels(d) if yes(w("chan_read")) else None
    if chans:
        print(w("chan_list"))
        for i, n in sorted(chans.items()):
            print(f"  {i}) {n}")
        v = ask_default("chan_pick", d.get("MESH_CHANNEL", ""))
        d["MESH_CHANNEL"] = chans[int(v)] if v.isdigit() and int(v) in chans else v
    else:
        d["MESH_CHANNEL"] = ask_default("chan_name", d.get("MESH_CHANNEL", ""))


def mask(tok):
    return tok[:6] + "…" + tok[-4:] if len(tok) > 12 else tok


def step_token(d):
    print(w("token_help"))
    while True:
        old = d.get("TG_TOKEN", "")
        v = ask(w("token_ask", d=mask(old) if old else ""))
        tok = v or old
        if not tok:
            continue
        try:
            me = tg(tok, "getMe")
            print(w("token_ok", u=me.get("username", "?")))
            d["TG_TOKEN"] = tok
            return
        except Exception as ex:
            print(w("token_bad", err=bridge.tg_clean(ex).replace(tok, "***")))
            if yes(w("token_keep"), default=False):
                d["TG_TOKEN"] = tok
                return


def detect_chat(token, wait=120):
    """Wait for a message to the bot; returns [(id, title, type)]. Confirms the updates read,
    so the bridge will not forward this test message when it starts."""
    print(w("chat_wait", s=wait))
    chats, last, end = {}, None, time.time() + wait
    try:
        while time.time() < end and not chats:
            par = {"timeout": min(20, max(1, int(end - time.time())))}
            if last is not None:
                par["offset"] = last + 1
            try:
                ups = tg(token, "getUpdates", par, timeout=30)
            except bridge.TgError as ex:
                if ex.code == 409:
                    print(w("chat_409"))
                    return []
                raise
            for u in ups:
                last = u["update_id"]
                for k in ("message", "channel_post", "my_chat_member", "edited_message"):
                    c = (u.get(k) or {}).get("chat")
                    if c and c.get("type") != "private":
                        chats[str(c["id"])] = (str(c["id"]), c.get("title") or "?", c.get("type", "?"))
    except KeyboardInterrupt:
        print()
    if last is not None:
        try:
            tg(token, "getUpdates", {"offset": last + 1, "timeout": 0})
        except Exception:
            pass
    return list(chats.values())


def step_chat(d):
    if ask(w("chat_how")) != "2":
        try:
            chats = detect_chat(d["TG_TOKEN"], int(os.environ.get("MTB_CHAT_WAIT", "120")))
        except Exception as ex:
            print(w("test_bad", err=bridge.tg_clean(ex).replace(d["TG_TOKEN"], "***")))
            chats = []
        if chats:
            print(w("chat_found"))
            for i, (cid, title, typ) in enumerate(chats, 1):
                print(f"  {i}) {title} ({typ}) id {cid}")
            v = ask(w("chat_pick")) or "1"
            if v.isdigit() and 1 <= int(v) <= len(chats):
                d["TG_CHAT_ID"] = chats[int(v) - 1][0]
                return
        else:
            print(w("chat_none"))
    while True:
        v = ask_default("chat_ask", d.get("TG_CHAT_ID", ""))
        if re.fullmatch(r"-?\d+", v):
            d["TG_CHAT_ID"] = v
            return


def step_admin(d):
    print(w("admin_help"))
    while True:
        v = ask_default("admin_ask", d.get("BRIDGE_ADMINS", ""))
        ids = [x.strip().lower() for x in v.split(",") if x.strip()]
        ids = [x if x.startswith("!") else "!" + x for x in ids]
        bad = [x for x in ids if not re.fullmatch(r"![0-9a-f]{8}", x)]
        if bad:
            print(w("admin_bad", x=bad[0]))
            continue
        d["BRIDGE_ADMINS"] = ",".join(ids)
        break
    if ids:
        d["BRIDGE_ADMIN_PKI_ONLY"] = "1" if yes(w("admin_pki"), d.get("BRIDGE_ADMIN_PKI_ONLY", "1") == "1") else "0"
    else:
        d.setdefault("BRIDGE_ADMIN_PKI_ONLY", "1")


def step_prefix(d):
    print(w("prefix_help"))
    while True:
        v = ask_default("prefix_ask", d.get("BRIDGE_PREFIX") or "!")
        if " " not in v:
            d["BRIDGE_PREFIX"] = v
            break
        print(w("prefix_bad"))
    d["BRIDGE_SERVICE"] = ask_default("service_ask", service_name(d))


def guided():
    d = read_conf()
    d.setdefault("BRIDGE_LANG", w.lang)
    steps = [("s_conn", step_connection), ("s_chan", step_channel), ("s_token", step_token),
             ("s_chat", step_chat), ("s_admin", step_admin), ("s_prefix", step_prefix)]
    for n, (what, fn) in enumerate(steps, 1):
        print(w("step", n=n, what=w(what)))
        fn(d)
    write_conf(d)
    print("\n" + w("saved", f=CONF))
    show_conf()
    if yes(w("install_now")):
        install_service()


# ================================================================== service
def unit_text(d):
    user = getpass.getuser()
    py = ROOT / "venv" / "bin" / "python"
    if not py.exists():
        py = Path(sys.executable)
    groups = "SupplementaryGroups=dialout\n" if run(["getent", "group", "dialout"], check=False,
                                                    stdout=subprocess.DEVNULL) else ""
    return (f"[Unit]\nDescription=Meshtastic <-> Telegram bridge\n"
            f"After=network-online.target\nWants=network-online.target\n\n"
            f"[Service]\nType=simple\nUser={user}\n{groups}WorkingDirectory={ROOT}\n"
            f"EnvironmentFile={CONF}\nEnvironment=PYTHONUNBUFFERED=1\n"
            f"ExecStart={py} {ROOT / 'bridge.py'}\n"
            f"Restart=always\nRestartSec=10\nRestartPreventExitStatus={bridge.EX_CONFIG}\n\n"
            f"[Install]\nWantedBy=multi-user.target\n")


def port_users(port):
    if not port or not shutil.which("fuser") or not os.path.exists(port):
        return ""
    r = subprocess.run(["fuser", "-v", port], capture_output=True, text=True)
    return (r.stdout + r.stderr).strip() if r.returncode == 0 else ""


def install_service():
    d = read_conf()
    m = missing(d)
    if m:
        print(w("incomplete", k=", ".join(m)))
        return False
    s = service_name(d)
    unit = SYSTEMD_DIR / f"{s}.service"
    who = port_users(d.get("MESH_PORT"))
    if who and s not in who:
        print(w("port_busy", who=who))
    print(w("installing", f=unit))
    with tempfile.NamedTemporaryFile("w", suffix=".service", delete=False) as f:
        f.write(unit_text(d))
    try:
        ok = (run(SUDO + ["install", "-m", "644", f.name, str(unit)])
              and run(SUDO + ["systemctl", "daemon-reload"])
              and run(SUDO + ["systemctl", "enable", s])
              and run(SUDO + ["systemctl", "restart", s]))
    finally:
        os.unlink(f.name)
    if ok:
        print(w("installed", s=s))
        time.sleep(float(os.environ.get("MTB_STATUS_DELAY", "3")))
        run(["systemctl", "status", s, "--no-pager", "-n", "15"], check=False)
    return ok


def service_menu():
    s = service_name()
    while True:
        v = ask(w("svc_menu"))
        if v == "1":
            run(["systemctl", "status", s, "--no-pager", "-n", "20"], check=False)
        elif v in ("2", "3", "4"):
            run(SUDO + ["systemctl", {"2": "start", "3": "stop", "4": "restart"}[v], s])
        elif v == "0" or v == "":
            return
        else:
            print(w("invalid"))


def logs():
    print(w("logs_hint"))
    try:
        run(SUDO + ["journalctl", "-u", service_name(), "-f", "-n", "50"], check=False)
    except KeyboardInterrupt:
        print()


def test_telegram():
    d = read_conf()
    if not (d.get("TG_TOKEN") and d.get("TG_CHAT_ID")):
        print(w("incomplete", k="TG_TOKEN, TG_CHAT_ID"))
        return False
    try:
        tg(d["TG_TOKEN"], "sendMessage", {"chat_id": d["TG_CHAT_ID"], "text": w("test_text")})
        print(w("test_ok"))
        return True
    except Exception as ex:
        print(w("test_bad", err=bridge.tg_clean(ex).replace(d["TG_TOKEN"], "***")))
        return False


def show_conf():
    d = read_conf()
    if not d:
        print(w("no_conf"))
        return
    print()
    for k in MAIN_KEYS + list(ADVANCED):
        v = d.get(k, "")
        print(f"  {k}={mask(v) if k == 'TG_TOKEN' and v else v}")


def installed(s):
    return (SYSTEMD_DIR / f"{s}.service").exists()


def uninstall():
    s = service_name()
    if not installed(s):
        print(w("not_installed", s=s))
    elif yes(w("uninstall_ask", s=s), default=False):
        run(SUDO + ["systemctl", "disable", "--now", s], check=False)
        run(SUDO + ["rm", "-f", str(SYSTEMD_DIR / f"{s}.service")])
        run(SUDO + ["systemctl", "daemon-reload"], check=False)
        if yes(w("uninstall_files"), default=False):
            for f in (CONF, ROOT / "state.json", ROOT / "history.json"):
                f.unlink(missing_ok=True)
        print(w("uninstalled", d=ROOT))


def change_language():
    d = read_conf()
    choose_language(d)
    if d.get("TG_TOKEN") or d.get("MESH_CHANNEL"):
        write_conf(d)
    print(w("lang_set", l=LANGS[w.lang]))
    s = service_name(d)
    if installed(s) and yes(w("restart_ask")):
        run(SUDO + ["systemctl", "restart", s])


# ================================================================== main
def main():
    d = read_conf()
    if d.get("BRIDGE_LANG"):
        set_lang(d["BRIDGE_LANG"])
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if not d.get("BRIDGE_LANG") and action in ("", "config"):
        choose_language()
    actions = {"config": guided, "install": install_service, "uninstall": uninstall,
               "status": lambda: run(["systemctl", "status", service_name(), "--no-pager"], check=False),
               "logs": logs, "test": test_telegram}
    if action:
        if action not in actions:
            print(__doc__)
            sys.exit(2)
        r = actions[action]()
        sys.exit(0 if r is not False else 1)
    if not d:
        guided()
    while True:
        print("\n" + w("title"))
        v = ask(w("menu") + w("choice"))
        fn = {"1": guided, "2": install_service, "3": service_menu, "4": logs, "5": test_telegram,
              "6": show_conf, "7": change_language, "8": uninstall}.get(v)
        if v == "0":
            print(w("bye"))
            return
        if fn is None:
            print(w("invalid"))
            continue
        fn()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
