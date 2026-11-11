# Security policy

## Reporting a vulnerability

Please do **not** open a public issue for a security hole.

Report it privately through GitHub: on the repository page open **Security -> Report a vulnerability**
(GitHub private vulnerability reporting). Include what you found, how to reproduce it, and the version
(`leadforge version`).

You get an answer within 7 days. A fix ships as a new patch version; plugin users receive it when the
plugin manifest version changes.

## Scope

- The `leadforge` Python package and its command line.
- The plugin launcher `bin/leadforge` and the plugin manifests.
- The two skills under `skills/`.

Secrets, keys and personal data must never be committed. If you find one in the repository or its
history, report it the same way.

## Supported versions

Only the newest release is supported.
