# Portal polish: what to verify manually

Needs: the portal multi-tenant app registration (docs/PORTAL_SSO.md) and a client test tenant with a user. The portal turned on; two clients, each with a contact; an admin login.

## Sign in with Microsoft
- [ ] Set the client's *Client Entra tenant ID* on its organization page; the contact has portal access and a matching email
- [ ] `/portal` shows *Sign in with Microsoft* above the email form; a FIRST sign-in from the client tenant returns to `/portal?sso=confirm` with "Check your email: we sent a link to confirm your Microsoft account. It works once." and nothing is linked yet
- [ ] The contact receives "Your sign-in link for ...: confirm your Microsoft account"; opening the link signs in and the contact card then shows *Microsoft linked*; opening it a second time is refused
- [ ] A later *Sign in with Microsoft* lands straight in the portal (no email)
- [ ] Same-browser rule: unlink, sign in with Microsoft in browser A, open the confirm email in browser B (or a private window): you are signed in but the card does NOT show *Microsoft linked*; the audit log shows `portal.sso_link_skipped` with reason `different_browser`. Repeat from browser A to link
- [ ] Changing the organization's tenant id removes *Microsoft linked* from its contacts and signs them out
- [ ] A user from a tenant that is not listed on any client is sent back to `/portal?sso=denied` with the "could not sign you in with Microsoft" message
- [ ] The emailed one-time link still works for the same contact
- [ ] *Unlink Microsoft* on the contact card removes the badge (org:write users only)
- [ ] With SSO not configured, the button is not shown

## Files on tickets
- [ ] On an open ticket, attach a file (for example a .png): it is listed and downloads as a file
- [ ] The staff ticket's Attachments card shows it with a *Portal* badge and the contact's name
- [ ] A file over 10 MB is refused before anything is sent
- [ ] A disallowed type (for example .exe) is refused; the allowed list is txt, log, csv, pdf, png, jpg, jpeg, gif, webp, doc, docx, xls, xlsx, ppt, pptx, zip, eml, msg
- [ ] On a closed ticket there is no upload control; resolved and waiting-on-customer tickets still accept files
- [ ] A contact of the second client cannot see or download the first client's files (try the download URL directly: "not found")

## My details
- [ ] *My details* shows the email read-only with "Contact us to change your email"
- [ ] Change name, phone and title, save: "Saved" appears and staff see the new values
- [ ] An invalid value shows an inline error

## CSV exports
- [ ] *Export tickets (CSV)* on Tickets opens cleanly in a spreadsheet and only lists that contact's visible tickets
- [ ] *Export invoices (CSV)* appears only for billing contacts; totals and balances are correct
- [ ] *Export devices (CSV)* appears on Devices for contacts who may see devices
