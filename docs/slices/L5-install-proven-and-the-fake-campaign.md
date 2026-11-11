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
