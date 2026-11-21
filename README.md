# Matera Experience — sistema proprietario di prenotazioni

## Inclusi
- Homepage Matera Experience integrata con collegamenti a `/prenota` e `/operatori`
- Esperienze con modalità `request` (su richiesta) e `direct` (checkout Stripe)
- Dashboard operatori con login tramite password hash, inserimento esperienze e partenze, lista prenotazioni, conferma/rifiuto richieste
- Calendario delle partenze, posti residui e prenotazione con capienza verificata in transazione
- Blocco temporaneo dei posti per 35 minuti durante il pagamento
- Stripe Checkout server-side e webhook con firma verificata
- PostgreSQL per produzione; SQLite per sviluppo locale

## Avvio
1. Python 3.12+ e ambiente virtuale: `python -m venv .venv` e attivarlo.
2. `pip install -r requirements.txt`.
3. Configurare le variabili di `.env.example` nell'ambiente del sistema (Flask non carica automaticamente il file `.env`).
4. Eseguire `flask --app app init-demo` **solo in sviluppo**, con `DEMO_OPERATOR_PASSWORD` valorizzata.
5. Avviare `python app.py`.
6. Aprire `/` (sito), `/prenota` (prenotazioni), `/operatori` (dashboard).

## Pubblicazione
- Hosting Python/Docker con HTTPS e database PostgreSQL persistente.
- `gunicorn app:app --bind 0.0.0.0:$PORT`.
- Variabili `DATABASE_URL`, `SECRET_KEY`, `COOKIE_SECURE=1`, `PUBLIC_BASE_URL`.
- Per Stripe: `STRIPE_SECRET_KEY` e `STRIPE_WEBHOOK_SECRET`, webhook `POST /api/stripe/webhook`.
- Non usare password demo, chiavi test o SQLite effimero in produzione.

## API principali
- `GET /api/experiences`
- `GET /api/experiences/:id/slots`
- `POST /api/bookings` (slot_id, guests, name, email, privacy_ack)
- `POST /api/bookings/:id/checkout` (header X-Booking-Reference)
- `POST /api/stripe/webhook`
- `POST /api/operator/login`, `POST /api/operator/logout`, `GET /api/operator/me`
- `GET /api/operator/dashboard`
- `POST /api/operator/experiences`, `POST /api/operator/slots`
- `PATCH /api/operator/bookings/:id` (solo richieste pending_request)

## LIMITAZIONI — NON PRONTO PER PAGAMENTI REALI
Questo è un MVP tecnico, **non un prodotto production-ready**.
- I posti sono controllati in transazione e i blocchi di pagamento scadono dopo 35 minuti. Tuttavia **un pagamento tardivo può essere incassato quando i posti sono già stati liberati e rivenduti**: serve una gestione di riconciliazione, rimborsi e conferme con capienza atomica prima del lancio.
- Non sono presenti CSRF token sulle API operatori, rate limiting su login/booking, recupero password, verifica email, audit log, ruoli multipli, pannello superadmin, migrazioni, code email, notifiche, cancellazioni e rimborsi automatici, idempotenza del booking POST, integrazione Stripe Connect/payout operatori, fatturazione, test end-to-end e backup automatici.
- Gli orari nel database sono in UTC; la UI mostra Europe/Rome. Verificare fusi orari e ora legale.
- Le fotografie esterne non sono verificate una per una per licenza e affidabilità; sostituirle con asset verificati e corretta attribuzione.
- L'informativa privacy è ancora un segnaposto. Prima di acquisire dati reali, pubblicare privacy policy e termini contrattuali e definire retention, ruoli del trattamento, cancellazione/esportazione.
- Verificare attività turistiche regolamentate, obblighi di intermediazione, pacchetti turistici, assicurazioni e aspetti fiscali.
- Nessuna email automatica viene inviata: l'operatore deve consultare la dashboard.
- La homepage conserva schede editoriali dimostrative; il calendario `/prenota` usa invece il catalogo effettivo nel database.
