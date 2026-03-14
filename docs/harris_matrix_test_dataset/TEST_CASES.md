# Harris Matrix Test Dataset - Test Cases

## Obiettivo

Questo dataset serve a validare:

- parsing relazioni stratigrafiche da `sequenza_fisica`
- costruzione grafo Harris Matrix
- gestione relazioni inverse
- cross-reference US/USM

## Scope dei Test

1. Relazioni dirette (`copre`, `taglia`, `riempie`, `si_appoggia_a`, `si_lega_a`, `uguale_a`).
2. Relazioni inverse (`coperto_da`, `tagliato_da`, `riempito_da`, `gli_si_appoggia`).
3. Riferimenti misti US/USM.
4. Casi invalidi e riferimenti mancanti.
5. Stabilita output grafo (nodes/edges/metadata).

## Criteri di Accettazione

- nessuna eccezione non gestita su input parziale
- output consistente per stesso input
- errori espliciti quando il dato e semanticamente invalido
- livello di accesso sito rispettato negli endpoint

## Endpoint Coperti (API v1)

- `/api/v1/harris-matrix/sites/{site_id}`
- `/api/v1/harris-matrix/sites/{site_id}/units/{unit_code}`
- `/api/v1/harris-matrix/sites/{site_id}/statistics`
- endpoint mapping/validation sotto `/api/v1/harris-matrix/...`

## Dataset Guidelines

- usare codici unita realistici e stabili
- separare casi "validi" da casi "corrotti"
- mantenere fixture piccole e leggibili
- includere almeno un caso con ciclo intenzionale

## Note

Per i dettagli implementativi consultare:

- `app/services/harris_matrix_service.py`
- `app/services/harris_matrix_validation_service.py`
- `app/routes/api/v1/harris_matrix.py`
