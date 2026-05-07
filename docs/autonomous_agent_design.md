# Autonomous Agent Design

Wave C (2026-05-06) — design document for the move from a memory-rich
conversational avatar to an authorized agent that can take actions on
behalf of the user. This document describes **identity policy**,
**permission model**, **audit logging**, and **draft-mode flow**. It
does NOT describe execution semantics for any specific capability —
those come in a future phase, after the schema and prompt boundaries
ship and bake.

## 1. Identity / representation modes

The avatar today says "I am your avatar, not you" — fine for chat. For
action, that posture is wrong. We introduce four explicit modes; the
mode is *always* set by the request context, never inferred:

| Mode | Posture | Tool access | Approval |
|---|---|---|---|
| **`companion`** (default) | "I am your avatar, not you." Conversational. | Read-only tools (web_search, fetch_urls). | None. |
| **`representative`** | "I am acting as the authorized representative of {display_name}." | Capability-gated read tools (calendar.read, email.read). | None for read; per-action for write. |
| **`draft`** | "I propose actions for {display_name} to approve before they are executed." | Capability-gated read tools + capability-gated write tool *drafts*. Tool calls produce structured proposals, not real-world side effects. | Always — the user must approve every draft before it can be promoted. |
| **`autopilot`** | "I am acting on behalf of {display_name} under a pre-approved capability." | Capability-gated write tools that fall under a pre-existing per-capability approval. | Pre-approved at capability-grant time; per-action approval is bypassed only for the explicitly granted capabilities. |

**Mode is exposed to the prompt** as a new top-of-prompt section
(after `mode_section`, before `location_section`). The avatar is told
explicitly which mode it is operating in and what that means.

The reactive chat path defaults to `companion`. Other modes are entered
only by an explicit Rails-side controller decision — e.g. a
`POST /api/v1/agent/run-mode-draft` endpoint that accepts a target
capability + user-approved scope.

## 2. Permission model — `agent_permissions`

Rails-owned, one row per `(user, capability)`.

```ruby
class AgentPermission < ApplicationRecord
  belongs_to :user

  CAPABILITIES = %w[
    web_search read_calendar draft_calendar_event create_calendar_event
    draft_email send_email draft_message send_message
    create_reminder purchase post_social book_reservation
  ].freeze

  RISK_LEVELS = %w[
    read_only draft_only low_risk_execute
    external_commitment financial sensitive
  ].freeze
end
```

| Column | Type | Purpose |
|---|---|---|
| `user_id` | `bigint FK users.id ON DELETE CASCADE` | Owner. |
| `capability` | `varchar` | One of `CAPABILITIES`. |
| `scope` | `jsonb` | Capability-specific qualifiers (calendar id, email folder, social account). |
| `enabled` | `boolean default false` | Master switch. Default OFF for everything. |
| `approval_required` | `boolean default true` | Per-action approval flag. False only for pre-approved autopilot capabilities. |
| `max_risk_level` | `varchar` | Highest `RISK_LEVELS` the avatar may attempt under this row. |
| `spend_limit_cents` | `integer NULL` | Optional per-action ceiling for `purchase` / `book_reservation`. |
| `allowed_recipients` | `jsonb` | Allowlist for messaging caps (emails / phone numbers / handles). |
| `allowed_domains` | `jsonb` | Allowlist of domains the agent may transact with. |
| `quiet_hours` | `jsonb` | `{tz, ranges: [{from, to}, ...]}` blocks during which write actions are refused. |
| `created_at`, `updated_at` | timestamps | |

**Defaults at user creation**: only `web_search` is `enabled: true`,
`risk_level: read_only`. Every write capability is opt-in via the user
panel. There is no hidden default-on capability.

**Index**: `(user_id, capability)` unique, `(user_id, enabled)` for the
agent fast-path that loads the user's full permission set on each turn.

## 3. Audit log — `agent_action_logs`

Every agent action — proposed, approved, rejected, executed, or failed —
creates a row. Append-only.

```ruby
class AgentActionLog < ApplicationRecord
  belongs_to :user
  belongs_to :conversation, optional: true

  STATUSES = %w[proposed approved rejected executed failed rolled_back].freeze
end
```

| Column | Type | Purpose |
|---|---|---|
| `user_id` | `bigint FK users.id ON DELETE CASCADE` | Owner. |
| `conversation_id` | `uuid FK conversations.id`, nullable | Originating chat. |
| `capability` | `varchar` | Same enum as `agent_permissions.capability`. |
| `requested_action` | `text` | Free-text human description ("send email to Lucia confirming Friday lunch"). |
| `tool_name` | `varchar` | Concrete tool invoked (e.g. `gmail.send`). |
| `tool_input` | `jsonb` | Full structured inputs — recipient, subject, body, etc. |
| `tool_output` | `jsonb` | Full result payload from the tool (or error metadata). |
| `risk_level` | `varchar` | Snapshot of the `agent_permissions.max_risk_level` at decision time. |
| `approval_status` | `varchar` | One of `STATUSES`. |
| `executed_at` | `timestamptz` nullable | When the side effect actually happened. |
| `rollback_available` | `boolean default false` | Whether `rollback_payload` carries enough info to undo. |
| `rollback_payload` | `jsonb` | Capability-specific undo data (e.g. message id to delete). |
| `status` | `varchar` | Convenience alias of `approval_status` for retrieval scopes. |
| `error` | `text` nullable | Failure detail. |
| `created_at`, `updated_at` | timestamps | |

**Indexes**: `(user_id, executed_at desc)`, `(conversation_id)`,
`(approval_status)` for the user-facing approvals queue.

## 4. Draft-mode flow

The first ship-able autonomy surface. No real-world side effects.

```
user                  Rails                       FastAPI
 │  send message       │                           │
 ├────────────────────►│                           │
 │                     │  draft mode kicked off    │
 │                     │  (controller decision)    │
 │                     ├──────────────────────────►│
 │                     │  /internal/chat/stream    │
 │                     │  with mode = "draft" +    │
 │                     │  capability allowlist     │
 │                     │                           │
 │                     │   ◄── token stream + a    │
 │                     │       structured "tool    │
 │                     │       proposal" frame     │
 │                     │                           │
 │   approve|reject    │                           │
 │   /agent/proposals  │                           │
 │   /:id/(approve     │                           │
 │   |reject|edit)     │                           │
 │◄────────────────────┤                           │
```

Endpoints (all Rails, none of which executes a tool yet):

```
POST   /api/v1/agent/proposals
       { conversation_id, capability, requested_action, tool_name,
         tool_input, risk_level }
       → 201 { id, approval_status: "proposed", expires_at }

GET    /api/v1/agent/proposals?status=proposed
       → list of pending proposals for current user

PATCH  /api/v1/agent/proposals/:id/approve
       → 200 { approval_status: "approved" }
       (does NOT execute. Sets the row up for an executor that doesn't ship in v1.)

PATCH  /api/v1/agent/proposals/:id/reject
       → 200 { approval_status: "rejected" }

PATCH  /api/v1/agent/proposals/:id/edit
       { tool_input }
       → 200 { …updated proposal… }
```

## 5. Action memory

A new insight category outside the regular six-fact taxonomy. Examples:

- "Always ask before emailing clients."
- "Use my short direct tone for work messages."
- "Never schedule meetings before 9am."
- "Lunch meetings are okay on Fridays."
- "Don't book anything without showing me price."

Schema option: a dedicated `action_preferences` table on the FastAPI
side (so it's mode-scoped retrievable like other memory) with columns
`(id, user_id, capability, preference, confidence, source, created_at)`.

These rows are surfaced as a **distinct prompt section** in agent-mode
prompts only — they never leak into companion-mode chat. Insight
extraction during chat in non-companion modes runs an additional chain
(future work) that classifies messages into action_preferences.

## 6. Rollout gates

Ship in this order; do not skip:

1. ✅ Identity policy section in prompts (Wave C.1).
2. ✅ `agent_permissions` and `agent_action_logs` migrations + models (Wave C.2 / C.3).
3. ✅ Draft-mode endpoints + controller (Wave C.4) — proposals only, no execution.
4. ⛔ User-facing settings UI to manage permissions (out of scope for Wave C).
5. ⛔ First read-only capability adapter (e.g. `read_calendar`) under representative mode (out of scope for Wave C).
6. ⛔ Per-capability executor (e.g. Gmail send) — only after at least 2 weeks of telemetry on draft-mode proposals shows the avatar is producing reasonable proposals (out of scope for Wave C).
7. ⛔ Autopilot for narrowly-scoped capabilities (e.g. add-event-to-calendar with allowlist) — only after the executor has shipped (out of scope).

The gating principle: **the avatar must demonstrate that it can
generate good proposals before it gets to take real actions.**

## 7. What we explicitly do not do

- **No global "act as the user"** flag. Modes are explicit per-action.
- **No silent autopilot.** Autopilot exists, but only for capabilities
  the user has granted in the permission UI with explicit
  `approval_required: false`.
- **No undo-by-default.** Some capabilities are inherently irreversible
  (sent email, paid purchase). Those go through draft mode *forever*
  unless the user explicitly approves autopilot for that capability.
- **No bypass of `restricted_topics` or `quiet_hours`** even when
  autopilot is granted.
