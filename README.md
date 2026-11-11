# plugin-platform-digitalocean

DigitalOcean for Liminal's platform: your DigitalOcean account through DigitalOcean's API, everything it holds shown,
only the changes that cost nothing made (each one confirmed first), and Dynamic DNS keeping hosts at this network's
public address through DigitalOcean's DNS.

The user's words (2026-11-11): "ALSO i would like to add two new plugins, Digital Ocean and LINODE"; for the cloud
plugins the user chose "Free changes only"; and of every plugin: "each plugin should reflect the the API its attached
to, and present links that provide documentation, the plugin interface should more or less contain what it already
has, BUT, it should also expose more of what the API is about".

## What it shows

A machine plugin of the platform (`liminal_libs.machines.MachinePlugin`, plugin API 2.2, its icon DigitalOcean's mark):

- **The account**: its email, status and team, its Droplet limit; the balance (used this month, the month-to-date
  balance, the balance before it).
- **Droplets** (and GPU Droplets): name and tags, state (on, off, being made), region, size (vCPUs, memory, disk),
  public IPv4 and IPv6 (and the private address), the price a month and an hour as DigitalOcean gives it for the
  Droplet's size, when it was made, and what they come to a month in all.
- **Domains** on DigitalOcean's DNS, and each one's **records** (name, type, data, TTL, priority, weight, port, flags,
  tag).
- **Cloud firewalls**: their status and pending changes, the Droplets and tags they apply to, and each one's inbound
  and outbound rules (allow or deny, protocol, ports, sources or destinations).
- **Volumes** (size, region, the Droplet attached), **SSH keys** (name, fingerprint, key), **reserved IPs** (the
  Droplet each is assigned to).
- **Also in the account**: how many Kubernetes clusters, load balancers, databases, apps, snapshots, custom images,
  projects and VPCs it holds (one request each).
- **A powered-off Droplet still bills.** DigitalOcean bills a Droplet until it is destroyed, powered off or not
  (bundled-plan CPU and GPU Droplets alike); the page says so beside the Droplets, in the facts and in every power
  confirmation. Volumes bill whether they are attached or not, a reserved IPv4 address while it is not assigned.

## What it changes, each confirmed (all free)

- **Power…** on each Droplet: **power on** (when it is off; asked once, since it starts no new charge: DigitalOcean
  billed the Droplet while it was off too, and the dialog says so); **shut down** and **reboot** (graceful: its system
  is asked); **power off** and **power cycle** (hard: the power is cut at once and unsaved data is lost, so they are
  asked twice; DigitalOcean advises a shutdown first, and a power-off only when that does not work). The Droplet is
  read again first: its name, its state, not locked by an action under way.
- **Set a record…** in each domain: an A, AAAA or CNAME changes the host's record of its type in place (made when it
  has none); a TXT, MX, NS, CAA or SRV record is added beside the others (or changed in place when one with the same
  data is there: its TTL, its priority). **Changing what a record holds is asked twice**: the refusal names what it
  holds now ("www A 203.0.113.10 is there now"), and the page's second confirmation says it is replaced. **Remove** on
  each record. DigitalOcean changes records one at a time, so every other record is kept: none is ever sent. A change
  is planned on the records at that name read just before it, and refused, with nothing sent, when it could do other
  than what was confirmed (several A records at the host, a CNAME beside other records, a record changed since it was
  shown). The SOA record and DigitalOcean's own NS records at the domain itself have no Remove.
- **Add a rule…** to each cloud firewall, and **Remove** on each rule: only the rule is sent (POST or DELETE of the
  firewall's rules), so its other rules, its Droplets and its tags are kept; a rule removed is sent back as it was
  read. A rule allows or denies: DigitalOcean's rules take an action, allow unless set ("This may be one of `allow` or
  `deny`", its reference's rule object; deny rules came in August 2026), and a deny takes precedence over the allow
  rules matching the same traffic. A deny rule added is read back, and were DigitalOcean to take it as an allow it is
  removed again at once and the answer says so. **Asked twice**: an allow opening SSH (port 22), another way in
  (Telnet, Remote Desktop, VNC, WinRM, Docker's API, MySQL, PostgreSQL, Redis, MongoDB, Elasticsearch, memcached) or
  every port (a range of 1,000 ports or more) to the whole internet or a wide part of it (public ranges of a /8 or more
  in all, an IPv6 /32); any deny over SSH or every port, added or removed, whatever the firewall applies to now; and
  removing the rule letting SSH in to the firewall's Droplets (a cloud firewall blocks what no rule allows).
- **Add a key…** and **Remove** on each SSH key: new Droplets can be made with a key added; the Droplets made with a
  key removed keep it (DigitalOcean copied it into them when they were made). A private key pasted by mistake is
  refused: nothing of it is sent to DigitalOcean (and liminal-platform 0.20.1 and later log no form's values).

On the platform's page, each form's confirmation names the exact change; a hard power-off, a risky rule or a record's
value replaced is refused first, and the page then asks a second time ("Cut its power?", "Add this rule anyway?",
"Replace what it holds?"), sending it only on that second yes. A second confirmation counts only when it is exactly
true, as the page sends it: a "yes", a "false" or a 1 from another program on this machine is refused like none. Its
answer says what was done.

## Dynamic DNS

Each host of `DIGITALOCEAN_DDNS_HOSTS` (in one of the account's domains) is kept at this network's public IPv4 address,
through the library's keeper (liminal-libs 1.49.2), which changes only what is its own: every few minutes
(`DIGITALOCEAN_DDNS_MINUTES`, 5) the address is asked of DNS (`myip.opendns.com` of OpenDNS's resolver, else Google's
`o-o.myaddr.l.google.com`, each asked by its IPv4 address), and the host's A records of DigitalOcean's DNS by their full
name.

- **Its own**, and kept current: a host with no A record (one is made, a TTL of 60 seconds), one already pointing at
  this network, one holding the address the keeper set last (after a restart too: what is its own is kept in
  `digitalocean/ddns.json` under the platform's folder, `LIMINAL_PLATFORM_DIR` or the data folder's `platform/`), and
  one you took over. A record of its own that differs is changed in place (its TTL kept).
- **Not its own**, and left as it is: a host holding another address (a live server's, set by hand) or several. Its
  row says what it holds and offers **Take over…**: confirmed (the dialog names what it holds and that whatever answers
  there stops answering at that name), the host is pointed at this network on a pass at once, and kept there; a host
  that held several addresses then keeps one A record. Several addresses are never cut to one unasked.
- Just before a write the address is asked again: a stale one is never written back. **Update DNS now** is confirmed
  first, and sets every host of its own (never one that is not). A host taken out of the setting is let go (no longer
  its own). Once the plugin is detached, a pass under way writes nothing more.

The domain's registrar must name DigitalOcean's name servers (ns1, ns2 and ns3.digitalocean.com) for the record to be
the one the world sees.

## Setting it up

1. **Make a personal access token**: https://cloud.digitalocean.com/account/api/tokens (Applications & API > Tokens >
   Generate New Token), choose its expiry, and **Custom Scopes** limited to the scopes below (a token's scopes are
   fixed when it is made: a missing one answers 403, and the plugin's page names the scope a part lacks). Copy it: it
   is shown once.
2. **Enter the settings**: on the platform's page, the plugin's **Settings…** asks for each (the token typed hidden; a
   field left empty keeps its value; no value is ever shown back). They are pairs the plugin asks of the login of the
   app it is attached to, each named by its variable (DIGITALOCEAN_TOKEN is the pair `digitalocean-token`): today the
   platform's login keeps them as your user environment variables, and the plugin reads them at once. Setting the
   variables yourself works too.

| Variable | | |
|---|---|---|
| `DIGITALOCEAN_TOKEN` | the API (secret) | the personal access token of step 1 |
| `DIGITALOCEAN_DDNS_HOSTS` | Dynamic DNS | optional: hosts kept at this network's address, comma separated, each in one of the account's domains: `home.example.com`, `@.example.com` (the domain itself) |
| `DIGITALOCEAN_DDNS_MINUTES` | optional | minutes between Dynamic DNS checks, 1 to 1440 (5 unless set) |

The plugin keeps no settings file and never shows the token: its status names the settings that are set.

### The token's scopes

DigitalOcean's scopes (https://docs.digitalocean.com/reference/api/scopes/) are `resource:action`. The plugin needs these
and no other: the reads,

`account:read`, `billing:read`, `droplet:read`, `domain:read`, `firewall:read`, `block_storage:read`, `ssh_key:read`,
`reserved_ip:read`, `tag:read`, `image:read`, `snapshot:read`, `kubernetes:read`, `load_balancer:read`,
`database:read`, `app:read`, `project:read`, `vpc:read`

and the writes of the free changes,

`droplet:update` (the power actions), `domain:create`, `domain:update`, `domain:delete` (the records: in DigitalOcean's
specification a record made asks `domain:create` with `domain:update`, one deleted `domain:delete` with
`domain:update`), `firewall:update` (a firewall's rules), `ssh_key:create`, `ssh_key:delete`.

A Read Only token (`api:read`) shows everything and changes nothing. Scopes cannot be narrower than DigitalOcean makes
them: `droplet:update` also allows Droplet actions the plugin never sends (turning backups on, which costs, renaming,
changing the kernel; resizing, rebuilding, restoring and snapshots need scopes beyond these), `domain:delete` also
deletes a whole domain, and `firewall:update` also replaces a firewall whole. Keep the token as secret as a password.

## Its API

It attaches to **DigitalOcean's public API v2** (https://api.digitalocean.com/v2): JSON over HTTPS, a personal access
token as a Bearer token. Its card on the plugin's page (plugin API 2.2, `card.py`) lists every part of the API's
reference (its 61 public areas and the 4 of its Inference APIs, the ones the plugin uses first, the rest under "more of
the API"), the 26 calls the plugin makes and what for, and 37 others worth knowing (those that change something, and
those that start or raise a charge); its limits, its costs and DigitalOcean's pages, verified 2026-11-11:

- the API reference: https://docs.digitalocean.com/reference/api/reference/ (overview:
  https://docs.digitalocean.com/reference/api/)
- rate limits, pagination and errors: https://docs.digitalocean.com/reference/api/reference/public-apis/
- making a token: https://docs.digitalocean.com/reference/api/create-personal-access-token/, its scopes:
  https://docs.digitalocean.com/reference/api/scopes/, the tokens: https://cloud.digitalocean.com/account/api/tokens
- pricing: https://www.digitalocean.com/pricing and https://docs.digitalocean.com/products/droplets/details/pricing/
- status: https://status.digitalocean.com/; release notes: https://docs.digitalocean.com/release-notes/
- the OpenAPI specification: https://github.com/digitalocean/openapi; doctl: https://docs.digitalocean.com/reference/doctl/;
  PyDo: https://docs.digitalocean.com/reference/pydo/

What the plugin learned of it while it ran (the requests made, the last answer, the rate limit left and when its oldest
request expires, when the account was read) is the card's facts, asking nothing to say them.

## What it never does

No Droplet, volume, snapshot, backup, reserved IP, load balancer, Kubernetes cluster, database or app is made; nothing
is resized, rebuilt, restored or destroyed; backups are never turned on; no domain is added or deleted; no firewall is
made, replaced whole or deleted, and its Droplets and tags are never changed. The client's source holds none of those
calls (its writes are the eight free ones; a test reads it for them): they are named on the API card alone. The token is
never shown, logged or written; every error's words have it taken out. Nothing runs while the plugin is detached.

## Valid, and the platform

The plugin is valid while the token is set and the last read worked, or has not been tried yet: the platform disables
a plugin that is not valid. A part the token cannot read (a scope it lacks) is said beside the rest, not taken for the
plugin's failure. A read that failed is taken as untried a quarter of an hour later (the platform attaches it again and
it is tried again), or at once when its settings change. A token holding a space or a line break (a wrapped paste set
outside the page) is never sent: the status asks for it again.

While the platform has it attached, it reads the account every quarter of an hour (about 20 to 30 requests; the records
of at most 12 domains), the Droplets again half a minute after a power action, and the Dynamic DNS hosts every few
minutes. Another app attaching it (the charts app run alone attaches every plugin it finds) starts none of it. Detached,
nothing of it runs: a step under way ends there, asking no login, reading none of the environment and writing nothing.
Its status is what was read last (no request is made to answer it).

## Its hooks

`present`, `status` (the summary, the facts, `tables`, `actions`, `forms`), `refresh()`, the reads `droplets()`,
`domains()`, `records(domain)`, `firewalls()`, `ssh_keys()`, `balance()`, and the changes
`power(droplet_id, name=None, action="shutdown", accept_hard=False)`,
`set_record(domain, name, rtype, data, ttl=None, priority=None, port=None, weight=None, flags=None, tag=None, accept_replace=False)`,
`remove_record(domain, name, rtype, data=None, record_id=None)`,
`add_firewall_rule(firewall_id, firewall=None, direction="inbound", protocol="tcp", ports=None, action="allow", addresses=None, droplets=None, tags=None, accept_risky=False)`,
`remove_firewall_rule(firewall_id, firewall=None, direction="inbound", rule="", accept_risky=False)`,
`add_ssh_key(name, public_key)`, `remove_ssh_key(fingerprint, name=None)`, `ddns_update(force=True)`,
`ddns_take_over(host, holds=None)`. A refusal is
`errors.Refusal` (a ValueError); its `accept` names the argument the page's second confirmation sets. A change's
answer: `said`, `lines`, `ok`, `changed`.

## From the command line

Its settings read from the environment (as this shell has them):

```
python -m plugin_platform_digitalocean status
python -m plugin_platform_digitalocean servers
python -m plugin_platform_digitalocean domains
python -m plugin_platform_digitalocean records example.com
python -m plugin_platform_digitalocean firewalls
python -m plugin_platform_digitalocean keys
python -m plugin_platform_digitalocean ddns [--now]
python -m plugin_platform_digitalocean power web-1 on|off|reboot|hard-off|cycle
python -m plugin_platform_digitalocean set example.com home A 203.0.113.7 --ttl 300
python -m plugin_platform_digitalocean remove example.com @ TXT "google-site-verification=..."
```

`power`, `set` and `remove` ask "yes" first (`hard-off` and `cycle` twice, `set` again before what a record holds is
replaced); `off` is the graceful shutdown. The cloud
firewalls' rules and the SSH keys are changed from the platform's page. `--json` before the command prints the answer
as JSON.

## Limits

DigitalOcean's API allows 5,000 requests an hour and 250 a minute per token (listing SSH keys, 10 a minute); a refresh
asks about 20 to 30, a Dynamic DNS check one a host. A rate limit is waited out (its Retry-After, at most 30 s) by the
library's REST client, which also tries a read again after a server's error, never a write.

## Install

Once its repository is published (it is not yet):

```
pip install "plugin-platform-digitalocean @ git+https://github.com/pcxmac-dev/plugin-platform-digitalocean@main"
```

or, for the platform's preview, a checkout in the plugin directory (`LIMINAL_PLUGINS`). Its tests use stand-ins for
DigitalOcean and DNS alone (`python -m pytest`): none reaches DigitalOcean or the network, but the card's page check
(`LIMINAL_VENDOR_PAGES=1`), which asks each of the card's addresses once.
