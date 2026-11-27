# Changelog

## 0.1.6 (2026-11-26)

Its reads made with the account's key are asked only from the page too. The user, 2026-11-26: "Yes, closed by
default" (liminal-libs 1.107.0: a hook a plugin declares for no one is its page's alone), and of these reads:
"Page-only".

- **What only the page asks now, beside its changes**: `refresh`, `droplets`, `domains`, `records`, `firewalls`, `ssh_keys`, `balance`.
  Each sends requests to the provider as you and returns what the account holds. Until now any plugin, and any program
  on this machine through the platform, could ask them. Another plugin's ask and an ask that names no one are refused
  (403) in words, and liminal-platform asks its login whether you are at the page (401 otherwise).
- `present` and `status` stay reads anyone here may ask: the status is what was read last, and no request is made to
  answer it. The background's reads and the command line call the code themselves: those are not asks.
- Every hook now says who may ask it, so the library's `conformance.warnings` is empty.

Tests: "its reads by anyone" became "its reads by the page alone": each read refused to another plugin and to no one,
nothing sent for it, and answered for the page; a test that no hook is left undeclared. They fail when a read is taken
out of `PAGE_ONLY_HOOKS`, on liminal-libs 1.106.0 and on 1.107.0 alike. No new requirement: the word is liminal-libs
1.66.0's.

## 0.1.5 (2026-11-25)

Its changes are asked only from the page (`PAGE_ONLY_HOOKS`, liminal-libs 1.66.0's word): the independent review's
finding PLT-H1, and the sweep of every plugin's hooks that followed it. The user, 2026-11-25, chose "Plugin releases":
each plugin says which of its hooks only its page asks.

- **What only the page asks**: `power`, `set_record`, `remove_record`, `add_firewall_rule`, `remove_firewall_rule`,
  `add_ssh_key`, `remove_ssh_key`, `ddns_update` and `ddns_take_over`. Another plugin's ask of one is refused (403),
  and so is an ask that names no asker; liminal-platform 0.34.0 refuses one over HTTP (401) unless its login shows
  that you are at the page. A platform that holds no login asks them as before. The 401 rests on the login's word
  that your browser is signed in, and a local login signs `secret` and `default` in with no password, so a program on
  this PC can sign itself in and ask them still: a proof that a program cannot make is the login's and the platform's
  to give, not this plugin's.
- **Before**, the platform handed an ask of any program on this PC (`POST /api/machines/digitalocean/ask`, with a
  header anyone can send and a Host the client chooses, no sign-in) straight to the hook it named, and the hook used
  your token. The page's dialogs were the only confirmation, and a second confirmation is an argument the asker sets:
  `power` with `[id, name, "power_off", true]` cut a Droplet's power; `add_firewall_rule` with `accept_risky` true
  opened PostgreSQL or SSH to the whole internet, and `remove_firewall_rule` took out the rule letting SSH in;
  `ddns_take_over` with `[host, null, true]` pointed a Dynamic DNS host holding a live server's address at this
  network. `set_record` added an MX record beside yours and `remove_record` removed a record, neither asked twice.
- **As before**: its reads (`present`, `status`, `refresh` and the lists) are asked by anyone. The background (the
  account read every quarter of an hour, the Dynamic DNS passes) and the command line call the plugin's code
  themselves, not through an ask. The library floor stays 1.49.9: a library before 1.66.0 does not read the word, and
  asks the hooks as it did.
- Tests: `tests/test_who_asks.py`, through the library's own App over the stand-in DigitalOcean: each of the nine
  refused to another plugin and to no one, no request made; the same nine asked from the page, each sent; the reads
  answered to a plugin; a Dynamic DNS pass run by the plugin's own code. A hook taken out of `PAGE_ONLY_HOOKS` fails
  it. Skipped on a library before 1.66.0.

## 0.1.4 (2026-11-24)

A record's "Replace it" bound to what its refusal showed (the review of 2026-11-21, item 26). `set_record` with
`accept_replace` replaced whatever the record held when the confirmation came, which need not be the value the
refusal named. The page sends the same arguments again with its second confirmation, so the refusal now keeps the
record and the value it showed (by the change asked, for 15 minutes, 32 at most), and the accepted call is refused,
nothing sent, when the record holds anything else now, or when no refusal showed it lately: set again, the new
refusal names what it holds now. Binding as liminal-libs 1.49.9's take-over binds `holds`. Test: an accept never
shown, then one whose record changed after its refusal, both refused with nothing written; asked again, replaced.

## 0.1.3 (2026-11-14)

Drawn under the platform's Cloud plugins section, in the list on the left (the user: "classify the cloud plugins under the 'cloud plugins' section which should be on the far left"): `SECTION = "cloud"`. That is liminal-libs
1.51.0's machine-plugin attribute; liminal-platform 0.25.0 draws it, and an older platform keeps the plugin under Machine
plugins. Nothing else changes.

## 0.1.2 (2026-11-11)

What the re-verification of the audit's fixes found in Dynamic DNS (liminal-libs 1.49.7). Needs liminal-libs>=1.49.7.

- **Take over… is asked twice**: it sets the record at once and drops every address it holds. `ddns_take_over(host,
  holds, accept_take_over)` keeps its checks (the host is in the setting, the record still holds what the page showed),
  then asks the keeper, which refuses (`TakeOverRefused`, naming `accept_take_over`) unless that is exactly true; the
  page asks it as a second confirmation ("Drop what it holds?"). A "true", a 1 or a "yes" from another program is
  refused like none.
- **A host taken out of the setting is let go, while the plugin ran or not** (`Keeper.settle`, replacing 0.1.1's let-go
  of this process alone, which a restart forgot): settled with the whole setting after each refresh and in the
  background, once the account's domains are read, and only when the login answered with the token among what it
  furnished (a login that cannot be asked, or one signed out, lets nothing go). Put back later, the host is not its
  own: a record it set is left as it is, its row offering Take over… again.
- The third round of checks (liminal-libs 1.49.8, needed now): a take-over is single-use, used up once its write lands
  (the host is then the keeper's own); and only the serving platform's plugin settles, never its own command line or
  the platform's one-shot commands, whose setting may lack the hosts (they would empty the shared `ddns.json`). The
  guard comes before the settle's bookkeeping, so a settle not made is never marked as made.

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

Needs liminal-libs>=1.49.9: a take-over's consent is bound to the addresses it drops (a record changed after
a failed write is asked about again); the state file keeps each take-over's addresses.

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
