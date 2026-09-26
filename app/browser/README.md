# Browser boundary

`BrowserTool` exposes named safe actions: open, navigate, search, read page,
and extract visible text. Hosts must configure `HERMES_BROWSER_ALLOWED_HOSTS`;
an empty allowlist denies navigation. The backend has no cookie jar, does not
expose form values, passwords, cookies, or tokens, and redacts common secret
patterns from visible text.

Uploads, form submission, messaging, account changes, purchases,
authentication, and security changes are represented as sensitive actions and
require the host PermissionEngine policy. The model cannot run JavaScript,
provide browser scripts, modify the host allowlist, or access browser session
internals.