# Headless API token-scope contract

Status: binding for the `helix-api` FastAPI spine. This document describes the
token-scope contract enforced by `server/auth.py` and `server/scope.py`.

## Rule

Every bearer token is bound to a tenant scope. A scoped token may only act
inside its own scope. Request values naming another tenant or client are
refused with `403`. Omitted tenant values default to the identity scope, never
to a caller-chosen tenant. Caller-supplied tenant ids are never the sole
authorization boundary; isolation itself stays enforced by the single policy
seam (`security.policy.authorize`) inside the control plane.

## Configuration

| Variable | Required | Meaning |
|---|---|---|
| `HELIX_API_TOKEN` | yes | shared bearer secret; missing fails closed at request time |
| `HELIX_API_TOKEN_ROLE` | no (default `sami`) | role bound to the token identity |
| `HELIX_API_TOKEN_TENANT_ID` | yes, unless global-operator mode | tenant scope for the token |
| `HELIX_API_TOKEN_CLIENT_ID` | no | optional client scope inside the tenant |
| `HELIX_API_ALLOW_GLOBAL_OPERATOR` | no (default off) | explicit opt-in for global-operator mode |

One token serves one tenant. Multi-tenant operators run one token (or one
instance) per tenant.

## Fail-closed matrix

| Situation | Result |
|---|---|
| No `HELIX_API_TOKEN_TENANT_ID`, global flag off | `500` on every authenticated route: token scope not configured |
| Empty-string tenant scope | same as missing: `500` |
| Client scope without tenant scope | `500`: misconfiguration |
| Non-global token, no explicit flag | any cross-tenant read is empty or `404`; any cross-tenant write is `403` |
| Global flag on, role is a universal approver | global-operator identity (tenant scope `None`) |
| Global flag on, ordinary role, no tenant scope | `500`: fail closed |

## Global-operator mode

Preserved only for an allowed universal role (read from
`organization/role-catalog.yaml` at request time, fail-closed when unreadable)
together with the explicit `HELIX_API_ALLOW_GLOBAL_OPERATOR` flag. There is no
other path to a tenant-less identity. Every global-scope access is audited to
the structured log as a `global_scope_access` entry carrying actor, role,
target tenant, target client, route, and correlation id.

## Endpoint behavior

- `GET /healthz` and `GET /readyz` stay public (no token required).
- Chat, docs, tasks create/list/get/update resolve the effective tenant from
  the identity; cross-tenant writes answer `403`, cross-tenant reads answer
  `404` or an empty list scoped to the caller.
- Workflow submit rejects payload tenant/client values outside the identity
  scope with `403`; workflow get/events/execute/result and approval decide
  answer `404` for foreign tenants so existence is not disclosed.
- Halt status answers only the caller scope for scoped tokens (other tenants'
  halt scopes are never listed); engage/release without a tenant value halt or
  release the caller scope, never the platform.
- `/metrics` stays behind the standard bearer-token guard (any valid token).
