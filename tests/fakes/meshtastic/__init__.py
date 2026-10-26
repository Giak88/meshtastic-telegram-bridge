"""Fake meshtastic package for the tests: a node driven by files.

FAKE_MESH_DIR/inbox.jsonl   packets "received" by the node (one JSON per line, appended by the test)
FAKE_MESH_DIR/outbox.jsonl  what the bridge transmits
FAKE_MESH_CHANNELS          comma-separated channel names (index 0 = primary, empty = preset name)
"""
