"""The plugin over the stand-ins: its settings read through the Login interface, its status from what was read (no request
made to answer it; no value of a setting in it), valid while the token is set and the last read worked or is untried, the
background reading only while attached, its hooks asked by name, its errors worded with the token scrubbed, the command
line."""
from __future__ import annotations

import json
import threading
import time

import pytest

import plugin_platform_digitalocean as module
import plugin_platform_digitalocean.__main__ as cli
import plugin_platform_digitalocean.settings as settings_mod
from conftest import DB, HOME, TOKEN, WEB, Charts, FakeDigitalOcean, Pairs, Platform, droplet, settings_of
from liminal_libs.machines.rest import RestError
from plugin_platform_digitalocean import NOT_SET, RETRY_S, SCOPES_WORDS
from plugin_platform_digitalocean.settings import read


def wait_until(test, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if test():
            return True
        time.sleep(0.02)
    return False


def table(status: dict, title: str) -> dict:
    return next(t for t in status["tables"] if t["title"] == title)


def test_nothing_set_is_not_valid_and_says_what_to_set_where_with_which_scopes(made):
    p, fake = made()
    st = p.status()
    assert st["present"] is False and st["valid"] is False and st["why"] == NOT_SET and not p.present()
    assert "DIGITALOCEAN_TOKEN" in st["why"] and "https://cloud.digitalocean.com/account/api/tokens" in st["why"]
    assert "Custom Scopes" in st["why"] and "droplet:update" in st["why"] and "firewall:update" in st["why"]
    assert st["tables"] == [] and st["actions"] == [] and st["forms"] == [] and fake.requests == []
    with pytest.raises(ValueError, match="not set up"):
        p.refresh()
    with pytest.raises(ValueError, match="Dynamic DNS is not set up"):
        p.ddns_update()


def test_hosts_without_the_token_are_set_up_halfway(made, env):
    env(settings_of(token=False, ddns=True))
    p, fake = made()
    st = p.status()
    assert st["valid"] is False and st["summary"] == "set up halfway" and "Dynamic DNS goes through" in st["why"]
    assert st["settingsSet"] == "DIGITALOCEAN_DDNS_HOSTS" and fake.requests == []


def test_the_settings_are_read_through_the_login_by_their_pairs():
    login = Pairs(settings_of(ddns=True, DIGITALOCEAN_DDNS_MINUTES="15"))
    c = read(login)
    assert (c.token, c.hosts, c.minutes) == (TOKEN, ("home.example.com",), 15.0) and c.api_ready and c.ddns_ready
    assert "digitalocean-token" in login.asked and "DIGITALOCEAN_TOKEN" not in login.asked  # asked by the pairs' names
    assert TOKEN not in repr(c)
    assert read(Pairs({"DIGITALOCEAN_DDNS_MINUTES": "lots"})).minutes == 5.0
    assert read(Pairs({"DIGITALOCEAN_DDNS_MINUTES": "99999"})).minutes == 1440.0

    class Down(Pairs):
        def names(self):
            raise ConnectionError("the login app is not answering")
    assert read(Down({})).problems == ("the settings could not be read from the login: ConnectionError",)


def test_a_refresh_draws_the_account_in_tables_and_the_status_asks_nothing(made, env):
    env(settings_of())
    p, fake = made()
    st = p.status()
    assert st["valid"] is True and st["summary"] == "the account is read once attached" and fake.requests == []
    done = p.refresh()
    assert (done["droplets"], done["domains"], done["firewalls"]) == (2, 2, 2)
    assert len(fake.requests) <= 30  # a refresh's requests, well under 250 a minute
    assert {(m, q.get("per_page")) for m, q in ((r["method"], r["query"]) for r in fake.requests)} <= {
        ("GET", "200"), ("GET", "1"), ("GET", None)}  # reads only, each list in pages of 200 (a count: one item)
    calls = len(fake.requests)
    st = p.status()
    assert len(fake.requests) == calls  # the status asks nothing of DigitalOcean
    assert st["valid"] is True and "problem" not in st
    assert st["summary"] == "2 Droplets (1 on, 1 off) · 2 domains · $11.21 used this month"
    assert st["account"] == "sammy@example.com · team My Team" and st["accountStatus"] == "active"
    assert st["dropletLimit"] == "25" and st["balance"].startswith("$11.21 used this month · month-to-date balance $23.44")
    assert st["poweredOffDroplets"].startswith("still billed") and st["tokenScopes"] == SCOPES_WORDS
    assert st["rateLimit"] == f"{5000 - calls:,} of 5,000 requests left this hour" and st["settingsSet"] == "DIGITALOCEAN_TOKEN"
    assert [t["title"] for t in st["tables"]] == [
        "Droplets", "Domains", "example.com records", "example.net records", "Cloud firewalls", "web rules", "db rules",
        "Volumes", "SSH keys", "Reserved IPs", "Also in the account"]
    for t in st["tables"]:
        assert set(t) >= {"title", "columns", "rows"} and all(len(r) == len(t["columns"]) for r in t["rows"]), t["title"]
    droplets = table(st, "Droplets")
    assert "A powered-off Droplet still bills" in droplets["note"] and "≈ $30.00 a month in all" in droplets["note"]
    web, db = droplets["rows"]
    assert web[0] == {"text": "web-1", "sub": "web"} and web[1] == "on" and web[2] == {"text": "nyc3", "sub": "New York 3"}
    assert web[3] == {"text": "s-1vcpu-1gb", "sub": "1 vCPU · 1 GB · 25 GB disk"}
    assert web[4] == {"text": "203.0.113.10", "sub": f"private 10.110.0.{WEB % 200}"} and web[5] == "2001:db8::10"
    assert (web[6], web[7], web[8]) == ("$6.00", "$0.00893", "2025-03-01")
    assert db[1] == "off" and (db[6], db[7]) == ("$24.00", "$0.03571")
    assert web[9]["form"] == f"power:{WEB}" and db[9]["form"] == f"power:{DB}"
    records = table(st, "example.com records")
    assert records["actions"] == [{"form": "set:example.com", "title": "Set a record…"}]
    kept = [r for r in records["rows"] if r[-1] == "DigitalOcean's"]
    assert [(r[0], r[1]) for r in kept] == [("@", "NS"), ("@", "NS"), ("@", "NS"), ("@", "SOA")]  # no Remove: DigitalOcean's
    assert table(st, "Domains")["rows"] == [["example.com", "1800", "10"], ["example.net", "3600", "2"]]
    fws = table(st, "Cloud firewalls")["rows"]
    assert fws[0][0] == {"text": "web", "sub": "bb4b2611-3d72-467b-8602-280330ecd65c"} and fws[0][2] == "web-1"
    assert fws[1][2] == {"text": "db-1", "sub": "tags db"} and (fws[0][3], fws[0][4]) == ("2", "2")
    rules = table(st, "web rules")
    assert rules["rows"][0][:4] == ["inbound", "allow", "tcp 22", "every IPv4 address, every IPv6 address"]
    assert rules["actions"] == [{"form": "fw-add:bb4b2611-3d72-467b-8602-280330ecd65c", "title": "Add a rule…"}]
    assert table(st, "db rules")["rows"][0][3] == "tags web"
    vols = table(st, "Volumes")
    assert "bills whether it is attached or not" in vols["note"]
    assert vols["rows"][0][:4] == [{"text": "data", "sub": "the database's disk"}, "nyc3", "100", "db-1"]
    assert vols["rows"][1][3] == "not attached"
    keys = table(st, "SSH keys")
    assert keys["rows"][0][0] == "laptop" and keys["rows"][0][2]["sub"] == "sammy@laptop"
    assert keys["actions"] == [{"form": "key-add", "title": "Add a key…"}]
    assert table(st, "Reserved IPs")["rows"] == [["198.51.100.20", "nyc3", "web-1", "–"], ["198.51.100.21", "nyc3", "not assigned", "–"]]
    assert "billed while it is not" in table(st, "Reserved IPs")["note"]
    assert table(st, "Also in the account")["rows"] == [["Kubernetes clusters", "1"], ["Load balancers", "0"],
                                                        ["Databases", "2"], ["Apps", "3"], ["Snapshots", "4"],
                                                        ["Custom images", "1"], ["Projects", "2"], ["VPCs", "1"]]
    assert [a["hook"] for a in st["actions"]] == ["refresh"]
    hooks = p.interface()["hooks"]
    assert all(a["hook"] in hooks for a in st["actions"]) and all(f["hook"] in hooks for f in st["forms"])
    flat = {k: v for k, v in st.items() if not isinstance(v, (list, dict))}
    assert all(isinstance(v, (str, bool)) for v in flat.values())
    assert TOKEN not in json.dumps(st)  # names of the settings, never a value


def test_a_list_is_read_across_its_pages_and_a_next_page_elsewhere_is_never_followed(made, env):
    env(settings_of())
    fake = FakeDigitalOcean()
    fake.droplets = fake.droplets + [{**fake.droplets[0], "id": 4000 + i, "name": f"n{i}"} for i in range(250)]
    p, fake = made(fake)
    assert len(p.droplets()) == 252
    pages = [r["query"] for r in fake.requests if r["path"] == "/v2/droplets"]
    assert pages[:2] == [{"per_page": "200"}, {"page": "2", "per_page": "200"}] and pages[2] == {"per_page": "200", "type": "gpus"}

    def elsewhere(method, url, headers, body, timeout):
        status, h, b = fake(method, url, headers, body, timeout)
        data = json.loads(b)
        data["links"] = {"pages": {"next": "https://api.example.org/v2/droplets?page=2"}}
        return status, h, json.dumps(data).encode()
    q, _ = made(public=None)
    q._transport = elsewhere
    with pytest.raises(RestError, match="not DigitalOcean's API: not followed"):
        q.droplets()


def test_gpu_droplets_are_listed_too_and_their_trouble_hides_none_of_the_others(made, env):
    env(settings_of())
    fake = FakeDigitalOcean()
    fake.gpus = [droplet(5000, "gpu-1", "active", "gpu-h100x1-80gb", 3201.02, 4.41, "203.0.113.30")]
    p, fake = made(fake)
    p.refresh()
    rows = table(p.status(), "Droplets")["rows"]
    assert [r[0] if isinstance(r[0], str) else r[0]["text"] for r in rows] == ["web-1", "db-1", "gpu-1"]
    assert (rows[2][6], rows[2][7]) == ("$3,201.02", "$4.41")
    fake.gpu_error = (500, {"id": "server_error", "message": "Server Error"})
    p.refresh()
    st = p.status()
    assert [r[0]["text"] if isinstance(r[0], dict) else r[0] for r in table(st, "Droplets")["rows"]] == ["web-1", "db-1"]
    assert "the GPU Droplets: GET /v2/droplets: HTTP 500: Server Error" in st["problem"] and st["valid"] is True
    assert [d["name"] for d in p.droplets()] == ["web-1", "db-1"]


def test_a_part_the_token_cannot_read_is_said_beside_the_rest(made, env):
    env(settings_of())
    fake = FakeDigitalOcean()
    fake.forbidden = {"/v2/customers/my/balance", "/v2/kubernetes/clusters", "/v2/firewalls"}
    p, fake = made(fake)
    p.refresh()
    st = p.status()
    assert st["valid"] is True and "balance" not in st
    assert "the balance: not readable with this token (it needs billing:read)" in st["problem"]
    assert "the cloud firewalls: not readable with this token (it needs firewall:read)" in st["problem"]
    assert "not counted: kubernetes:read" in st["problem"]
    assert table(st, "Also in the account")["rows"][0] == ["Kubernetes clusters", "needs kubernetes:read"]
    assert "Cloud firewalls" not in [t["title"] for t in st["tables"]] and not any(f["id"].startswith("fw-") for f in st["forms"])


def test_a_refused_token_is_not_valid_and_its_words_hold_no_token(made, env):
    env(settings_of())
    fake = FakeDigitalOcean(token="dop_v1_" + "f" * 64)  # not the token set
    fake.echo_token = True  # its message holds what was sent
    p, fake = made(fake)
    with pytest.raises(RestError) as refused:
        p.refresh()
    words = str(refused.value)
    assert refused.value.status == 401 and TOKEN not in words and "•••" in words
    assert "the token is wrong, expired or revoked: make one at https://cloud.digitalocean.com/account/api/tokens" in words
    st = p.status()
    assert st["valid"] is False and st["why"].startswith("the API: GET /v2/account: HTTP 401") and TOKEN not in json.dumps(st)
    assert TOKEN not in json.dumps(p.api_facts())


def test_a_connection_failure_is_worded_with_the_token_scrubbed_and_tried_again_later(made, env):
    env(settings_of())
    t = [1_000_000.0]
    fake = FakeDigitalOcean()
    fake.down = True  # its words hold the Authorization header sent
    p, fake = made(fake)
    p._clock = lambda: t[0]
    with pytest.raises(RestError) as failed:
        p.refresh()
    assert TOKEN not in str(failed.value) and "ConnectionError" in str(failed.value)
    st = p.status()
    assert st["valid"] is False and TOKEN not in json.dumps(st) and TOKEN not in json.dumps(p.api_facts())
    t[0] += RETRY_S
    st = p.status()
    assert st["valid"] is True and st["summary"] == "the account is read once attached"  # the platform attaches it again


def test_another_token_makes_a_failed_read_untried_and_forgets_what_the_last_one_read(made, env, monkeypatch):
    env(settings_of())
    p, fake = made()
    p.refresh()
    assert table(p.status(), "Droplets")["rows"]
    monkeypatch.setenv("DIGITALOCEAN_TOKEN", "dop_v1_" + "e" * 64)
    p.settings_changed()
    st = p.status()
    assert st["valid"] is True and st["summary"] == "the account is read once attached"
    p.client()
    assert "Droplets" not in [t["title"] for t in p.status()["tables"]]  # another token: nothing of the last one shown


def test_attached_by_the_platform_it_reads_in_the_background_through_its_login_and_detached_nothing_runs(made):
    p, fake = made()
    login = Pairs(settings_of(ddns=True))
    p.attach(Platform(), login)
    try:
        assert p.working
        assert wait_until(lambda: p.status()["summary"] ==
                          f"2 Droplets (1 on, 1 off) · 2 domains · $11.21 used this month · home.example.com at {HOME}")
        assert "digitalocean-token" in login.asked
    finally:
        p.detach()
    assert not p.working and p.login is None
    calls = len(fake.requests)
    time.sleep(0.1)
    assert len(fake.requests) == calls


def test_another_app_attaching_it_starts_nothing(made):
    """The charts app run alone attaches every plugin it finds: only the platform's attach starts the reads and Dynamic
    DNS (App.NAME "platform")."""
    p, fake = made()
    login = Pairs(settings_of(ddns=True))
    for app in (Charts(), object()):
        p.attach(app, login)
        try:
            assert not p.working
            time.sleep(0.1)
            assert fake.requests == [] and p.status()["summary"] == "the account is read once attached"
        finally:
            p.detach()


def test_a_pass_under_way_ends_once_detached_reading_no_settings_and_writing_nothing(made, monkeypatch):
    """Detached in the middle of a Dynamic DNS pass (its address asked again just before a write, a slow answer): the
    pass ends there. Nothing is written, no login is asked and none of the environment read after the detach."""
    monkeypatch.setattr(module, "STOP_WAIT_S", 0.05)
    hold, held = threading.Event(), threading.Event()
    asked_address = []

    def public():  # the pass's first ask answers; the ask again before its write hangs until released
        asked_address.append(1)
        if len(asked_address) > 1:
            held.set()
            hold.wait(5)
        return HOME, "OpenDNS"
    p, fake = made(public=public)
    login = Pairs(settings_of(ddns=True))  # home.example.com has no record: the pass would make one
    reads = []
    real = settings_mod.read
    monkeypatch.setattr(settings_mod, "read", lambda login=None: reads.append(login) or real(login))
    p.attach(Platform(), login)
    assert held.wait(5)  # the worker is in its pass, about to write
    p.detach()  # waits STOP_WAIT_S, then goes: the worker runs on, stopped
    asked = len(reads)
    hold.set()
    assert wait_until(lambda: not any(t.name == "digitalocean" and t.is_alive() for t in threading.enumerate()))
    assert len(reads) == asked  # no settings asked after the detach (none of the environment read)
    assert fake.writes() == []  # and no Dynamic DNS write
    assert p.keeper().state("home.example.com").result == "not updated: the plugin was detached: nothing written"


def test_a_token_with_a_line_break_is_never_sent_and_never_shown(made):
    p, fake = made()
    p.login = Pairs({"DIGITALOCEAN_TOKEN": TOKEN[:20] + "\r\n" + TOKEN[20:]})  # a wrapped paste, set outside the page
    st = p.status()
    assert st["valid"] is False and "holds a space or a line break: enter it again, alone" in st["why"]
    assert TOKEN[:20] not in json.dumps(st) and TOKEN[20:] not in json.dumps(st) and fake.requests == []
    with pytest.raises(ValueError, match="not set up"):
        p.refresh()
    assert fake.requests == []


def test_the_hooks_are_asked_by_name_as_the_platform_asks_them(made, env):
    env(settings_of())
    p, fake = made()
    assert [d["name"] for d in p.ask("droplets")] == ["web-1", "db-1"]
    assert [d["name"] for d in p.ask("domains")] == ["example.com", "example.net"]
    assert len(p.ask("records", "example.com")) == 10
    assert [f["name"] for f in p.ask("firewalls")] == ["web", "db"]
    assert [k["name"] for k in p.ask("ssh_keys")] == ["laptop"]
    assert p.ask("balance")["month_to_date_usage"] == "11.21"
    with pytest.raises(LookupError):
        p.ask("check")
    with pytest.raises(ValueError, match="not one of the account's domains"):
        p.ask("records", "example.org")


def test_settings_entered_on_the_platforms_page_are_read_at_once(made):
    from liminal_libs.apps import EnvironmentLogin

    p, fake = made()
    kept: dict[str, str] = {}
    p.login = EnvironmentLogin(env=kept)  # as the platform lends its login to a plugin not yet attached
    assert p.status()["valid"] is False
    for variable, value in settings_of().items():
        p.login.save(variable, value)
    assert p.status()["valid"] is False  # still the settings read a moment ago
    p.settings_changed()
    st = p.status()
    assert st["valid"] is True and "DIGITALOCEAN_TOKEN" in st["settingsSet"] and TOKEN not in str(st)


def test_the_command_line(made, env):
    env(settings_of(ddns=True))
    p, fake = made()
    lines, errors, answers = [], [], []

    def run(*argv, say=()):
        lines.clear()
        errors.clear()
        answers[:] = list(say)
        return cli.main(list(argv), plugin=p, out=lines.append, err=errors.append, ask=lambda prompt: answers.pop(0))
    assert run("servers") == 0 and lines[0].startswith("web-1") and "$6.00/month" in lines[0] and "still bills" in lines[-1]
    assert run("domains") == 0 and [x.split() for x in lines] == [["example.com", "ttl", "1800"], ["example.net", "ttl", "3600"]]
    assert run("records", "example.com") == 0 and len(lines) == 10 and "[14]" in lines[4]
    assert run("firewalls") == 0 and lines[0] == "web (succeeded): applies to 1 Droplet"
    assert lines[1] == "  inbound allow tcp 22 from addresses 0.0.0.0/0, ::/0"
    assert run("keys") == 0 and lines[0].startswith("laptop")
    assert run("ddns") == 0 and lines[0].startswith("home.example.com") and "made" in lines[0]
    assert run("--json", "ddns", "--now") == 0 and json.loads("\n".join(lines))[0]["ok"] is True
    writes = len(fake.writes())
    assert run("power", "web-1", "reboot", say=["no"]) == 1 and errors == ["not asked"] and len(fake.writes()) == writes
    assert run("power", "web-1", "reboot", say=["yes"]) == 0 and lines[0] == "reboot asked for web-1"
    assert fake.writes()[-1]["json"] == {"type": "reboot"}
    assert run("power", "web-1", "hard-off", say=["yes", "no"]) == 1 and fake.writes()[-1]["json"] == {"type": "reboot"}
    assert run("power", "web-1", "hard-off", say=["yes", "yes"]) == 0 and fake.writes()[-1]["json"] == {"type": "power_off"}
    assert run("set", "example.com", "home", "A", "203.0.113.99", "--ttl", "300", say=["yes", "no"]) == 1
    assert errors == ["not written"] and fake.writes()[-1]["json"] == {"type": "power_off"}  # what it holds is named first
    assert run("set", "example.com", "home", "A", "203.0.113.99", "--ttl", "300", say=["yes", "yes"]) == 0
    assert lines[0].startswith("example.com: set home A 203.0.113.99")  # ddns made home a moment ago: changed in place
    assert run("set", "example.com", "home", "A", "203.0.113.99", "--ttl", "600", say=["yes"]) == 0  # its TTL alone: once
    assert run("remove", "example.com", "@", "TXT", say=["yes"]) == 0 and lines[0] == "example.com: removed @ TXT v=spf1 -all"
    assert run("remove", "example.com", "@", "NS", "ns1.digitalocean.com", say=["yes"]) == 1
    assert errors[0].startswith("refused: DigitalOcean keeps its name servers' NS records")
    assert run("status") == 0 and json.loads("\n".join(lines))["valid"] is True
    fake.fail[("GET", "/v2/droplets")] = (500, {"id": "server_error", "message": "Server Error"})
    assert run("servers") == 1 and errors[0].startswith("digitalocean: GET /v2/droplets: HTTP 500: Server Error")
    with pytest.raises(SystemExit):
        run("nonsense")
