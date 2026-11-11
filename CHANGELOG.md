# Changelog

## 0.1.1 (2026-11-11)

What the audit of the cloud plugins found before any key went in (session 87405e6a: eight reviewers, a skeptic per
finding; its DigitalOcean section: 2 blockers, 6 should-fix, 4 minor). Needs liminal-libs>=1.49.2.

- **Dynamic DNS changes only what is its own** (liminal-libs 1.49.2's keeper; the audit: a listed host's live record
  pointed at home within a minute, unasked): a host with no A record, one already pointing here or holding the address
  it set last (kept in `digitalocean/ddns.json` under the platform's folder, so a restart still knows it), one taken
  over. Any other record (another address, or several) is left as it is and said so, with **Take over…** on its row
  (the hook `ddns_take_over(host, holds)`: the record read again and refused if it holds other than the confirmation
  named, then a pass for it); several addresses are never cut to one unasked; a write sets the host to exactly one
  address. **Update DNS now** is a confirmed form now, never one click. A host taken out of the setting is let go. The
  address is asked again just before a write.
- **The background starts only when the platform attaches the plugin** (App.NAME "platform"): the charts app run
  alone, which attaches every plugin it finds, starts none of it. Detached, a pass under way ends before its next write,
  and the thread asks no login and reads none of the environment after the detach (it wrote once more before).
- **A second confirmation counts only when it is exactly true**, as the page sends it (`accept_hard`, `accept_risky`,
  `accept_replace`): a "false", a "yes" or a 1 from another program on this machine is refused like none.
- **Deny rules are kept**: DigitalOcean documents them (its reference's rule object, in Add Rules to a Firewall too:
  "This may be one of `allow` or `deny`", allow unless set; its release note of August 2026). Every deny over SSH or
  every port is asked twice now, added or removed, whatever the firewall applies to. A deny added is read back: one
  DigitalOcean took as an allow is removed again at once, and the answer says so. The API card links that release
  note (every address on it checked again: all answer).
- **Wider openings are asked twice**: every port but SSH (a range of 1,000 ports or more), the other ways in (Telnet,
  Remote Desktop, VNC, WinRM, Docker's API, the databases' ports) and wide sources (public ranges of a /8 or more in
  all, 0.0.0.0/1 with 128.0.0.0/1, an IPv6 /32), not only SSH or every port from 0.0.0.0/0.
- **A record's value replaced is asked twice** (`accept_replace`): the refusal names what it holds now; its TTL or
  priority alone is asked once. The command line's `set` asks a second yes likewise.
- **A token holding a space or a line break is never sent** (a wrapped paste set outside the page): the status asks for
  it again, and no part of it is shown (liminal-libs 1.49.2 scrubs a secret's lines too).
- The power dialog says that powering a Droplet on starts no new charge (it was billed while off): asked once.
- The SSH key form says never to paste the private key (liminal-platform 0.20.1 logs no form's values).

Left as they are, as the user's calls: the account read every quarter of an hour while the platform has it attached,
and the variable DIGITALOCEAN_TOKEN, which Terraform and PyDo read too.

The platform's one-shot commands (status, machine: `PlatformApp.once`, liminal-platform 0.20.1) start none of its background work.

## 0.1.0 (2026-11-11)

The first release (the user: "ALSO i would like to add two new plugins, Digital Ocean and LINODE"; for the cloud plugins
the user chose "Free changes only"; and of every plugin: "each plugin should reflect the the API its attached to, and
present links that provide documentation, the plugin interface should more or less contain what it already has, BUT, it
should also expose more of what the API is about"):

- the settings read through the library's Login interface alone, as pairs named by their variables (`digitalocean-token`
  for DIGITALOCEAN_TOKEN, `digitalocean-ddns-hosts`, `digitalocean-ddns-minutes`): the platform's EnvironmentLogin
  today, the login app's pairs once the platform binds it; no settings file; the status names the settings set, never a
  value; the token is taken out of every error's words;
- the account through DigitalOcean's API v2 (liminal-libs 1.49.0's RestClient: a Bearer token, its lists read 200 a page
  and their next pages followed on DigitalOcean's API host alone, a rate limit waited out, a read tried again after a
  server's error, a write never): the account and its balance, the Droplets and GPU Droplets with their prices a month
  and an hour, the domains and their records (at most 12 domains' records a refresh), the cloud firewalls and their
  rules, the volumes, the SSH keys, the reserved IPs, and how many Kubernetes clusters, load balancers, databases, apps,
  snapshots, custom images, projects and VPCs the account holds; a part the token's scopes do not reach said beside the
  rest, naming the scope;
- only the free changes, each through a form the platform's page confirms: a Droplet powered on, shut down, rebooted,
  powered off or power cycled (the hard two asked twice, saying unsaved data is lost; the Droplet read again first);
  a DNS record set (changed in place or made) and removed, every other record kept since none is sent, refused when it
  could do other than confirmed; a cloud firewall's rule added and removed through its rules' own calls (its other
  rules, Droplets and tags kept), the risky ones asked twice (SSH or every port opened to the whole internet, a deny
  over SSH, the rule letting SSH in removed); an SSH key added and removed (a private key refused);
- nothing that starts a charge or destroys: no Droplet, volume, snapshot, backup, reserved IP or anything billable made,
  nothing resized, rebuilt, restored or destroyed, backups never turned on; a test reads the client's source for those
  calls, which are named on the API card alone; the page says plainly that a powered-off Droplet still bills;
- Dynamic DNS through DigitalOcean's DNS (liminal-libs' Keeper): this network's IPv4 address asked of OpenDNS's and
  Google's name servers, each host's A records by their full name, one changed in place or made, a host with several
  left as it is; its table on the page and Update DNS now;
- its API card (plugin API 2.2): DigitalOcean's API with every part of its reference (65 areas, 18 of them used), the 26
  calls it makes and 37 others worth knowing (those that change something, those that cost), its auth, limits and costs
  and DigitalOcean's pages (reference, limits, tokens, scopes, pricing, status, release notes, the OpenAPI
  specification, doctl, PyDo), each address checked on 2026-11-11; its facts (the requests made, the last answer, the
  rate limit left, when the account was read) asking nothing;
- while attached to the platform app: the account read every quarter of an hour, the Droplets again half a minute after
  a power action, the Dynamic DNS hosts every DIGITALOCEAN_DDNS_MINUTES (5) in a thread of its own; detached, nothing
  runs. Valid while the token is set and the last read worked or is untried; a failed read tried again a quarter of an
  hour later, or at once when the settings change;
- `python -m plugin_platform_digitalocean status | servers | domains | records | firewalls | keys | ddns | power | set |
  remove` (the changes ask "yes" first, a hard power-off twice).
