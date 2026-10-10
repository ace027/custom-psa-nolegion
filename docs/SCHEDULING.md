# Scheduling: working hours, time off and appointments

Scheduling answers "who can go where, and when". Every tech has a timezone and weekly
working hours. Time off goes through a request and admin-approval workflow. Appointments book
a tech against a client ticket. Conflicts produce **warnings**: a booking is never refused
because the tech is busy.

Code: `backend/app/scheduling.py` (services), `backend/app/availability.py` (pure interval
math), `backend/app/routers/scheduling.py` (routes), `backend/app/scheduling_schemas.py`
(API shapes). Migration: `backend/alembic/versions/0024_scheduling.py`.

## Data model

| Table | What it holds | Isolation | App role grants |
|---|---|---|---|
| `users.timezone` | IANA zone override; NULL = the Settings timezone | — | (users) |
| `user_work_hours` | One window per weekday (0 = Monday), `start_minute` < `end_minute` <= 1440, minutes from local midnight. No rows = the org business hours | none (staff data) | SELECT, INSERT, UPDATE, DELETE |
| `user_time_off` | `starts_at`/`ends_at` (at most 366 days), `reason`, `status` pending / approved / rejected / cancelled, `requested_by`, `decided_by`/`decided_at`/`decision_note` | none (staff data) | SELECT, INSERT, UPDATE (no delete) |
| `appointments` | `ticket_id`, `organization_id` (follows the ticket through a composite FK), `tech_id`, `starts_at`/`ends_at` (at most 24 h), `status` scheduled / cancelled, `notes`, `client_visible`, `created_by`, `cancelled_at`/`cancelled_by`/`cancel_reason` | **forced RLS** (`org_scope`) plus `Scope` in every query | SELECT, INSERT, UPDATE (no delete) |

Nothing is deleted. Time off is cancelled or rejected, and appointments are cancelled. The
database requires `status = 'cancelled'` and `cancelled_at` to be set together. Every write is
audited in the same transaction with before and after snapshots: `schedule.update`,
`time_off.create|approve|reject|cancel` and `appointment.create|update|cancel`. Appointment
audit rows carry the client's `organization_id`.

## Permissions

| Permission | admin | tech | billing | read_only |
|---|---|---|---|---|
| `schedule:read`: appointments, availability, time-off list, own schedule | yes | yes | yes | yes |
| `schedule:write`: book, move and cancel appointments; own hours and own time-off requests | yes | yes | — | — |
| `timeoff:approve`: approve or reject time off; manage anyone's hours and time off | yes | — | — | — |

Further rules enforced by the service:

- **Schedules.** Anyone can read and change their own schedule. Reading or changing another
  user's schedule needs `timeoff:approve`; otherwise the answer is 403.
- **Bookable users.** Only active admins and techs can have working hours, time off or
  appointments. Any other target gets 409 "Appointments and working hours are for active
  admins and techs".
- **Time-off reasons.** A reason is shown only to the owner and to approvers. Everyone else
  sees `null`.
- **Booking.** Any `schedule:write` holder can book, move or cancel any tech's appointment.
  This is the dispatcher model.

## Time-off workflow

```
tech requests ──> pending ──approve──> approved ──cancel (before it ends)──> cancelled
                     │ └──reject───> rejected
                     └──cancel──> cancelled
admin enters (for anyone) ──> approved (decided_by = the admin)
```

- Approving or rejecting works only on `pending`; otherwise the answer is 409.
- The owner or an approver can cancel time off that is `pending`, or `approved` with
  `ends_at` still in the future. Past approved time off stays on the record, so cancelling it
  returns 409.
- Only **approved** time off removes availability. Pending time off is reported as a warning.

## Conflict kinds (warnings only)

`POST /appointments`, `GET /appointments/{id}` and `PATCH /appointments/{id}` return
`conflicts: [{kind, time_off_id, appointment_id}]`. These are computed live for scheduled
appointments. Cancelled appointments and list results return `[]`.

| kind | Meaning | Id set |
|---|---|---|
| `outside_hours` | The slot is not fully inside the tech's working windows (adjacent windows count as one) | — |
| `time_off` | Overlaps approved time off | `time_off_id` |
| `time_off_pending` | Overlaps a pending request | `time_off_id` |
| `overlap` | Overlaps another scheduled appointment for the same tech (a double booking; both are saved) | `appointment_id` |

Intervals are half-open, so back-to-back slots (10:00-11:00 and 11:00-12:00) do not overlap.

## Booking rules

- The ticket must be visible in scope (otherwise 404) and assigned to a client (otherwise 409
  "Assign the ticket to a client first"). It must not be closed (otherwise 409 "Reopen the
  ticket first").
- `ends_at > starts_at` and the slot lasts at most 24 hours; otherwise 422.
- Only `scheduled` appointments can be patched. A patch re-validates the tech and the range
  and recomputes conflicts. Cancelling an appointment that is already cancelled returns 409.

## Timezones and holidays

- All API times are timezone-aware ISO 8601. Naive datetimes (no offset) get 422. Responses
  are in UTC.
- A user's working hours are wall-clock minutes in **their own** timezone (`users.timezone`,
  else the Settings timezone). A tech in New York and an org in Chicago each work 08:00-17:00
  local time. Conversion is DST-correct, and 1440 means the next local midnight.
- With no `user_work_hours` rows, a user works the org business days and hours from Settings.
- Holidays (from the shared holiday calendar) apply to everyone, in each user's local date:
  - A closed day removes that day.
  - A shortened day intersects with the user's hours.
  - A holiday on a day the user does not work has no effect.

## Limits (422)

- Appointment list: `from` and `to` are required unless `ticket_id` is given, and the range is
  at most 62 days.
- Appointment list with `with_conflicts=true`: `from` and `to` are both required and the range is
  at most 8 days.
- Availability: the range is at most 31 days.
- Time off: at most 366 days.
- `end` must be after `start` in every range.

## API

All routes are under `/api`, tagged `scheduling`. Errors use `{detail}` with 403, 404, 409 or 422.

| Method and path | Permission | Notes |
|---|---|---|
| `GET /users/{user_id}/schedule` | schedule:read | Effective timezone, the override, `uses_default_hours` and `work_hours`. Self or approver only |
| `PUT /users/{user_id}/schedule` | schedule:write | `{timezone, work_hours}`. A null field means the org default. An empty list or a duplicate weekday gets 422. Self or approver only |
| `GET /time-off` | schedule:read | Query `user_id`, `status`, `from`, `to` (overlap); ordered by start |
| `POST /time-off` | schedule:write | `{user_id?, starts_at, ends_at, reason?}`, 201 |
| `POST /time-off/{id}/approve` | timeoff:approve | `{note?}` |
| `POST /time-off/{id}/reject` | timeoff:approve | `{note?}` |
| `POST /time-off/{id}/cancel` | schedule:write | Owner or approver |
| `GET /appointments` | schedule:read | Query `tech_id`, `ticket_id`, `from`, `to`, `include_cancelled`, `with_conflicts` (default false). With `with_conflicts=true` every item carries its server-computed `conflicts` (cancelled ones keep `[]`); `from` and `to` are required and at most 8 days apart, else 422 |
| `POST /appointments` | schedule:write | `{ticket_id, tech_id, starts_at, ends_at, notes?, client_visible?}`, 201, with conflicts |
| `GET /appointments/{id}` | schedule:read | With conflicts |
| `PATCH /appointments/{id}` | schedule:write | Any of `tech_id`, `starts_at`, `ends_at`, `notes`, `client_visible`; returns conflicts |
| `POST /appointments/{id}/cancel` | schedule:write | `{reason?}` |
| `GET /availability` | schedule:read | Query `user_ids` (comma-separated; omit for all active admins and techs), `from`, `to`. Per user: `timezone`, `working`, approved `time_off`, `time_off_pending` (pending requests overlapping the range; they do not reduce `free`, and move to `time_off` once approved), scheduled `appointments` (with `id`), and `free` = working minus time off minus appointments |
