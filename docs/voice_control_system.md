# Sistema di Controllo Vocale FastZoom

> **Versione:** 2.0  
> **Data:** 2026-01-17  
> **Autore:** FastZoom Team

## Indice

1. [Panoramica](#panoramica)
2. [Requisiti e Dipendenze](#requisiti-e-dipendenze)
3. [Struttura File](#struttura-file)
4. [Architettura](#architettura)
5. [Flusso di Esecuzione](#flusso-di-esecuzione)
6. [Componenti del Sistema](#componenti-del-sistema)
7. [Comandi Disponibili](#comandi-disponibili)
8. [Sicurezza](#sicurezza)
9. [Configurazione](#configurazione)
10. [Estensione](#estensione)
11. [Troubleshooting](#troubleshooting)

---

## Panoramica

FastZoom include un sistema di controllo vocale basato su AI **completamente on-premise** che permette agli utenti di navigare l'applicazione e eseguire operazioni tramite comandi vocali in italiano.

### Caratteristiche Principali

- ✅ **On-premise** - Nessun dato inviato a servizi cloud
- ✅ **Real-time** - Comunicazione WebSocket a bassa latenza
- ✅ **Italiano** - Ottimizzato per comandi in italiano
- ✅ **Sicuro** - Whitelist di operazioni, conferma per scritture
- ✅ **Estensibile** - Facile aggiunta di nuovi comandi

### Tecnologie Utilizzate

| Componente      | Tecnologia       | Versione | Descrizione                  |
| --------------- | ---------------- | -------- | ---------------------------- |
| **STT**         | Whisper (OpenAI) | latest   | Trascrizione audio → testo   |
| **LLM**         | Ollama           | v0.1.x   | Interprete comandi           |
| **Modello LLM** | qwen2.5:7b       | -        | Modello per function calling |
| **WebSocket**   | FastAPI          | 0.100+   | Comunicazione real-time      |
| **HTTP Client** | httpx            | 0.24+    | ASGI transport per API calls |
| **Frontend**    | Alpine.js        | 3.x      | Componente UI reattivo       |

---

## Requisiti e Dipendenze

### Dipendenze Python

Aggiungi al `requirements.txt`:

```txt
# Voice Control - Core
faster-whisper>=0.10.0      # STT engine (GPU accelerated)
ollama>=0.1.0               # LLM client
httpx>=0.24.0               # ASGI HTTP client

# Voice Control - Audio
numpy>=1.24.0               # Audio processing
soundfile>=0.12.0           # Audio file handling

# Already in project
fastapi>=0.100.0            # WebSocket support
pydantic>=2.0.0             # Schema validation
loguru>=0.7.0               # Logging
```

### Dipendenze Sistema

```bash
# Windows - CUDA (opzionale, per GPU acceleration)
# Scaricare da: https://developer.nvidia.com/cuda-downloads

# Ollama - Installare da https://ollama.ai
# Poi scaricare il modello:
ollama pull qwen2.5:7b

# FFmpeg (per audio processing)
# Windows: scaricare da https://ffmpeg.org/download.html
# Aggiungere a PATH
```

### Dipendenze Frontend

```html
<!-- Già incluso in base.html -->
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
```

### Verifica Installazione

```bash
# Verifica Ollama
ollama list
# Deve mostrare: qwen2.5:7b

# Verifica Whisper
python -c "from faster_whisper import WhisperModel; print('OK')"

# Verifica httpx
python -c "import httpx; print('OK')"
```

---

## Struttura File

```
FastZoom/
├── app/
│   ├── routes/
│   │   └── api/
│   │       └── v1/
│   │           ├── pipecat.py              # WebSocket endpoint principale
│   │           └── voice.py                # HTTP endpoints REST
│   │
│   ├── services/
│   │   ├── voice_tools_registry.py         # Whitelist 55 tools
│   │   ├── voice_execute.py                # Esecuzione via ASGI
│   │   ├── pipecat_local_services.py       # Whisper STT + Ollama LLM
│   │   ├── pipecat_service.py              # Session management
│   │   └── pipecat_functions.py            # Function handlers (legacy)
│   │
│   ├── schemas/
│   │   └── voice_commands.py               # Pydantic models
│   │
│   ├── static/
│   │   └── js/
│   │       └── voice_assistant.js          # Alpine.js component (794 lines)
│   │
│   ├── templates/
│   │   └── partials/
│   │       └── voice_assistant.html        # HTML template (284 lines)
│   │
│   └── core/
│       └── pipecat_settings.py             # Configurazione
│
├── docs/
│   └── voice_control_system.md             # Questo documento
│
└── tests/
    └── services/
        ├── test_voice_commands.py          # 17 test
        └── test_voice_tools_registry.py    # 34 test
```

---

## Architettura

### Diagramma di Flusso Completo

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              BROWSER                                        │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  voice_assistant.html                                                │   │
│  │  ├── Mic Button (toggle recording)                                  │   │
│  │  ├── Expand/Collapse Panel                                          │   │
│  │  ├── Commands Help Modal (?)                                        │   │
│  │  └── Messages History                                                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  voice_assistant.js (Alpine.js)                                      │   │
│  │  ├── MediaRecorder API → cattura audio                              │   │
│  │  ├── WebSocket client → ws://host/api/v1/pipecat/stream            │   │
│  │  ├── handleCommand() → esegue navigate/toast/focus                 │   │
│  │  └── showCommandsHelp → modal con comandi                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
└────────────────────────────────────┼────────────────────────────────────────┘
                                     │ WebSocket (binary audio + JSON)
                                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                              SERVER (FastAPI)                               │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  pipecat.py - WebSocket Handler                                      │   │
│  │  ├── @router.websocket("/stream")                                    │   │
│  │  ├── LocalWhisperSTT → trascrizione                                 │   │
│  │  ├── LocalOllamaLLM → interpretazione                               │   │
│  │  ├── _build_voice_system_prompt() → system prompt                   │   │
│  │  ├── _process_voice_input() → processing                            │   │
│  │  └── _parse_llm_json_response() → JSON extraction                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  voice_tools_registry.py - Whitelist                                 │   │
│  │  ├── VOICE_TOOLS_REGISTRY (55 tools)                                │   │
│  │  ├── READ_ONLY_TOOLS (33 tools)                                     │   │
│  │  ├── NAVIGATION_TOOLS (12 tools)                                    │   │
│  │  └── WRITE_TOOLS (10 tools)                                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  voice_execute.py - Execution Engine                                 │   │
│  │  ├── _get_asgi_client() → httpx.ASGITransport                       │   │
│  │  ├── execute_voice_command() → API call                             │   │
│  │  ├── _handle_navigation_tool() → UI navigation                      │   │
│  │  └── _build_ui_actions() → toast/navigate                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼ ASGI Transport (in-process)            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Existing API Endpoints                                              │   │
│  │  ├── /api/v1/sites/...                                              │   │
│  │  ├── /api/v1/photos/...                                             │   │
│  │  ├── /api/v1/us/...                                                 │   │
│  │  └── etc.                                                            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

### Comunicazione Frontend ↔ Backend

```
Frontend                          Backend
   │                                 │
   │─── WebSocket CONNECT ──────────>│
   │<── {"type": "ready"} ──────────│
   │                                 │
   │─── Audio Bytes ────────────────>│ Whisper STT
   │<── {"type": "transcript"} ─────│
   │                                 │ Ollama LLM
   │<── {"type": "command"} ────────│
   │<── {"type": "response"} ───────│
   │                                 │
```

---

## Flusso di Esecuzione

### Step 1: Inizializzazione WebSocket

```javascript
// voice_assistant.js
async connect() {
    this.websocket = new WebSocket(this.wsUrl);

    this.websocket.onopen = async () => {
        // Aspetta che sia veramente aperto
        await this.waitForConnection();

        // Invia messaggio init con contesto sito
        this.websocket.send(JSON.stringify({
            type: 'init',
            site_id: this.getSiteId()
        }));
    };
}
```

### Step 2: Cattura Audio

```javascript
// voice_assistant.js
async startRecording() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });

    this.mediaRecorder.ondataavailable = (event) => {
        if (this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(event.data);  // Binary audio
        }
    };
}
```

### Step 3: Trascrizione (Server)

```python
# pipecat.py
from app.services.pipecat_local_services import LocalWhisperSTT

stt = LocalWhisperSTT(model="medium", device="auto", language="it")

# Aggiungi audio al buffer
ready = stt.add_audio(audio_data)

if ready:
    result = await stt.transcribe()
    # result.text = "vai ai siti"
```

### Step 4: Interpretazione LLM

```python
# pipecat.py
llm = LocalOllamaLLM(model="qwen2.5:7b")

# System prompt forza output JSON
messages_history = [{
    "role": "system", 
    "content": _build_voice_system_prompt(tool_descriptions, site_id)
}]

messages_history.append({"role": "user", "content": "vai ai siti"})
response = await llm.simple_chat(messages_history)

# response = '{"action_type": "navigate", "tool": "nav_goto_sites", "explain": "Vado ai siti"}'
```

### Step 5: Parsing Risposta

```python
# pipecat.py
def _parse_llm_json_response(response: str) -> Optional[dict]:
    import json
    import re

    # Try direct parse
    try:
        return json.loads(response.strip())
    except:
        pass

    # Try to find JSON in response
    json_match = re.search(r'\{[^{}]*\}', response)
    if json_match:
        try:
            return json.loads(json_match.group())
        except:
            pass

    return None
```

### Step 6: Esecuzione Comando

```python
# pipecat.py → _process_voice_input()
if action_type == "navigate" and tool_name:
    tool = get_tool(tool_name)
    if tool and tool.category == ToolCategory.NAVIGATION:
        result = _handle_navigation_tool(tool, args, site_id)

        # Invia UI action
        await websocket.send_json({
            "type": "command",
            "action": "navigate",
            "url": "/"
        })
```

### Step 7: Esecuzione Frontend

```javascript
// voice_assistant.js
handleCommand(data) {
    switch(data.action) {
        case 'navigate':
            window.location.href = data.url;
            break;
        case 'toast':
            this.showToast(data.message, data.level);
            break;
        case 'focus':
            document.querySelector(data.target)?.focus();
            break;
    }
}
```

---

## Componenti del Sistema

### 1. pipecat.py

**Percorso:** `app/routes/api/v1/pipecat.py`

WebSocket endpoint principale per la comunicazione real-time.

```python
# Endpoint principale
@router.websocket("/stream")
async def voice_stream(websocket: WebSocket, token: Optional[str] = None):
    ...

# Helper functions
def _build_voice_system_prompt(tool_descriptions: list, site_id: Optional[str]) -> str:
    """Costruisce il system prompt per forzare output JSON."""
    ...

async def _process_voice_input(websocket, llm, messages_history, text, site_id) -> None:
    """Processa input vocale/testuale con sistema strutturato."""
    ...

def _parse_llm_json_response(response: str) -> Optional[dict]:
    """Estrae JSON dalla risposta LLM."""
    ...
```

### 2. voice_tools_registry.py

**Percorso:** `app/services/voice_tools_registry.py`

Contiene il **whitelist** di tutte le operazioni vocali permesse.

```python
# Struttura di un tool
@dataclass
class VoiceTool:
    operation_id: str           # "nav_goto_sites"
    http_method: str            # "GET"
    path_template: str          # "/_nav/sites"
    description: str            # "Vai alla lista dei siti"
    category: ToolCategory      # ToolCategory.NAVIGATION
    requires_confirmation: bool # False
    read_only: bool             # True
    site_scoped: bool           # False
    path_params: List[str]      # []
    query_params: List[str]     # []
    has_body: bool              # False
    permission: Optional[str]   # None

# Registri
READ_ONLY_TOOLS: Dict[str, VoiceTool]    # 33 tools
NAVIGATION_TOOLS: Dict[str, VoiceTool]   # 12 tools
WRITE_TOOLS: Dict[str, VoiceTool]        # 10 tools
VOICE_TOOLS_REGISTRY: Dict[str, VoiceTool]  # Combined: 55 tools

# Funzioni utili
def get_tool(operation_id: str) -> Optional[VoiceTool]
def list_tools(category=None, read_only=None, site_scoped=None) -> List[VoiceTool]
def is_tool_whitelisted(operation_id: str) -> bool
def validate_tool_args(operation_id: str, args: dict) -> tuple[bool, Optional[str]]
def build_path(operation_id: str, args: dict) -> Optional[str]
def log_voice_execution(...) -> None
```

### 3. voice_execute.py

**Percorso:** `app/services/voice_execute.py`

Esegue i comandi tramite ASGI transport (chiamate in-process).

```python
# ASGI Client
def _get_asgi_client() -> httpx.AsyncClient:
    from app.app import app as fastapi_app
    transport = httpx.ASGITransport(app=fastapi_app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")

# Esecuzione comando
async def execute_voice_command(
    command: VoiceCommand,
    user: User,
    site_id: Optional[UUID],
    auth_token: str,
) -> VoiceCommandResult:
    ...

# Navigazione
def _handle_navigation_tool(
    tool: VoiceTool,
    args: Dict[str, Any],
    site_id: Optional[UUID],
) -> VoiceCommandResult:
    ...

# UI Actions
NAVIGATION_URL_MAP: Dict[str, str] = {
    "nav_goto_sites": "/",
    "nav_goto_giornale": "/giornale",
    "nav_goto_cantieri": "/cantieri",
    ...
}

API_TOOLS_WITH_NAVIGATION: Dict[str, str] = {
    "get_site_photos": "/photos",
    "v1_list_us": "/us",
    ...
}
```

### 4. pipecat_local_services.py

**Percorso:** `app/services/pipecat_local_services.py`

Servizi AI locali (Whisper STT + Ollama LLM).

```python
class LocalWhisperSTT:
    """Speech-to-Text using faster-whisper."""

    def __init__(self, model="medium", device="auto", language="it"):
        self.model_name = model
        self.device = device
        self.language = language

    async def ensure_model_loaded(self) -> bool:
        """Carica modello Whisper (lazy loading)."""
        ...

    def add_audio(self, audio_bytes: bytes) -> bool:
        """Aggiunge audio al buffer. Ritorna True se pronto."""
        ...

    async def transcribe(self) -> TranscriptionResult:
        """Trascrive audio bufferizzato."""
        ...


class LocalOllamaLLM:
    """LLM using Ollama."""

    def __init__(self, model="qwen2.5:7b"):
        self.model = model

    async def simple_chat(self, messages: list) -> str:
        """Chat semplice, ritorna testo."""
        ...

    async def chat_with_functions(self, text: str, functions: list) -> dict:
        """Chat con function calling."""
        ...
```

### 5. voice_commands.py (Schemas)

**Percorso:** `app/schemas/voice_commands.py`

Pydantic models per validazione.

```python
class CommandIntent(str, Enum):
    API_CALL = "api_call"
    UI_ACTION = "ui_action"
    CLARIFY = "clarify"

class UIActionType(str, Enum):
    NAVIGATE = "navigate"
    TOAST = "toast"
    FOCUS = "focus"
    SET_FIELD = "set_field"
    OPEN_MODAL = "open_modal"
    CLOSE_MODAL = "close_modal"

class UIAction(BaseModel):
    action: UIActionType
    url: Optional[str] = None
    message: Optional[str] = None
    level: Optional[str] = None  # success, error, warning, info
    target: Optional[str] = None

class VoiceCommand(BaseModel):
    intent: CommandIntent
    tool: Optional[str] = None
    args: Dict[str, Any] = {}
    explain: str = ""

class VoiceCommandResult(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    error: Optional[str] = None
    ui_actions: Optional[List[UIAction]] = None
```

### 6. voice_assistant.js

**Percorso:** `app/static/js/voice_assistant.js`

Componente Alpine.js per l'interfaccia utente.

```javascript
Alpine.data('voiceAssistant', () => ({
    // State
    isOpen: false,
    isConnected: false,
    isListening: false,
    isProcessing: false,
    showCommandsHelp: false,

    // WebSocket
    websocket: null,
    wsUrl: `${protocol}//${host}/api/v1/pipecat/stream`,

    // Audio
    mediaRecorder: null,
    audioChunks: [],

    // UI
    messages: [],
    transcript: '',

    // Methods
    init() { ... },
    connect() { ... },
    toggleListening() { ... },
    startRecording() { ... },
    stopRecording() { ... },
    handleMessage(event) { ... },
    handleCommand(data) { ... },
    sendText(text) { ... },
}));
```

### 7. voice_assistant.html

**Percorso:** `app/templates/partials/voice_assistant.html`

Template HTML del componente.

```html
<div x-data="voiceAssistant()" x-cloak class="relative">
    <!-- Mic Button -->
    <button @click="toggleListening()">...</button>

    <!-- Expand Button -->
    <button @click="isOpen = !isOpen">...</button>

    <!-- Help Button (?) -->
    <button @click="showCommandsHelp = !showCommandsHelp">...</button>

    <!-- Commands Help Modal -->
    <div x-show="showCommandsHelp">...</div>

    <!-- Messages Panel -->
    <div x-show="isOpen">...</div>
</div>
```

---

## Comandi Disponibili

### Navigazione Globale (12 tools)

| Comando Vocale       | Tool                | URL Target     |
| -------------------- | ------------------- | -------------- |
| "Vai ai siti"        | `nav_goto_sites`    | `/`            |
| "Vai al giornale"    | `nav_goto_giornale` | `/giornale`    |
| "Vai ai cantieri"    | `nav_goto_cantieri` | `/cantieri`    |
| "Vai alle analisi"   | `nav_goto_analisi`  | `/analisi`     |
| "Vai al sito {nome}" | `nav_goto_site`     | Cerca e naviga |
| "Aggiorna"           | `nav_refresh`       | Reload pagina  |
| "Torna indietro"     | `nav_go_back`       | Browser back   |

### Navigazione Sito (richiede site_id)

| Comando Vocale       | Tool                 | URL Target                      |
| -------------------- | -------------------- | ------------------------------- |
| "Vai alle foto"      | `nav_goto_photos`    | `/view/{site_id}/photos`        |
| "Vai alle US"        | `nav_goto_us`        | `/view/{site_id}/us`            |
| "Vai alla Harris"    | `nav_goto_harris`    | `/view/{site_id}/harris-matrix` |
| "Vai ai documenti"   | `nav_goto_documents` | `/view/{site_id}/documents`     |
| "Vai alla dashboard" | `nav_goto_dashboard` | `/view/{site_id}/dashboard`     |

### API Read-Only (33 tools)

| Comando Vocale            | Tool                        | Descrizione          |
| ------------------------- | --------------------------- | -------------------- |
| "Mostra i siti"           | `v1_get_sites_list`         | Lista siti           |
| "Mostra statistiche"      | `v1_get_overview_stats`     | Stats generali       |
| "Mostra attività recenti" | `v1_get_recent_activities`  | Attività             |
| "Elenca le foto"          | `get_site_photos`           | Foto del sito        |
| "Cerca foto {query}"      | `search_photos_by_metadata` | Ricerca foto         |
| "Elenca documenti"        | `v1_get_site_documents`     | Documenti            |
| "Elenca US"               | `v1_list_us`                | Unità stratigrafiche |
| "Mostra Harris Matrix"    | `v1_generate_harris_matrix` | Genera matrice       |

### API Write (10 tools, richiedono conferma)

| Comando Vocale         | Tool                           | Note             |
| ---------------------- | ------------------------------ | ---------------- |
| "Aggiorna US {id}"     | `v1_update_us`                 | ⚠️ Conferma      |
| "Aggiorna USM {id}"    | `v1_update_usm`                | ⚠️ Conferma      |
| "Salva layout matrice" | `v1_save_harris_matrix_layout` | ⚠️ Conferma      |
| "Valida la matrice"    | `v1_validate_harris_matrix`    | Solo validazione |

---

## Sicurezza

### 1. Whitelist

Solo le operazioni in `VOICE_TOOLS_REGISTRY` sono eseguibili:

```python
if not is_tool_whitelisted(tool_name):
    return VoiceCommandResult(success=False, error="Tool not allowed")
```

### 2. Metodi HTTP Limitati

```python
# voice_execute.py
if tool.http_method not in ("GET", "POST", "PUT"):
    return VoiceCommandResult(
        success=False,
        error=f"HTTP method '{tool.http_method}' not allowed"
    )
```

**DELETE è esplicitamente bloccato.**

### 3. Conferma per Scritture

```python
# voice.py
if tool.requires_confirmation and not request.confirmed:
    return VoiceCommandResult(
        success=False,
        error="Confirmation required",
        message=f"Conferma richiesta: {command.explain}"
    )
```

### 4. Autorizzazione

L'auth token viene inoltrato a tutti gli endpoint:

```python
# voice_execute.py
headers = {
    "Authorization": f"Bearer {auth_token}",
    "Content-Type": "application/json",
}
```

### 5. Audit Log

```python
log_voice_execution(
    user_id=current_user.id,
    site_id=site_id,
    transcript=command.explain,
    operation_id=command.tool,
    args=command.args,
    success=result.success,
    error=result.error
)
```

---

## Configurazione

### pipecat_settings.py

```python
# app/core/pipecat_settings.py
class PipecatSettings:
    ENABLED: bool = True
    LANGUAGE: str = "it"

    # Whisper
    WHISPER_MODEL: str = "medium"  # tiny, base, small, medium, large
    WHISPER_DEVICE: str = "auto"   # auto, cpu, cuda

    # Ollama
    OLLAMA_MODEL: str = "qwen2.5:7b"
    OLLAMA_HOST: str = "http://localhost:11434"

    # WebSocket
    MAX_SESSIONS: int = 10
    SESSION_TIMEOUT: int = 300  # seconds

pipecat_settings = PipecatSettings()
```

### Variabili Ambiente

```bash
# .env
PIPECAT_ENABLED=true
WHISPER_MODEL=medium
WHISPER_DEVICE=cuda  # o cpu
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_HOST=http://localhost:11434
```

---

## Estensione

### Aggiungere un Nuovo Tool di Navigazione

1. **Aggiungi a `voice_tools_registry.py`:**

```python
# In NAVIGATION_TOOLS
"nav_goto_my_page": VoiceTool(
    operation_id="nav_goto_my_page",
    http_method="GET",
    path_template="/_nav/my-page",
    description="Vai alla mia pagina",
    category=ToolCategory.NAVIGATION,
    site_scoped=False,
),
```

2. **Aggiungi URL mapping in `voice_execute.py`:**

```python
NAVIGATION_URL_MAP["nav_goto_my_page"] = "/my-page"
```

3. **Aggiorna system prompt in `pipecat.py`:**

```python
# In _build_voice_system_prompt, sezione MAPPATURA
"vai alla mia pagina" → {"action_type": "navigate", "tool": "nav_goto_my_page"}
```

### Aggiungere un Nuovo Tool API

1. **Aggiungi a `voice_tools_registry.py`:**

```python
# In READ_ONLY_TOOLS o WRITE_TOOLS
"v1_my_endpoint": VoiceTool(
    operation_id="v1_my_endpoint",
    http_method="GET",
    path_template="/api/v1/my-endpoint/{id}",
    description="Ottiene qualcosa",
    category=ToolCategory.DASHBOARD,
    path_params=["id"],
    query_params=["limit"],
    site_scoped=True,
),
```

2. **Se deve navigare dopo esecuzione, aggiungi:**

```python
# In voice_execute.py
API_TOOLS_WITH_NAVIGATION["v1_my_endpoint"] = "/my-page"
```

---

## Troubleshooting

### LLM risponde con testo invece di JSON

**Sintomo:** L'assistente risponde "Mi dispiace, non posso..." invece di eseguire il comando.

**Cause e Soluzioni:**

1. **Modello non supporta bene le istruzioni**
   
   - Prova un modello più grande: `ollama pull qwen2.5:14b`
   - Modifica `OLLAMA_MODEL` in settings

2. **System prompt non abbastanza forte**
   
   - Aggiungi più esempi nella sezione `MAPPATURA COMANDI`
   - Rinforza le regole

### WebSocket si disconnette

**Verifica:**

```bash
# Ollama in esecuzione?
curl http://localhost:11434/api/tags

# Whisper model caricato?
python -c "from app.services.pipecat_local_services import LocalWhisperSTT; s = LocalWhisperSTT(); print('OK')"
```

### Comando non riconosciuto

1. Verifica che il tool sia in `VOICE_TOOLS_REGISTRY`
2. Controlla i log: `logger.info("Voice execute: ...")`
3. Testa con input testuale invece di vocale

### Audio non catturato

**Browser:**

- Verifica permessi microfono
- HTTPS richiesto in produzione
- Controlla console JS per errori

---

## Test

### Eseguire i Test

```bash
# Test voice tools registry
pytest tests/services/test_voice_tools_registry.py -v

# Test voice commands
pytest tests/services/test_voice_commands.py -v

# Tutti i test
pytest tests/ -v --tb=short
```

### Test Manuali

1. Apri browser su `http://localhost:8000`
2. Clicca il pulsante microfono
3. Dì "vai ai siti"
4. Verifica navigazione a `/`

---

## Changelog

| Versione | Data       | Modifiche                                                         |
| -------- | ---------- | ----------------------------------------------------------------- |
| 2.0      | 2026-01-17 | Sistema strutturato JSON, ASGI transport, rimosso vecchio sistema |
| 1.5      | 2026-01-16 | Aggiunto help modal, navigation tools                             |
| 1.0      | 2026-01-15 | Implementazione iniziale                                          |
