# NeuronOS Implementation Guides

**Comprehensive roadmap for taking NeuronOS from pre-alpha to production**

Based on the [Comprehensive Audit Report](../../COMPREHENSIVE_AUDIT_REPORT.md) which identified 287+ issues across the codebase.

---

## Overview

| Phase | Focus | Time Estimate | Priority |
|-------|-------|---------------|----------|
| [Phase 1](./PHASE_1_CRITICAL_FIXES.md) | Critical Security & Data Loss Fixes | 1-2 weeks | **HIGHEST** |
| [Phase 2](./PHASE_2_CORE_FEATURES.md) | Core Feature Completion | 2-3 weeks | HIGH |
| [Phase 2A](./PHASE_2A_VM_MANAGER.md) | VM Manager Deep Dive | 1-2 weeks | HIGH |
| [Phase 3](./PHASE_3_FEATURE_PARITY.md) | Feature Parity & Polish | 2 weeks | MEDIUM |
| [Phase 3A](./PHASE_3A_GUEST_AGENT.md) | Guest Agent Protocol | 1-2 weeks | MEDIUM |
| [Phase 4](./PHASE_4_ERROR_HANDLING.md) | Error Handling & Robustness | 1-2 weeks | MEDIUM |
| [Phase 5](./PHASE_5_TESTING.md) | Testing & Quality Assurance | 2 weeks | MEDIUM |
| [Phase 6](./PHASE_6_PRODUCTION.md) | Production Readiness | 2 weeks | Required for release |

**Total Estimated Time:** 10-16 weeks

---

## Phase Summary

### Phase 1: Critical Fixes (MUST DO FIRST)

Addresses security vulnerabilities and data loss bugs:

- **SEC-001:** Command injection in VM Manager GUI
- **SEC-002:** Unsafe file path handling
- **SEC-003:** Downloads without verification
- **DATA-001:** Migration file/directory confusion (causes SSH key loss)
- **DATA-002:** Non-atomic config writes
- **SYS-001:** Hardcoded GRUB paths
- **SYS-002:** Missing sudo for system operations

### Phase 2: Core Features

Completes stub implementations:

- **FEAT-001:** PROTON installer (currently missing)
- **FEAT-002:** VMInstaller full implementation
- **FEAT-003:** VM creation dialog (currently shows toast only)
- **FEAT-004:** Onboarding wizard completion
- **FEAT-005:** Looking Glass integration
- **FEAT-006:** Fix broken test assertions

### Phase 2A: VM Manager Deep Dive

Refactors the VM manager for maintainability:

- Split God class (LibvirtManager 529 lines)
- Implement connection pooling
- Full VM creator with templates
- Complete Looking Glass integration
- Proper state machine for VM lifecycle

### Phase 3: Feature Parity

Completes partial features:

- Guest agent communication (host-side client)
- Migration system improvements (browser profiles)
- Hardware detection enhancements (ACS override)
- Update system completion (verification)
- UI/UX polish (consistent dialogs)

### Phase 3A: Guest Agent Protocol

Secure host-guest communication:

- Protocol specification (length-prefix framing)
- Encryption (X25519 + ChaCha20-Poly1305)
- Authentication (HMAC challenge-response)
- Clipboard synchronization
- Resolution synchronization
- Application launching

### Phase 4: Error Handling

Robust error management:

- Custom exception hierarchy
- Structured logging
- Resource management (context managers)
- Thread safety (singleton fixes)
- Graceful degradation

### Phase 5: Testing

Comprehensive test coverage:

- pytest configuration
- Unit tests for all modules
- Integration tests for critical paths
- CI/CD pipeline (GitHub Actions)
- Pre-commit hooks
- Code quality (ruff, black, mypy)

### Phase 6: Production Readiness

Release preparation:

- API documentation
- User guide
- Reproducible builds
- Security hardening
- Performance optimization
- Release automation

---

## Quick Start

### 1. Fix Critical Security Issues (Day 1)

```bash
# See Phase 1 for details
# Priority: Command injection fix
# File: src/vm_manager/gui/app.py:218
```

### 2. Run Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests (many will fail initially)
pytest tests/ -v

# Check coverage
pytest tests/ --cov=src --cov-report=html
```

### 3. Set Up CI/CD

```bash
# Copy GitHub Actions workflow
mkdir -p .github/workflows
# See Phase 5 for workflow configuration
```

---

## Progress Tracking

Use this checklist to track progress:

```markdown
## Phase Progress

### Phase 1: Critical Fixes
- [ ] SEC-001: Command injection fixed
- [ ] SEC-002: Path traversal fixed
- [ ] SEC-003: Download verification added
- [ ] DATA-001: Migration file/dir fixed
- [ ] DATA-002: Atomic writes implemented
- [ ] SYS-001: Dynamic GRUB paths
- [ ] SYS-002: Sudo fallback added

### Phase 2: Core Features
- [ ] PROTON installer implemented
- [ ] VMInstaller complete
- [ ] VM creation works
- [ ] Onboarding applies settings
- [ ] Tests fixed

### Phase 3+: Remaining
- [ ] Guest agent secure
- [ ] Error handling robust
- [ ] 60%+ test coverage
- [ ] Documentation complete
- [ ] Ready for release
```

---

## Key Files Changed

Each phase modifies specific files. Here's a quick reference:

| File | Phases | Changes |
|------|--------|---------|
| `src/vm_manager/gui/app.py` | 1, 2, 4 | Security fix, VM creation |
| `src/store/installer.py` | 1, 2 | PROTON, path safety, downloads |
| `src/migration/migrator.py` | 1, 3 | File/dir fix, browser migration |
| `src/updater/rollback.py` | 1, 3 | GRUB paths, verification |
| `src/guest_agent/**` | 1, 3A | Encryption, protocol |
| `src/onboarding/wizard.py` | 2 | Apply settings |
| `tests/**` | 2, 5 | Fix assertions, add tests |
| `.github/workflows/**` | 5 | CI/CD pipeline |

---

## Getting Help

If you encounter issues implementing these guides:

1. Check the [audit report](../../COMPREHENSIVE_AUDIT_REPORT.md) for context
2. Review the specific phase guide for detailed code
3. Open a GitHub issue with the phase number and problem

---

*Generated from comprehensive code audit on January 2026*
