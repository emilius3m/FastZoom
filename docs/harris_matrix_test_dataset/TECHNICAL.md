# Harris Matrix Test Dataset - Technical Documentation

This document provides comprehensive technical specifications for the Harris Matrix system implementation in FastZoom, including database schemas, API endpoints, data structures, and architectural details.

## Database Schema

### Core Tables

#### 1. `unita_stratigrafica` (US - Unità Stratigrafiche)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Unique identifier |
| `id_sito` | UUID | FOREIGN KEY → `archaeological_sites.id` | Site reference |
| `codice_us` | VARCHAR(20) | UNIQUE, NOT NULL | Unit code (US001-US999) |
| `definizione` | TEXT | NOT NULL | Archaeological definition |
| `descrizione` | TEXT | Extended description of the unit |
| `interpretazione` | TEXT | Archaeological interpretation |
| `datazione` | TEXT | Dating information |
| `periodo` | TEXT | Chronological period |
| `sequenza_fisica` | JSONB | NOT NULL DEFAULT '{}' | Stratigraphic relationships |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Creation timestamp |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | Last update timestamp |
| `created_by` | UUID | FOREIGN KEY → `users.id` | Creator user |
| `updated_by` | UUID | FOREIGN KEY → `users.id` | Last updater user |

**Example Record:**
```sql
INSERT INTO unita_stratigrafica (
    id, id_sito, codice_us, definizione, descrizione, 
    interpretazione, datazione, periodo, sequenza_fisica
) VALUES (
    'eb8d88e1-74e3-46d3-8e86-81f926c01cab',
    'site-uuid-here',
    'US001',
    'Modern surface soil',
    'Modern surface layer with recent contamination and organic material.',
    'Contemporary contamination from recent activities',
    'Contemporanea',
    'Contemporanea',
    '{
        "copre": ["US002", "US003", "USM174(usm)", "USM175(usm)"],
        "taglia": ["US005"],
        "note": "Surface layer, removed in first phase"
    }'
);
```

#### 2. `unita_stratigrafica_muraria` (USM - Unità Stratigrafiche Murarie)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Unique identifier |
| `id_sito` | UUID | FOREIGN KEY → `archaeological_sites.id` | Site reference |
| `codice_us` | VARCHAR(20) | UNIQUE, NOT NULL | Unit code (USM001-USM999) |
| `definizione` | TEXT | NOT NULL | Structural definition |
| `descrizione` | TEXT | Extended description |
| `interpretazione` | TEXT | Archaeological interpretation |
| `tecnica_edilizia` | TEXT | Construction technique |
| `datazione` | TEXT | Dating information |
| `periodo` | TEXT | Chronological period |
| `sequenza_fisica` | JSONB | NOT NULL DEFAULT '{}' | Stratigraphic relationships |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Creation timestamp |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | Last update timestamp |
| `created_by` | UUID | FOREIGN KEY → `users.id` | Creator user |
| `updated_by` | UUID | FOREIGN KEY → `users.id` | Last updater user |

**Example Record:**
```sql
INSERT INTO unita_stratigrafica_muraria (
    id, id_sito, codice_us, definizione, descrizione,
    interpretazione, tecnica_edilizia, datazione, periodo, sequenza_fisica
) VALUES (
    'eeeedd3c-eda3-4bf3-b47d-749a971b22ba',
    'site-uuid-here',
    'USM174',
    'Perimeter wall',
    'Perimeter wall constructed with regular stone blocks, shows evidence of multiple construction phases.',
    'Main structural element, likely perimeter wall or dividing wall',
    'Opus incertum',
    'II secolo d.C.',
    'Romano imperiale',
    '{
        "si_lega_a": ["US002(usm)", "USM175(usm)"],
        "gli_si_appoggia": ["US005(usm)"],
        "note": "Well-preserved masonry, shows multiple construction phases"
    }'
);
```

### Supporting Tables

#### 3. `archaeological_sites`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Site identifier |
| `nome_sito` | VARCHAR(255) | NOT NULL | Site name |
| `codice_sito` | VARCHAR(50) | UNIQUE | Site code |
| `descrizione` | TEXT | Site description |
| `periodo` | TEXT | Primary period |
| `tipo_sito` | VARCHAR(100) | Site type (e.g., 'abitato') |
| ... | ... | ... | Additional site metadata |

## JSON Structure: `sequenza_fisica`

The `sequenza_fisica` field stores stratigraphic relationships in JSONB format:

### Complete Relationship Schema

```json
{
  "copre": ["US002", "US003", "USM001(usm)"],
  "coperto_da": ["US999"],
  "taglia": ["US004"],
  "tagliato_da": ["US998"],
  "uguale_a": ["US005"],
  "si_appoggia_a": ["USM002(usm)"],
  "gli_si_appoggia": ["US006"],
  "si_lega_a": ["USM003(usm)"],
  "riempie": ["US007"],
  "riempito_da": ["US008"],
  "note": "Additional descriptive notes about relationships"
}
```

### Relationship Types Reference

| Field | Direction | Description | Example |
|-------|-----------|-------------|---------|
| `copre` | ↓ | Unit covers units below | Topsoil covering foundation |
| `coperto_da` | ↑ | Unit is covered by units above | Foundation covered by topsoil |
| `taglia` | ↓ | Unit cuts through units below | Pit cutting through layers |
| `tagliato_da` | ↑ | Unit is cut by units above | Layer cut by pit |
| `uguale_a` | ↔ | Units are contemporaneous | Two phases of same construction |
| `si_appoggia_a` | ↓ | Unit rests on unit below | Wall on foundation |
| `gli_si_appoggia` | ↑ | Other units rest on this unit | Foundation supporting walls |
| `si_lega_a` | ↔ | Units are structurally bonded | Connected walls |
| `riempie` | ↓ | Unit fills another unit | Backfill in cut |
| `riempito_da` | ↑ | Unit is filled by other unit | Cut filled with material |
| `note` | N/A | Additional descriptive information | Notes on interpretation |

### Cross-Reference Format

Cross-references between US and USM units use the format `USMXXX(usm)`:

```json
{
  "si_lega_a": ["USM174(usm)"],
  "copre": ["US002", "USM175(usm)"],
  "si_appoggia_a": ["USM175(usm)", "US004"]
}
```

**Parsing Rules:**
- `US001` → US unit (type: 'us')
- `USM001(usm)` → USM unit (type: 'usm')
- Invalid formats are ignored with warnings

### Data Validation

```python
# JSON Schema validation example
schema = {
    "type": "object",
    "properties": {
        "copre": {"type": "array", "items": {"type": "string"}},
        "taglia": {"type": "array", "items": {"type": "string"}},
        "uguale_a": {"type": "array", "items": {"type": "string"}},
        "note": {"type": "string"}
    },
    "additionalProperties": False
}
```

## API Endpoints

### Authentication

All Harris Matrix endpoints require JWT authentication:

```bash
# Login endpoint
POST /api/v1/auth/login/json
Content-Type: application/json

{
  "username": "user@example.com",
  "password": "user@example.com"
}

# Response
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {...}
}
```

### Harris Matrix Endpoints

#### 1. Get Complete Matrix

```http
GET /api/v1/harris-matrix/sites/{site_id}
Authorization: Bearer {access_token}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "site_id": "site-uuid",
    "matrix": {
      "nodes": [
        {
          "id": "US001",
          "label": "US001 - Modern surface soil",
          "type": "us",
          "level": 0,
          "data": {
            "definizione": "Modern surface soil",
            "interpretazione": "Contemporary contamination",
            "datazione": "Contemporanea"
          }
        },
        {
          "id": "USM174",
          "label": "USM174 - Perimeter wall",
          "type": "usm",
          "level": 0,
          "data": {
            "definizione": "Perimeter wall",
            "tecnica_edilizia": "Opus incertum",
            "datazione": "II secolo d.C."
          }
        }
      ],
      "edges": [
        {
          "source": "US001",
          "target": "US002",
          "type": "copre",
          "label": "copre"
        },
        {
          "source": "US001",
          "target": "USM174",
          "type": "copre",
          "label": "copre"
        }
      ]
    }
  }
}
```

**Node Properties:**
- `id`: Unit code
- `label`: Display label with definition
- `type`: 'us' or 'usm'
- `level`: Chronological level (0 = most recent)
- `data`: Unit metadata

**Edge Properties:**
- `source`: Source unit code
- `target`: Target unit code
- `type`: Relationship type
- `label`: Display label

#### 2. Get Matrix Statistics

```http
GET /api/v1/harris-matrix/sites/{site_id}/statistics
Authorization: Bearer {access_token}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "site_id": "site-uuid",
    "statistics": {
      "total_units": 12,
      "us_count": 10,
      "usm_count": 2,
      "total_relationships": 29,
      "chronological_levels": 5,
      "relationship_types": {
        "copre": 8,
        "taglia": 3,
        "uguale_a": 2,
        "si_appoggia_a": 6,
        "si_lega_a": 2,
        "riempie": 2
      },
      "levels": {
        "0": ["US001", "USM174", "USM175"],
        "1": ["US002", "US003", "US005"],
        "2": ["US004", "US006", "US007"],
        "3": ["US008", "US009"],
        "4": ["US010"]
      }
    }
  }
}
```

#### 3. Get Unit Details

```http
GET /api/v1/harris-matrix/sites/{site_id}/units/{unit_code}
Authorization: Bearer {access_token}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "unit": {
      "id": "us-uuid",
      "codice_us": "US001",
      "definizione": "Modern surface soil",
      "descrizione": "Modern surface layer with recent contamination...",
      "interpretazione": "Contemporary contamination from recent activities",
      "datazione": "Contemporanea",
      "periodo": "Contemporanea",
      "sequenza_fisica": {
        "copre": ["US002", "US003", "USM174(usm)", "USM175(usm)"],
        "taglia": ["US005"]
      }
    },
    "relationships": [
      {
        "type": "copre",
        "target": "US002",
        "target_type": "us",
        "relationship": "US001 copre US002"
      }
    ],
    "position_in_matrix": {
      "level": 0,
      "is_earliest": false,
      "is_latest": true,
      "connected_units": 4
    }
  }
}
```

### Error Responses

All endpoints return consistent error format:

```json
{
  "success": false,
  "error": {
    "code": "SITE_NOT_FOUND",
    "message": "Site not found",
    "details": "The specified site ID does not exist"
  }
}
```

**Common Error Codes:**
- `SITE_NOT_FOUND`: Site does not exist
- `UNIT_NOT_FOUND`: Unit does not exist
- `MATRIX_GENERATION_ERROR`: Error during matrix generation
- `UNAUTHORIZED`: Invalid or missing authentication
- `FORBIDDEN`: User does not have access to site

## Service Architecture

### Core Service: `HarrisMatrixService`

Located in `app/services/harris_matrix_service.py`

#### Key Methods

```python
class HarrisMatrixService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def generate_harris_matrix(self, site_id: str) -> Dict:
        """Generate complete Harris matrix for a site"""
    
    async def get_matrix_statistics(self, site_id: str) -> Dict:
        """Get statistics about the matrix"""
    
    async def get_unit_details(self, site_id: str, unit_code: str) -> Dict:
        """Get detailed information about a specific unit"""
    
    def _extract_relationships(self, unit_code: str, sequenza_fisica: Dict) -> List[Dict]:
        """Parse relationships from sequenza_fisica JSON"""
    
    def _calculate_chronological_levels(self, nodes: List[Dict], edges: List[Dict]) -> None:
        """Calculate chronological levels using topological sorting"""
    
    def _convert_to_cytoscape_format(self, units: List, relationships: List) -> Dict:
        """Convert data to Cytoscape.js format"""
```

#### Relationship Processing Algorithm

```python
def _extract_relationships(self, unit_code: str, sequenza_fisica: Dict) -> List[Dict]:
    """
    Extract relationships from sequenza_fisica JSON field
    Handles cross-references between US and USM units
    """
    relationships = []
    
    for relationship_type, targets in sequenza_fisica.items():
        if relationship_type not in self.RELATIONSHIP_TYPES:
            continue
            
        for target in targets:
            target_code, target_type = self._parse_cross_reference(target)
            if target_code:
                relationships.append({
                    'source': unit_code,
                    'target': target_code,
                    'type': relationship_type,
                    'source_type': 'us' if unit_code.startswith('US') else 'usm',
                    'target_type': target_type
                })
    
    return relationships
```

#### Cross-Reference Parser

```python
def _parse_cross_reference(self, reference: str) -> Tuple[str, str]:
    """
    Parse cross-references like 'USM174(usm)' or 'US001'
    Returns: (code, type) where type is 'us' or 'usm'
    """
    if '(usm)' in reference:
        code = reference.replace('(usm)', '')
        return code, 'usm'
    else:
        return reference, 'us'
```

#### Chronological Level Calculation

```python
def _calculate_chronological_levels(self, nodes: List[Dict], edges: List[Dict]) -> None:
    """
    Calculate chronological levels using topological sorting
    Level 0 = most recent, higher numbers = older
    """
    # Build adjacency list
    graph = {node['id']: [] for node in nodes}
    reverse_graph = {node['id']: [] for node in nodes}
    
    for edge in edges:
        if edge['type'] in self.PRIMARY_RELATIONSHIPS:
            # Primary relationships define chronological order
            graph[edge['source']].append(edge['target'])
            reverse_graph[edge['target']].append(edge['source'])
    
    # Topological sort
    levels = {}
    visited = set()
    
    def assign_level(node: str, level: int):
        if node in visited:
            return
        visited.add(node)
        levels[node] = level
        for neighbor in graph[node]:
            assign_level(neighbor, level + 1)
    
    # Process nodes with no incoming edges first (most recent)
    for node in nodes:
        if not reverse_graph[node['id']] and node['id'] not in visited:
            assign_level(node['id'], 0)
    
    # Assign levels to all nodes
    for node in nodes:
        if node['id'] not in visited:
            assign_level(node['id'], 0)
    
    # Update node data
    for node in nodes:
        node['level'] = levels.get(node['id'], 0)
```

## Frontend Implementation

### Cytoscape.js Integration

Located in `app/templates/pages/us/harris_matrix_viewer.html`

#### Graph Configuration

```javascript
const cy = cytoscape({
  container: document.getElementById('cy'),
  
  elements: {
    nodes: matrixData.nodes,
    edges: matrixData.edges
  },
  
  style: [
    {
      selector: 'node[type="us"]',
      style: {
        'background-color': '#4A90E2',
        'shape': 'ellipse',
        'label': 'data(label)',
        'text-valign': 'center',
        'text-halign': 'center',
        'color': 'white',
        'font-size': '12px',
        'width': '60px',
        'height': '60px'
      }
    },
    {
      selector: 'node[type="usm"]',
      style: {
        'background-color': '#9B59B6',
        'shape': 'rectangle',
        'label': 'data(label)',
        'text-valign': 'center',
        'text-halign': 'center',
        'color': 'white',
        'font-size': '12px',
        'width': '80px',
        'height': '50px'
      }
    },
    {
      selector: 'edge[type="copre"]',
      style: {
        'width': 2,
        'line-color': '#E74C3C',
        'target-arrow-color': '#E74C3C',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier'
      }
    }
    // ... more style definitions
  ],
  
  layout: {
    name: 'dagre',
    rankDir: 'TB',  // Top to bottom
    align: 'UL',
    rankSep: 100,
    nodeSep: 50,
    edgeSep: 10
  }
});
```

#### Interactive Features

```javascript
// Node click handler
cy.on('tap', 'node', function(evt) {
  const node = evt.target;
  const nodeId = node.id();
  
  // Load unit details
  fetch(`/api/v1/harris-matrix/sites/${siteId}/units/${nodeId}`, {
    headers: {
      'Authorization': `Bearer ${accessToken}`
    }
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      showUnitDetails(data.data);
    }
  });
});

// Relationship filter
function filterByRelationshipType(type) {
  cy.edges().style('display', 'none');
  if (type !== 'all') {
    cy.edges(`[type="${type}"]`).style('display', 'element');
  }
}

// Export functionality
function exportMatrix() {
  const pngData = cy.png({scale: 2});
  const link = document.createElement('a');
  link.download = 'harris-matrix.png';
  link.href = pngData;
  link.click();
}
```

## Performance Considerations

### Database Optimization

#### Indexes

```sql
-- Essential indexes for Harris Matrix queries
CREATE INDEX idx_unita_stratigrafica_site ON unita_stratigrafica(id_sito);
CREATE INDEX idx_unita_stratigrafica_codice ON unita_stratigrafica(codice_us);
CREATE INDEX idx_usm_site ON unita_stratigrafica_muraria(id_sito);
CREATE INDEX idx_usm_codice ON unita_stratigrafica_muraria(codice_us);

-- JSONB indexes for relationship queries
CREATE INDEX idx_sequenza_fisica_gin ON unita_stratigrafica USING GIN(sequenza_fisica);
CREATE INDEX idx_sequenza_fisica_gin_usm ON unita_stratigrafica_muraria USING GIN(sequenza_fisica);
```

#### Query Optimization

```python
# Use eager loading to avoid N+1 queries
query = (
    select(UnitaStratigrafica)
    .options(selectinload(UnitaStratigrafica.site))
    .where(UnitaStratigrafica.id_sito == site_id)
    .order_by(UnitaStratigrafica.codice_us)
)
```

### Caching Strategy

```python
# Redis caching for frequently accessed matrices
@cache.memoize(timeout=300)  # 5 minutes
async def get_cached_matrix(site_id: str, user_id: str) -> Dict:
    return await generate_harris_matrix(site_id)
```

### Memory Management

```python
# Process large datasets in batches
async def generate_matrix_large_dataset(site_id: str) -> Dict:
    batch_size = 100
    all_units = []
    
    async with get_async_session() as db:
        offset = 0
        while True:
            batch = await get_units_batch(db, site_id, offset, batch_size)
            if not batch:
                break
            all_units.extend(batch)
            offset += batch_size
    
    return process_units(all_units)
```

## Security Considerations

### Input Validation

```python
# Validate unit codes
def validate_unit_code(code: str) -> bool:
    """Validate US/USM code format"""
    pattern = r'^(US|MUS)\d{3}$'
    return bool(re.match(pattern, code))

# Sanitize JSON input
def sanitize_sequenza_fisica(data: Dict) -> Dict:
    """Remove potentially dangerous data from JSON"""
    allowed_fields = set(RELATIONSHIP_TYPES.keys())
    return {k: v for k, v in data.items() if k in allowed_fields}
```

### Authorization

```python
# Check site access permissions
async def check_site_access(user_id: str, site_id: str) -> bool:
    """Verify user has access to the site"""
    user_site = await db.execute(
        select(UserSite)
        .where(UserSite.user_id == user_id, UserSite.site_id == site_id)
    )
    return user_site is not None
```

### Rate Limiting

```python
# API rate limiting for matrix generation
@limiter.limit("10/minute")  # 10 requests per minute per user
async def generate_harris_matrix_endpoint(site_id: str):
    """Generate Harris matrix with rate limiting"""
    pass
```

## Integration Points

### Related Services

1. **Archaeological Records Service**: Links US/USM to excavation records
2. **Media Service**: Connects units to photos and documents
3. **GIS Service**: Provides spatial context for units
4. **Reporting Service**: Generates PDF reports with matrix

### External APIs

1. **MinIO Storage**: For file uploads and media management
2. **PostgreSQL**: Primary database storage
3. **Redis**: Caching and session management
4. **Elasticsearch**: Full-text search capabilities

### Data Exchange Formats

```python
# Export to JSON
def export_matrix_to_json(matrix_data: Dict) -> str:
    """Export matrix to JSON format"""
    return json.dumps(matrix_data, indent=2, default=str)

# Export to CSV
def export_units_to_csv(units: List[Dict]) -> str:
    """Export units to CSV format"""
    import csv
    import io
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['Code', 'Definition', 'Interpretation', 'Period', 'Level'])
    for unit in units:
        writer.writerow([
            unit['codice_us'],
            unit['definizione'],
            unit['interpretazione'],
            unit['periodo'],
            unit.get('level', '')
        ])
    
    return output.getvalue()
```

---

**Technical Specifications Version**: 1.0  
**Last Updated**: 2025-11-29  
**Compatible With**: FastZoom Harris Matrix System v1.0+

For implementation details and code examples, refer to the actual source files in the FastZoom repository.