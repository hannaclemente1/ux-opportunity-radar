# UX Opportunity Radar — live job board

A deployable, responsive UX/Product Design job board with an **hourly public-feed refresh**, filters, posting age, experience, salary, company excerpt, direct application links, and browser-local application tracking.

## Launch with a permanent URL (GitHub Pages)

1. Create a **public GitHub repository** (for example `ux-opportunity-radar`).
2. Upload the contents of this ZIP to the repository root, including `.github/workflows/update.yml`. Use the `main` branch.
3. In GitHub → **Settings → Pages**, choose **Deploy from a branch**, `main`, `/ (root)`, then Save.
4. In GitHub → **Actions**, enable workflows if prompted. Select **Refresh UX job board** → **Run workflow** to populate the first feed immediately.
5. In GitHub → **Settings → Actions → General → Workflow permissions**, enable **Read and write permissions** if the refresh workflow cannot commit `data/jobs.json`.
6. Your permanent dashboard URL will be `https://YOUR-GITHUB-USERNAME.github.io/ux-opportunity-radar/` (replace the name with your actual repository name). Bookmark it.

GitHub scheduled workflows can be delayed; hourly is the target, not a guarantee. GitHub can disable scheduled workflows on inactive repositories after 60 days.

## Important limitations

- The app is **not yet deployed** until you complete the steps above. It does not inherit ChatGPT hourly alerts and does not connect to Notion.
- Feeds: Remotive public API (remote design) and Arbeitnow public API (multiple pages). Coverage is partial and not exhaustive. Some source feeds may be cached or stale; inclusion means the listing appeared in a provider feed, not that the employer's application page was individually verified open.
- To avoid unsupported claims, applicant counts are always marked **Not available**. Neither feed provides verified counts. The UI cannot rank by verified under-30 applicant counts without adding another licensed/authorized data source.
- Minimum experience is extracted conservatively from requirement-like description text. Unclear requirements show **Unspecified**; always verify on the employer page. A range like 5–8 years qualifies because the minimum is 5.
- Location is intentionally conservative: only explicitly San Diego or U.S.-eligible remote roles are included. This can omit valid jobs.
- Salary is shown only when the feed supplies it.
- “Company summary” is a brief job-description excerpt, not a separately researched company profile.
- Application statuses are saved in your browser's localStorage and will not sync across devices or private browsing. To sync across devices you would need authentication and a database.
- GitHub Pages is a public site: do not put private personal data in the repo.
- If one provider fails and the other succeeds, the partial feed is still published; if both fail, the previous feed remains and the workflow fails visibly.

## Run locally

Run `python fetch_jobs.py`, then `python -m http.server 8000`, and open `http://localhost:8000/`. The fetch script uses only Python standard-library modules. You can inspect the generated data in `data/jobs.json`.

## Customization

Modify `fetch_jobs.py` to add authorized job sources or adjust filtering. The front end is plain HTML/CSS/JS with no build system. If you want a fully managed service with cross-device statuses and verified applicant counts, the next phase requires a hosted database, authenticated user accounts and a source that actually supplies applicant counts.
