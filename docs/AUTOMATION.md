# Automation rules

Rules do routine dispatch and escalation work: **when** something happens, **if** every condition is true,
**then** run the actions. Manage them under **Automation** in the sidebar (admins, permission
`automation:manage`). API: `GET/POST /api/automation/rules`, `PATCH /api/automation/rules/{id}`,
`POST /api/automation/rules/{id}/archive`, `POST /api/automation/rules/test`,
`GET /api/automation/rules/{id}/runs`.

## Triggers

The same eight events webhooks use: `ticket.created`, `ticket.assigned`, `ticket.status_changed`,
`ticket.priority_changed`, `ticket.customer_reply`, `ticket.sla_breached`, `rmm_alert.opened`,
`rmm_alert.cleared`.

## Conditions

A rule matches when **all** its conditions are true. No conditions means every event of that trigger.

| Field | Operators | Value |
| --- | --- | --- |
| `organization_id`, `category_id`, `ticket_type_id`, `assignee_id` | eq, ne, in, not_in, is_empty, is_not_empty | id |
| `queue_id`, `priority_id` | eq, ne, in, not_in | id |
| `status` | eq, ne, in, not_in | new, open, waiting_on_customer, resolved, closed |
| `source` | eq, ne, in, not_in | ui, email, portal, rmm, rule |
| `subject` | eq, ne, contains, is_empty, is_not_empty | text (contains is a case-insensitive substring) |
| `alert_severity` | eq, ne, in, not_in | NONE, MINOR, MODERATE, MAJOR, CRITICAL |

`alert_severity` only works on `rmm_alert.*` triggers. `contains` only works on the subject. Ids must exist.
A condition is `{"field": "queue_id", "op": "eq", "value": 3}`; `is_empty` and `is_not_empty` take no value.

## Actions

1 to 10 per rule, run in the order given.

| Action | Parameters | Notes |
| --- | --- | --- |
| `assign` | `user_id` | Active admin or tech. Skipped if already assigned to them |
| `set_queue` | `queue_id` | Skipped if already in it |
| `set_priority` | `priority_id` | Skipped if already that priority |
| `escalate` | none | Next more urgent priority, plus an internal note. Skipped ("already most urgent") at the top |
| `notify` | `user_id` | Email to that person, like the assigned email. Skipped if they turned it off or mail is not configured |
| `webhook` | `endpoint_id` | Queues this event for one endpoint, even if it is not subscribed. Skipped if it already receives the event |
| `create_ticket` | `subject`, optional `queue_id`, `priority_id` | A related ticket for the same client (source "rule"). Skipped when the ticket has no client |

## Ordering

Rules for an event run in `position` order (then id). Two rules that match both run.
Disabled and archived rules never run.

## Loop guard, rate cap and safety

- While a rule's actions run, nothing they change triggers other rules. Webhooks still fire for those
  changes (an assign by a rule still sends `ticket.assigned`).
- A rule runs at most once per event, even if the event is processed twice.
- A rule that matches more than 200 times in a rolling hour is switched off with the reason
  "Fired more than 200 times in an hour" and one `automation.rule_auto_disabled` audit entry. Enable it
  again after fixing it.
- Each action runs on its own: a failing action is recorded as `failed` in the trace and never undoes
  the ticket change or the other actions.
- Audit entries: `automation.rule_created`, `_updated`, `_archived`, `_fired`, `_auto_disabled`.

## Run history and trace

Each run stores `{conditions: [{field, op, value, actual, matched}], actions: [{type, params,
status done|skipped|failed, detail}]}`. Runs that did not match are kept too, so you can see why.

## Dry run

**Test against ticket #** (or `POST /api/automation/rules/test` with `rule_id` or an unsaved `rule`, plus
`ticket_id`) evaluates the conditions against the ticket's current values and lists what would run. It
writes nothing: no run, no audit, no ticket change.

## Examples

Route Security queue tickets to a tech:

```json
{"name": "Security to Sam", "trigger": "ticket.created",
 "conditions": [{"field": "queue_id", "op": "eq", "value": 2}],
 "actions": [{"type": "assign", "user_id": 7}]}
```

Escalate critical monitoring alerts:

```json
{"name": "Critical alerts", "trigger": "rmm_alert.opened",
 "conditions": [{"field": "alert_severity", "op": "eq", "value": "CRITICAL"}],
 "actions": [{"type": "escalate"}, {"type": "notify", "user_id": 7}]}
```

Post SLA breaches to Teams (a Teams webhook must exist; use its id):

```json
{"name": "SLA to Teams", "trigger": "ticket.sla_breached", "conditions": [],
 "actions": [{"type": "webhook", "endpoint_id": 3}]}
```
