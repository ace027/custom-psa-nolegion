# Phase 1: what to verify manually

Prep: dev stack running with seed data (`docs/DEVELOPMENT.md`), or a deployed stack with Entra set up.

## Sign-in
- [ ] Unauthenticated visit shows the sign-in page, not data
- [ ] (Deployed) "Sign in with Microsoft" works for a pre-provisioned user
- [ ] (Deployed) A Microsoft account that is **not** on the Users page is refused, and the audit log shows `auth.login_failed` / `not_provisioned`
- [ ] Sign out returns to the sign-in page; browser back button shows no data

## Roles (sign in as each seeded user in turn)
- [ ] `admin`: sees Organizations, Users, Audit log; can edit everything
- [ ] `tech`: can add/edit organizations, sites, contacts; **no** Audit log link; Users page has no edit controls
- [ ] `billing` and `read_only`: can browse but see no Add/Save/Archive controls
- [ ] As `read_only`, `curl`/DevTools a POST to `/api/organizations` gets **403**, and the denial appears in the audit log as `auth.denied`

## Organizations, sites, contacts
- [ ] Create an organization; duplicate name (any capitalization) is refused
- [ ] Add a site and a contact; a duplicate contact email in the same org is refused, the same email in another org is allowed
- [ ] "Make primary" moves the primary flag (only one primary per org)
- [ ] Archive then restore an organization, site and contact; archived ones are hidden from the default list

## Audit
- [ ] After each change above, Audit log shows the matching row with who, what and before/after values
- [ ] Deactivate a user in Users: their open session stops working immediately
- [ ] You cannot change your own role or deactivate yourself

## Platform
- [ ] `/api/docs` lists every endpoint with descriptions
- [ ] `docker compose up -d --build` starts cleanly on your VM (it was verified in the dev sandbox; your VM adds real DNS/HTTPS and Entra)
- [ ] Run the backup script once and do the restore drill from `docs/BACKUP_RESTORE.md`
