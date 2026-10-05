> HISTORICAL PLAN / SPEC: retained for design history, not current runtime status.
> See [current documentation](../README.md) for implementation, commands and evidence.

# Employee enrollment and multi-company demo

## Scope

The company creates an employee and issues a short-lived, single-use enrollment link. The employee opens the exam demo, supplies two distinct face images and two distinct WAV recordings in one submission, and consents. The service binds that action to the invited employee and tenant without giving the browser an operator or integration key. The company continues to control exam timing; the demo submits start and subsequent checks with that company's server-side integration key.

## Implementation

1. Add a hashed enrollment invitation in PostgreSQL. Make issue/inspect/consume tenant scoped and reject expiry, reuse, inactive employee/company, duplicate media, invalid media, and partial enrollment. Audit issuance and successful enrollment.
2. Keep the existing operator enrollment endpoint compatible. The employee invitation endpoint validates all four samples first, then commits those samples and consumes the invitation together.
3. Add server-side multi-company selection to the exam simulator. Validate that the selected employee belongs to that company before submitting a check. Never send company credentials to the browser.
4. Rebuild the employee page around choose company, choose employee, enroll, start check, and later batch check. Put raw JSON in a closed disclosure. Add friendly status and error text, keyboard focus, and responsive layout.
5. Update the company portal with invitation issuance, plain-language labels and report presentation. Keep raw API payloads behind expanders.
6. Run focused and full tests, build and deploy the local Compose stack with persistent data, submit genuine and suspicious multi-tenant checks, inspect webhook/report/Prometheus/Grafana, and record the demo steps and limits.

## Acceptance

- A one-use employee invitation can enroll only its own active employee with two distinct valid samples per modality in one request.
- Company A cannot read or submit Company B's employees using A's integration key.
- A nontechnical user can follow the exam page without reading IDs or JSON.
- A suspicious check has a tenant-scoped report and retrievable evidence; a normal check does not retain raw evidence.
- Platform monitoring receives resulting metrics. The demo's simulated identity selector is explicitly labelled as simulated login.
