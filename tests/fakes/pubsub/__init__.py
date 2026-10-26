"""Minimal stand-in for pypubsub, used only by the tests."""


class _Pub:
    def __init__(self):
        self.subs = {}

    def subscribe(self, fn, topic):
        self.subs.setdefault(topic, []).append(fn)

    def sendMessage(self, topic, **kw):
        for fn in self.subs.get(topic, []):
            fn(**kw)


pub = _Pub()
