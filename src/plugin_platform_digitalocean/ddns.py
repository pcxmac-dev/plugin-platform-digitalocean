"""Dynamic DNS through DigitalOcean's DNS: hosts kept at this network's public IPv4 address (liminal_libs.machines.ddns's
Keeper), their A records read and set through the API's domain records (a host's A records asked by its full name, as the
records' name= filter takes it; one changed in place by its ID, or made when the host has none). Only for the account's
domains: DigitalOcean's DNS holds no other.

The Keeper decides what is its own to change (liminal-libs 1.49.2): a host with no A record, one holding the address it
set last (or this network's already), one the user took over on the page. Any other record is left as it is, so `write`
is asked only of those. It sets the host's A record to exactly the one address given: a host the user took over while it
held several addresses keeps one record, changed in place, and loses the others, as its confirmation said.

This network's address is asked of name servers that answer with the asker's own (the library's dns.public_address over
PUBLIC_IPV4, each server asked by its IPv4 address so the answer is the IPv4 one): OpenDNS's resolver, else Google's."""
from __future__ import annotations

from liminal_libs.machines.ddns import Host

from .records import TTL_MIN, full_name

PUBLIC_IPV4 = (("myip.opendns.com", "a", "208.67.222.222", "OpenDNS"),
               ("o-o.myaddr.l.google.com", "txt", "216.239.32.10", "Google"))
TTL = 60  # a host's A record made by Dynamic DNS: a minute, so a new address spreads soon (DigitalOcean's least is 30)


def a_records(api, host: Host) -> list[dict]:
    """The host's A records in its zone, read now (its full name: the zone itself for @)."""
    found = api.records(host.zone, "A", full_name(host.name, host.zone))
    return [r for r in found if str(r.get("type") or "").upper() == "A" and str(r.get("name") or "@").lower() == host.name]


def read(api, host: Host) -> list[str]:
    """The addresses the host's A records hold ([] when it has none)."""
    return [str(r.get("data") or "") for r in a_records(api, host)]


def write(api, host: Host, ip: str) -> str:
    """The host's A record set to exactly `ip`: its first record changed in place (its own TTL kept) and any other A record
    of the host deleted (only a host taken over holds several: the keeper leaves any other as it is), or one made."""
    found = a_records(api, host)
    if not found:
        api.create_record(host.zone, {"type": "A", "name": host.name, "data": ip, "ttl": TTL})
        return "made"
    first, rest = found[0], found[1:]
    ttl = max(TTL_MIN, int(first.get("ttl") or TTL))
    api.update_record(host.zone, first["id"], {"type": "A", "name": host.name, "data": ip, "ttl": ttl})
    for r in rest:
        api.delete_record(host.zone, r["id"])
    return "set" if not rest else f"set, {len(rest)} other A record{'' if len(rest) == 1 else 's'} removed"
