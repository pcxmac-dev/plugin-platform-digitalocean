"""A cloud firewall's rules, as DigitalOcean's reference gives them (its firewall_rule: protocol tcp | udp | icmp, ports
"22" | "8000-9000" | "0" for every port, action allow | deny, allow unless said; an inbound rule's `sources` and an
outbound rule's `destinations`: addresses, droplet_ids, load_balancer_uids, kubernetes_ids, tags), changed only through the
rules' own calls (POST and DELETE /v2/firewalls/{id}/rules: the firewall's other rules, Droplets and tags are never sent,
so they are kept). A cloud firewall blocks all traffic no rule allows, and a deny rule takes precedence over the allow
rules matching the same traffic (DigitalOcean's Cloud Firewalls page).

A rule's `action` is DigitalOcean's own (its reference's rule object: "This may be one of `allow` or `deny`", allow
unless set; its release note of August 2026: "Cloud firewall rules now support an action of allow or deny"). A deny rule
added is read back, and one DigitalOcean took as an allow is removed again at once (the plugin's add_firewall_rule).

A rule is named on the page by its key (`key_of`: its direction, action, protocol, ports and every target, sorted): the
rule removed is the one read fresh with that key, sent back as it was read. Risky changes (`risk_of_add`,
`risk_of_remove`) are asked a second time: an allow opening SSH, another way in (EXPOSED: Remote Desktop, Docker's API, a
database ...) or every port (a range of WIDE_PORTS or more) to the whole internet or a wide part of it; any deny over SSH
or every port, added or removed; and removing the rule that lets SSH in to the firewall's Droplets."""
from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable, Mapping

from .errors import Refusal

DIRECTIONS = ("inbound", "outbound")
PROTOCOLS = ("tcp", "udp", "icmp")
ACTIONS = ("allow", "deny")
TARGETS = (("addresses", "addresses"), ("droplet_ids", "Droplets"), ("load_balancer_uids", "load balancers"),
           ("kubernetes_ids", "Kubernetes clusters"), ("tags", "tags"))
EVERYWHERE = ("0.0.0.0/0", "::/0")
SSH = 22
WIDE_PORTS = 1000  # a range of this many ports or more is taken as every port (23-65535: every port but SSH)
WIDE_V4, WIDE_V6 = 2 ** 24, 32  # sources this wide are taken as the whole internet: a /8 of IPv4 in all, an IPv6 /32
EXPOSED = {  # what an allow from the whole internet is asked twice for, beside SSH and every port
    22: "SSH", 23: "Telnet", 2375: "Docker's API", 2376: "Docker's API over TLS", 3389: "Remote Desktop", 5900: "VNC",
    5985: "WinRM", 5986: "WinRM over HTTPS", 3306: "MySQL", 5432: "PostgreSQL", 6379: "Redis", 27017: "MongoDB",
    9200: "Elasticsearch", 11211: "memcached"}
TAG = re.compile(r"^[A-Za-z0-9:_.\-]{1,255}$")


def side(direction: str) -> str:
    """The rule's field of its targets: an inbound rule's sources, an outbound rule's destinations."""
    return "sources" if direction == "inbound" else "destinations"


def rules_key(direction: str) -> str:
    return "inbound_rules" if direction == "inbound" else "outbound_rules"


def targets_of(direction: str, rule: Mapping) -> dict[str, list]:
    got = rule.get(side(direction)) or {}
    return {k: list(got.get(k) or []) for k, _ in TARGETS}


def action_of(rule: Mapping) -> str:
    return str(rule.get("action") or "allow").lower()


def ports_words(protocol: str, ports) -> str:
    p = str(ports if ports is not None else "0").strip().lower()
    if protocol == "icmp":
        return "icmp"
    return f"{protocol} every port" if p in ("0", "all", "", "1-65535") else f"{protocol} {p}"


def key_of(direction: str, rule: Mapping) -> str:
    """A rule's key: everything it is, in words, its targets sorted (what the page's Remove names and the hook finds)."""
    protocol = str(rule.get("protocol") or "").lower()
    targets = targets_of(direction, rule)
    parts = [f"{label} {', '.join(sorted(str(v) for v in targets[k]))}" for k, label in TARGETS if targets[k]]
    known = {k for k, _ in TARGETS}
    more = rule.get(side(direction)) or {}
    parts += [f"{k} {', '.join(sorted(str(v) for v in (vs if isinstance(vs, list) else [vs])))}"  # a target named since
              for k, vs in sorted(more.items()) if k not in known and vs]
    return (f"{direction} {action_of(rule)} {ports_words(protocol, rule.get('ports'))} "
            f"{'from' if direction == 'inbound' else 'to'} " + ("; ".join(parts) or "nothing"))


def targets_words(direction: str, rule: Mapping, droplet_names: Mapping | None = None) -> str:
    """A rule's targets in words for the page (Droplets by their names where known)."""
    names = droplet_names or {}
    targets = targets_of(direction, rule)
    out = []
    for k, label in TARGETS:
        values = targets[k]
        if not values:
            continue
        if k == "addresses":
            shown = ["every IPv4 address" if v == "0.0.0.0/0" else "every IPv6 address" if v == "::/0" else str(v)
                     for v in values]
            out.append(", ".join(shown))
        elif k == "droplet_ids":
            out.append("Droplets " + ", ".join(str(names.get(v, v)) for v in values))
        else:
            out.append(f"{label} " + ", ".join(str(v) for v in values))
    return "; ".join(out) or "nothing"


def covers(ports, port: int) -> bool:
    """Whether a rule's ports take `port` ("0": every port)."""
    p = str(ports if ports is not None else "0").strip().lower()
    if p in ("0", "all", ""):
        return True
    if "-" in p:
        low, _, high = p.partition("-")
        try:
            return int(low) <= port <= int(high)
        except ValueError:
            return False
    try:
        return int(p) == port
    except ValueError:
        return False


def span(ports) -> tuple[int, int] | None:
    """The ports a rule takes, (first, last): every port for "0"; None when they cannot be read."""
    p = str(ports if ports is not None else "0").strip().lower()
    if p in ("0", "all", ""):
        return 1, 65535
    low, _, high = p.partition("-")
    try:
        return int(low), int(high or low)
    except ValueError:
        return None


def wide_ports(ports) -> bool:
    """Whether a rule takes every port, or a range of WIDE_PORTS or more (23-65535 is every port but SSH)."""
    s = span(ports)
    return s is not None and s[1] - s[0] + 1 >= WIDE_PORTS


def ports_said(protocol: str, ports) -> str:
    s = span(ports)
    if s == (1, 65535):
        return f"every {protocol} port"
    return f"{protocol} ports {s[0]}-{s[1]}" if s else f"{protocol} ports {ports}"


def to_everyone(addresses: Iterable[str]) -> bool:
    """Whether the addresses take in the whole internet (0.0.0.0/0, ::/0) or a wide part of it: public IPv4 ranges of a
    /8 or more in all (0.0.0.0/1 and 128.0.0.0/1 together are all of it), a public IPv6 range of a /32 or wider. A
    private range (a VPC's 10.0.0.0/8) is not the internet."""
    v4 = 0
    for a in addresses:
        try:
            n = ipaddress.ip_network(str(a), strict=False)
        except ValueError:
            continue
        if n.is_private:
            continue
        if n.version == 4:
            v4 += n.num_addresses
        elif n.prefixlen <= WIDE_V6:
            return True
    return v4 >= WIDE_V4


def everyone_said(addresses: Iterable[str]) -> str:
    whole = any(str(a) in EVERYWHERE for a in addresses)
    return "the whole internet" if whole else f"a wide part of the internet ({', '.join(str(a) for a in addresses)})"


def lets_ssh_in(rule: Mapping) -> bool:
    return action_of(rule) == "allow" and str(rule.get("protocol") or "").lower() == "tcp" and covers(rule.get("ports"), SSH)


def denied(rule: Mapping) -> str | None:
    """What a deny rule shuts that is asked twice, in words: every port (or a wide range of them) of its protocol, or
    SSH; None for any other rule."""
    if action_of(rule) != "deny":
        return None
    protocol = str(rule.get("protocol") or "").lower()
    if protocol in ("tcp", "udp") and wide_ports(rule.get("ports")):
        return ports_said(protocol, rule.get("ports"))
    if protocol == "tcp" and covers(rule.get("ports"), SSH):
        return "SSH (port 22)"
    return None


def applies_to(fw: Mapping) -> str:
    """What the firewall applies to, in words ("" when nothing)."""
    droplets, tags = list(fw.get("droplet_ids") or []), list(fw.get("tags") or [])
    bits = []
    if droplets:
        bits.append(f"{len(droplets)} Droplet{'' if len(droplets) == 1 else 's'}")
    if tags:
        bits.append("the Droplets tagged " + ", ".join(str(t) for t in tags))
    return " and ".join(bits)


def risk_of_add(direction: str, rule: Mapping, fw: Mapping) -> str | None:
    """Why adding `rule` to `fw` is risky (asked a second time), or None: an inbound allow opening SSH, another way in
    (EXPOSED) or every port (a wide range) to the whole internet or a wide part of it; any deny over SSH or every port,
    whatever the firewall applies to now (it may be applied to Droplets later)."""
    protocol = str(rule.get("protocol") or "").lower()
    shut = denied(rule)
    if shut:
        whom = applies_to(fw) or "the Droplets it is applied to (none yet)"
        return (f"a deny rule takes precedence over the allow rules matching the same traffic: it shuts {shut} of "
                f"{fw.get('name')} ({whom}) {'from' if direction == 'inbound' else 'to'} {targets_words(direction, rule)}")
    if direction != "inbound" or action_of(rule) != "allow":
        return None
    addresses = targets_of(direction, rule)["addresses"]
    if not to_everyone(addresses):
        return None
    if protocol in ("tcp", "udp") and wide_ports(rule.get("ports")):
        return f"it opens {ports_said(protocol, rule.get('ports'))} of {fw.get('name')}'s Droplets to {everyone_said(addresses)}"
    if protocol == "tcp":
        ways = [f"{name} (port {port})" for port, name in EXPOSED.items() if covers(rule.get("ports"), port)]
        if ways:
            return f"it opens {', '.join(ways)} of {fw.get('name')}'s Droplets to {everyone_said(addresses)}"
    return None


def risk_of_remove(direction: str, rule: Mapping, fw: Mapping) -> str | None:
    """Why removing `rule` from `fw` is risky (asked a second time), or None: a deny over SSH or every port (what it
    shut is let through again), and the rule letting SSH in to the Droplets the firewall applies to (a cloud firewall
    blocks what no rule allows)."""
    shut = denied(rule)
    if shut:
        return (f"it is a deny rule over {shut}: without it, {shut} is let through again "
                f"{'from' if direction == 'inbound' else 'to'} {targets_words(direction, rule)} wherever an allow rule "
                "lets it")
    if direction != "inbound" or not lets_ssh_in(rule) or not applies_to(fw):
        return None
    others = [r for r in (fw.get("inbound_rules") or []) if lets_ssh_in(r) and key_of("inbound", r) != key_of("inbound", rule)]
    still = ("; other rules still let SSH in from " + " | ".join(targets_words("inbound", r) for r in others)) if others         else "; no other rule lets SSH in"
    return (f"it lets SSH (port 22) in to {applies_to(fw)} from {targets_words(direction, rule)}: without it SSH from there "
            f"is blocked (a cloud firewall blocks what no rule allows){still}")


# -- a rule as typed in the page's form -----------------------------------------------------------------------------------
def ports_of(protocol: str, value) -> str:
    """The ports as the API takes them: "0" for every port (and for icmp), "22", "8000-9000"."""
    if protocol == "icmp":
        return "0"
    p = str(value if value is not None else "").strip().lower()
    if p in ("", "0", "all", "*", "every"):
        return "0"
    m = re.fullmatch(r"(\d{1,5})(?:\s*-\s*(\d{1,5}))?", p)
    if not m:
        raise ValueError(f"{value!r} is not ports: one port (22), a range (8000-9000) or all")
    low, high = int(m.group(1)), int(m.group(2) or m.group(1))
    if not 1 <= low <= high <= 65535:
        raise ValueError("a port is 1 to 65535, a range's first not after its last")
    return str(low) if low == high else f"{low}-{high}"


def split_list(value) -> list[str]:
    return [x.strip() for x in re.split(r"[,;\s]+", str(value or "")) if x.strip()]


def addresses_of(value) -> list[str]:
    out = []
    for a in split_list(value):
        try:
            out.append(str(ipaddress.ip_network(a, strict=False)) if "/" in a else str(ipaddress.ip_address(a)))
        except ValueError:
            raise ValueError(f"{a!r} is not an address or a range (203.0.113.7, 198.51.100.0/24, 0.0.0.0/0, ::/0)") from None
    return list(dict.fromkeys(out))


def droplet_ids_of(value, droplets: Iterable[Mapping]) -> list[int]:
    """Droplets typed by their IDs or names, as IDs (a name the account's Droplets share: refused)."""
    known = list(droplets)
    out = []
    for x in split_list(value):
        if x.isdigit():
            out.append(int(x))
            continue
        named = [d for d in known if str(d.get("name") or "").lower() == x.lower()]
        if not named:
            raise ValueError(f"no Droplet is named {x!r}: give its name or its ID")
        if len(named) > 1:
            raise Refusal(f"{len(named)} Droplets are named {x!r}: give the one's ID ({', '.join(str(d.get('id')) for d in named)})")
        out.append(int(named[0]["id"]))
    return list(dict.fromkeys(out))


def tags_of(value) -> list[str]:
    out = split_list(value)
    for t in out:
        if not TAG.match(t):
            raise ValueError(f"{t!r} is not a tag (letters, digits, :, -, _ and .)")
    return list(dict.fromkeys(out))


def rule_from(direction: str, protocol: str, ports, action, addresses, droplets, tags, known_droplets=()) -> dict:
    """A rule as the API takes it, from what the form holds; ValueError when it is not one."""
    d = str(direction or "").strip().lower()
    if d not in DIRECTIONS:
        raise ValueError(f"the direction is {' or '.join(DIRECTIONS)}")
    p = str(protocol or "").strip().lower()
    if p not in PROTOCOLS:
        raise ValueError(f"the protocol is one of {', '.join(PROTOCOLS)}")
    a = str(action or "allow").strip().lower()
    if a not in ACTIONS:
        raise ValueError(f"the action is {' or '.join(ACTIONS)}")
    targets = {"addresses": addresses_of(addresses), "droplet_ids": droplet_ids_of(droplets, known_droplets),
               "tags": tags_of(tags)}
    targets = {k: v for k, v in targets.items() if v}
    if not targets:
        raise ValueError(f"a rule needs {'a source' if d == 'inbound' else 'a destination'}: addresses, Droplets or tags")
    return {"protocol": p, "ports": ports_of(p, ports), "action": a, side(d): targets}


def find(fw: Mapping, direction: str, key: str) -> dict:
    """The rule of `fw` (read fresh) with this key; Refusal when there is none any more."""
    for r in fw.get(rules_key(direction)) or []:
        if key_of(direction, r) == key:
            return dict(r)
    raise Refusal(f"{fw.get('name')} holds no such {direction} rule any more ({key}): the page is read again")
