# Sistema Voice Control - FastZoom

## Stato Attuale

Il sistema voice e disponibile tramite API v1 e supporta due modalita:

- HTTP planning/execution: `/api/v1/voice/*`
- WebSocket streaming assistant: `/api/v1/pipecat/*`

File principali:

- `app/routes/api/v1/voice.py`
- `app/routes/api/v1/pipecat.py`
- `app/services/voice_tools_registry.py`
- `app/services/voice_execute.py`
- `app/core/pipecat_settings.py`

## Architettura

1. L'input vocale/testuale viene interpretato in un comando strutturato.
2. Il comando viene validato contro una whitelist di tool.
3. L'esecuzione usa chiamate ASGI in-process agli endpoint gia esistenti.
4. Il risultato ritorna con eventuali azioni UI.

Questo approccio riduce il rischio di invocazioni arbitrarie e riusa autorizzazioni e validazioni API esistenti.

## Configurazione

Variabili principali (da `.env`):

- `PIPECAT_ENABLED`
- `PIPECAT_STT_PROVIDER` (`whisper` o `deepgram`)
- `PIPECAT_LLM_PROVIDER` (`ollama` o `openai`)
- `PIPECAT_TTS_PROVIDER` (`silero`, `openai`, `cartesia`)
- `OLLAMA_BASE_URL`, `OLLAMA_MODEL`
- `OPENAI_API_KEY` (se provider OpenAI)
- `DEEPGRAM_API_KEY` (se provider Deepgram)

## Endpoint Utili

- `GET /api/v1/pipecat/status`
- `POST /api/v1/voice/plan`
- `POST /api/v1/voice/execute`

## Sicurezza

- Tool invocabili solo se registrati in `voice_tools_registry.py`.
- Validazione argomenti prima dell'esecuzione.
- Possibile conferma utente per operazioni sensibili.
- Esecuzione con token utente corrente.

## Estendere il Sistema

1. Aggiungere tool nella whitelist (`VoiceTool`).
2. Definire parametri e livello di conferma.
3. Aggiornare eventuale prompt/system mapping.
4. Aggiungere test su parsing e autorizzazione.

## Troubleshooting Rapido

- Voice non disponibile: controllare `PIPECAT_ENABLED` e provider config.
- Piano comando fallisce: verificare modello LLM raggiungibile.
- Esecuzione fallisce: verificare token auth e permessi sito.
