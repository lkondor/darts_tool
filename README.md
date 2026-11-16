# darts_stats_tool

Proiezioni Monte Carlo per il Mondiale PDC: H2H, handicap, totale set, totale
leg, 180 giocatore, 180 totali. Versione 0.3: scheletro funzionante su dati
sintetici, parser dello storico scritti su file reali e raccolta automatica.

## Stato

| Pezzo | Stato |
|---|---|
| Schema dati canonico (`darts/schema.py`) | pronto |
| Formato del Mondiale per turno (`darts/formats.py`) | pronto, regole 2025/26 da riconfermare |
| Modello del leg e calibrazione (`darts/leg_model.py`) | pronto, parametri di chiusura euristici |
| Simulatore match (`darts/simulator.py`) | pronto |
| Mercati e fair lines (`darts/markets.py`) | pronto |
| Profili giocatore (`darts/profiles.py`) | pronto, prior provvisorio |
| Fonte sintetica (`darts/adapters/synthetic.py`) | pronta (dati inventati) |
| Adapter Sportradar (`darts/adapters/sportradar.py`) | client e budget pronti, parser da scrivere sui payload reali |
| Parser darts1.de (`darts/adapters/darts1.py`) | testato sui PDF reali del Mondiale 2026 (ottavi-finale) e delle Players Championship Finals 2025 (formato a leg) |
| Parser globaldarts.de (`darts/adapters/globaldarts.py`) | testato sulle pagine reali UK Open 2024 ed European Tour 1 2026; nomi col solo cognome |
| Raccolta storico (`scripts/build_history.py`, workflow **Build history**) | pronta; pagine giornaliere del Mondiale non ancora viste |
| Riconciliazione nomi tra fonti | da fare sull'elenco prodotto dalla raccolta |
| Elo, dashboard Streamlit, tracking, bot | non iniziati |

## Come si usa

```
pip install -r requirements.txt
python -m pytest -q
python scripts/run_projections.py --source synthetic --sims 10000
```

Risultato in `output/projections.json` (dettaglio) e `output/projections.csv`
(una riga per match). Da GitHub: il workflow **Tests** esegue le stesse cose a
ogni push.

## Come funziona il modello

1. **Profilo**: per ogni giocatore media 3 freccette, 180 per leg, checkout %,
   pesati per recency (emivita 180 giorni) e tirati verso un prior quando i
   dati sono pochi.
2. **Calibrazione**: i parametri di visita (media di scoring, probabilita' di
   180) vengono cercati in modo che un leg simulato contro un avversario medio
   riproduca media e 180 per leg del profilo.
3. **Leg**: per ogni giocatore si genera un pool di 20.000 leg simulati visita
   per visita. Un leg tra A e B = un leg pescato da ciascun pool; vince chi
   chiude in meno visite, a parita' chi tira per primo.
4. **Match**: set al meglio dei 5 leg, tiro alternato per leg e per set, set
   decisivo con due leg di scarto e leg secco sul 5-5 (dal secondo turno).
   10.000 simulazioni, seed derivato dall'identita' del match.
5. **Mercati**: probabilita' e quote fair dalla distribuzione simulata; la
   linea fair e' la mezza linea con Over piu' vicino al 50%.

## Limiti noti (da chiudere con i dati reali)

- **Nessuna varianza di forma tra un match e l'altro**: ogni giocatore rende
  sempre al livello del profilo. Questo rende le probabilita' H2H troppo
  estreme a favore del favorito. Va aggiunta e calibrata con un backtest.
- **Zone di chiusura euristiche**: le probabilita' di checkout per fascia di
  resto sono stime, non misurate.
- **Chi tira per primo** non e' nei dati aggregati: nel match e' estratto
  50/50.
- **Prior unico** per tutti i giocatori senza storico.
- Nessun effetto palco (TV contro floor) e nessun Elo.

## Fonti dati

- `scripts/build_history.py` + workflow **Build history**: legge
  `config/history_sources.csv`, scarica e converte le pagine, scrive
  `data/history.json` e `data/build_report.json` (artifact `history`).

- `scripts/probe_sources.py` + workflow **Probe sources**: scarica le pagine
  candidate elencate in `config/probe_urls.txt` e le salva come artifact. I
  parser si scrivono su quei file.
- `scripts/sportradar_dump.py`: da lanciare quando la chiave trial e' attiva
  (segreto `SPORTRADAR_API_KEY`), salva i payload grezzi.
