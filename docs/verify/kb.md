# Manual check: knowledge base (Phase 13)

Needs: seeded demo data (including its knowledge-base articles), an admin or tech login, a read-only login, and a portal contact for a client.

## Staff search and edit
- [ ] Knowledge base in the sidebar lists the articles with visibility and status badges.
- [ ] Type one character in the search box: nothing is searched. Type two or more: results narrow after a short pause.
- [ ] Filter by status and by visibility.
- [ ] New article: write a title, a body with line breaks, tags "vpn, setup", visibility Client, status Draft. Save. The article opens and line breaks are kept.
- [ ] Edit it, set status Published, Save. A body containing `<b>x</b>` shows as literal text.
- [ ] Archive it: the status becomes Archived.
- [ ] Sign in as read-only: the list and articles are visible, but there is no New article, Edit or Archive button.

## Ticket suggestions
- [ ] Open a ticket whose subject matches a published article: "Suggested articles" shows up to 5 links with a Client or Internal badge and a snippet.
- [ ] Open a ticket that matches nothing: the card says "No matching articles".
- [ ] Draft and archived articles never appear in the suggestions.

## Portal visibility
- [ ] Create one Internal published article, one Client draft and one Client published article, all with a shared word in the title.
- [ ] Portal > Help articles lists only the Client published article. Searching the shared word finds only that one.
- [ ] Open the Client published article: the body shows, with no status, visibility or author names.
- [ ] Open /portal/kb/<id> of the Internal article and of the draft: the page says "This article was not found."
- [ ] Archive the Client article: it disappears from the portal list.
