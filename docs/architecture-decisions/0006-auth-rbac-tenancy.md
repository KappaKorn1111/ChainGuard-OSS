# ADR 0006: Organization-scoped authentication, authorization, and tenancy

- Status: Accepted
- Date: 2026-11-14

## Context

ChainGuard needs persistent users, organizations, projects, and security settings
without allowing one organization to observe another organization's records. Access
tokens alone cannot provide revocation or refresh-token reuse detection, and global
roles are insufficient for users who belong to multiple organizations.

## Decision

Users are global identities. Authorization is represented by an
`organization_memberships` row with one of four roles: owner, admin, member, or viewer.
Every tenant-owned query includes the active organization ID from the validated access
token. Cross-tenant lookups return not found. Platform superusers are explicit and may
perform platform-level organization operations; project and user queries remain scoped
to the token's active organization.

Passwords use Argon2id and must satisfy the configured minimum length plus uppercase,
lowercase, and numeric requirements. Login errors do not distinguish missing accounts
from incorrect passwords.

JWT access tokens are short lived. Refresh JWTs are longer lived, but only a SHA-256
hash is stored. Every refresh rotates the token and marks the previous token used and
revoked. Reuse of any used token revokes its complete token family. Logout revokes the
family. JWT signing secrets are mandatory and must contain at least 32 characters
outside development.

Redis provides fixed-window rate limits. Authentication endpoints fail closed if Redis
is unavailable. Other API endpoints fail open so an observability dependency cannot
block already authenticated work; this tradeoff is recorded in structured logs and
should be monitored.

Security-sensitive mutations and successful authentication events append an audit-log
record with actor, organization, target, action, and correlation ID.

## Consequences

- A token selects one organization; clients log in again with an organization slug to
  switch active organization.
- Revocation checks occur when refreshing, not on every access-token request. Short
  access-token lifetime bounds that window.
- Organization-owned tables carry indexed `organization_id` foreign keys.
- Integration settings contain only catalog IDs, per-organization configuration, and
  secret references. They do not copy tool definitions or store plaintext secrets.
- The first bootstrap endpoint is serialized with a PostgreSQL advisory lock and is
  permanently disabled once a user exists.
