# Bridge Meshtastic ↔ Telegram

[English](README.md) · **Italiano**

Collega un canale Meshtastic a un gruppo Telegram, nei due sensi, tramite un nodo attaccato a
un computer Linux. Chi è in giro parla via radio, chi è a casa parla su Telegram, e tutti
leggono tutto.

```
 [nodi radio] ~~ LoRa ~~ [il tuo nodo] --USB-- [PC Linux: bridge.py] --internet-- [gruppo Telegram]
```

- **Ponte nei due sensi**: ogni messaggio di testo sul canale collegato va nel gruppo come
  `Alice: testo`; ogni messaggio del gruppo va sul canale come `TG Bob: testo`, diviso in
  messaggi da 200 caratteri con il contatore `[x/y]`.
- **Recupero dei messaggi persi**: chiunque sul canale scrive `!ripeti 5` e il bridge rimanda
  gli ultimi 5 messaggi di Telegram *e* del canale (esclusi i suoi): utile ai nodi ai margini
  della mesh. Nel gruppo, `/ripeti 5` restituisce gli ultimi 5 messaggi radio. Fino a 20 per
  lato, conservati anche dopo un riavvio.
- **Niente doppioni dopo un riavvio o un'interruzione**: la posizione su Telegram viene
  salvata; i messaggi del gruppo più vecchi di un'ora restano disponibili per `ripeti` ma non
  vengono riversati in radio.
- **Rispetto del tempo d'aria**: i messaggi Telegram lunghi sono tagliati a 4 messaggi radio
  (configurabile), le trasmissioni sono distanziate e Telegram ha un thread tutto suo, così una
  rete lenta non blocca mai la radio.
- **Controllo remoto con DM cifrato o canale admin**: `stato`, `bridge on|off`, `ban <id>`,
  `unban <id>`, `log` (il log del bot via radio) e `ripeti <n>` (rimanda le ultime risposte).
- **Italiano o inglese**: menu, log e messaggi del bridge; i comandi sono accettati in entrambe
  le lingue (`ripeti`/`repeat`, `stato`/`status`).
- **Configurazione guidata**: un menu trova la porta seriale, legge i canali dal nodo, verifica
  il token del bot, rileva il gruppo e installa un servizio systemd che parte all'avvio.

Niente MQTT, niente broker, nessuna connessione internet necessaria dal lato radio.

## Requisiti

- Un nodo Meshtastic (qualsiasi scheda) via USB, oppure via Wi-Fi/Ethernet (TCP 4403).
- Linux con systemd e Python 3.9+ (Debian, Ubuntu, Raspberry Pi OS...).
- Un bot Telegram e un gruppo.

## Avvio rapido

```bash
sudo apt install git python3-venv
git clone https://github.com/Giak88/mesh-telegram-bridge.git
cd mesh-telegram-bridge
./setup.sh
```

Al primo avvio chiede la lingua, poi guida in sette passi:

1. **Collegamento al nodo**: scegli la porta USB (prima i nomi stabili `/dev/serial/by-id/...`) o scrivi l'IP del nodo.
2. **Canale mesh**: l'elenco dei canali viene letto dal nodo; scegli quello da collegare.
   Usa un canale privato con la sua PSK, condiviso con le persone del gruppo: tutto ciò che vi
   si scrive finisce su Telegram.
3. **Bot Telegram**: crealo con [@BotFather](https://t.me/BotFather) (`/newbot`) e incolla il
   token (viene verificato subito). Aggiungi il bot al gruppo **come amministratore**, oppure
   disattiva la privacy (`/setprivacy` → Disable), altrimenti non può leggere il gruppo. La configurazione lo controlla e ti avvisa; il bridge scrive lo stesso avviso nel log all'avvio.
4. **Gruppo Telegram**: scrivi qualcosa nel gruppo e il bridge ne rileva l'id.
5. **Amministratori** (facoltativo): gli ID dei nodi che possono controllare il bridge via DM.
6. **Canale di amministrazione** (facoltativo): un canale privato per gli stessi comandi admin. Un canale
   si raggiunge più facilmente di un DM (crittografia più leggera, nessuno scambio di chiavi). La
   configurazione può usare un canale già presente sul nodo, oppure aggiungerne uno per te: con una nuova
   chiave casuale o con la chiave di un canale che usi già altrove. Quello che vi si scrive non va a Telegram.
7. **Prefisso dei comandi**: `!` di default (`!ripeti 3`); va bene anche una parola (`BOT` → `BOT ripeti 3`).

Infine propone di installare il servizio: da quel momento il bridge parte a ogni avvio.

Rilancia `./setup.sh` quando vuoi per il menu:

```
  1) Configurazione guidata
  2) Installa / aggiorna il servizio (avvio automatico)
  3) Servizio: stato, avvia, ferma, riavvia
  4) Log in tempo reale
  5) Prova: invia un messaggio a Telegram
  6) Mostra la configurazione
  7) Lingua / Language
  8) Disinstalla il servizio
```

Le stesse azioni si possono lanciare direttamente: `./setup.sh config|install|uninstall|status|logs|test`.

## Comandi

| Dove | Comando | Effetto |
|---|---|---|
| Canale collegato | `!ripeti <n>` (`!repeat <n>`) | Ultimi *n* messaggi di Telegram e del canale, esclusi i tuoi |
| Gruppo Telegram | `/ripeti <n>` o `!ripeti <n>` | Ultimi *n* messaggi del canale |
| DM al nodo del bridge, o sul canale admin (admin) | `stato` | Stato del bridge, tempo di attività, contatori |
| | `bridge on` / `bridge off` | Riprende o sospende l'inoltro (i messaggi restano disponibili per `ripeti`) |
| | `ban <id>` / `unban <id>` | Ignora un nodo sul canale collegato |
| | `ripeti <n>` (`repeat <n>`) | Rimanda le ultime *n* risposte del bridge in quel posto (DM o canale admin), ad es. una pagina persa |
| | `log [n]` (`botlog`) | Il log del bridge, dal più recente, in massimo 3 messaggi (*n* = righe massime) |

Di default i comandi admin sono accettati solo nei DM cifrati PKI (Meshtastic 2.5+), così
nessuno può spacciarsi per un admin falsificando l'ID del nodo.

**Canale admin** (`BRIDGE_ADMIN_CHANNEL`): gli stessi comandi funzionano anche su un canale privato
dedicato, più facile da raggiungere di un DM. I messaggi su un canale non sono firmati dal singolo nodo,
quindi **la chiave del canale è la password**: chi la possiede potrebbe falsificare l'ID di un admin.
Usa una chiave casuale (la configurazione la genera) e condividila solo con gli admin. Se `BRIDGE_ADMINS`
è impostato vengono ascoltati solo quei nodi; se è vuoto, chiunque sia sul canale. Le risposte vanno sul
canale, i messaggi sconosciuti non ricevono risposta e nulla arriva a Telegram. Non usare mai il canale
primario pubblico.

## Configurazione

`./setup.sh` scrive `config.env` (permessi 600, mai incluso nel repository). Ogni impostazione
è descritta in [`config.env.example`](config.env.example). Dopo una modifica a mano:
`sudo systemctl restart mesh-telegram-bridge`.

## Provarlo accanto a un altro programma che usa il nodo

Un nodo può essere usato da un solo programma alla volta. Per provare il bridge su un nodo già
usato da altro, ferma prima quel programma (`sudo systemctl stop <suo-servizio>`), poi
`./setup.sh` → 3 → Avvia. Usa un bot dedicato: due programmi che leggono lo stesso bot danno
`409 Conflict`. Per tornare indietro: menu 3 → Ferma, poi riavvia l'altro programma. La
disinstallazione (menu 8) rimuove solo il servizio di questo bridge.

## Log

```bash
journalctl -u mesh-telegram-bridge -f        # oppure ./setup.sh logs
```

```
Bridge: canale mesh 'MioGruppo' (indice 2) <-> chat Telegram -100..., bridge on
[MESH>TG] Alice: arrivo tra poco
[TG>MESH] Bob: ci vediamo al rifugio
[TX MioGruppo] TG Bob: ci vediamo al rifugio
[RIPETI] mesh <- ultimi 5 da Telegram e MioGruppo (escluso !1a2b3c4d)
```

## Problemi frequenti

| Sintomo | Causa / soluzione |
|---|---|
| I messaggi del gruppo non arrivano mai in radio | Il bot non legge il gruppo: rendilo amministratore, oppure `/setprivacy` → Disable e poi togli e riaggiungi il bot. |
| `409 Conflict` nel log | Un altro programma usa lo stesso token. Usa un bot dedicato. |
| `Canale mesh '...' non presente` e il servizio si ferma | Il nome in `MESH_CHANNEL` non coincide con quello sul nodo (controlla con l'opzione 1 del menu). |
| Errori sulla porta seriale | Il nodo è usato da un altro programma, o la porta è cambiata: usa il percorso `/dev/serial/by-id/...`. |
| L'id del gruppo è cambiato | Un gruppo diventato supergruppo cambia id: ripeti il passo 4. |

## Sviluppo

```bash
python3 -m unittest discover -s tests -t .
```

I test fanno girare i veri `bridge.py` e `setup_wizard.py` con un nodo simulato e un finto
server Telegram locale: non servono radio, token né permessi di root.

## Licenza

MIT, vedi [LICENSE](LICENSE). Idea e prove sul campo di Giak88; progettato e scritto con l'aiuto
di Claude (Anthropic).
