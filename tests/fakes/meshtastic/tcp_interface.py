from .serial_interface import SerialInterface


class TCPInterface(SerialInterface):
    def __init__(self, hostname=None, **kw):
        super().__init__(devPath=hostname)
