# Vendored frontend libraries

These files are committed so a self-hosted box never depends on a third-party
CDN. They are the minified release builds, used exactly as shipped upstream.

| File | Version | License | Source |
| --- | --- | --- | --- |
| htmx.min.js | 2.0.10 | 0BSD | https://unpkg.com/htmx.org@2.0.10/dist/htmx.min.js |
| alpine.min.js | 3.17.2 | MIT | https://unpkg.com/alpinejs@3.17.2/dist/cdn.min.js |

Update these files only from a tagged upstream release, and record the new
version here in the same commit.