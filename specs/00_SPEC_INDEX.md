# MEMORA — Complete TDD Specification Suite

## How to Read These Specs

Every `.md` file in this `specs/` directory is a **binding specification**.
A module is **done** when:
1. All functions described in the spec are implemented.
2. All test cases listed in the corresponding test spec pass.
3. No test outside that module's boundary is broken.

## Spec → File → Test Mapping

| Spec File | Covers | Test File(s) |
|---|---|---|
| `core/SPEC_types.md` | `core/types.py` | `tests/unit/test_mem_cube.py` (partial) |
| `core/SPEC_events.md` | `core/events.py` | inline in integration tests |
| `core/SPEC_interfaces.md` | `core/interfaces.py` | used in all mock fixtures |
| `core/SPEC_errors.md` | `core/errors.py` | all modules |
| `core/SPEC_config.md` | `core/config.py` | `tests/conftest.py` |
| `storage/SPEC_postgres.md` | `storage/postgres/*` | `tests/integration/` |
| `storage/SPEC_vector.md` | `storage/vector/*` | `tests/unit/test_hybrid_retriever.py` |
| `storage/SPEC_graph.md` | `storage/graph/*` | `tests/integration/test_court_to_vault.py` |
| `vault/SPEC_mem_cube.md` | `vault/mem_cube.py` | `tests/unit/test_mem_cube.py` |
| `vault/SPEC_repos.md` | `vault/episodic_repo.py`, `semantic_repo.py`, `kg_repo.py` | `tests/integration/` |
| `vault/SPEC_tier_router.md` | `vault/tier_router.py` | `tests/unit/test_tier_router.py` |
| `vault/SPEC_quarantine.md` | `vault/quarantine_repo.py` | `tests/integration/test_court_to_vault.py` |
| `vault/SPEC_provenance.md` | `vault/provenance.py`, `ttl_manager.py` | `tests/unit/test_mem_cube.py` |
| `scheduler/SPEC_segmenter.md` | `scheduler/episode_segmenter.py`, `boundary_detector.py` | `tests/unit/test_episode_segmenter.py` |
| `scheduler/SPEC_pipeline.md` | `scheduler/ingestion_pipeline.py`, `type_classifier.py`, `predict_calibrate.py` | `tests/integration/test_ingestion_pipeline.py` |
| `court/SPEC_judge.md` | `court/judge_agent.py`, `contradiction_detector.py` | `tests/unit/test_contradiction_detector.py` |
| `court/SPEC_quarantine_mgr.md` | `court/quarantine_manager.py`, `resolution_handler.py` | `tests/integration/test_court_to_vault.py` |
| `retrieval/SPEC_retrieval.md` | All `retrieval/` files | `tests/unit/test_hybrid_retriever.py` |
| `experience/SPEC_experience.md` | All `experience/` files | `tests/unit/test_experience_learner.py` |
| `agent/SPEC_agent.md` | All `agent/` files | `tests/integration/test_agent_conversation.py` |
| `llm/SPEC_llm.md` | All `llm/` files | mocked in all tests |
| `api/SPEC_api.md` | All `api/` files | `tests/integration/test_agent_conversation.py` |
| `frontend/SPEC_frontend.md` | All `frontend/` files | component/hook specs |
| `tests/SPEC_conftest.md` | `tests/conftest.py` | shared fixtures |
| `tests/SPEC_e2e.md` | `tests/e2e/test_demo_scenario.py` | end-to-end |
| `scripts/SPEC_scripts.md` | All `scripts/` files | manual verification |

## TDD Workflow

```
1. Read module spec → understand contracts
2. Read test spec → understand what pass looks like
3. Write test stubs (failing)
4. Implement module until tests pass
5. Run full suite — no regressions allowed
```

## Definition of Done (per module)

- [ ] All functions from spec implemented with correct signatures
- [ ] All `MUST` requirements from spec met
- [ ] All test cases in test spec pass
- [ ] Type annotations on all public functions
- [ ] Docstring on every class and public method
- [ ] No direct cross-module imports that violate the coupling table
- [ ] `make test-unit` passes
- [ ] `make test-integration` passes (requires Docker)
