# Componente Upload Foto (`_photo_upload.html`)

## Scopo

Componente UI riusabile per upload foto con metadati archeologici e supporto TUS.

File correlati:

- Template: `app/templates/sites/photos/_photo_upload.html`
- JS orchestrazione: `app/static/js/photo_upload.js` e/o logica pagina `photos.js`
- Endpoint principali: API foto in `app/routes/api/v1/photos.py`

## Configurazione via `data-*`

Attributi principali disponibili nel markup:

- `data-upload-url`
- `data-site-id`
- `data-allowed-types`
- `data-max-file-size`
- `data-max-files`
- `data-success-callback`
- `data-error-callback`
- `data-custom-styles`
- `data-show-archaeological-fields`

## Funzionalita

- drag & drop multiplo
- preview file
- validazione lato client (tipo/dimensione/limiti)
- upload standard + opzione TUS
- metadati comuni applicati al batch

## Integrazione Tipica

1. includere il partial nel template pagina foto
2. passare `site.id` e upload URL corretto
3. collegare callback JS per refresh gallery

## Note di Compatibilita

- tenere coerenti i campi metadati del form con gli enum supportati lato backend
- verificare limiti server-side (dimensione massima e policy storage)
- in caso di errori upload, controllare risposta API e log applicativi

## Checklist di Modifica

- [ ] aggiornare template
- [ ] aggiornare JS client
- [ ] verificare endpoint API compatibili
- [ ] test manuale con upload singolo e multiplo
