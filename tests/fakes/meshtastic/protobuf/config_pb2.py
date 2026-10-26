class Config:
    class LoRaConfig:
        class ModemPreset:
            @staticmethod
            def Name(p):
                return {0: "LONG_FAST", 4: "MEDIUM_FAST"}.get(p, "LONG_FAST")
