"""The plugin conforms to the class contract (plugin API 2.2: liminal_libs.sources.conformance, read from the plugin
alone), its API card names the calls its client really makes, and nothing billable is in the client: no call that makes,
resizes, restores or destroys a billable thing, nor one turning backups on, outside the card."""
from __future__ import annotations

import ast
import inspect
import os
import re
from pathlib import Path

import pytest

import plugin_platform_digitalocean as module
from liminal_libs.sources.apis import dead_links, facts_of, problems
from liminal_libs.sources.conformance import assert_module_conforms
from plugin_platform_digitalocean import api as api_mod
from plugin_platform_digitalocean import card

PACKAGE = Path(module.__file__).parent
FREE_WRITES = {  # the free changes, and nothing else
    ("POST", "/droplets/{droplet_id}/actions"), ("POST", "/domains/{domain_name}/records"),
    ("PUT", "/domains/{domain_name}/records/{domain_record_id}"), ("DELETE", "/domains/{domain_name}/records/{domain_record_id}"),
    ("POST", "/firewalls/{firewall_id}/rules"), ("DELETE", "/firewalls/{firewall_id}/rules"),
    ("POST", "/account/keys"), ("DELETE", "/account/keys/{ssh_key_identifier}"),
}


def test_it_conforms_to_the_class_contract_for_plugin_api_2_2():
    found = assert_module_conforms(module)
    assert found and all(p.api == "2.2" and not p.is_record for p in found)
    assert {p.SYSTEM for p in found} == {"platform"} and {p.KIND for p in found} == {"machine"}
    assert {(p.name, p.title, p.order, p.ICON) for p in found} == {("digitalocean", "DigitalOcean", 760, "digitalocean")}
    assert module.__version__ == "0.1.1"
    text = (PACKAGE.parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^version = "0\.1\.1"', text, re.M) and '"liminal-libs>=1.49.2"' in text


def test_its_settings_are_pairs_named_by_their_variables_and_only_the_token_is_secret():
    p = module.MACHINE
    assert [k.pair for k in p.keys] == ["digitalocean-token", "digitalocean-ddns-hosts", "digitalocean-ddns-minutes"]
    assert {k.name for k in p.keys if k.secret} == {"DIGITALOCEAN_TOKEN"}
    hint = p.keys[0].hint
    assert card.TOKENS in hint and all(s in hint for s in card.SCOPES)  # where it is made, with the exact scopes
    hooks = p.interface()["hooks"]
    assert {"present", "status", "refresh", "droplets", "domains", "records", "firewalls", "ssh_keys", "balance", "power",
            "set_record", "remove_record", "add_firewall_rule", "remove_firewall_rule", "add_ssh_key", "remove_ssh_key",
            "ddns_update", "ddns_take_over"} <= set(hooks)
    assert "check" not in hooks  # the platform's check is a plugin's check of this PC for an install: not this


def test_its_icon_is_its_makers_mark_drawn_by_the_library():
    from liminal_libs.ui import STATIC

    drawn = set(re.findall(r"^\s*([a-z]+):\s*'", (STATIC / "icons.js").read_text(encoding="utf-8"), re.M))
    assert module.MACHINE.ICON in drawn


def test_its_api_card_is_sound_and_names_every_part_of_the_reference():
    (api,) = module.MACHINE.apis
    assert problems(module.MACHINE.apis) == [] and api.name == card.NAME and api.verified == "2026-11-11"
    assert api.kind == "rest" and api.base == "https://api.digitalocean.com/v2" and api.docs == card.DOCS
    assert {x.kind for x in api.links} >= {"docs", "reference", "limits", "auth", "pricing", "status", "changelog", "spec",
                                            "console", "tool", "sdk"}
    assert len(api.areas) == 65  # the reference's 61 public areas and the 4 of its Inference APIs
    assert all(a.docs.startswith("https://docs.digitalocean.com/reference/api/reference/") for a in api.areas)
    covered = {a.name for a in api.covered}
    assert {"Account", "Billing", "Droplets", "Droplet Actions", "Domains", "Domain Records", "Firewalls", "Block Storage",
            "SSH Keys", "Reserved IPs"} <= covered
    assert {c.area for c in api.calls} <= {a.name for a in api.areas} and all(c.docs for c in api.calls)
    assert all(not c.costs for c in api.used)  # nothing it makes costs
    assert any(c.costs and not c.used for c in api.calls) and "powered off too" in api.costs


def test_the_card_names_the_calls_the_client_makes():
    """Every endpoint of the client (api.ENDPOINTS) is a call the card says the plugin makes, and the card says it makes
    no other; each write is a write on the card."""
    (api,) = module.MACHINE.apis
    made = {f"{m} /v2{p}" for m, p in api_mod.ENDPOINTS.values()}
    assert made == {c.name for c in api.used}
    for c in api.used:
        assert c.writes == (not c.name.startswith("GET ")), c.name


def test_nothing_billable_is_in_the_client():
    """The client's writes are the free changes alone (FREE_WRITES), every write sent through `path_of` one of them, a
    Droplet's action one of the five power actions; no billable or destroying call's path or action is anywhere in the
    package outside its API card."""
    writes = {(m, p) for m, p in api_mod.ENDPOINTS.values() if m != "GET"}
    assert writes == FREE_WRITES
    assert api_mod.POWER == ("power_on", "shutdown", "reboot", "power_off", "power_cycle")
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("post", "put", "patch", "delete", "request")):
                continue
            owner = node.func.value
            if not (isinstance(owner, ast.Attribute) and owner.attr == "rest"):
                continue
            assert path.name == "api.py", f"{path.name} sends a write itself"
            target = node.args[0] if node.args else None
            assert isinstance(target, ast.Call) and getattr(target.func, "id", "") == "path_of", ast.unparse(node)
            what = target.args[0].value
            method = {"post": "POST", "put": "PUT", "patch": "PATCH", "delete": "DELETE"}[node.func.attr]
            assert api_mod.ENDPOINTS[what] in FREE_WRITES and api_mod.ENDPOINTS[what][0] == method, ast.unparse(node)
        if path.name == "card.py":
            continue
        source = path.read_text(encoding="utf-8")
        for spends in ('"snapshot"', '"resize"', '"rebuild"', '"restore"', "enable_backups", "change_backup_policy",
                       "password_reset", "destroy_with_associated_resources", "/volumes/{", "/reserved_ips/{",
                       "/snapshots/{", "/load_balancers/{", "/kubernetes/clusters/{"):
            assert spends not in source, f"{path.name} holds {spends}"
        for creates in ("/droplets", "/volumes", "/reserved_ips", "/kubernetes/clusters", "/load_balancers", "/databases",
                        "/apps", "/snapshots", "/images"):
            assert not re.search(rf'\(\s*"(POST|PUT|PATCH|DELETE)"\s*,\s*"{re.escape(creates)}"\s*\)', source), creates


def test_a_droplet_action_other_than_power_is_never_sent(made, env):
    from conftest import WEB, settings_of

    env(settings_of())
    p, fake = made()
    api = p.client()
    for spends in ("snapshot", "resize", "enable_backups", "rebuild", "restore", "password_reset"):
        with pytest.raises(ValueError, match="not one of this plugin's Droplet actions"):
            api.power(WEB, spends)
        with pytest.raises(ValueError):
            p.power(WEB, "web-1", spends)
    assert fake.writes() == []


def test_api_facts_are_keyed_by_the_api_and_ask_nothing(made, env):
    from conftest import settings_of

    env(settings_of())
    p, fake = made()
    assert facts_of(p) == {card.NAME: {"Requests": "none yet", "Account read": "not yet",
                                       "Read": "every quarter of an hour while attached, and by Refresh"}}
    p.refresh()
    calls = len(fake.requests)
    facts = facts_of(p)[card.NAME]
    assert len(fake.requests) == calls  # asking nothing
    assert facts["Requests"] == f"{calls:,} made" and facts["Last answer"].startswith("HTTP 200")
    assert facts["Rate limit (an hour)"] == "5000" and int(facts["Requests left this hour"]) == 5000 - calls
    assert facts["Its oldest request expires"] != "1762871000" and facts["Account read"] != "not yet"


@pytest.mark.skipif(os.environ.get("LIMINAL_VENDOR_PAGES") != "1", reason="asks DigitalOcean's pages: LIMINAL_VENDOR_PAGES=1")
def test_every_address_on_the_card_answers():
    assert dead_links(module.MACHINE.apis) == []


def test_the_card_is_where_the_billable_calls_are_named():
    source = inspect.getsource(card)
    assert "enable_backups" in source and "destroy_with_associated_resources" in source  # named, as the API's
