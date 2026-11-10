# Editor's Notes

Each note is one file in this folder. To write one:

1. Open `_template.md`, click the copy icon to copy its text.
2. Go back to this folder, click **Add file → Create new file**.
3. Name it with the date and a short title, for example `2026-11-16-layoffs-and-readiness.md`.
4. Paste the template, write your note, and set `draft: false` when it's ready.
5. Click **Commit changes**. The note appears on the site within a few minutes.

## The top block

```
---
title: "Your headline"        # required; keep the quotes if it has a colon
date: 2026-11-16              # required; a future date publishes on that day
summary: "One sentence."      # optional; shown on the front page
draft: true                   # true = not on the site yet
---
```

## Formatting (Markdown)

- `## Heading` for a section heading
- `*italic*` and `**bold**`
- `[link text](https://example.org)` for links
- `> quote` for a quotation
- A blank line starts a new paragraph

To fix or remove a published note, edit the file or delete it, then commit.
If something is wrong with a note, the update stops and GitHub emails you
the reason (for example, a missing date).
