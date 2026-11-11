"""Dynamic DNS through DigitalOcean's DNS (the library's Keeper, liminal-libs 1.49.2): it changes only what is its own, a
host with no A record (made), one already pointing here or at the address it set last (kept current, after a restart too:
its state file under the platform's folder), one the user took over on the page; any other record is left as it is and
said so, with a Take over… on its row. A write sets the host to exactly one address; several addresses are never cut to
one unasked. Each host's A records are asked by its full name. Over the stand-ins: this network's address is given, no
name server asked."""
from __future__ import annotations

import json
import threading

import pytest

from conftest import HOME, FakeDigitalOcean, record, settings_of
from plugin_platform_digitalocean import DigitalOceanPlugin

NEW = "93.184.216.77"  # this network's address after it changed


def a_writes(fake) -> list[tuple]:
    return [(w["method"], w["path"], w["json"]) for w in fake.writes()]


def home_id(fake, name="home") -> int:
    return next(r["id"] for r in fake.records["example.com"] if r["name"] == name and r["type"] == "A")


def ddns_table(status: dict) -> dict:
    return next(t for t in status["tables"] if t["title"] == "Dynamic DNS")


def test_a_missing_record_is_made_and_kept_its_own_and_the_name_is_asked_in_full(made, env, tmp_path):
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
    state = json.loads((tmp_path / "platform" / "digitalocean" / "ddns.json").read_text(encoding="utf-8"))
    assert state == {"own": {"home.example.com": HOME}, "taken": []}  # its own, kept for a restart


def test_its_own_old_address_is_updated_after_the_networks_address_changed_a_restart_too(made, env):
    env(settings_of(ddns=True))
    p, fake = made()
    p.refresh()
    p.ddns_update(force=False)  # made at HOME: its own
    q, _ = made(fake, public=lambda: (NEW, "OpenDNS"))  # the platform started again, the network's address changed
    q.refresh()
    (h,) = q.ddns_update(force=False)
    assert a_writes(fake)[-1] == ("PUT", f"/v2/domains/example.com/records/{home_id(fake)}",
                                  {"type": "A", "name": "home", "data": NEW, "ttl": 60})
    assert h["ok"] is True and h["result"] == f"set (was {HOME})"


def test_a_host_holding_another_address_is_left_as_it_is_with_take_over_offered(made, env):
    env(settings_of(ddns=True, DIGITALOCEAN_DDNS_HOSTS="www.example.com"))  # www points at the web Droplet
    p, fake = made()
    p.refresh()
    (h,) = p.ddns_update(force=False)
    assert fake.writes() == [] and h["ok"] is False and h["foreign"] is True and h["holds"] == ["203.0.113.10"]
    assert h["result"] == "holds 203.0.113.10, not this network's address: left as it is (Take over… to point it here)"
    (h,) = p.ddns_update(force=True)  # Update DNS now never takes a record that is not its own
    assert fake.writes() == [] and h["foreign"] is True
    st = p.status()
    row = ddns_table(st)["rows"][0]
    assert row[0] == "www.example.com" and row[1] == "203.0.113.10"
    assert row[5] == {"form": "ddns-take", "title": "Take over…", "label": "Take over www.example.com",
                      "values": {"host": "www.example.com", "holds": "203.0.113.10"}}
    forms = {f["id"]: f for f in st["forms"]}
    assert forms["ddns-take"]["hook"] == "ddns_take_over" and forms["ddns-take"]["confirm"]["danger"] is True
    assert [x["name"] for x in forms["ddns-take"]["fields"]] == ["host", "holds"]
    assert forms["ddns-now"]["hook"] == "ddns_update" and forms["ddns-now"]["fields"] == []
    assert {"form": "ddns-now", "title": "Update DNS now"} in st["actions"]  # confirmed now, not asked on one click
    assert not any(a.get("hook") == "ddns_update" for a in st["actions"])
    assert "www.example.com: holds 203.0.113.10" in st["problem"] and st["valid"] is True


def test_take_over_then_a_pass_sets_it(made, env):
    env(settings_of(ddns=True, DIGITALOCEAN_DDNS_HOSTS="www.example.com"))
    p, fake = made()
    p.refresh()
    p.ddns_update(force=False)
    with pytest.raises(ValueError, match="holds 203.0.113.10 now, not 198.51.100.1: nothing taken over"):
        p.ask("ddns_take_over", "www.example.com", "198.51.100.1")  # not what the confirmation named
    with pytest.raises(ValueError, match="is not one of the Dynamic DNS hosts"):
        p.ask("ddns_take_over", "blog.example.com", "www.example.com.")
    assert fake.writes() == []
    rep = p.ask("ddns_take_over", "www.example.com", "203.0.113.10")  # as the page's Take over… sends it
    assert a_writes(fake) == [("PUT", "/v2/domains/example.com/records/15",
                               {"type": "A", "name": "www", "data": HOME, "ttl": 3600})]  # its own TTL kept
    assert rep["ok"] is True and rep["lines"] == ["it held 203.0.113.10", "set (was 203.0.113.10)"]
    (h,) = p.ddns_update(force=False)
    assert h["result"] == "current" and len(fake.writes()) == 1


def test_a_host_with_several_addresses_is_never_cut_to_one_unasked(made, env):
    env(settings_of(ddns=True))
    fake = FakeDigitalOcean()
    fake.records["example.com"] += [record(40, "A", "home", "198.51.100.1"), record(41, "A", "home", "198.51.100.2")]
    p, fake = made(fake)
    p.refresh()
    for force in (False, True):
        (h,) = p.ddns_update(force=force)
        assert fake.writes() == [] and h["ok"] is False and h["holds"] == ["198.51.100.1", "198.51.100.2"]
    assert h["result"].startswith("holds 2 addresses (198.51.100.1, 198.51.100.2): left as it is")
    rep = p.ask("ddns_take_over", "home.example.com", "198.51.100.1, 198.51.100.2")  # taken over: what it held is dropped
    assert a_writes(fake) == [("PUT", "/v2/domains/example.com/records/40", {"type": "A", "name": "home", "data": HOME,
                                                                             "ttl": 1800}),
                              ("DELETE", "/v2/domains/example.com/records/41", None)]
    assert rep["lines"][1] == "set, 1 other A record removed (was 198.51.100.1, 198.51.100.2)"
    assert [(r["name"], r["data"]) for r in fake.records["example.com"] if r["type"] == "A"].count(("home", HOME)) == 1


def test_a_record_someone_else_changed_is_left_as_it_is(made, env):
    env(settings_of(ddns=True))
    p, fake = made()
    p.refresh()
    p.ddns_update(force=False)  # made at HOME
    next(r for r in fake.records["example.com"] if r["name"] == "home")["data"] = "198.51.100.99"  # set by hand since
    (h,) = p.ddns_update(force=False)
    assert len(fake.writes()) == 1 and h["foreign"] is True and h["holds"] == ["198.51.100.99"]


def test_no_address_found_sends_nothing_and_says_why(made, env):
    env(settings_of(ddns=True))
    p, fake = made(public=lambda: (None, "neither OpenDNS nor Google answered with a public IPv4 address"))
    p.refresh()
    (h,) = p.ddns_update(force=True)
    assert fake.writes() == [] and h["ok"] is False
    assert h["result"] == ("this network's address was not found: neither OpenDNS nor Google answered with a public IPv4 "
                           "address")


def test_the_domain_itself_is_asked_by_its_own_name(made, env):
    env(settings_of(ddns=True, DIGITALOCEAN_DDNS_HOSTS="@.example.net"))
    p, fake = made()
    p.refresh()
    (h,) = p.ddns_update(force=False)
    asked = [r["query"] for r in fake.requests if r["path"] == "/v2/domains/example.net/records" and "name" in r["query"]]
    assert asked[0]["name"] == "example.net" and h["host"] == "example.net"
    assert a_writes(fake) == [("POST", "/v2/domains/example.net/records", {"type": "A", "name": "@", "data": HOME, "ttl": 60})]


def test_a_pass_whose_plugin_was_detached_writes_nothing(made, env):
    env(settings_of(ddns=True))
    p, fake = made()
    p.refresh()
    hosts, _ = p.config().ddns_hosts(p.zones())
    stop = threading.Event()
    stop.set()
    p.keeper().run_pass(hosts, force=True, stop=stop)
    assert fake.writes() == []


def test_a_host_taken_out_of_the_settings_is_let_go(made, env, monkeypatch):
    env(settings_of(ddns=True, DIGITALOCEAN_DDNS_HOSTS="home.example.com, www.example.com"))
    p, fake = made()
    p.refresh()
    p.ddns_update(force=False)
    p.ask("ddns_take_over", "www.example.com", "203.0.113.10")
    keeper = p.keeper()
    assert keeper.own("home.example.com") == HOME and keeper.taken("www.example.com")
    monkeypatch.setenv("DIGITALOCEAN_DDNS_HOSTS", "home.example.com")
    p.settings_changed()
    p.ddns_update(force=False)
    assert not keeper.taken("www.example.com") and keeper.own("www.example.com") is None  # no longer its own
    assert keeper.own("home.example.com") == HOME


def test_hosts_in_none_of_the_accounts_domains_are_said_and_the_page_draws_the_rest(made, env):
    env(settings_of(ddns=True, DIGITALOCEAN_DDNS_HOSTS="home.example.com, nas.example.org"))
    p, fake = made()
    st = p.status()
    table = ddns_table(st)
    assert table["rows"] == [] and table["empty"] == "The hosts are checked once the account's domains are read."
    p.refresh()
    p.ddns_update(force=False)
    st = p.status()
    table = ddns_table(st)
    assert [r[0] for r in table["rows"]] == ["home.example.com"] and table["rows"][0][1] == HOME
    assert f"this network's address: {HOME}" in table["note"] and table["rows"][0][4] == "made (was none)"
    assert table["rows"][0][5] == ""  # its own: no Take over…
    assert "Dynamic DNS: nas.example.org is in none of the account's domains" in st["problem"]
    assert st["ddnsEvery"] == "every 5 min, once attached" and st["summary"].endswith(f"home.example.com at {HOME}")
    with pytest.raises(ValueError, match="no Dynamic DNS host is in the account's domains"):
        env({"DIGITALOCEAN_DDNS_HOSTS": "nas.example.org"})
        p.settings_changed()
        p.ddns_update()


def test_the_state_file_is_under_the_platforms_folder(tmp_path, monkeypatch):
    from liminal_libs import layout
    from plugin_platform_digitalocean import ddns_state

    assert ddns_state() == tmp_path / "platform" / "digitalocean" / "ddns.json"
    monkeypatch.delenv("LIMINAL_PLATFORM_DIR")
    assert ddns_state() == layout.data_dir() / "platform" / "digitalocean" / "ddns.json"
    assert DigitalOceanPlugin(state=tmp_path / "x.json").state_path == tmp_path / "x.json"
