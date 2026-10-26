"""Translations (English / Italian) shared by bridge.py and setup_wizard.py.

To add a language, copy the "en" block, translate the values and keep the {placeholders}.
Missing keys fall back to English.
"""

STRINGS = {
    "en": {
        # ---------------------------------------------------------------- mesh / Telegram
        "repeat_word": "repeat",
        "repeat_usage": "Usage: {cmd} <number>, e.g. {cmd} 3 (max {max}).",
        "repeat_empty": "Repeat: no messages from {src}.",
        "repeat_head": "Last {n} from {src}:",
        "src_both": "Telegram and {ch}",
        "src_mesh": "Meshtastic",
        "tg_failed": "Telegram: send failed, message not delivered.",
        "non_text": "[non-text content]",
        "adm_status": ("Status: bridge {state} ({ch} <-> Telegram), up {up}. Mesh->TG {m2t}, "
                       "TG->mesh {t2m}, TG errors {err}. Banned {ban}."),
        "adm_bridge": "Bridge: {state} ({ch} <-> Telegram).",
        "adm_ban": "Ban: {id} banned.",
        "adm_unban": "Unban: {id} unbanned.",
        "adm_help": ("Admin: status, bridge on|off, ban <id>, unban <id>, repeat <n> (my last n replies here), "
                     "log [n] (bot log, newest first)."),
        "adm_repeat_none": "Repeat: no replies to repeat yet.",
        "adm_log_head": "Log, newest first:",
        "adm_log_empty": "Log: empty.",
        # ---------------------------------------------------------------- log
        "log_start": "Meshtastic-Telegram bridge {ver} starting (language: English)",
        "log_cfg_missing": "Missing setting {key} in config.env: run ./setup.sh",
        "log_wait_dev": "Waiting for device {port}...",
        "log_no_dev": "Device {port} not found after {s} s",
        "log_connected": "Connected to node {id} ({name}). Channels: {ch}",
        "log_no_channel": ("Mesh channel '{ch}' not found on the node (available: {avail}). "
                           "Fix MESH_CHANNEL in config.env."),
        "log_bridge": "Bridge: mesh channel '{ch}' (index {idx}) <-> Telegram chat {chat}, bridge {state}",
        "log_admins": "Admins: {ids} (PKI-encrypted DM only: {pki})",
        "log_admin_channel": "Admin channel: '{ch}' (index {idx}), commands accepted from: {who}",
        "who_any": "any node on the channel",
        "log_no_admin_channel": ("Admin channel '{ch}' not found on the node (available: {avail}): "
                                 "admin commands work by DM only (admin channel disabled)."),
        "log_admin_same": "BRIDGE_ADMIN_CHANNEL must be different from MESH_CHANNEL ('{ch}').",
        "log_admin_ch_ignored": "[ADMIN-CH {uid}] ignored (not an admin)",
        "log_not_forwarded": " (bridge off, not forwarded)",
        "log_tg_old": "[TG] message older than 1 h, kept only for repeat: {name}: {text}",
        "log_tg_err": "[TG] error: {err}",
        "log_tg_conflict": ("[TG] 409 Conflict: another program is reading this bot's updates "
                            "(same token used twice). Retrying in 30 s."),
        "log_tg_unauth": "[TG] invalid token (401): check TG_TOKEN. Retrying in 5 min.",
        "log_tg_privacy": ("[TG] WARNING: the bot is not an administrator of the group and its privacy mode is ON: "
                           "Telegram only delivers commands and mentions to it, so normal group messages will NOT "
                           "reach the mesh. Make the bot an administrator, or disable privacy (BotFather: /setprivacy -> "
                           "Disable) and then remove and re-add the bot to the group."),
        "log_tg_wait": "[TG] rate limited by Telegram, waiting {s} s",
        "log_tg_send_fail": "[TG] send failed after {n} attempts: {err}",
        "log_tg_other_chat": "[TG] message from '{title}' ({type}) id {id}: not the configured chat, ignored",
        "log_repeat_mesh": "[REPEAT] mesh <- last {n} from Telegram and {ch} (excluding {uid})",
        "log_repeat_tg": "[REPEAT] Telegram <- last {n} from the mesh",
        "log_repeat_wait": "[REPEAT] {side}: ignored, asked less than {s} s ago",
        "log_dm_ignored": "[DM {uid}] ignored (not an admin, or not PKI-encrypted)",
        "log_bridge_set": "Bridge {state} (by admin {uid})",
        "log_truncated": "[TG>MESH] message truncated to {n} parts",
        "log_lost": "Connection to the node lost, exiting (systemd will restart the service)",
        "log_file_bad": "{file} unreadable, starting fresh: {err}",
        "log_error": "[ERROR] {err}",
    },
    "it": {
        "repeat_word": "ripeti",
        "repeat_usage": "Uso: {cmd} <numero>, es. {cmd} 3 (max {max}).",
        "repeat_empty": "Recupero: nessun messaggio da {src}.",
        "repeat_head": "Ultimi {n} da {src}:",
        "src_both": "Telegram e {ch}",
        "src_mesh": "Meshtastic",
        "tg_failed": "Telegram: invio fallito, messaggio non consegnato.",
        "non_text": "[contenuto non testuale]",
        "adm_status": ("Stato: bridge {state} ({ch} <-> Telegram), attivo da {up}. Mesh->TG {m2t}, "
                       "TG->mesh {t2m}, errori TG {err}. Bannati {ban}."),
        "adm_bridge": "Bridge: {state} ({ch} <-> Telegram).",
        "adm_ban": "Ban: {id} bannato.",
        "adm_unban": "Unban: {id} sbannato.",
        "adm_help": ("Admin: stato, bridge on|off, ban <id>, unban <id>, ripeti <n> (mie ultime n risposte qui), "
                     "log [n] (log del bot, dal più recente)."),
        "adm_repeat_none": "Ripeti: ancora nessuna risposta da ripetere.",
        "adm_log_head": "Log, dal più recente:",
        "adm_log_empty": "Log: vuoto.",
        "log_start": "Avvio del bridge Meshtastic-Telegram {ver} (lingua: italiano)",
        "log_cfg_missing": "Manca l'impostazione {key} in config.env: esegui ./setup.sh",
        "log_wait_dev": "Attendo il dispositivo {port}...",
        "log_no_dev": "Dispositivo {port} non trovato dopo {s} s",
        "log_connected": "Collegato al nodo {id} ({name}). Canali: {ch}",
        "log_no_channel": ("Canale mesh '{ch}' non presente sul nodo (disponibili: {avail}). "
                           "Correggi MESH_CHANNEL in config.env."),
        "log_bridge": "Bridge: canale mesh '{ch}' (indice {idx}) <-> chat Telegram {chat}, bridge {state}",
        "log_admins": "Admin: {ids} (solo DM cifrati PKI: {pki})",
        "log_admin_channel": "Canale admin: '{ch}' (indice {idx}), comandi accettati da: {who}",
        "who_any": "qualsiasi nodo sul canale",
        "log_no_admin_channel": ("Canale admin '{ch}' non presente sul nodo (disponibili: {avail}): "
                                 "canale admin disattivato, i comandi admin funzionano solo in DM."),
        "log_admin_same": "BRIDGE_ADMIN_CHANNEL deve essere diverso da MESH_CHANNEL ('{ch}').",
        "log_admin_ch_ignored": "[CANALE-ADMIN {uid}] ignorato (non è un admin)",
        "log_not_forwarded": " (bridge spento, non inoltrato)",
        "log_tg_old": "[TG] messaggio più vecchio di 1 h, conservato solo per ripeti: {name}: {text}",
        "log_tg_err": "[TG] errore: {err}",
        "log_tg_conflict": ("[TG] 409 Conflict: un altro programma legge gli aggiornamenti di questo bot "
                            "(stesso token usato due volte). Riprovo tra 30 s."),
        "log_tg_unauth": "[TG] token non valido (401): controlla TG_TOKEN. Riprovo tra 5 min.",
        "log_tg_privacy": ("[TG] ATTENZIONE: il bot non è amministratore del gruppo e la sua modalità privacy è ATTIVA: "
                           "Telegram gli consegna solo comandi e menzioni, quindi i messaggi normali del gruppo NON "
                           "arriveranno in mesh. Rendi il bot amministratore, oppure disattiva la privacy (BotFather: "
                           "/setprivacy -> Disable) e poi togli e riaggiungi il bot al gruppo."),
        "log_tg_wait": "[TG] limite di frequenza di Telegram, attendo {s} s",
        "log_tg_send_fail": "[TG] invio fallito dopo {n} tentativi: {err}",
        "log_tg_other_chat": "[TG] messaggio da '{title}' ({type}) id {id}: non è la chat configurata, ignorato",
        "log_repeat_mesh": "[RIPETI] mesh <- ultimi {n} da Telegram e {ch} (escluso {uid})",
        "log_repeat_tg": "[RIPETI] Telegram <- ultimi {n} dalla mesh",
        "log_repeat_wait": "[RIPETI] {side}: ignorato, richiesto da meno di {s} s",
        "log_dm_ignored": "[DM {uid}] ignorato (non è un admin, o non è cifrato PKI)",
        "log_bridge_set": "Bridge {state} (dall'admin {uid})",
        "log_truncated": "[TG>MESH] messaggio tagliato a {n} parti",
        "log_lost": "Connessione con il nodo persa, esco (systemd riavvia il servizio)",
        "log_file_bad": "{file} illeggibile, riparto da zero: {err}",
        "log_error": "[ERRORE] {err}",
    },
}

LANGS = {"en": "English", "it": "Italiano"}


class Tr:
    """t = Tr("it"); t("repeat_usage", cmd="!ripeti", max=20)"""

    def __init__(self, lang="en", table=STRINGS):
        self.table = table
        self.lang = lang if lang in table else "en"

    def __call__(self, _key, **kw):
        s = self.table[self.lang].get(_key, self.table["en"].get(_key, _key))
        return s.format(**kw) if kw else s
