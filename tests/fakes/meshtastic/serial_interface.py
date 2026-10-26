import os, json, time, base64, threading
from types import SimpleNamespace as NS
from pubsub import pub

MY = 0x11111111
NODES = {MY: {"user": {"longName": "Bridge Node"}},
         0x22222222: {"user": {"longName": "Alice"}},
         0x33333333: {"user": {"longName": "Carol"}},
         0x44444444: {"user": {"longName": "Admin"}}}


def _channels_file():
    d = os.environ.get("FAKE_MESH_DIR")
    return os.path.join(d, "channels.json") if d else None


def _load_channels():
    """8 slots like a real node. Persisted in channels.json once something is written to the node."""
    path = _channels_file()
    if path and os.path.exists(path):
        return [NS(index=i, role=c["role"], settings=NS(name=c["name"], psk=base64.b64decode(c["psk"])))
                for i, c in enumerate(json.load(open(path)))]
    names = os.environ.get("FAKE_MESH_CHANNELS", ",Group").split(",")
    chans = [NS(index=i, role=1 if i == 0 else 2, settings=NS(name=n, psk=b"\x01")) for i, n in enumerate(names)]
    while len(chans) < 8:
        chans.append(NS(index=len(chans), role=0, settings=NS(name="", psk=b"")))
    return chans


class SerialInterface:
    def __init__(self, devPath=None, **kw):
        d = os.environ.get("FAKE_MESH_DIR")
        if os.environ.get("FAKE_MESH_FAIL"):
            raise OSError("could not open port " + str(devPath))
        self.dir = d
        self.myInfo = NS(my_node_num=MY)
        self.nodesByNum = NODES
        chans = _load_channels()
        self.localNode = NS(channels=chans, localConfig=NS(lora=NS(modem_preset=4)),
                            writeChannel=lambda idx, adminIndex=0: self._write(chans, idx))
        self.closed = False
        if d:
            threading.Thread(target=self._tail, daemon=True).start()

    def _write(self, chans, idx):
        if os.environ.get("FAKE_MESH_WRITE_FAIL"):
            raise OSError("admin message not acknowledged")
        path = _channels_file()
        if path:
            json.dump([{"role": c.role, "name": c.settings.name, "psk": base64.b64encode(c.settings.psk).decode()}
                       for c in chans], open(path, "w"))

    def _tail(self):
        path = os.path.join(self.dir, "inbox.jsonl")
        pos = 0
        while not self.closed:
            if os.path.exists(path):
                with open(path) as f:
                    f.seek(pos)
                    for line in f:
                        if line.strip():
                            pub.sendMessage("meshtastic.receive.text", packet=json.loads(line), interface=self)
                    pos = f.tell()
            time.sleep(0.1)

    def sendText(self, text, destinationId=None, channelIndex=0, wantAck=False):
        if self.dir:
            with open(os.path.join(self.dir, "outbox.jsonl"), "a") as f:
                f.write(json.dumps({"text": text, "dest": destinationId, "ch": channelIndex}) + "\n")

    def close(self):
        self.closed = True
