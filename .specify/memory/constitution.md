# FastZoom Constitution

<!-- Sync Impact Report:
Version change: 0.0.0 → 1.0.0 (initial ratification)
Modified principles: N/A (new constitution)
Added sections: Core Principles (5), Technical Standards, Development Workflow, Governance
Removed sections: N/A (new constitution)
Templates requiring updates: ✅ plan-template.md, ✅ spec-template.md, ✅ tasks-template.md
Follow-up TODOs: N/A
-->

## Core Principles

### I. Code Quality Excellence

All code MUST follow Python 3.12+ standards with enforced linting via Ruff and formatting via Black. SQLAlchemy models MUST include proper field validation, comprehensive docstrings, and follow archaeological domain modeling best practices. Services MUST implement proper error handling, logging with structured Loguru output, and maintain clear separation of concerns between business logic, data access, and API layers. Rationale: Archaeological data integrity and long-term maintainability require strict code discipline and consistent patterns.

### II. Test-First Archaeological Safety

Critical archaeological data operations (photo uploads, site data modifications, user permissions) MUST have failing tests written before implementation. Tests MUST cover: data validation for archaeological metadata, file integrity for deep zoom processing, user permission boundaries, and MinIO object storage operations. Rationale: Archaeological documentation is irreplaceable; validation failures MUST be caught before data corruption occurs.

### III. User Experience Consistency

All frontend components MUST use Alpine.js with consistent event-driven patterns, dark mode support, and responsive design. Archaeological metadata forms MUST be reusable components with consistent validation and error handling. OpenSeadragon viewer MUST be the exclusive method for high-resolution photo viewing with standardized navigation and annotation capabilities. Rationale: Archaeological workflows require consistent, professional interfaces across all data entry and viewing operations.

### IV. Performance for Scientific Imaging

Deep zoom processing MUST implement efficient tile generation with background task processing for large images. API responses MUST maintain <200ms p95 latency for database queries and <2s for file upload acknowledgments. MinIO storage MUST use efficient bucket organization and CDN-friendly caching headers. Rationale: Archaeological research involves high-resolution images that demand specialized performance optimization for scientific examination.

### V. Archaeological Data Integrity

All modifications to archaeological data MUST be auditable with user activity tracking, modification history, and data versioning. UUID normalization MUST be transparently handled for both UUID and hexadecimal hash site IDs. Bulk operations MUST implement transactional safety with rollback capabilities. Rationale: Archaeological records are legal documents requiring complete audit trails and data consistency guarantees.

## Technical Standards

### Code Quality Standards

- **Linting**: Ruff with select = ["E", "F", "ANN", "ARG", "BLE", "COM", "DJ", "DTZ", "EM", "ERA", "EXE", "FBT", "ICN", "INP", "ISC", "NPY", "PD", "PGH", "PIE", "PL", "PT", "PTH", "PYI", "RET", "RSE", "RUF", "SIM", "SLF", "TCH", "TID", "TRY", "UP", "YTT"]
- **Formatting**: Black with 88-character line length
- **Complexity**: Maximum McCabe complexity of 10
- **Type hints**: Required for all function parameters and return values
- **Documentation**: All public functions and models must have comprehensive docstrings

### Testing Standards

- **Coverage**: Minimum 80% coverage for critical paths (photo processing, user authentication, site management)
- **Test Types**: Unit tests for individual components, integration tests for service interactions, contract tests for API endpoints
- **Test Data**: Archaeological test data sets for validating metadata processing and image workflows
- **Performance Tests**: Load testing for concurrent photo uploads and deep zoom generation
- **Database Tests**: Transaction rollback validation and constraint violation handling

### Performance Requirements

- **API Latency**: <200ms p95 for database queries, <2s for file upload acknowledgment
- **Image Processing**: Deep zoom tiles must be generated within 30 seconds for 100MP images
- **Concurrent Users**: Support 100+ concurrent users without performance degradation
- **Storage Efficiency**: MinIO bucket organization with lifecycle policies for temporary files
- **Memory Usage**: <500MB for application runtime under normal load

### User Experience Standards

- **Responsive Design**: Mobile-first approach with breakpoints at 640px, 768px, 1024px, 1280px
- **Dark Mode**: Full dark mode support with system preference detection
- **Accessibility**: WCAG 2.1 AA compliance for all user interfaces
- **Error Handling**: User-friendly error messages with archaeological context
- **Loading States**: Loading indicators for all operations >200ms

## Development Workflow

### Code Review Requirements

All pull requests MUST:
- Pass all automated tests and linting checks
- Include test coverage for new functionality
- Document any archaeological data schema changes
- Demonstrate UI consistency with existing patterns
- Include performance impact assessment for image processing changes

### Database Migration Standards

Alembic migrations MUST:
- Include rollback procedures
- Handle existing archaeological data safely
- Test against production data snapshots
- Include data validation steps post-migration
- Document any breaking changes to API contracts

### Deployment Standards

- **Staging Validation**: All features must be validated in staging with production data
- **Rollback Plans**: Every deployment must have documented rollback procedures
- **Monitoring**: Structured logging for all critical operations with correlation IDs
- **Health Checks**: Comprehensive health endpoints for database, MinIO, and application status

## Governance

This constitution supersedes all other development practices and guidelines for FastZoom. All team members MUST ensure architectural decisions align with these core principles. Technical complexity MUST be justified in the context of archaeological data integrity requirements. Use this constitution as the primary reference for all technical decisions and implementation choices.

### Amendment Procedure

- **Proposal**: Any team member can propose amendments with archaeological context justification
- **Review**: Core team review with archaeological data impact assessment
- **Approval**: Majority vote with archaeological domain expert consensus required
- **Implementation**: Minimum 2-week transition period for any breaking changes

### Compliance Review

- **Monthly**: Technical compliance audit against constitution principles
- **Quarterly**: Archaeological workflow and user experience review
- **Annually**: Full constitution review with stakeholder input

### Version Policy

Constitution versions follow semantic versioning:
- **MAJOR**: Breaking changes requiring code modifications or architectural rework
- **MINOR**: New principles or substantial guidance additions
- **PATCH**: Clarifications, wording improvements, or non-substantive updates

**Version**: 1.0.0 | **Ratified**: 2025-11-18 | **Last Amended**: 2025-11-18