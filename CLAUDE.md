# Instructions for AI edits — Apulainen.pro

Cleaning and window washing site (Apulainen.pro, Ksm Service Oy, Y-tunnus 3528429-3). Site language: Finnish only. Owners: Sergei (Russian, edits via Claude) and a business partner (may edit via GPT Codex).

- PILOT: the site must stay `noindex` (meta robots, `public/robots.txt`, `public/_headers`) until the owners approve the move from Tilda. Never remove noindex on your own.
- SEO migration: every URL in `migration/tilda-pages.json` must exist on the new site with the same path, or get a 301 in `public/_redirects`. Never change an existing URL without a redirect.
- Design: apulainen.pro design system (olive off-white #F4F5EF, green #2E6B45, deep #1C3A27, yellow #F2C14E for offers only; Bricolage Grotesque display + Plus Jakarta Sans body). Pages must work at 390 px.
- Contact priority: WhatsApp → form/email. Phone is never a call-to-action.
- Copy: plain Finnish, no invented stats or reviews. Prices "alk." and incl. ALV 25,5 %.
- Work on a branch and open a PR; Cloudflare builds a preview per branch.
