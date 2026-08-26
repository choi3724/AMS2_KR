# AMS2 Project Memory

## GitHub Release Korean text encoding rule

This rule is mandatory for every future AMS2 Korean patch release.

1. Do not place Korean release title or body literals directly in a BOM-less Windows PowerShell 5 `.ps1` file.
2. Keep the intended title and body in a UTF-8 Markdown file.
3. Read that file with strict, explicit UTF-8 decoding:
   - `New-Object Text.UTF8Encoding($false, $true)`
   - `[IO.File]::ReadAllBytes(...)`
4. Serialize the GitHub API payload to JSON, then send explicit UTF-8 bytes rather than a PowerShell string:
   - `(New-Object Text.UTF8Encoding($false)).GetBytes($json)`
5. After creating or updating a release, fetch it from GitHub and verify:
   - release title exact match
   - release body exact match with the UTF-8 Markdown source
   - replacement character count is zero
   - repository Markdown files are byte-exact with the local Git commit
6. A Release metadata correction must not replace or modify the tested ZIP asset.

Root cause recorded on 2026-08-26: Windows PowerShell 5 interpreted Korean literals in a BOM-less UTF-8 release script as ANSI. Git repository files and the ZIP were correct; only the GitHub Release title and body were corrupted.
