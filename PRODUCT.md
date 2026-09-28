# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary users are Talenta pod owners who create work, monitor agent and pipeline progress, respond to blocked tasks, and decide what needs attention next. Qualified reviewers are a secondary user group who inspect deliverables and record artifact-bound approval or rejection.

Users commonly open the app on a mid-range Android device over mobile data. The interface must remain usable on desktop for longer review work and operational oversight.

## Product Purpose

AOS is the human-facing control layer for Talenta's AI-agent roster. It lets authorized people request work, monitor it, inspect deliverables, and enforce human review before controlled outputs are released.

Success means a pod owner can understand current work and take the correct next action quickly, while Amber review, signer qualification, artifact integrity, and pod isolation remain explicit and enforceable.

## Positioning

Hermes runs the workers; AOS governs the human workflow around them. Its distinguishing mechanism is a board-per-pod authorization boundary combined with approval records bound to the SHA-256 hash of the exact artifact reviewed.

## Operating Context

- Six pods use physically separate Hermes board databases.
- A role may be agentic, a deterministic n8n pipeline, or human seat work.
- Composite roles expose multiple stages with a human gate between them.
- Pod owners create tasks, monitor running and blocked work, open deliverables, and clear finished items without deleting audit history.
- Qualified reviewers inspect a file before signing it; approval is attached to the current bytes, not merely to a task status.
- The first frontend revamp covers the core flow: home, task detail, deliverable review, and approval or rejection.

## Capabilities and Constraints

- Preserve all backend behavior, routes, authorization, review gates, integrity checks, task lifecycle rules, and audit semantics.
- Keep the app server-rendered with FastAPI and Jinja. It has no frontend build step and does not require an SPA or client-side state framework.
- Pod authorization must be checked before board data is read.
- Amber output cannot be released without a qualified signature against the current artifact hash.
- Green work may be held when evidence-tool health is degraded.
- Composite role gates must remain visible as controls rather than being presented as unrelated agents.
- The development identity query parameter is a local-only stub and must not be presented as production authentication.
- No patient-identifiable data may be introduced into the repository, fixtures, screenshots, or design demonstrations.
- Existing uncommitted repository changes are outside the frontend revamp and must remain untouched.

## Evidence on Hand

- Working FastAPI/Jinja implementation and route tests.
- Existing queue, task, agent, composite-family, file-review, and queue-health templates.
- Registry data for 25 role stages across six pods.
- Real approval, integrity, and authorization behavior implemented in the application code.
- No confirmed brand assets, logo system, testimonials, benchmarks, or public product claims are available for the redesign. Future work must not fabricate them.

## Product Principles

1. Make the next responsible action obvious before showing operational detail.
2. Treat governance state as primary product information, not administrative metadata.
3. Preserve the distinction between worker completion, human approval, and release readiness.
4. Design for quick mobile checks while supporting careful desktop review.
5. Keep safety and authorization deterministic; the interface explains controls but never substitutes for them.

## Accessibility & Inclusion

No formal conformance target has been selected yet. The revamp must establish a practical accessibility floor: keyboard-operable controls, visible focus, semantic structure, sufficient contrast, touch targets suitable for mobile use, reduced-motion support, and status communication that does not rely on color alone.
