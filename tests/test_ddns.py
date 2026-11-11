"""Dynamic DNS through DigitalOcean's DNS (the library's Keeper): each host's A records asked by its full name, one changed
in place by its ID (its TTL kept) or made when the host has none, nothing sent for a host that is current (every host with
force, the page's Update DNS now), a host with several A records left as it is and said so; only for the account's
domains. Over the stand-ins: this network's address is given, no name server asked."""
from __future__ import annotations

import pytest

from conftest import HOME, FakeDigitalOcean, record, settings_of


def a_writes(fake) -> list[tuple]:
    return [(w["method"], w["path"], w["json"]) for w in fake.writes()]


def test_a_pass_makes_a_missing_record_then_leaves_a_current_one_and_sets_one_that_differs(made, env):
    env(settings_of(ddns=True))
    p, fake = made()
    p.refresh()
    (h,) = p.ddns_update(force=False)
    assert a_writes(fake) == [("POST", "/v2/domains/example.com/records",
                               {"type": "A", "name": "home", "data": HOME, "ttl": 60})]
    assert h["ok"] is True and h["address"] == HOME and h["result"] == "made (was none)"
    asked = [r["query"] for r in fake.requests if r["path"] == "/v2/domains/example.com/records" and "name" in r["query"]]
    assert asked[0] == {"type": "A", "name": "home.example.com", "per_page": "200"}  # by its full name, as the API asks
    (h,) = p.ddns_update(force=False)
    assert len(fake.writes()) == 1 and h["result"] == "current"  # current: nothing sent
    made_id = next(r["id"] for r in fake.records["example.com"] if r["name"] == "home")
    next(r for r in fake.records["example.com"] if r["name"] == "home").update({"data": "198.51.100.99", "ttl": 300})
    (h,) = p.ddns_update(force=False)
    assert a_writes(fake)[-1] == ("PUT", f"/v2/domains/example.com/records/{made_id}",
                                  {"type": "A", "name": "home", "data": HOME, "ttl": 300})  # its own TTL kept
    assert h["result"] == "set (was 198.51.100.99)"
    (h,) = p.ddns_update(force=True)  # Update DNS now: sent whether it differs or not
    assert a_writes(fake)[-1][0] == "PUT" and len(fake.writes()) == 3 and h["ok"] is True
    rows = [(r["name"], r["type"]) for r in fake.records["example.com"]]
    assert rows.count(("home", "A")) == 1 and ("@", "A") in rows and ("www", "A") in rows  # the others kept


def test_the_domain_itself_is_asked_by_its_own_name(made, env):
    env(settings_of(ddns=True, DIGITALOCEAN_DDNS_HOSTS="@.example.net"))
    p, fake = made()
    p.refresh()
    (h,) = p.ddns_update(force=False)
    asked = [r["query"] for r in fake.requests if r["path"] == "/v2/domains/example.net/records" and "name" in r["query"]]
    assert asked[0]["name"] == "example.net" and h["host"] == "example.net"
    assert a_writes(fake) == [("POST", "/v2/domains/example.net/records", {"type": "A", "name": "@", "data": HOME, "ttl": 60})]


def test_a_host_with_several_a_records_is_left_as_it_is_and_said_so(made, env):
    env(settings_of(ddns=True))
    fake = FakeDigitalOcean()
    fake.records["example.com"] += [record(40, "A", "home", "198.51.100.1"), record(41, "A", "home", "198.51.100.2")]
    p, fake = made(fake)
    p.refresh()
    (h,) = p.ddns_update(force=False)
    assert fake.writes() == [] and h["ok"] is False
    assert h["result"].startswith("not updated: home.example.com holds 2 A records (198.51.100.1, 198.51.100.2)")
    st = p.status()
    assert st["valid"] is True and "Dynamic DNS: home.example.com: not updated" in st["problem"]


def test_no_address_found_sends_nothing_and_says_why(made, env):
    env(settings_of(ddns=True))
    p, fake = made(public=lambda: (None, "neither OpenDNS nor Google answered with a public IPv4 address"))
    p.refresh()
    (h,) = p.ddns_update(force=True)
    assert fake.writes() == [] and h["ok"] is False
    assert h["result"] == ("this network's address was not found: neither OpenDNS nor Google answered with a public IPv4 "
                           "address")


def test_hosts_in_none_of_the_accounts_domains_are_said_and_the_page_draws_the_rest(made, env):
    env(settings_of(ddns=True, DIGITALOCEAN_DDNS_HOSTS="home.example.com, nas.example.org"))
    p, fake = made()
    st = p.status()
    ddns = next(t for t in st["tables"] if t["title"] == "Dynamic DNS")
    assert ddns["rows"] == [] and ddns["empty"] == "The hosts are checked once the account's domains are read."
    p.refresh()
    p.ddns_update(force=False)
    st = p.status()
    ddns = next(t for t in st["tables"] if t["title"] == "Dynamic DNS")
    assert [r[0] for r in ddns["rows"]] == ["home.example.com"] and ddns["rows"][0][1] == HOME
    assert f"this network's address: {HOME}" in ddns["note"] and ddns["rows"][0][4] == "made (was none)"
    assert "Dynamic DNS: nas.example.org is in none of the account's domains" in st["problem"]
    assert [a["hook"] for a in st["actions"]] == ["refresh", "ddns_update"] and st["ddnsEvery"] == "every 5 min, once attached"
    assert st["summary"].endswith(f"home.example.com at {HOME}")
    with pytest.raises(ValueError, match="no Dynamic DNS host is in the account's domains"):
        env({"DIGITALOCEAN_DDNS_HOSTS": "nas.example.org"})
        p.settings_changed()
        p.ddns_update()
