# Pubblicazione Matera Experience — ambiente di prova

## Stato
Il pacchetto contiene il sito, backend, dashboard operatore, API, Stripe Checkout e webhook. **Non è stato pubblicato online**: è necessario autorizzare un repository Git e un account hosting. La sintassi Python è stata verificata, ma i test di integrazione non sono stati eseguiti perché le dipendenze non sono disponibili in questo ambiente.

## Pubblicazione su Render
1. Crea un repository GitHub privato e carica i file di questa cartella.
2. Apri Render, scegli New > Blueprint e seleziona il repository.
3. Controlla i costi dei piani prima di confermare. Il blueprint usa un servizio web e PostgreSQL persistente.
4. Imposta `PUBLIC_BASE_URL` all'indirizzo HTTPS effettivo del sito, senza slash finale.
5. Lascia vuote le chiavi Stripe fino a quando non vuoi testare i pagamenti in modalità test.
6. Dopo il deploy apri `/health`, `/`, `/prenota`, `/operatori`.
7. Imposta `DEMO_OPERATOR_EMAIL` e `DEMO_OPERATOR_PASSWORD` come variabili d'ambiente ed esegui `flask --app app init-demo` nella shell del servizio, solo in ambiente di prova.

## Test pagamenti Stripe
1. Usa chiavi di **test** Stripe e configura `STRIPE_SECRET_KEY`.
2. Crea un endpoint webhook `https://TUO-DOMINIO/api/stripe/webhook`.
3. Abilita gli eventi `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.expired`.
4. Imposta `STRIPE_WEBHOOK_SECRET` dal segreto di firma.
5. Prova pagamenti riusciti, rifiutati e scaduti usando le carte di test ufficiali.

## Blocchi prima della produzione
Mancano ancora migrazioni DB, backup e ripristino verificati, rate limiting, CSRF, gestione dei webhook concorrenti e pagamenti tardivi, email automatiche, cancellazioni/rimborsi, test di concorrenza PostgreSQL, test end-to-end, informativa privacy e termini, verifica autorizzazioni turistiche e licenze foto. **Non aprire il sito ai pagamenti reali prima di completare questi punti.**
