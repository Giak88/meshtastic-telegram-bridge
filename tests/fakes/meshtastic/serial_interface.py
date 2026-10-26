import os, json, time, threading
from types import SimpleNamespace as NS
from pubsub import pub

MY = 0x11111111
NODES = {MY: {"user": {"longName": "Bridge Node"}},
         0x22222222: {"user": {"longName": "Alice"}},
         0x33333333: {"user": {"longName": "Carol"}},
         0x44444444: {"user": {"longName": "Admin"}}}


class SerialInterface:
    def __init__(self, devPath=None, **kw):
        d = os.environ.get("FAKE_MESH_DIR")
        if os.environ.get("FAKE_MESH_FAIL"):
            raise OSError("could not open port " + str(devPath))
        self.dir = d
        self.myInfo = NS(my_node_num=MY)
        self.nodesByNum = NODES
        names = os.environ.get("FAKE_MESH_CHANNELS", ",Group").split(",")
        chans = [NS(index=i, role=1 if i == 0 else 2, settings=NS(name=n, psk=b"\x01"))
                 for i, n in enumerate(names)]
        chans.append(NS(index=len(names), role=0, settings=NS(name="", psk=b"")))
        self.localNode = NS(channels=chans, localConfig=NS(lora=NS(modem_preset=4)))
        self.closed = False
        if d:
            threading.Thread(target=self._tail, daemon=True).start()

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
