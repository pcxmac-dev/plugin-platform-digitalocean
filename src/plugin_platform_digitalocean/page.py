"""What the platform's page draws of the account as it was read last (the plugin's status: its tables and forms), asking
nothing of DigitalOcean. Each change is a form the page confirms first (liminal-platform's status.forms: the fields are
the hooks' arguments in order); a risky one also has a field of type accept, which the page asks as a second, explicit
confirmation when the hook refuses without it."""
from __future__ import annotations

import time
from collections.abc import Iterable, Mapping

from . import firewall as fwmod
from .api import COUNTS
from .records import CAA_TAGS, TTL_DEFAULT, TTL_MAX, TTL_MIN, TYPES, kept_by_digitalocean

ACCEPT_HARD = "accept_hard"  # power(): a hard power-off (power_off, power_cycle) accepted
ACCEPT_RISKY = "accept_risky"  # the firewall rules' hooks: a risky rule accepted
BILLING = ("A powered-off Droplet still bills: DigitalOcean bills a Droplet until it is destroyed, powered off or not "
           "(bundled-plan CPU and GPU Droplets alike), and this plugin never destroys one.")
STATES = {"active": "on", "off": "off", "new": "being made", "archive": "archived"}
POWER = {  # a Droplet's actions here: (title, what it does)
    "power_on": ("Power on", "turns it on"),
    "shutdown": ("Shut down", "asks its system to shut down, as the shutdown command would; DigitalOcean sends it but "
                 "cannot make it succeed. Off, it is still billed"),
    "reboot": ("Reboot", "asks its system to restart, as the reboot command would"),
    "power_off": ("Power off (hard)", "cuts its power at once, like pulling the plug: unsaved data is lost; asked twice. "
                  "Off, it is still billed"),
    "power_cycle": ("Power cycle (hard)", "cuts its power and turns it on again, like a reset button: unsaved data is "
                    "lost; asked twice"),
}
ACTIONS_BY_STATE = {"active": ("shutdown", "reboot", "power_off", "power_cycle"), "off": ("power_on",)}


def when(t: float | None) -> str:
    return "–" if not t else time.strftime("%b %d %H:%M", time.localtime(t))


def day(iso) -> str:
    return str(iso or "")[:10] or "–"


def cell(text, sub: str | None = None):
    return {"text": text, "sub": sub} if sub else text


def plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def money(value, places: int = 2) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return "–"
    text = f"{x:,.{places}f}"
    if places > 2:  # an hourly price: as many places as it has, at least two
        whole, _, frac = text.partition(".")
        frac = frac.rstrip("0")
        text = f"{whole}.{frac.ljust(2, '0')}"
    return f"${text}"


def addresses(d: Mapping, version: str, kind: str = "public") -> list[str]:
    nets = ((d.get("networks") or {}).get(version) or [])
    return [str(n.get("ip_address")) for n in nets if isinstance(n, Mapping) and n.get("type") == kind and n.get("ip_address")]


def droplet_names(droplets: Iterable[Mapping]) -> dict:
    return {d.get("id"): str(d.get("name") or d.get("id")) for d in droplets}


def monthly_total(droplets: Iterable[Mapping]) -> float:
    total = 0.0
    for d in droplets:
        try:
            total += float((d.get("size") or {}).get("price_monthly") or 0)
        except (TypeError, ValueError):
            continue
    return total


# -- the tables ------------------------------------------------------------------------------------------------------------
def droplets_table(droplets: list[dict], read_at, writable: bool) -> dict:
    rows = []
    for d in droplets:
        size = d.get("size") or {}
        state = str(d.get("status") or "")
        sub = "locked: an action is under way" if d.get("locked") else None
        v4, v6, private = addresses(d, "v4"), addresses(d, "v6"), addresses(d, "v4", "private")
        memory = d.get("memory")
        shape = " · ".join(x for x in (f"{d.get('vcpus')} vCPU" if d.get("vcpus") else "",
                                       f"{memory / 1024:g} GB" if isinstance(memory, (int, float)) else "",
                                       f"{d.get('disk')} GB disk" if d.get("disk") else "") if x)
        row = [cell(str(d.get("name") or d.get("id")), ", ".join(d.get("tags") or []) or None),
               cell(STATES.get(state, state or "–"), sub),
               cell(str((d.get("region") or {}).get("slug") or "–"), (d.get("region") or {}).get("name")),
               cell(str(d.get("size_slug") or size.get("slug") or "–"), shape or None),
               cell(v4[0] if v4 else "–", ", ".join([*v4[1:], *(f"private {p}" for p in private)]) or None),
               cell(v6[0] if v6 else "–"),
               money(size.get("price_monthly")), money(size.get("price_hourly"), 5), day(d.get("created_at"))]
        if writable:
            row.append(power_button(d))
        rows.append(row)
    total = monthly_total(droplets)
    note = (f"{BILLING} The prices are DigitalOcean's for each one's size"
            + (f" (≈ {money(total)} a month in all)" if droplets else "") + f" · read {when(read_at)}")
    return {"title": "Droplets", "note": note,
            "columns": [{"title": "Droplet"}, {"title": "State"}, {"title": "Region"}, {"title": "Size"},
                        {"title": "Public IPv4"}, {"title": "IPv6"}, {"title": "A month", "num": True},
                        {"title": "An hour", "num": True}, {"title": "Made"}, *([{"title": ""}] if writable else [])],
            "rows": rows, "empty": "No Droplets in this account."}


def power_button(d: Mapping):
    if d.get("locked"):
        return "–"
    if not ACTIONS_BY_STATE.get(str(d.get("status") or "")):
        return "–"
    name = str(d.get("name") or d.get("id"))
    return {"form": f"power:{d.get('id')}", "title": "Power…", "label": f"Power {name}…", "values": {}}


def domains_table(domains: list[dict], records: Mapping) -> dict:
    rows = []
    for d in domains:
        held = records.get(str(d.get("name") or "").lower())
        rows.append([str(d.get("name")), str(d.get("ttl") or "–"),
                     f"{len(held):,}" if isinstance(held, list) else "not read"])
    return {"title": "Domains", "note": "on DigitalOcean's DNS (served once the domain's registrar names ns1, ns2 and "
            "ns3.digitalocean.com); none is added or deleted here",
            "columns": [{"title": "Domain"}, {"title": "Default TTL", "num": True}, {"title": "Records", "num": True}],
            "rows": rows, "empty": "No domains on DigitalOcean's DNS."}


def records_table(domain: str, held, writable: bool, read_at) -> dict:
    if not isinstance(held, list):
        return {"title": f"{domain} records", "note": str(held), "columns": [{"title": "Name"}], "rows": [],
                "empty": "Not read."}
    rows = []
    for r in sorted(held, key=lambda r: (str(r.get("name") or "@") != "@", str(r.get("name") or "").lower(),
                                         str(r.get("type") or ""))):
        t = str(r.get("type") or "").upper()
        data = str(r.get("data") or "")
        short = data if len(data) <= 64 else data[:63] + "…"
        extra = ""
        if t == "MX":
            extra = str(r.get("priority") if r.get("priority") is not None else "")
        elif t == "SRV":
            extra = f"{r.get('priority')} {r.get('weight')} {r.get('port')}"
        elif t == "CAA":
            extra = f"{r.get('flags')} {r.get('tag')}"
        row = [str(r.get("name") or "@"), t, cell(short), str(r.get("ttl") or "–"), extra]
        if writable:
            kept = kept_by_digitalocean(r)
            row.append("DigitalOcean's" if kept else
                       {"form": f"remove:{domain}", "title": "Remove", "label": f"Remove {r.get('name') or '@'} {t} {short}",
                        "values": {"name": str(r.get("name") or "@"), "rtype": t, "data": data, "record_id": r.get("id")}})
        rows.append(row)
    table = {"title": f"{domain} records",
             "note": (f"read {when(read_at)} · " + ("set and removed here one record at a time: every other record is kept "
                                                    "as it is" if writable else "set and removed once the token is set")),
             "columns": [{"title": "Name"}, {"title": "Type"}, {"title": "Data"}, {"title": "TTL", "num": True},
                         {"title": "Priority, weight, port / flags, tag"}, *([{"title": ""}] if writable else [])],
             "rows": rows, "empty": "No records."}
    if writable:
        table["actions"] = [{"form": f"set:{domain}", "title": "Set a record…"}]
    return table


def firewalls_table(firewalls: list[dict], names: Mapping) -> dict:
    rows = []
    for fw in firewalls:
        pending = [p for p in (fw.get("pending_changes") or []) if isinstance(p, Mapping)]
        status = str(fw.get("status") or "–")
        applies = [str(names.get(i, i)) for i in (fw.get("droplet_ids") or [])]
        rows.append([cell(str(fw.get("name")), str(fw.get("id"))),
                     cell(status, f"{len(pending)} change{'' if len(pending) == 1 else 's'} pending" if pending else None),
                     cell(", ".join(applies) or "no Droplet", ("tags " + ", ".join(fw.get("tags") or [])) if fw.get("tags") else None),
                     f"{len(fw.get('inbound_rules') or []):,}", f"{len(fw.get('outbound_rules') or []):,}",
                     day(fw.get("created_at"))])
    return {"title": "Cloud firewalls", "note": "a cloud firewall blocks all traffic no rule allows; a deny rule takes "
            "precedence over the allow rules matching the same traffic",
            "columns": [{"title": "Firewall"}, {"title": "Status"}, {"title": "Applies to"},
                        {"title": "Inbound", "num": True}, {"title": "Outbound", "num": True}, {"title": "Made"}],
            "rows": rows, "empty": "No cloud firewalls."}


def rules_table(fw: Mapping, names: Mapping, writable: bool) -> dict:
    rows = []
    for direction in fwmod.DIRECTIONS:
        for r in fw.get(fwmod.rules_key(direction)) or []:
            protocol = str(r.get("protocol") or "").lower()
            row = [direction, fwmod.action_of(r), fwmod.ports_words(protocol, r.get("ports")),
                   fwmod.targets_words(direction, r, names)]
            if writable:
                key = fwmod.key_of(direction, r)
                row.append({"form": f"fw-remove:{fw.get('id')}", "title": "Remove", "label": f"Remove {key}",
                            "values": {"direction": direction, "rule": key}})
            rows.append(row)
    table = {"title": f"{fw.get('name')} rules",
             "note": (f"applies to {fwmod.applies_to(fw) or 'no Droplet'} · " +
                      ("added and removed here one rule at a time: its other rules, Droplets and tags are kept; a rule "
                       "opening SSH or every port to the whole internet, and removing the one letting SSH in, are asked "
                       "twice" if writable else "changed once the token is set")),
             "columns": [{"title": "Direction"}, {"title": "Action"}, {"title": "Protocol and ports"},
                         {"title": "From / to"}, *([{"title": ""}] if writable else [])],
             "rows": rows, "empty": "No rules: it blocks everything."}
    if writable:
        table["actions"] = [{"form": f"fw-add:{fw.get('id')}", "title": "Add a rule…"}]
    return table


def volumes_table(volumes: list[dict], names: Mapping) -> dict:
    rows = [[cell(str(v.get("name")), v.get("description") or None), str((v.get("region") or {}).get("slug") or "–"),
             f"{v.get('size_gigabytes'):,}" if isinstance(v.get("size_gigabytes"), int) else str(v.get("size_gigabytes") or "–"),
             ", ".join(str(names.get(i, i)) for i in (v.get("droplet_ids") or [])) or "not attached",
             str(v.get("filesystem_type") or "–"), day(v.get("created_at"))] for v in volumes]
    return {"title": "Volumes", "note": "a volume bills whether it is attached or not ($0.10 per GiB a month, DigitalOcean's "
            "pricing); none is made, resized or deleted here",
            "columns": [{"title": "Volume"}, {"title": "Region"}, {"title": "GiB", "num": True}, {"title": "Attached to"},
                        {"title": "File system"}, {"title": "Made"}],
            "rows": rows, "empty": "No volumes."}


def keys_table(keys: list[dict], writable: bool) -> dict:
    rows = []
    for k in keys:
        public = str(k.get("public_key") or "")
        parts = public.split()
        shown = f"{parts[0]} …{parts[1][-12:]}" if len(parts) >= 2 else (public[:24] + "…" if len(public) > 24 else public)
        row = [str(k.get("name")), cell(str(k.get("fingerprint") or "–")), cell(shown, " ".join(parts[2:]) or None),
               str(k.get("id") or "–")]
        if writable:
            row.append({"form": "key-remove", "title": "Remove", "label": f"Remove the key {k.get('name')}",
                        "values": {"fingerprint": str(k.get("fingerprint") or ""), "name": str(k.get("name") or "")}})
        rows.append(row)
    table = {"title": "SSH keys", "note": "the keys new Droplets can be made with; a Droplet made with one keeps it (its "
             "authorized_keys) when the key is deleted here",
             "columns": [{"title": "Name"}, {"title": "Fingerprint"}, {"title": "Key"}, {"title": "ID", "num": True},
                         *([{"title": ""}] if writable else [])],
             "rows": rows, "empty": "No SSH keys in this account."}
    if writable:
        table["actions"] = [{"form": "key-add", "title": "Add a key…"}]
    return table


def reserved_table(reserved: list[dict]) -> dict:
    rows = [[str(r.get("ip")), str((r.get("region") or {}).get("slug") or "–"),
             str((r.get("droplet") or {}).get("name") or "not assigned") if isinstance(r.get("droplet"), Mapping) else "not assigned",
             "locked" if r.get("locked") else "–"] for r in reserved]
    return {"title": "Reserved IPs", "note": "a reserved IPv4 address is free while it is assigned to a Droplet and billed "
            "while it is not ($5.00 a month, DigitalOcean's pricing); none is reserved, assigned or released here",
            "columns": [{"title": "Address"}, {"title": "Region"}, {"title": "Assigned to"}, {"title": "Locked"}],
            "rows": rows, "empty": "No reserved IPs."}


def counts_table(counts: Mapping[str, str]) -> dict:
    rows = [[what, counts.get(what, "–")] for what, *_ in COUNTS]
    return {"title": "Also in the account", "note": "each counted with one request (its list's total); nothing of them is "
            "changed here", "columns": [{"title": "What"}, {"title": "How many", "num": True}],
            "rows": rows, "empty": "Not counted yet."}


# -- the forms ---------------------------------------------------------------------------------------------------------------
def power_form(d: Mapping) -> dict | None:
    actions = ACTIONS_BY_STATE.get(str(d.get("status") or ""))
    if not actions or d.get("locked"):
        return None
    name, did = str(d.get("name") or d.get("id")), d.get("id")
    accept = {"name": ACCEPT_HARD, "type": "accept", "title": "Cut its power?", "yes": "Cut the power",
              "words": ("{action} cuts {name}'s power at once, as pulling its plug would: unsaved data is lost (whatever "
                        "it has not written to disk), and its file systems may need checking when it starts again. "
                        "DigitalOcean's advice: shut it down first, and power it off only when that does not work.")}
    return {"id": f"power:{did}", "hook": "power", "title": f"Power {name}",
            "note": ("A shutdown or a reboot asks its system; a power-off or a power cycle cuts the power (asked twice). "
                     + BILLING),
            "fields": [{"name": "droplet_id", "label": "Droplet ID", "type": "fixed", "value": did},
                       {"name": "name", "label": "Droplet", "type": "fixed", "value": name},
                       {"name": "action", "label": "Action", "type": "choice", "value": actions[0],
                        "choices": [{"value": a, "title": POWER[a][0], "note": POWER[a][1]} for a in actions]},
                       accept],  # asked only for a hard one (HARD): the hook refuses it without
            "submit": "Review",
            "confirm": {"title": "{action}: {name}?",
                        "words": "{name} (ID {droplet_id}): {action}. " + BILLING,
                        "yes": "Ask DigitalOcean", "danger": True}}


def record_forms(domain: str, default_ttl: int | None = None) -> list[dict]:
    d = domain
    kept = (f"Only this record is sent: every other record of {d} is kept as it is (DigitalOcean changes records one at a "
            "time).")
    fixed = {"name": "domain", "label": "Domain", "type": "fixed", "value": d}
    ttl = default_ttl or TTL_DEFAULT
    return [
        {"id": f"set:{d}", "hook": "set_record", "title": f"Set a record in {d}",
         "note": ("An A, AAAA or CNAME changes the host's record of its type in place (made when it has none); a TXT, MX, "
                  "NS, CAA or SRV record is added beside the others, or changed when one with the same data is there."),
         "fields": [fixed,
                    {"name": "name", "label": "Name", "type": "text", "required": True, "placeholder": "@, www, home",
                     "note": f"@ is {d} itself; home is home.{d}"},
                    {"name": "rtype", "label": "Type", "type": "choice", "value": "A",
                     "choices": [{"value": t, "title": t, "note": TYPES[t]} for t in TYPES]},
                    {"name": "data", "label": "Data", "type": "text", "required": True,
                     "placeholder": "an address, a host name or text, as its type says"},
                    {"name": "ttl", "label": "TTL (seconds)", "type": "number", "min": TTL_MIN, "max": TTL_MAX,
                     "placeholder": str(ttl), "empty": f"the record's own, else {ttl}"},
                    {"name": "priority", "label": "Priority", "type": "number", "min": 0, "max": 65535, "placeholder": "10",
                     "when": {"rtype": ["MX", "SRV"]}, "empty": "the record's own, else 10"},
                    {"name": "port", "label": "Port", "type": "number", "min": 1, "max": 65535,
                     "when": {"rtype": ["SRV"]}, "empty": "the record's own"},
                    {"name": "weight", "label": "Weight", "type": "number", "min": 0, "max": 65535, "placeholder": "0",
                     "when": {"rtype": ["SRV"]}, "empty": "the record's own, else 0"},
                    {"name": "flags", "label": "Flags", "type": "number", "min": 0, "max": 255, "placeholder": "0",
                     "when": {"rtype": ["CAA"]}, "empty": "0"},
                    {"name": "tag", "label": "Tag", "type": "choice", "value": "issue", "when": {"rtype": ["CAA"]},
                     "choices": [{"value": t, "title": t} for t in CAA_TAGS]}],
         "submit": "Review the change",
         "confirm": {"title": f"Set this record in {d}?", "words": "{name} {rtype} {data} is set in {domain}. " + kept,
                     "yes": "Set the record"}},
        {"id": f"remove:{d}", "hook": "remove_record", "title": f"Remove a record from {d}",
         "fields": [fixed, {"name": "name", "label": "Name", "type": "fixed"}, {"name": "rtype", "label": "Type", "type": "fixed"},
                    {"name": "data", "label": "Data", "type": "fixed"},
                    {"name": "record_id", "label": "Record ID", "type": "fixed"}],
         "confirm": {"title": f"Remove this record from {d}?",
                     "words": "{name} {rtype} {data} (record {record_id}) is deleted from {domain}. " + kept,
                     "yes": "Remove the record", "danger": True}},
    ]


def firewall_forms(fw: Mapping) -> list[dict]:
    fid, name = str(fw.get("id")), str(fw.get("name"))
    kept = f"Only this rule is sent: {name}'s other rules, its Droplets and its tags are kept as they are."
    head = [{"name": "firewall_id", "label": "Firewall ID", "type": "fixed", "value": fid},
            {"name": "firewall", "label": "Firewall", "type": "fixed", "value": name}]
    add_accept = {"name": ACCEPT_RISKY, "type": "accept", "title": "Add this rule anyway?", "yes": "Add it anyway",
                  "words": ("The refusal above says what this rule does to {firewall}'s Droplets. A rule open to the whole "
                            "internet lets anyone try to reach them there; a deny rule over SSH can lock you out of them "
                            "until it is removed (DigitalOcean's web console still reaches them).")}
    remove_accept = {"name": ACCEPT_RISKY, "type": "accept", "title": "Remove this rule anyway?", "yes": "Remove it anyway",
                     "words": ("Without it, SSH may no longer reach {firewall}'s Droplets from where this rule let it in "
                               "(a cloud firewall blocks what no rule allows): you may lose your way in to them, short of "
                               "DigitalOcean's web console.")}
    return [
        {"id": f"fw-add:{fid}", "hook": "add_firewall_rule", "title": f"Add a rule to {name}",
         "note": ("A rule allows (or denies) traffic of a protocol on its ports, from its sources (inbound) or to its "
                  "destinations (outbound): addresses or ranges (0.0.0.0/0 and ::/0 are the whole internet), Droplets by "
                  "name or ID, tags. One opening SSH or every port to the whole internet is asked twice."),
         "fields": [*head,
                    {"name": "direction", "label": "Direction", "type": "choice", "value": "inbound",
                     "choices": [{"value": "inbound", "title": "inbound", "note": "traffic coming in to the Droplets"},
                                 {"value": "outbound", "title": "outbound", "note": "traffic the Droplets send out"}]},
                    {"name": "protocol", "label": "Protocol", "type": "choice", "value": "tcp",
                     "choices": [{"value": p, "title": p} for p in fwmod.PROTOCOLS]},
                    {"name": "ports", "label": "Ports", "type": "text", "placeholder": "22, 443, 8000-9000 or all",
                     "when": {"protocol": ["tcp", "udp"]}, "empty": "all"},
                    {"name": "action", "label": "Action", "type": "choice", "value": "allow",
                     "choices": [{"value": "allow", "title": "allow"},
                                 {"value": "deny", "title": "deny", "note": "takes precedence over the allow rules"}]},
                    {"name": "addresses", "label": "Addresses", "type": "text", "empty": "none",
                     "placeholder": "203.0.113.7, 198.51.100.0/24, 0.0.0.0/0, ::/0"},
                    {"name": "droplets", "label": "Droplets", "type": "text", "empty": "none",
                     "placeholder": "names or IDs, comma separated"},
                    {"name": "tags", "label": "Tags", "type": "text", "empty": "none", "placeholder": "web, db"},
                    add_accept],
         "submit": "Review the rule",
         "confirm": {"title": f"Add this rule to {name}?",
                     "words": ("{direction} {action} {protocol} on ports {ports}: addresses {addresses}; Droplets "
                               "{droplets}; tags {tags}. " + kept), "yes": "Add the rule"}},
        {"id": f"fw-remove:{fid}", "hook": "remove_firewall_rule", "title": f"Remove a rule from {name}",
         "fields": [*head, {"name": "direction", "label": "Direction", "type": "fixed"},
                    {"name": "rule", "label": "Rule", "type": "fixed"}, remove_accept],
         "confirm": {"title": f"Remove this rule from {name}?", "words": "{rule} is removed from {firewall}. " + kept,
                     "yes": "Remove the rule", "danger": True}},
    ]


def key_forms() -> list[dict]:
    return [
        {"id": "key-add", "hook": "add_ssh_key", "title": "Add an SSH key",
         "note": "A public key (one line: its type, its key, a comment), as ssh-keygen writes it to a .pub file.",
         "fields": [{"name": "name", "label": "Name", "type": "text", "required": True, "placeholder": "laptop"},
                    {"name": "public_key", "label": "Public key", "type": "text", "required": True,
                     "placeholder": "ssh-ed25519 AAAAC3Nza… you@host"}],
         "submit": "Review the key",
         "confirm": {"title": "Add {name} to the account's SSH keys?",
                     "words": ("{name} is added to the account's SSH keys: new Droplets can be made with it. No Droplet "
                               "made so far is changed."), "yes": "Add the key"}},
        {"id": "key-remove", "hook": "remove_ssh_key", "title": "Remove an SSH key",
         "fields": [{"name": "fingerprint", "label": "Fingerprint", "type": "fixed"},
                    {"name": "name", "label": "Name", "type": "fixed"}],
         "confirm": {"title": "Remove {name} from the account's SSH keys?",
                     "words": ("{name} ({fingerprint}) is deleted from the account's SSH keys. Droplets made with it keep "
                               "it (DigitalOcean copied it into them when they were made); new Droplets can no longer be "
                               "given it."), "yes": "Remove the key", "danger": True}},
    ]
