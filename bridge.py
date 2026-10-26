#!/usr/bin/env python3
"""Meshtastic <-> Telegram bridge.

Every text message written on one Meshtastic channel goes to a Telegram group, and every
message of the group goes to that channel. Anyone can ask for the messages they missed with
"<prefix>repeat <n>" (Italian: "<prefix>ripeti <n>"); admins control the bridge by encrypted DM.

Configuration: config.env next to this file (created by ./setup.sh, see config.env.example).
Run:  python bridge.py            (normally started by systemd)
"""

import os
import re
import sys
import json
import time
import queue
import logging
import threading
from pathlib import Path
from collections import deque

import requests

from i18n import Tr

__version__ = "1.0.0"
BASE = Path(__file__).resolve().parent
EX_CONFIG = 78                      # exit code for configuration errors: systemd does not restart

log = logging.getLogger("bridge")


# ================================================================== configuration
def load_env_file(path):
    """Read KEY=value lines into os.environ without overriding variables already set
    (under systemd, EnvironmentFile has already loaded them)."""
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            os.environ.setdefault(k.strip(), v)
    except FileNotFoundError:
        pass


def _bool(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on", "si", "sì")


class Config:
    def __init__(self, env=None):
        e = (env if env is not None else os.environ).get
        self.lang = e("BRIDGE_LANG", "en").strip().lower()
        self.mesh_port = e("MESH_PORT", "").strip()            # /dev/serial/by-id/... (empty = auto)
        self.mesh_host = e("MESH_HOST", "").strip()            # node over Wi-Fi/Ethernet (TCP 4403)
        self.mesh_channel = e("MESH_CHANNEL", "").strip()      # bridged channel name (case-insensitive)
        self.tg_token = e("TG_TOKEN", "").strip()
        self.tg_chat = e("TG_CHAT_ID", "").strip()
        self.tg_api = e("TG_API_BASE", "https://api.telegram.org").rstrip("/")
        self.prefix = e("BRIDGE_PREFIX", "!").strip()          # e.g. "!" -> "!repeat 3", "CLU" -> "CLU repeat 3"
        self.admins = {x.strip().lower() if x.strip().startswith("!") else "!" + x.strip().lower()
                       for x in e("BRIDGE_ADMINS", "").split(",") if x.strip()}
        self.admin_pki = _bool(e("BRIDGE_ADMIN_PKI_ONLY", "1"))
        self.history_n = max(1, int(e("BRIDGE_HISTORY", "20")))       # messages kept per side
        self.repeat_pause = int(e("BRIDGE_REPEAT_PAUSE", "30"))       # s between two repeats per side
        self.max_parts = max(1, int(e("BRIDGE_MAX_PARTS", "4")))      # max mesh messages per TG message
        self.tx_gap = float(e("MESH_TX_INTERVAL", "1.5"))             # s between two mesh transmissions
        self.max_age = int(e("TG_MAX_AGE", "3600"))                    # older TG messages are not sent to mesh
        self.state_file = Path(e("BRIDGE_STATE", str(BASE / "state.json")))
        self.history_file = Path(e("BRIDGE_HISTORY_FILE", str(BASE / "history.json")))

    def missing(self):
        return [k for k, v in (("MESH_CHANNEL", self.mesh_channel), ("TG_TOKEN", self.tg_token),
                               ("TG_CHAT_ID", self.tg_chat)) if not v]


MAX_CHARS = 200          # characters per mesh message, counter included
MAX_BYTES = 228          # UTF-8 bytes per mesh message (LoRa payload limit)

cfg = Config({})
t = Tr("en")


# ================================================================== persistence
def write_json(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


class State:
    """bridge on/off, banned nodes, Telegram offset, counters. Survives restarts."""

    def __init__(self, path):
        self.path, self.lock = path, threading.Lock()
        self.bridge, self.ban, self.tg_offset = True, set(), None
        self.count = {"m2t": 0, "t2m": 0, "tg_err": 0}
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            self.bridge = d.get("bridge", True)
            self.ban = set(d.get("ban", []))
            self.tg_offset = d.get("tg_offset")
            self.count.update(d.get("count", {}))
        except FileNotFoundError:
            pass
        except Exception as ex:
            log.warning(t("log_file_bad", file=path.name, err=ex))

    def save(self):
        with self.lock:
            write_json(self.path, {"bridge": self.bridge, "ban": sorted(self.ban),
                                   "tg_offset": self.tg_offset, "count": self.count})

    def inc(self, k):
        with self.lock:
            self.count[k] += 1


class History:
    """Last N messages of each side: 'M' (mesh channel) and 'TG' (Telegram group)."""

    def __init__(self, path, n):
        self.path, self.n, self.lock = path, n, threading.Lock()
        self.sides = {"M": [], "TG": []}
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            self.sides.update({k: d.get(k, [])[-n:] for k in self.sides})
        except FileNotFoundError:
            pass
        except Exception as ex:
            log.warning(t("log_file_bad", file=path.name, err=ex))

    def add(self, side, name, text, ts=None, mid=None, uid=""):
        """False if the message is already stored (same id)."""
        with self.lock:
            lst = self.sides[side]
            if mid and any(m.get("id") == mid for m in lst):
                return False
            m = {"ts": int(ts or time.time()), "n": name, "t": text}
            if mid:
                m["id"] = mid
            if uid:
                m["u"] = uid
            self.sides[side] = sorted(lst + [m], key=lambda x: x["ts"])[-self.n:]
            write_json(self.path, self.sides)
            return True

    def last(self, side):
        with self.lock:
            return list(self.sides[side])


# ================================================================== pagination
def _split(text, maxc, maxb):
    parts, cur = [], ""
    for w in text.split(" "):
        cand = w if not cur else cur + " " + w
        if len(cand) <= maxc and len(cand.encode()) <= maxb:
            cur = cand
            continue
        if cur:
            parts.append(cur)
            cur = ""
        while len(w) > maxc or len(w.encode()) > maxb:      # word longer than a message
            k = maxc
            while len(w[:k].encode()) > maxb:
                k -= 1
            parts.append(w[:k])
            w = w[k:]
        cur = w
    if cur:
        parts.append(cur)
    return parts


def paginate(text, prefix=""):
    """Split into mesh messages of at most 200 characters; with more than one, each ends with [x/y]."""
    text = re.sub(r"\s+", " ", text).strip()
    whole = prefix + text
    if len(whole) <= MAX_CHARS and len(whole.encode()) <= MAX_BYTES:
        return [whole]
    n = 2
    for _ in range(6):
        tag = len(f" [{n}/{n}]")
        parts = _split(text, MAX_CHARS - len(prefix) - tag, MAX_BYTES - len(prefix.encode()) - tag)
        if len(str(len(parts))) <= len(str(n)):
            break
        n = len(parts)
    return [f"{prefix}{p} [{i}/{len(parts)}]" for i, p in enumerate(parts, 1)]


def paginate_lines(lines):
    """Pack lines into mesh messages without breaking a line when possible; always [x/y]."""
    tag = len(" [99/99]")
    maxc, maxb = MAX_CHARS - tag, MAX_BYTES - tag
    pages, cur = [], ""
    for r in lines:
        r = re.sub(r"\s+", " ", r).strip()
        if not r:
            continue
        cand = f"{cur} {r}" if cur else r
        if len(cand) <= maxc and len(cand.encode()) <= maxb:
            cur = cand
            continue
        if cur:
            pages.append(cur)
        pz = _split(r, maxc, maxb)
        pages += pz[:-1]
        cur = pz[-1]
    if cur:
        pages.append(cur)
    return [f"{p} [{i}/{len(pages)}]" for i, p in enumerate(pages, 1)]


def paginate_limited(text, prefix, max_parts):
    """Like paginate, but cuts the text (with …) so it fits in max_parts messages."""
    pages = paginate(text, prefix)
    if len(pages) <= max_parts:
        return pages, False
    text = re.sub(r"\s+", " ", text).strip()
    keep = max_parts * (MAX_CHARS - len(prefix) - 8)
    while keep > 0:
        pages = paginate(text[:keep].rstrip() + "…", prefix)
        if len(pages) <= max_parts:
            return pages, True
        keep -= 10
    return pages[:max_parts], True


# ================================================================== runtime
state = None
history = None
iface = None
MY_NUM = None
CHANNELS = {}            # index -> name
BRIDGE_IDX = None
STARTED = time.time()
jobs = queue.Queue()     # everything that transmits on the mesh runs here, one at a time
tg_out = queue.Queue()   # messages for Telegram, sent by their own thread (never blocks the radio)
tx_lock = threading.Lock()
repeat_ts = {"M": 0.0, "TG": 0.0}
seen = deque(maxlen=500)
http = requests.Session()


def channel_name():
    return CHANNELS.get(BRIDGE_IDX, cfg.mesh_channel)


def mesh_send(text, dest=None, ch=None):
    ch = BRIDGE_IDX if ch is None else ch
    with tx_lock:
        if dest:
            iface.sendText(text, destinationId=dest, channelIndex=ch, wantAck=True)
        else:
            iface.sendText(text, channelIndex=ch)
        log.info(f"[TX {dest or CHANNELS.get(ch, ch)}] {text}")
        time.sleep(cfg.tx_gap)


def node_user(num):
    return ((iface.nodesByNum or {}).get(num) or {}).get("user", {})


def long_name(num):
    return node_user(num).get("longName") or f"!{num:08x}"


def read_channels(node_iface):
    """{index: name} of the enabled channels; an unnamed primary gets the preset name (MediumFast)."""
    from meshtastic.protobuf import channel_pb2, config_pb2
    out = {}
    for c in node_iface.localNode.channels or []:
        if c.role == channel_pb2.Channel.Role.DISABLED:
            continue
        name = c.settings.name
        if not name and c.role == channel_pb2.Channel.Role.PRIMARY:
            p = node_iface.localNode.localConfig.lora.modem_preset
            name = "".join(w.capitalize() for w in
                           config_pb2.Config.LoRaConfig.ModemPreset.Name(p).split("_"))
        out[c.index] = name
    return out


# ================================================================== Telegram
class TgError(Exception):
    def __init__(self, code, desc, retry_after=None):
        super().__init__(f"HTTP {code} {desc}".strip())
        self.code, self.retry_after = code, retry_after


def tg_clean(err):
    """Error text without the token (requests puts it in the URL)."""
    s = f"{type(err).__name__}: {err}"
    return s.replace(cfg.tg_token, "***") if cfg.tg_token else s


def tg_api(method, params=None, timeout=15):
    r = http.post(f"{cfg.tg_api}/bot{cfg.tg_token}/{method}", json=params or {}, timeout=timeout)
    try:
        d = r.json()
    except ValueError:
        d = {}
    if not d.get("ok"):
        raise TgError(r.status_code, d.get("description", ""),
                      (d.get("parameters") or {}).get("retry_after"))
    return d["result"]


def tg_send(text, attempts=4):
    """Send to the group with retries; respects Telegram's 429 retry_after. True if sent."""
    err = None
    for i in range(attempts):
        try:
            tg_api("sendMessage", {"chat_id": cfg.tg_chat, "text": text[:4096],
                                   "disable_web_page_preview": True})
            return True
        except TgError as ex:
            err = ex
            if ex.code == 429 and ex.retry_after:
                log.warning(t("log_tg_wait", s=ex.retry_after))
                time.sleep(min(int(ex.retry_after), 120))
                continue
            if ex.code in (400, 401, 403, 404):          # permanent: retrying will not help
                break
        except Exception as ex:                          # network error
            err = ex
        time.sleep(2 * (i + 1))
    state.inc("tg_err")
    log.error(t("log_tg_send_fail", n=i + 1, err=tg_clean(err)))
    return False


def tg_sender():
    """Worker for tg_out: (text, notify_mesh_on_failure)."""
    while True:
        text, notify = tg_out.get()
        if not tg_send(text) and notify:
            jobs.put(lambda: mesh_send(t("tg_failed")))


def tg_to_mesh(text, author):
    pages, cut = paginate_limited(text, f"TG {author}: " if author else "TG: ", cfg.max_parts)
    if cut:
        log.info(t("log_truncated", n=len(pages)))
    for p in pages:
        mesh_send(p)
    state.inc("t2m")


def handle_tg_update(u):
    """One update from getUpdates. Runs in the polling thread; mesh sends go to jobs."""
    p = u.get("message") or u.get("channel_post")
    if not p:
        return
    chat = p.get("chat", {})
    cid = str(chat.get("id"))
    if cid != cfg.tg_chat:
        log.info(t("log_tg_other_chat", title=chat.get("title") or chat.get("first_name", "?"),
                   type=chat.get("type", "?"), id=cid))
        return
    sender = p.get("from") or {}
    if sender.get("is_bot"):
        return
    text = p.get("text") or p.get("caption") or t("non_text")
    author = sender.get("first_name") or sender.get("username") or chat.get("title") or ""
    age = time.time() - p.get("date", 0)
    n = parse_repeat(text)
    if n is not None:
        log.info(f"[TG] {author}: {text}")
        if age <= cfg.max_age:
            repeat_on_telegram(n)
        return
    if text.startswith("/"):                                 # other bot commands (/start...): ignored
        return
    if not history.add("TG", author or "?", text, ts=p.get("date"), mid=f"tg{u['update_id']}"):
        return
    if age > cfg.max_age:
        log.info(t("log_tg_old", name=author, text=text))
        return
    if not state.bridge:
        log.info(f"[TG>MESH] {author}: {text}" + t("log_not_forwarded"))
        return
    log.info(f"[TG>MESH] {author}: {text}")
    jobs.put(lambda: tg_to_mesh(text, author))


def tg_check_access():
    """Warn if Telegram will not deliver the group's normal messages to the bot: that happens when
    privacy mode is on and the bot is not an administrator (messages bridge only mesh -> Telegram)."""
    try:
        me = tg_api("getMe")
        member = tg_api("getChatMember", {"chat_id": cfg.tg_chat, "user_id": me["id"]})
    except Exception:
        return                                           # cannot tell: no false alarm
    if member.get("status") in ("administrator", "creator") or me.get("can_read_all_group_messages"):
        return
    log.warning(t("log_tg_privacy"))


def tg_poll():
    """Long polling. The offset is saved, so nothing is lost or duplicated across restarts."""
    try:
        tg_api("deleteWebhook", {"drop_pending_updates": False})   # getUpdates fails if a webhook is set
    except Exception:
        pass
    tg_check_access()
    while True:
        try:
            par = {"timeout": 50, "allowed_updates": ["message", "channel_post"]}
            if state.tg_offset is not None:
                par["offset"] = state.tg_offset
            updates = tg_api("getUpdates", par, timeout=60)
            for u in updates:
                try:
                    handle_tg_update(u)
                except Exception as ex:
                    log.error(t("log_error", err=f"{type(ex).__name__}: {ex}"))
                state.tg_offset = u["update_id"] + 1
            if updates:
                state.save()
        except TgError as ex:
            if ex.code == 409:
                log.error(t("log_tg_conflict"))
                time.sleep(30)
            elif ex.code == 401:
                log.error(t("log_tg_unauth"))
                time.sleep(300)
            elif ex.code == 429 and ex.retry_after:
                time.sleep(int(ex.retry_after))
            else:
                log.error(t("log_tg_err", err=tg_clean(ex)))
                time.sleep(10)
        except Exception as ex:
            log.error(t("log_tg_err", err=tg_clean(ex)))
            time.sleep(10)


# ================================================================== repeat
REPEAT_RE = None


def build_repeat_re():
    global REPEAT_RE
    p = re.escape(cfg.prefix)
    sep = r"[,:.!?]*\s+" if cfg.prefix and cfg.prefix[-1].isalnum() else r"\s*"
    head = rf"(?:{p}{sep}|/)" if cfg.prefix else r"/?"
    REPEAT_RE = re.compile(rf"(?i)\s*{head}(?:repeat|ripeti)(?:@\w+)?(?:\s+(\S+?))?[.!?]*\s*")


def repeat_cmd():
    """How the command is written in this language, e.g. '!repeat' or 'CLU ripeti'."""
    sep = " " if cfg.prefix and cfg.prefix[-1].isalnum() else ""
    return f"{cfg.prefix}{sep}{t('repeat_word')}"


def parse_repeat(text):
    """None if not the command; 0 if the number is missing/invalid; otherwise the number (capped)."""
    m = REPEAT_RE.fullmatch(text)
    if not m:
        return None
    n = m.group(1) or ""
    return min(int(n), cfg.history_n) if n.isdigit() and int(n) > 0 else 0


def repeat_lines(sides, src, n, exclude=""):
    msgs = sorted(([side, m] for side in sides for m in history.last(side)
                   if not exclude or m.get("u") != exclude), key=lambda x: x[1]["ts"])[-n:]
    if not msgs:
        return [t("repeat_empty", src=src)]
    today = time.strftime("%Y%m%d")
    out = [t("repeat_head", n=len(msgs), src=src)]
    for side, m in msgs:
        lt = time.localtime(m["ts"])
        when = time.strftime("%H:%M" if time.strftime("%Y%m%d", lt) == today else "%d/%m %H:%M", lt)
        tg = "TG " if side == "TG" and len(sides) > 1 else ""
        out.append(f"{when} {tg}{m['n'][:20]}: {m['t']}")
    return out


def too_soon(side):
    if time.time() - repeat_ts[side] < cfg.repeat_pause:
        log.info(t("log_repeat_wait", side=side, s=cfg.repeat_pause))
        return True
    repeat_ts[side] = time.time()
    return False


def repeat_on_mesh(n, uid):
    """Asked on the mesh channel: the last n messages of Telegram and of the channel itself,
    except those of whoever asks."""
    if not n:
        return mesh_send(t("repeat_usage", cmd=repeat_cmd(), max=cfg.history_n))
    if too_soon("M"):
        return
    log.info(t("log_repeat_mesh", n=n, ch=channel_name(), uid=uid))
    for p in paginate_lines(repeat_lines(("TG", "M"), t("src_both", ch=channel_name()), n, exclude=uid)):
        mesh_send(p)


def repeat_on_telegram(n):
    """Asked in the Telegram group: the last n messages written on the mesh channel."""
    if not n:
        return tg_out.put((t("repeat_usage", cmd=repeat_cmd(), max=cfg.history_n), False))
    if too_soon("TG"):
        return
    log.info(t("log_repeat_tg", n=n))
    tg_out.put(("\n".join(repeat_lines(("M",), t("src_mesh"), n)), False))


# ================================================================== mesh side
def uptime():
    s = int(time.time() - STARTED)
    return f"{s // 86400}d{s % 86400 // 3600}h{s % 3600 // 60:02d}m"


def norm_id(x):
    x = x.strip().lower()
    return x if x.startswith("!") else "!" + x


def handle_admin(uid, text):
    """Admin commands by DM. Returns the reply, or None if it is not a command."""
    w = text.split()
    if w and cfg.prefix and w[0].lower().rstrip(",:.!?") == cfg.prefix.lower():
        w = w[1:]
    if not w:
        return None
    c, a = w[0].lower().strip("!.,:;?"), (w[1].lower() if len(w) > 1 else "")
    onoff = lambda b: "on" if b else "off"
    if c in ("status", "stato") and len(w) == 1:
        return t("adm_status", state=onoff(state.bridge), ch=channel_name(), up=uptime(),
                 m2t=state.count["m2t"], t2m=state.count["t2m"], err=state.count["tg_err"],
                 ban=len(state.ban))
    if c == "bridge" and a in ("", "on", "off") and len(w) <= 2:
        if a:
            state.bridge = a == "on"
            state.save()
            log.info(t("log_bridge_set", state=a, uid=uid))
        return t("adm_bridge", state=onoff(state.bridge), ch=channel_name())
    if c in ("ban", "unban") and len(w) == 2:
        i = norm_id(w[1])
        (state.ban.add if c == "ban" else state.ban.discard)(i)
        state.save()
        return t("adm_" + c, id=i)
    if c in ("help", "aiuto", "comandi", "commands"):
        return t("adm_help")
    return None


def handle_packet(pkt):
    text = (pkt.get("decoded") or {}).get("text", "").strip()
    num = pkt.get("from")
    if not text or num is None or num == MY_NUM:
        return
    uid = (pkt.get("fromId") or f"!{num:08x}").lower()
    ch = pkt.get("channel", 0)
    if pkt.get("to") == MY_NUM:                                  # direct message
        if uid in cfg.admins and (pkt.get("pkiEncrypted") or not cfg.admin_pki):
            log.info(f"[ADMIN {uid}] {text}")
            reply = handle_admin(uid, text) or t("adm_help")
            for p in paginate(reply):
                mesh_send(p, dest=uid, ch=ch)
        else:
            log.info(t("log_dm_ignored", uid=uid))
        return
    if ch != BRIDGE_IDX or uid in state.ban:
        return
    n = parse_repeat(text)
    if n is not None:                                            # not forwarded to Telegram
        log.info(f"[MESH {uid}] {text}")
        return repeat_on_mesh(n, uid)
    name = long_name(num)
    history.add("M", name, text, uid=uid)
    if not state.bridge:
        return log.info(f"[MESH>TG] {name}: {text}" + t("log_not_forwarded"))
    log.info(f"[MESH>TG] {name}: {text}")
    state.inc("m2t")
    tg_out.put((f"{name}: {text}", True))


def on_receive(packet, interface=None):
    pid = packet.get("id")
    if pid:
        if pid in seen:
            return
        seen.append(pid)
    jobs.put(lambda: handle_packet(packet))


def on_lost(interface=None):
    log.error(t("log_lost"))
    os._exit(1)


def worker():
    while True:
        f = jobs.get()
        try:
            f()
        except Exception as ex:
            log.error(t("log_error", err=f"{type(ex).__name__}: {ex}"))


# ================================================================== start
def setup(config):
    """Apply a configuration (also used by the tests)."""
    global cfg, t, state, history
    cfg, t = config, Tr(config.lang)
    build_repeat_re()
    state = State(cfg.state_file)
    history = History(cfg.history_file, cfg.history_n)


def open_node():
    if cfg.mesh_host:
        import meshtastic.tcp_interface
        return meshtastic.tcp_interface.TCPInterface(hostname=cfg.mesh_host)
    import meshtastic.serial_interface
    if cfg.mesh_port:                         # the USB device may appear a few seconds after boot
        for i in range(60):
            if os.path.exists(cfg.mesh_port):
                break
            if i == 0:
                log.info(t("log_wait_dev", port=cfg.mesh_port))
            time.sleep(1)
        else:
            log.error(t("log_no_dev", port=cfg.mesh_port, s=60))
            sys.exit(1)
    return meshtastic.serial_interface.SerialInterface(devPath=cfg.mesh_port or None)


def main():
    global iface, MY_NUM, CHANNELS, BRIDGE_IDX
    load_env_file(os.environ.get("BRIDGE_CONFIG", BASE / "config.env"))
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    setup(Config())
    log.info(t("log_start", ver=__version__))
    miss = cfg.missing()
    if miss:
        log.error(t("log_cfg_missing", key=", ".join(miss)))
        sys.exit(EX_CONFIG)
    from pubsub import pub
    iface = open_node()
    MY_NUM = iface.myInfo.my_node_num
    CHANNELS = read_channels(iface)
    log.info(t("log_connected", id=f"!{MY_NUM:08x}", name=long_name(MY_NUM), ch=CHANNELS))
    BRIDGE_IDX = next((k for k, v in CHANNELS.items() if v.lower() == cfg.mesh_channel.lower()), None)
    if BRIDGE_IDX is None:
        log.error(t("log_no_channel", ch=cfg.mesh_channel, avail=", ".join(CHANNELS.values())))
        iface.close()
        sys.exit(EX_CONFIG)
    log.info(t("log_bridge", ch=channel_name(), idx=BRIDGE_IDX, chat=cfg.tg_chat,
               state="on" if state.bridge else "off"))
    if cfg.admins:
        log.info(t("log_admins", ids=", ".join(sorted(cfg.admins)), pki="on" if cfg.admin_pki else "off"))
    pub.subscribe(on_receive, "meshtastic.receive.text")
    pub.subscribe(on_lost, "meshtastic.connection.lost")
    for target in (worker, tg_sender, tg_poll):
        threading.Thread(target=target, daemon=True).start()
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
