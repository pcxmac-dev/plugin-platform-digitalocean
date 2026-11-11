"""A domain's records changed one at a time, as DigitalOcean's API changes them (POST a record, PUT a record by its ID,
DELETE a record by its ID): every other record of the domain is kept as it is, since none is ever sent. A change is
planned on the domain's records at that name read fresh just before it, and refused, with nothing sent, when it could do
other than what the user confirmed: a host with several records of a type that holds one, a CNAME beside other records,
the SOA record, the name server records DigitalOcean keeps at the domain itself.

The record's fields as DigitalOcean takes them (its reference's domain_record: type, name, data, priority, port, ttl,
weight, flags, tag): `name` relative to the domain, "@" for the domain itself; a host name in `data` (CNAME, MX, NS, SRV)
ends with a dot, as the API asks; the TTL 30 seconds at least (DigitalOcean's DNS limits)."""
from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from .errors import Refusal

TYPES = {  # what the page's form sets, in the order offered: what each holds and what setting it does
    "A": "an IPv4 address; changes the host's A record in place (made when it has none)",
    "AAAA": "an IPv6 address; changes the host's AAAA record in place (made when it has none)",
    "CNAME": "a host name the host stands for; it holds nothing else, and @ takes none",
    "TXT": "text (SPF, DKIM, DMARC, a verification); added beside the host's others",
    "MX": "a mail server, with its priority; added beside the others",
    "NS": "a subdomain's name server; added beside the others",
    "CAA": "a certificate authority allowed to issue for the host, with its flags and tag; added beside the others",
    "SRV": "a service's host, with its priority, weight and port; added beside the others",
}
SINGLE = frozenset({"A", "AAAA", "CNAME"})  # set: the host's record of the type changed in place
NAMED = frozenset({"CNAME", "MX", "NS", "SRV"})  # data that is a host name (ends with a dot)
CAA_TAGS = ("issue", "issuewild", "iodef")
TTL_MIN, TTL_MAX, TTL_DEFAULT = 30, 604800, 1800  # DigitalOcean's least; a week; its examples' 1800
MAX_TEXT = 4096
LABEL = re.compile(r"^[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?$")
DO_NS = re.compile(r"^ns\d+\.digitalocean\.com\.?$", re.IGNORECASE)  # the name servers DigitalOcean keeps at @


@dataclass(frozen=True)
class Change:
    """A record change planned: `op` create | update | none; the record changed (update), the body sent, in words."""

    op: str
    said: str
    body: dict = field(default_factory=dict)
    record_id: int | None = None
    was: dict | None = None


def record_type(value: str) -> str:
    t = str(value or "").strip().upper()
    if t == "SOA":
        raise Refusal("the SOA record is DigitalOcean's to keep: it is not written here")
    if t not in TYPES:
        raise ValueError(f"{value!r} is no record type here: {', '.join(TYPES)}")
    return t


def relative_name(name: str, domain: str) -> str:
    """A record's name as DigitalOcean takes it in `domain`: @ (the domain itself), www, home, *, _dmarc, a.b; the
    domain's own name given in full is taken off (home.example.com is home)."""
    n = str(name or "").strip().lower().rstrip(".")
    d = str(domain or "").strip().lower().rstrip(".")
    if n in ("", "@") or n == d:
        if not n:
            raise ValueError("no name given: @ for the domain itself, or www, home …")
        return "@"
    if n.endswith("." + d):
        n = n[: -len(d) - 1]
    labels = n.split(".")
    if len(n) > 253 or not all(LABEL.match(x) or (i == 0 and x == "*") for i, x in enumerate(labels)):
        raise ValueError(f"{str(name).strip()!r} is not a record's name: @, www, home, *, _dmarc")
    return n


def full_name(name: str, domain: str) -> str:
    """A record's full name (what the API's name= filter takes): the domain for @."""
    d = domain.lower().rstrip(".")
    return d if name in ("@", "") else f"{name}.{d}"


def host_data(value: str, rtype: str) -> str:
    """A host name as a record's data: lowercase, ending with a dot (@: the domain itself, for CNAME and MX)."""
    a = str(value or "").strip().lower()
    if a == "@" and rtype in ("CNAME", "MX"):
        return "@"
    labels = a.rstrip(".").split(".")
    if len(a) > 254 or len(labels) < 2 or not all(LABEL.match(x) for x in labels):
        raise ValueError(f"{str(value).strip()!r} is not a host name (a {rtype} record's)")
    return a.rstrip(".") + "."


def data_for(rtype: str, value: str) -> str:
    """A record's data as written; ValueError when it is none."""
    a = str(value or "").strip()
    if not a:
        raise ValueError("no data given")
    if rtype == "A":
        try:
            return str(ipaddress.IPv4Address(a))
        except ValueError:
            raise ValueError(f"{a!r} is not an IPv4 address (an A record's)") from None
    if rtype == "AAAA":
        try:
            return str(ipaddress.IPv6Address(a))
        except ValueError:
            raise ValueError(f"{a!r} is not an IPv6 address (an AAAA record's)") from None
    if rtype in NAMED:
        return host_data(a, rtype)
    if len(a) > MAX_TEXT or any(ord(c) < 32 or ord(c) == 127 for c in a):  # TXT, CAA
        raise ValueError(f"a {rtype} record's data is one line of at most {MAX_TEXT} characters")
    return a


def same_data(rtype: str, a, b) -> bool:
    """Whether two records' data are the same (host names in any case, with or without their dot)."""
    x, y = str(a or "").strip(), str(b or "").strip()
    if rtype in NAMED:
        return x.lower().rstrip(".") == y.lower().rstrip(".")
    if rtype in ("A", "AAAA"):
        try:
            return ipaddress.ip_address(x) == ipaddress.ip_address(y)
        except ValueError:
            return x == y
    return x == y


def number(value, low: int, high: int, what: str) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{what} is a whole number, {low} to {high}") from None
    if not low <= n <= high:
        raise ValueError(f"{what} is {low} to {high}")
    return n


def said(r: Mapping) -> str:
    """A record in words: its name, type and data (shortened), its priority or port where it has one."""
    data = str(r.get("data") or "")
    short = data if len(data) <= 60 else data[:59] + "…"
    extra = ""
    t = str(r.get("type") or "").upper()
    if t == "MX" and r.get("priority") is not None:
        extra = f" (priority {r['priority']})"
    elif t == "SRV":
        extra = f" (priority {r.get('priority')}, weight {r.get('weight')}, port {r.get('port')})"
    elif t == "CAA":
        extra = f" ({r.get('flags')} {r.get('tag')})"
    return f"{r.get('name') or '@'} {t} {short}{extra}"


def kept_by_digitalocean(r: Mapping) -> str | None:
    """Why a record is DigitalOcean's own to keep (no Remove offered, none sent), or None."""
    t = str(r.get("type") or "").upper()
    if t == "SOA":
        return "the SOA record is DigitalOcean's to keep"
    if t == "NS" and (r.get("name") or "@") == "@" and DO_NS.match(str(r.get("data") or "")):
        return "DigitalOcean keeps its name servers' NS records at the domain itself"
    return None


def plan_set(domain: str, at_name: Iterable[Mapping], name: str, rtype: str, data: str, ttl=None, priority=None,
             port=None, weight=None, flags=None, tag=None, default_ttl: int = TTL_DEFAULT) -> Change:
    """A record set at `name` of `domain`, planned on the records at that name read just now (`at_name`): an A, AAAA or
    CNAME changes the host's record of its type in place (made when it has none); a TXT, MX, NS, CAA or SRV is added
    beside the others, or changed in place when one with the same data is there (its TTL, its priority)."""
    t = record_type(rtype)
    n = relative_name(name, domain)
    tag_ = None
    if t == "CAA":
        tag_ = str(tag or "issue").strip().lower()
        if tag_ not in CAA_TAGS:
            raise ValueError(f"a CAA record's tag is one of {', '.join(CAA_TAGS)}")
    value = data_for(t, data)
    here = [dict(r) for r in at_name if (str(r.get("name") or "@").lower() == n)]
    if t == "CNAME" and n == "@":
        raise Refusal("a CNAME cannot stand for the domain itself (@): an A or AAAA record does")
    others = sorted({str(r.get("type") or "").upper() for r in here} - {"CNAME"})
    if t == "CNAME" and others:
        raise Refusal(f"{n} holds other records ({', '.join(others)}): a CNAME stands alone")
    if t != "CNAME" and any(str(r.get("type") or "").upper() == "CNAME" for r in here):
        raise Refusal(f"{n} is a CNAME: it holds no {t} record beside it")
    body: dict = {"type": t, "name": n, "data": value}
    if t in ("MX", "SRV"):
        body["priority"] = None if priority is None else number(priority, 0, 65535, "the priority")
    if t == "SRV":
        body["port"] = None if port is None else number(port, 1, 65535, "the port")
        body["weight"] = None if weight is None else number(weight, 0, 65535, "the weight")
    if t == "CAA":
        body["flags"] = 0 if flags is None else number(flags, 0, 255, "the CAA flags")
        body["tag"] = tag_
    of_type = [r for r in here if str(r.get("type") or "").upper() == t]
    if t in SINGLE:
        if len(of_type) > 1:
            raise Refusal(f"{n} holds {len(of_type)} {t} records ({', '.join(str(r.get('data')) for r in of_type)}): "
                          "which one to change is not clear, so none is; remove the ones no longer wanted first")
        base = of_type[0] if of_type else None
    else:
        def same(r):
            if not same_data(t, r.get("data"), value):
                return False
            if t == "CAA":
                return str(r.get("tag") or "").lower() == tag_
            if t == "SRV" and body.get("port") is not None:
                return r.get("port") == body["port"]
            return True
        base = next((r for r in of_type if same(r)), None)
    if base is None:
        for k in ("priority", "port", "weight"):
            if k in body and body[k] is None:
                body[k] = 10 if k == "priority" else 0 if k == "weight" else None
        if t == "SRV" and body.get("port") is None:
            raise ValueError("an SRV record needs its port")
        body["ttl"] = number(ttl, TTL_MIN, TTL_MAX, "the TTL (seconds)") if ttl is not None else default_ttl
        return Change("create", f"added {said(body)}", body)
    for k in ("priority", "port", "weight"):  # what was not given is kept as it is
        if k in body and body[k] is None:
            body[k] = base.get(k)
    body["ttl"] = number(ttl, TTL_MIN, TTL_MAX, "the TTL (seconds)") if ttl is not None else int(base.get("ttl") or default_ttl)
    keys = [k for k in ("data", "ttl", "priority", "port", "weight", "flags", "tag") if k in body]
    changed = [k for k in keys if not (same_data(t, base.get(k), body[k]) if k == "data" else base.get(k) == body[k])]
    if not changed:
        return Change("none", f"{said(body)} is there already: nothing sent", body, base.get("id"), base)
    if "data" in changed:
        words = f"set {said(body)} (it was {base.get('data')})"
    else:
        words = f"set {said(body)}: " + ", ".join(f"{k} {base.get(k)} → {body[k]}" for k in changed)
    return Change("update", words, body, base.get("id"), base)


def pick_removal(domain: str, at_name: Iterable[Mapping], name: str, rtype: str, data=None, record_id=None) -> dict:
    """The record to remove among those at `name` read just now: the one of `rtype` (with `data`, the one of that ID,
    when given); Refusal when there is none, several, DigitalOcean's own, or not the record named."""
    t = str(rtype or "").strip().upper()
    n = relative_name(name, domain)
    here = [dict(r) for r in at_name if str(r.get("name") or "@").lower() == n and str(r.get("type") or "").upper() == t]
    if record_id not in (None, ""):
        try:
            rid = int(record_id)
        except (TypeError, ValueError):
            raise ValueError(f"{record_id!r} is not a record's ID") from None
        found = [r for r in here if r.get("id") == rid]
        if not found:
            raise Refusal(f"{domain} has no {t} record {rid} at {n} any more: the page is read again")
        r = found[0]
        if data not in (None, "") and not same_data(t, r.get("data"), data):
            raise Refusal(f"{domain}'s record {rid} now holds {r.get('data')}, not {data}: nothing removed, the page is read again")
        matches = [r]
    else:
        matches = [r for r in here if data in (None, "") or same_data(t, r.get("data"), data)]
    if not matches:
        raise Refusal(f"{domain} has no {t} record at {n}" + (f" holding {data}" if data not in (None, "") else ""))
    if len(matches) > 1:
        raise Refusal(f"{domain} has {len(matches)} {t} records at {n}: name the one to remove by its data")
    why = kept_by_digitalocean(matches[0])
    if why:
        raise Refusal(f"{why}: it is not removed here")
    return matches[0]
