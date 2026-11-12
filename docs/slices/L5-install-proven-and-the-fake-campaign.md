# L5 install proven and the fake campaign

## Starting list (from the L4 refactor proof)
- ZERO: the fake campaign check runs on `windows-latest` only (L4 merge, 0.7.2). On `ubuntu-latest` it differed in `refused`
  only: 0 entries against the 21 saved. Cause (read from the runner): its `/etc/resolv.conf` names `nameserver 127.0.0.53`,
  a local stub resolver. The guard allows loopback, so the email-validity step's DNS packets (`dns.resolver.Resolver()` reads
  that file) went to the stub, were not refused and were not logged. The path separators and the short Windows temp name
  (`RUNNER~1`) were the other two differences; the compare now absorbs both. For Linux: make the guard see DNS sent to a
  loopback port 53 (refuse and log it, as it does for `getaddrinfo`), or give the campaign its own resolver setting, then
  save a Linux-side result or compare without `refused`. This also means: on a machine with such a stub, the guard as it is
  lets a DNS question reach the outside through the stub.
- FIRST: Companies House's address becomes a setting, so that source can be faked. It is fixed in the code today (`providers/registry.py` `CH_BASE`) and was off in both versions of the proof.
- 0.6.14 installed the way its own README says fails at enrich (`selectolax` 1.0.2 `ImportError`: its open-ended `selectolax>=0.3.21` follows to a release that removed the backend it uses). The upgrade note must say it.
- The socket guard is Python-level: asyncio's Windows `ConnectEx` and native sockets are not covered. One probe through `asyncio.open_connection` inside the guard settles it.
- Not shown at all by the proof: the real sources, the browser, the agent call, sending.

# Build (0.7.3) — first part of L5

Run `l5-build`, 2026-11-12. Items in the order of the brief; per item the text of what the change must do is written before the
code, the reading check after it.

## Item 0 — the Linux DNS gap

**Must do (written before the change).** In `tests/fixtures/e2e/harness/sitecustomize.py` a connection or datagram whose destination
port is 53 (UDP `sendto`, TCP/UDP `connect`/`connect_ex`) is refused and logged exactly like an outside call, whatever the address
(loopback included). A loopback address on any other port stays reachable, so the fake world's own server (port 18765) and the
probe's ephemeral loopback listener are untouched. The log entry has the same shape (`kind`, `host`, `port`, `caller`).

**Which refused-list cells move.**
- Windows (saved result made there): NONE. Its system resolver is not loopback, so its packets were already refused and normalized
  to the one `<system resolver>` entry; the 20 fallback entries (8.8.8.8, 1.1.1.1) are unchanged.
- Linux (`ubuntu-latest`): 0 entries → the same 21 as saved. The stub `127.0.0.53` now refuses the probe question
  (`sendto 127.0.0.53:53`, normalized to `<system resolver>`), `get_resolver()` falls to its public fallbacks, whose refused sends
  are the same 20 entries as on Windows. The saved result stays unchanged; if Linux shows any other difference, that is not predicted.
- Nothing else in the result moves: the request log and the tabs do not depend on DNS packets (names of the `.example` sites resolve
  inside the guard, not by packet).

**Seen red first.** `harness/probe.py` gets two cases (UDP `sendto` and TCP connect to `127.0.0.53:53`) and `--probe` demands that the
guard log holds both (TCP to a closed loopback port is refused by the OS anyway, so the log, not the exception, is the evidence).
