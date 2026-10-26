# Meshtastic ↔ Telegram Bridge

**English** · [Italiano](README.it.md)

Connects one Meshtastic channel to a Telegram group, in both directions, through a node plugged
into a Linux machine. People in the field talk on the radio, people at home talk on Telegram, and
everyone reads everything.

```
 [radio nodes] ~~ LoRa ~~ [your node] --USB-- [Linux PC: bridge.py] --internet-- [Telegram group]
```

- **Two-way bridging**: every text on the bridged channel goes to the group as `Alice: text`;
  every group message goes to the channel as `TG Bob: text`, split into 200-character messages
  with `[x/y]` counters.
- **Catch up on missed messages**: anyone on the channel writes `!repeat 5` and the bridge sends
  back the last 5 messages from Telegram *and* from the channel (except their own), which helps
  nodes at the edge of the mesh. In the group, `/repeat 5` returns the last 5 radio messages.
  Up to 20 per side, kept across restarts.
- **No duplicates after a restart or an outage**: the Telegram position is saved; group
  messages older than 1 hour are kept for `repeat` but not flooded onto the radio.
- **Airtime-friendly**: long Telegram messages are cut to 4 radio messages (configurable),
  transmissions are paced, and Telegram is handled on its own thread so a slow network never
  blocks the radio.
- **Remote control by encrypted DM**: admins send `status`, `bridge on|off`, `ban <id>`,
  `unban <id>` to the bridge node.
- **English or Italian**: menu, logs and bridge messages; commands are accepted in both
  (`repeat`/`ripeti`, `status`/`stato`).
- **Guided setup**: one menu finds the serial port, reads the channels from the node, checks
  the bot token, detects the group, and installs a systemd service that starts at boot.

No MQTT, no broker, no internet needed on the radio side.

## Requirements

- A Meshtastic node (any board) on USB, or on Wi-Fi/Ethernet (TCP 4403).
- Linux with systemd and Python 3.9+ (Debian, Ubuntu, Raspberry Pi OS...).
- A Telegram bot and a group.

## Quick start

```bash
sudo apt install git python3-venv
git clone https://github.com/Giak88/mesh-telegram-bridge.git
cd mesh-telegram-bridge
./setup.sh
```

The first run asks for the language, then guides you through six steps:

1. **Node connection**: pick the USB port (stable `/dev/serial/by-id/...` names are shown first) or type the node's IP.
2. **Mesh channel**: the channel list is read from the node; choose the one to bridge.
   Use a private channel with its own PSK, shared with the people of your group: everything
   written there ends up on Telegram.
3. **Telegram bot**: create one with [@BotFather](https://t.me/BotFather) (`/newbot`), paste the
   token (it is checked immediately). Add the bot to your group **as administrator**, or disable
   its privacy mode (`/setprivacy` → Disable), otherwise it cannot read the group. The setup checks this and warns you; the bridge logs the same warning at start.
4. **Telegram group**: write anything in the group and the bridge detects its id.
5. **Administrators** (optional): node ids allowed to control the bridge by DM.
6. **Command prefix**: `!` by default (`!repeat 3`); any word works (`BOT` → `BOT repeat 3`).

Then it offers to install the service. From now on the bridge starts at every boot.

Run `./setup.sh` again at any time for the menu:

```
  1) Guided configuration
  2) Install / update the service (starts at boot)
  3) Service: status, start, stop, restart
  4) Live log
  5) Test: send a message to Telegram
  6) Show configuration
  7) Language / Lingua
  8) Uninstall the service
```

The same actions are available directly: `./setup.sh config|install|uninstall|status|logs|test`.

## Commands

| Where | Command | Effect |
|---|---|---|
| Bridged channel | `!repeat <n>` (`!ripeti <n>`) | Last *n* messages from Telegram and the channel, except yours |
| Telegram group | `/repeat <n>` or `!repeat <n>` | Last *n* messages from the channel |
| DM to the bridge node (admin) | `status` | Bridge state, uptime, counters |
| | `bridge on` / `bridge off` | Stop or resume forwarding (messages are still kept for `repeat`) |
| | `ban <id>` / `unban <id>` | Ignore a node on the bridged channel |

By default admin commands are accepted only in PKI-encrypted DMs (Meshtastic 2.5+), so nobody
can impersonate an admin by faking a node id.

## Configuration

`./setup.sh` writes `config.env` (permissions 600, never committed). Every setting is documented
in [`config.env.example`](config.env.example). After editing it by hand:
`sudo systemctl restart mesh-telegram-bridge`.

## Running it next to another program that uses the node

A node can be used by only one program at a time. To try the bridge on a node that is already
used by something else, stop that program first (`sudo systemctl stop <its-service>`), then
`./setup.sh` → 3 → Start. Use a separate bot token: two programs reading the same bot cause a
`409 Conflict`. To go back: menu 3 → Stop, then start the other program again. Uninstalling
(menu 8) removes only this bridge's service.

## Logs

```bash
journalctl -u mesh-telegram-bridge -f        # or ./setup.sh logs
```

```
Bridge: mesh channel 'MyGroup' (index 2) <-> Telegram chat -100..., bridge on
[MESH>TG] Alice: on my way
[TG>MESH] Bob: see you at the hut
[TX MyGroup] TG Bob: see you at the hut
[REPEAT] mesh <- last 5 from Telegram and MyGroup (excluding !1a2b3c4d)
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Group messages never reach the radio | The bot cannot read the group: make it admin, or `/setprivacy` → Disable and then remove and re-add the bot. |
| `409 Conflict` in the log | Another program uses the same bot token. Use a dedicated bot. |
| `Mesh channel '...' not found` and the service stops | The name in `MESH_CHANNEL` does not match the node (check with option 1 of the menu). |
| Serial port errors | The node is used by another program, or the port changed: prefer the `/dev/serial/by-id/...` path. |
| The group id changed | A group converted to supergroup gets a new id: run step 4 again. |

## Development

```bash
python3 -m unittest discover -s tests -t .
```

The tests run the real `bridge.py` and `setup_wizard.py` against a simulated node and a local
fake of the Telegram API, so no radio, token or root access is needed.

## License

MIT, see [LICENSE](LICENSE). Idea and field testing by Giak88; designed and written with the
help of Claude (Anthropic).
