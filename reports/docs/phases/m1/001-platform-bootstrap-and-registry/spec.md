# 001 — Platform Bootstrap & Registry

**Phase:** M1 — Platform Foundation 
**Status:**  
**Parent decision record:** `../implementation_plan.md`  
**Execution stage:** 

### 1. Purpose

Establish a shared platform initialization boundary and an explicit, validated registry through which approved business modules become part of the running platform.

The Sourcing module must use this mechanism rather than being mounted directly by the application entrypoint.

### 2. Scope

**Included**
- Shared platform bootstrap used by independent API and worker entrypoints.
- Configuration and critical dependency validation.
- Explicit code-defined module registry.
- Module manifest loading and validation.
- Typed module contract conformance.
- Minimum platform-version compatibility validation.
- Registry-driven module route composition.
- Persistent registration-state integration through the platform persistence interface.
- Module registration diagnostics and lifecycle state.

**Excluded**
- Arbitrary filesystem discovery or dynamic plugin loading.
- Third-party module installation.
- Generalized dependency graphs or capability negotiation.
- Sourcing business functionality.
- A generalized dependency-injection framework.

### 3. Required behavior

1. API and worker processes must use the same shared bootstrap boundary while retaining independent lifecycles.
2. Critical configuration and dependencies must be validated before the process becomes ready.
3. The registry must contain only explicitly approved module implementations.
4. A module manifest must describe and validate an implementation; it must not authorize arbitrary code execution.
5. The platform must validate module identity, version, required manifest fields, minimum platform version, declared capabilities and permissions, and contract conformance before accepting registration.
6. Registration must be deterministic and safe to repeat.
7. The Sourcing module must register through the same contract intended for future modules.
8. An invalid or incompatible module must not be activated or have its routes exposed.
9. The registry must distinguish available module implementations from persisted registration and operational state.

### 4. Contract boundaries

- **Code and manifest:** authoritative definition of approved module implementations and their metadata.
- **Registry:** controls registration and route composition.
- **Platform database:** records observed registration and compatibility state; it does not authorize code loading.
- **Module contract:** provides the required metadata, route registration, declared permissions/capabilities, and health behavior.
- **Bootstrap:** composes shared services without coupling API and worker lifecycles.

The existing Sourcing manifest and typed precursor contract are the starting point. Their actual structure must be reconciled with the accepted System Design before implementation.

### 5. Acceptance criteria

- [ ] API startup initializes the platform through the shared bootstrap.
- [ ] Worker startup uses the same bootstrap boundary without starting or supervising the API.
- [ ] Sourcing registers through the explicit registry.
- [ ] The application no longer depends on hardcoded Sourcing router mounting.
- [ ] A missing or malformed manifest is rejected.
- [ ] An incompatible platform-version requirement is rejected.
- [ ] A module that fails contract validation is rejected.
- [ ] Unapproved modules cannot register merely by placing a manifest in the repository.
- [ ] Repeated registration does not create inconsistent state.
- [ ] Module registration and health state can be inspected through the platform's internal contract.

### 6. Constraints and governing decisions

- M1-D01 — Shared bootstrap and independent process composition.
- M1-D02 / D02.1 — Explicit registry and metadata authority.
- M1-D03 — Compatibility and module health semantics.
- M1-D06 — Platform-owned registration metadata.
- ADR-001, ADR-002, ADR-003, ADR-005, ADR-007.
- Relevant invariants: INV-001, INV-003, INV-004, INV-005, INV-006, INV-008, INV-010, INV-015.

### 7. Dependencies

- M0 application factory and configuration boundary.
- Existing Sourcing manifest and module precursor.
- Platform persistence interface from SDD 003.

The registry contract may be developed before the persistence implementation, but persistent registration-state integration must not be considered complete until SDD 003 is available.
