"""The platform's page changes the account through the plugin's forms (liminal-platform's status.forms): the fields are the
hooks' arguments in order, each change confirmed by the user with the exact change named; a hard power-off or power
cycle and a risky firewall rule only once the user has accepted that too, a second confirmation offered when the hook
refuses without it. Each hook sends exactly the request DigitalOcean's reference gives (method, path, body). Over the
stand-ins alone."""
from __future__ import annotations

import inspect

import pytest

from conftest import DB, DB_FW, WEB, WEB_FW, FakeDigitalOcean, ed25519, fingerprint, record, settings_of
from liminal_libs.machines.rest import RestError
from plugin_platform_digitalocean import ACCEPT_HARD, ACCEPT_RISKY, BILLING
from plugin_platform_digitalocean.errors import Refusal


def page_args(form: dict, values: dict, accepted=()) -> list:
    """What the platform's page sends for a form (platform.js argsOf): the fields' values in order, a field whose `when` is
    unmet or left empty null (the hook's default), a number as a number, an accept field true only once accepted."""
    now = {**{x["name"]: x.get("value") for x in form["fields"]}, **values}
    out = []
    for x in form["fields"]:
        if x["type"] == "accept":
            out.append(x["name"] in accepted)
            continue
        shown = all(str(now.get(k) or "") in [str(v) for v in vs] for k, vs in (x.get("when") or {}).items())
        v = now.get(x["name"])
        out.append(None if not shown or v in (None, "") else int(v) if x["type"] == "number" else v)
    return out


def forms_of(status: dict) -> dict:
    return {f["id"]: f for f in status["forms"]}


def table(status: dict, title: str) -> dict:
    return next(t for t in status["tables"] if t["title"] == title)


def last(fake) -> tuple:
    w = fake.writes()[-1]
    return w["method"], w["path"], w["json"]


@pytest.fixture
def ready(made, env):
    env(settings_of())

    def make(fake=None):
        p, fake = made(fake)
        p.refresh()
        return p, fake, forms_of(p.status())
    return make


def test_every_form_names_its_hooks_arguments_in_order_and_drawing_writes_nothing(ready):
    p, fake, forms = ready()
    assert set(forms) == {f"power:{WEB}", f"power:{DB}", "set:example.com", "remove:example.com", "set:example.net",
                          "remove:example.net", f"fw-add:{WEB_FW}", f"fw-remove:{WEB_FW}", f"fw-add:{DB_FW}",
                          f"fw-remove:{DB_FW}", "key-add", "key-remove"}
    hooks = p.interface()["hooks"]
    for f in forms.values():
        assert f["hook"] in hooks
        assert [x["name"] for x in f["fields"]] == list(inspect.signature(getattr(p, f["hook"])).parameters), f["id"]
        assert all(x["type"] in ("text", "number", "choice", "fixed", "accept") for x in f["fields"])
        assert f["confirm"]["title"] and f["confirm"]["words"] and f["confirm"]["yes"]
    web, db = forms[f"power:{WEB}"], forms[f"power:{DB}"]
    assert [c["value"] for c in next(x for x in web["fields"] if x["name"] == "action")["choices"]] == [
        "shutdown", "reboot", "power_off", "power_cycle"]
    assert [c["value"] for c in next(x for x in db["fields"] if x["name"] == "action")["choices"]] == ["power_on"]
    assert BILLING in web["confirm"]["words"] and web["confirm"]["danger"] is True
    (hard,) = [x for x in web["fields"] if x["type"] == "accept"]
    assert hard["name"] == ACCEPT_HARD and "unsaved data is lost" in hard["words"]
    for fid in (f"fw-add:{WEB_FW}", f"fw-remove:{WEB_FW}"):
        (risky,) = [x for x in forms[fid]["fields"] if x["type"] == "accept"]
        assert risky["name"] == ACCEPT_RISKY and "{firewall}" in risky["words"]
    assert "every other record of example.com is kept" in forms["set:example.com"]["confirm"]["words"]
    assert forms["remove:example.com"]["confirm"]["danger"] is True
    assert "keep it" in forms["key-remove"]["confirm"]["words"]
    assert fake.writes() == []  # drawn: nothing written


def test_power_sends_the_action_the_reference_gives(ready):
    p, fake, forms = ready()
    web, db = forms[f"power:{WEB}"], forms[f"power:{DB}"]
    assert page_args(db, {}) == [DB, "db-1", "power_on", False]
    rep = p.ask(db["hook"], *page_args(db, {}))
    assert last(fake) == ("POST", f"/v2/droplets/{DB}/actions", {"type": "power_on"})
    assert rep["said"] == "power on asked for db-1" and rep["ok"] and rep["action"]["status"] == "in-progress"
    fresh = [r for r in fake.requests if r["path"] == f"/v2/droplets/{DB}"]
    assert fresh and fresh[-1]["method"] == "GET"  # the Droplet read again before its action was asked
    for action in ("shutdown", "reboot"):
        rep = p.ask(web["hook"], *page_args(web, {"action": action}))
        assert last(fake) == ("POST", f"/v2/droplets/{WEB}/actions", {"type": action})
    assert BILLING in p.ask(web["hook"], *page_args(web, {"action": "shutdown"}))["lines"]  # off, it still bills
    assert all(r["type"] == "application/json" and r["auth"].startswith("Bearer ") for r in fake.writes())


def test_a_hard_power_off_is_asked_twice_saying_unsaved_data_is_lost(ready):
    p, fake, forms = ready()
    web = forms[f"power:{WEB}"]
    for action in ("power_off", "power_cycle"):
        writes = len(fake.writes())
        with pytest.raises(Refusal, match="unsaved data is lost") as refused:  # the first confirmation is not enough
            p.ask(web["hook"], *page_args(web, {"action": action}))
        assert refused.value.accept == ACCEPT_HARD and len(fake.writes()) == writes
        p.ask(web["hook"], *page_args(web, {"action": action}, accepted={ACCEPT_HARD}))
        assert last(fake) == ("POST", f"/v2/droplets/{WEB}/actions", {"type": action})


def test_power_refuses_what_the_droplet_as_it_is_now_cannot_take(ready):
    p, fake, forms = ready()
    web, db = forms[f"power:{WEB}"], forms[f"power:{DB}"]
    with pytest.raises(Refusal, match="is on: it can be shut down, reboot, power off"):
        p.ask("power", WEB, "web-1", "power_on")
    with pytest.raises(Refusal, match="is off: it can be power on here, not shut down"):
        p.ask("power", DB, "db-1", "shutdown")
    fake.droplets[0]["name"] = "web-renamed"
    with pytest.raises(Refusal, match="is named web-renamed now, not web-1"):
        p.ask(web["hook"], *page_args(web, {"action": "reboot"}))
    fake.droplets[1]["locked"] = True
    with pytest.raises(Refusal, match="is locked"):
        p.ask(db["hook"], *page_args(db, {}))
    with pytest.raises(RestError, match="HTTP 404"):
        p.ask("power", 999, None, "reboot")
    assert fake.writes() == []


def test_a_record_set_sends_exactly_the_request_the_reference_gives_and_keeps_every_other(ready):
    p, fake, forms = ready()
    s = forms["set:example.com"]
    before = fake.rows()

    def put(values):
        rep = p.ask(s["hook"], *page_args(s, values))
        return rep, last(fake)
    rep, sent = put({"name": "home", "rtype": "A", "data": "203.0.113.50"})
    assert sent == ("POST", "/v2/domains/example.com/records", {"type": "A", "name": "home", "data": "203.0.113.50", "ttl": 1800})
    asked = [r for r in fake.requests if r["method"] == "GET" and r["path"] == "/v2/domains/example.com/records"][-2]
    assert asked["query"] == {"name": "home.example.com", "per_page": "200"}  # the records at its full name, read first
    assert rep["said"] == "added home A 203.0.113.50" and rep["changed"] and fake.rows()[:len(before)] == before
    rep, sent = put({"name": "www.example.com", "rtype": "A", "data": "203.0.113.60"})  # changed in place, its TTL kept
    assert sent == ("PUT", "/v2/domains/example.com/records/15", {"type": "A", "name": "www", "data": "203.0.113.60", "ttl": 3600})
    assert rep["said"] == "set www A 203.0.113.60 (it was 203.0.113.10)"
    writes = len(fake.writes())
    rep = p.ask(s["hook"], *page_args(s, {"name": "www", "rtype": "A", "data": "203.0.113.60"}))
    assert rep["changed"] is False and "there already: nothing sent" in rep["said"] and len(fake.writes()) == writes
    _, sent = put({"name": "@", "rtype": "MX", "data": "mail2.example.com", "priority": "20"})
    assert sent == ("POST", "/v2/domains/example.com/records",
                    {"type": "MX", "name": "@", "data": "mail2.example.com.", "priority": 20, "ttl": 1800})
    rep, sent = put({"name": "@", "rtype": "MX", "data": "mail.example.com.", "priority": "5"})  # the same server: changed
    assert sent == ("PUT", "/v2/domains/example.com/records/16",
                    {"type": "MX", "name": "@", "data": "mail.example.com.", "priority": 5, "ttl": 14400})
    assert rep["said"] == "set @ MX mail.example.com. (priority 5): priority 10 → 5"
    _, sent = put({"name": "shop", "rtype": "CNAME", "data": "shops.example.net"})
    assert sent[2] == {"type": "CNAME", "name": "shop", "data": "shops.example.net.", "ttl": 1800}  # a host name ends with a dot
    _, sent = put({"name": "@", "rtype": "TXT", "data": "google-site-verification=abc"})
    assert sent == ("POST", "/v2/domains/example.com/records",
                    {"type": "TXT", "name": "@", "data": "google-site-verification=abc", "ttl": 1800})
    _, sent = put({"name": "@", "rtype": "CAA", "data": "letsencrypt.org", "flags": "0", "tag": "issue", "ttl": "3600"})
    assert sent[2] == {"type": "CAA", "name": "@", "data": "letsencrypt.org", "flags": 0, "tag": "issue", "ttl": 3600}
    _, sent = put({"name": "_sip._tcp", "rtype": "SRV", "data": "sip.example.com", "priority": "10", "weight": "5",
                   "port": "5060"})
    assert sent[2] == {"type": "SRV", "name": "_sip._tcp", "data": "sip.example.com.", "priority": 10, "port": 5060,
                       "weight": 5, "ttl": 1800}
    assert ("@", "TXT", "v=spf1 -all") in fake.rows() and ("_dmarc", "TXT", "v=DMARC1; p=none") in fake.rows()
    assert [w["method"] for w in fake.writes()] == ["POST", "PUT", "POST", "PUT", "POST", "POST", "POST", "POST"]


def test_a_record_removed_is_the_one_shown_and_the_rest_kept(ready):
    p, fake, forms = ready()
    rm = forms["remove:example.com"]
    rows = table(p.status(), "example.com records")["rows"]
    dmarc = next(r[-1] for r in rows if r[0] == "_dmarc")
    assert dmarc["values"] == {"name": "_dmarc", "rtype": "TXT", "data": "v=DMARC1; p=none", "record_id": 18}
    assert page_args(rm, dmarc["values"]) == ["example.com", "_dmarc", "TXT", "v=DMARC1; p=none", 18]
    before = fake.rows()
    rep = p.ask(rm["hook"], *page_args(rm, dmarc["values"]))
    assert last(fake) == ("DELETE", "/v2/domains/example.com/records/18", None)
    assert rep["said"] == "removed _dmarc TXT v=DMARC1; p=none" and fake.rows() == [r for r in before if r[0] != "_dmarc"]
    assert all(r[0] != "_dmarc" for r in table(p.status(), "example.com records")["rows"])  # read again after it


def test_record_changes_that_could_do_other_than_confirmed_are_refused_with_nothing_sent(ready):
    fake = FakeDigitalOcean()
    fake.records["example.com"].append(record(20, "A", "rr", "203.0.113.1"))
    fake.records["example.com"].append(record(21, "A", "rr", "203.0.113.2"))
    p, fake, forms = ready(fake)
    s, rm = forms["set:example.com"], forms["remove:example.com"]
    for values, why in (({"name": "@", "rtype": "CNAME", "data": "www.example.com"}, "cannot stand for the domain itself"),
                        ({"name": "www", "rtype": "CNAME", "data": "x.example.net"}, "holds other records"),
                        ({"name": "blog", "rtype": "A", "data": "203.0.113.5"}, "is a CNAME"),
                        ({"name": "rr", "rtype": "A", "data": "203.0.113.3"}, "holds 2 A records"),
                        ({"name": "@", "rtype": "SOA", "data": "x"}, "the SOA record is DigitalOcean's"),
                        ({"name": "home", "rtype": "A", "data": "not-an-ip"}, "not an IPv4 address"),
                        ({"name": "bad name!", "rtype": "A", "data": "203.0.113.5"}, "is not a record's name")):
        with pytest.raises(ValueError, match=why):
            p.ask(s["hook"], *page_args(s, values))
    with pytest.raises(Refusal, match="has 2 A records at rr: name the one to remove by its data"):
        p.ask("remove_record", "example.com", "rr", "A")
    with pytest.raises(Refusal, match="now holds 203.0.113.1, not 203.0.113.9"):
        p.ask(rm["hook"], *page_args(rm, {"name": "rr", "rtype": "A", "data": "203.0.113.9", "record_id": 20}))
    with pytest.raises(Refusal, match="DigitalOcean keeps its name servers' NS records"):
        p.ask("remove_record", "example.com", "@", "NS", "ns1.digitalocean.com")
    with pytest.raises(Refusal, match="not one of the account's domains"):
        p.ask("set_record", "example.org", "home", "A", "203.0.113.5")
    assert fake.writes() == []


def test_firewall_rules_added_and_removed_as_the_reference_gives_the_others_kept(ready):
    p, fake, forms = ready()
    add, rm = forms[f"fw-add:{DB_FW}"], forms[f"fw-remove:{DB_FW}"]
    others = {k: list(fake.fw(DB_FW)[k]) for k in ("droplet_ids", "tags")}
    rep = p.ask(add["hook"], *page_args(add, {"ports": "8080", "addresses": "203.0.113.0/24"}))
    assert last(fake) == ("POST", f"/v2/firewalls/{DB_FW}/rules", {"inbound_rules": [
        {"protocol": "tcp", "ports": "8080", "action": "allow", "sources": {"addresses": ["203.0.113.0/24"]}}]})
    assert rep["said"] == f"added to db: inbound allow tcp 8080 from addresses 203.0.113.0/24"
    p.ask(add["hook"], *page_args(add, {"direction": "outbound", "protocol": "udp", "ports": "53", "addresses": "0.0.0.0/0"}))
    assert last(fake)[2] == {"outbound_rules": [{"protocol": "udp", "ports": "53", "action": "allow",
                                                 "destinations": {"addresses": ["0.0.0.0/0"]}}]}
    p.ask(add["hook"], *page_args(add, {"protocol": "icmp", "droplets": "web-1", "tags": "monitor"}))
    assert last(fake)[2] == {"inbound_rules": [{"protocol": "icmp", "ports": "0", "action": "allow",
                                                "sources": {"droplet_ids": [WEB], "tags": ["monitor"]}}]}
    writes = len(fake.writes())
    rep = p.ask(add["hook"], *page_args(add, {"ports": "8080", "addresses": "203.0.113.0/24"}))
    assert rep["changed"] is False and len(fake.writes()) == writes  # held already: nothing sent
    rows = table(p.status(), "db rules")["rows"]
    postgres = next(r[-1] for r in rows if r[2] == "tcp 5432")
    assert postgres["values"] == {"direction": "inbound", "rule": "inbound allow tcp 5432 from tags web"}
    rep = p.ask(rm["hook"], *page_args(rm, postgres["values"]))
    assert last(fake) == ("DELETE", f"/v2/firewalls/{DB_FW}/rules", {"inbound_rules": [
        {"protocol": "tcp", "ports": "5432", "action": "allow", "sources": {"tags": ["web"]}}]})  # the rule as it was read
    assert {k: fake.fw(DB_FW)[k] for k in others} == others  # its Droplets and tags kept
    assert len(fake.fw(DB_FW)["inbound_rules"]) == 3 and rep["said"] == "removed from db: inbound allow tcp 5432 from tags web"
    with pytest.raises(ValueError, match="needs a source"):
        p.ask(add["hook"], *page_args(add, {"ports": "80"}))
    with pytest.raises(ValueError, match="not an address"):
        p.ask(add["hook"], *page_args(add, {"ports": "80", "addresses": "the internet"}))
    with pytest.raises(ValueError, match="not ports"):
        p.ask(add["hook"], *page_args(add, {"ports": "http", "addresses": "203.0.113.7"}))
    with pytest.raises(Refusal, match="holds no such inbound rule any more"):
        p.ask(rm["hook"], *page_args(rm, postgres["values"]))


def test_a_risky_firewall_rule_is_refused_without_accept_and_sent_with_it(ready):
    p, fake, forms = ready()
    add, web_rm = forms[f"fw-add:{DB_FW}"], forms[f"fw-remove:{WEB_FW}"]
    cases = (({"ports": "22", "addresses": "0.0.0.0/0"}, "opens SSH \\(port 22\\) of db's Droplets to the whole internet"),
             ({"ports": "all", "addresses": "::/0"}, "opens every tcp port of db's Droplets to the whole internet"),
             ({"ports": "22", "action": "deny", "addresses": "198.51.100.0/24"}, "a deny rule takes precedence"))
    for values, why in cases:
        writes = len(fake.writes())
        with pytest.raises(Refusal, match=why) as refused:  # the first confirmation is not enough
            p.ask(add["hook"], *page_args(add, values))
        assert refused.value.accept == ACCEPT_RISKY and len(fake.writes()) == writes
        rep = p.ask(add["hook"], *page_args(add, values, accepted={ACCEPT_RISKY}))
        assert last(fake)[:2] == ("POST", f"/v2/firewalls/{DB_FW}/rules") and rep["lines"][0].startswith("accepted: ")
    ssh = next(r[-1] for r in table(p.status(), "web rules")["rows"] if r[2] == "tcp 22")
    writes = len(fake.writes())
    with pytest.raises(Refusal, match="lets SSH \\(port 22\\) in to 1 Droplet.*no other rule lets SSH in") as refused:
        p.ask(web_rm["hook"], *page_args(web_rm, ssh["values"]))
    assert refused.value.accept == ACCEPT_RISKY and len(fake.writes()) == writes
    p.ask(web_rm["hook"], *page_args(web_rm, ssh["values"], accepted={ACCEPT_RISKY}))
    assert last(fake) == ("DELETE", f"/v2/firewalls/{WEB_FW}/rules", {"inbound_rules": [
        {"protocol": "tcp", "ports": "22", "sources": {"addresses": ["0.0.0.0/0", "::/0"]}}]})
    https = next(r[-1] for r in table(p.status(), "web rules")["rows"] if r[2] == "tcp 443")
    p.ask(web_rm["hook"], *page_args(web_rm, https["values"]))  # not SSH: one confirmation is enough
    assert last(fake)[2] == {"inbound_rules": [{"protocol": "tcp", "ports": "443", "sources": {"addresses": ["0.0.0.0/0", "::/0"]}}]}


def test_ssh_keys_added_and_removed_as_the_reference_gives(ready):
    p, fake, forms = ready()
    add, rm = forms["key-add"], forms["key-remove"]
    key = ed25519(b"\x07" * 32, "desk@home")
    rep = p.ask(add["hook"], *page_args(add, {"name": "desk", "public_key": "  " + key + "\n"}))
    assert last(fake) == ("POST", "/v2/account/keys", {"name": "desk", "public_key": key})
    assert rep["said"] == "added the SSH key desk" and fingerprint(key) in rep["lines"][0]
    rows = table(p.status(), "SSH keys")["rows"]
    assert [r[0] for r in rows] == ["laptop", "desk"]
    desk = rows[1][-1]
    assert desk["values"] == {"fingerprint": fingerprint(key), "name": "desk"}
    rep = p.ask(rm["hook"], *page_args(rm, desk["values"]))
    assert last(fake) == ("DELETE", f"/v2/account/keys/{fingerprint(key)}", None)
    assert [k["name"] for k in fake.keys] == ["laptop"] and "keep it" in rep["lines"][1]
    writes = len(fake.writes())
    with pytest.raises(Refusal, match="that is a private key"):
        p.ask(add["hook"], "oops", "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n-----END OPENSSH PRIVATE KEY-----")
    with pytest.raises(ValueError, match="not a public key"):
        p.ask(add["hook"], "oops", "ssh-ed25519 not-base64!")
    with pytest.raises(ValueError, match="its key is not one of ssh-rsa"):
        p.ask(add["hook"], "oops", key.replace("ssh-ed25519", "ssh-rsa", 1))
    with pytest.raises(ValueError, match="not an SSH key's fingerprint"):
        p.ask(rm["hook"], "../../droplets/1", "x")
    assert len(fake.writes()) == writes
