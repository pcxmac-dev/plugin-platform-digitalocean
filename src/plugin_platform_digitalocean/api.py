"""DigitalOcean's API v2 as its reference gives it (https://docs.digitalocean.com/reference/api/reference/, read
2026-11-11): https://api.digitalocean.com/v2, a personal access token as a Bearer token, JSON in and out; one object under
its singular key (droplet, domain_record, ssh_key, action), a list under its plural key with `links.pages.next` while more
pages follow and `meta.total`; an error as {"id", "message", "request_id"}; a DELETE answered 204 with no body. Its limits:
5,000 requests an hour and 250 a minute per token (ratelimit-limit, ratelimit-remaining, ratelimit-reset), a 429 waited
out by the library's RestClient.

Only what the plugin uses is here (ENDPOINTS, named the way the API card names them): the reads, and the free changes. No
call that makes, resizes, restores or destroys something billable, nor one that turns backups on, is in this module: a
Droplet's action is one of POWER and nothing else."""
from __future__ import annotations

import time
from collections.abc import Mapping
from urllib.parse import quote, urlsplit

from liminal_libs.machines.rest import Answer, RestClient, RestError, bearer

from .card import TOKENS

BASE = "https://api.digitalocean.com/v2"
HOST = "api.digitalocean.com"  # a list's next page is followed only on this host: the token goes nowhere else
PER_PAGE = 200  # the most a page holds
MOST_PAGES = 25
# what the plugin asks, by what for: (method, path under /v2); the API card names each "METHOD /v2PATH"
ENDPOINTS = {
    "account": ("GET", "/account"),
    "balance": ("GET", "/customers/my/balance"),
    "droplets": ("GET", "/droplets"),
    "droplet": ("GET", "/droplets/{droplet_id}"),
    "droplet_action": ("POST", "/droplets/{droplet_id}/actions"),
    "domains": ("GET", "/domains"),
    "records": ("GET", "/domains/{domain_name}/records"),
    "record_create": ("POST", "/domains/{domain_name}/records"),
    "record_update": ("PUT", "/domains/{domain_name}/records/{domain_record_id}"),
    "record_delete": ("DELETE", "/domains/{domain_name}/records/{domain_record_id}"),
    "firewalls": ("GET", "/firewalls"),
    "rules_add": ("POST", "/firewalls/{firewall_id}/rules"),
    "rules_remove": ("DELETE", "/firewalls/{firewall_id}/rules"),
    "volumes": ("GET", "/volumes"),
    "keys": ("GET", "/account/keys"),
    "key_add": ("POST", "/account/keys"),
    "key_delete": ("DELETE", "/account/keys/{ssh_key_identifier}"),
    "reserved_ips": ("GET", "/reserved_ips"),
}
# the other kinds the account holds, each counted by one cheap list call: (what, path, its list's key, params, its scope)
COUNTS = (
    ("Kubernetes clusters", "/kubernetes/clusters", "kubernetes_clusters", {}, "kubernetes:read"),
    ("Load balancers", "/load_balancers", "load_balancers", {}, "load_balancer:read"),
    ("Databases", "/databases", "databases", {}, "database:read"),
    ("Apps", "/apps", "apps", {}, "app:read"),
    ("Snapshots", "/snapshots", "snapshots", {}, "snapshot:read"),
    ("Custom images", "/images", "images", {"private": "true"}, "image:read"),
    ("Projects", "/projects", "projects", {}, "project:read"),
    ("VPCs", "/vpcs", "vpcs", {}, "vpc:read"),
)
for _what, _path, _key, _params, _scope in COUNTS:
    ENDPOINTS[f"count:{_key}"] = ("GET", _path)
POWER = ("power_on", "shutdown", "reboot", "power_off", "power_cycle")  # the only Droplet actions this plugin sends
HARD = frozenset({"power_off", "power_cycle"})  # cut the power at once: unsaved data lost


def path_of(what: str, **ids) -> str:
    """The path of an endpoint (ENDPOINTS) with its ids put in, each quoted as one path segment."""
    method, template = ENDPOINTS[what]
    return template.format(**{k: quote(str(v), safe=":") for k, v in ids.items()})


def words_of(answer: Answer) -> tuple[str, str]:
    """DigitalOcean's error in words ({"id", "message"}), with what to do about the usual ones."""
    data = answer.data if isinstance(answer.data, Mapping) else {}
    said = str(data.get("message") or "").strip()
    code = str(data.get("id") or "")
    hint = ""
    if answer.status == 401:
        hint = f"the token is wrong, expired or revoked: make one at {TOKENS}"
    elif answer.status == 403:
        hint = "the token's scopes do not allow this (a token's scopes are fixed when it is made: make one with them)"
    elif answer.status == 429:
        hint = "DigitalOcean's rate limit: 5,000 requests an hour and 250 a minute per token"
    elif answer.status == 422 and "lock" in said.lower():
        hint = "an action is under way on it: try again once it is done"
    words = "; ".join(w for w in (said, hint) if w)
    return words, code


class DigitalOceanApi:
    """The account through DigitalOcean's API: the reads the page draws and the free changes it asks."""

    def __init__(self, token: str, transport=None, clock=time.time, sleep=time.sleep, wait_most: float = 30.0):
        if not token:
            raise ValueError("DigitalOcean's API needs DIGITALOCEAN_TOKEN")
        self.rest = RestClient(BASE, auth=bearer(token), secrets=(token,), error=words_of, transport=transport,
                               clock=clock, sleep=sleep, wait_most=wait_most)

    def __repr__(self) -> str:
        return "<DigitalOceanApi>"

    # -- reading ----------------------------------------------------------------------------------------------------------
    def _next(self, data, params):
        """A list's next page: its `links.pages.next`, followed only on DigitalOcean's API host over HTTPS."""
        links = (data.get("links") or {}) if isinstance(data, Mapping) else {}
        nxt = (links.get("pages") or {}).get("next") if isinstance(links, Mapping) else None
        if not nxt:
            return None
        parts = urlsplit(str(nxt))
        if parts.scheme != "https" or parts.netloc.lower() != HOST:
            raise RestError(f"a next page at {parts.scheme}://{parts.netloc} is not DigitalOcean's API: not followed")
        return str(nxt), {}

    def every(self, what: str, key: str, params: Mapping | None = None, **ids) -> list[dict]:
        """Every item of a list (its pages followed, PER_PAGE each)."""
        query = {"per_page": PER_PAGE, **(params or {})}
        return [x for x in self.rest.pages(path_of(what, **ids), query, items=key, next_of=self._next, most=MOST_PAGES)
                if isinstance(x, Mapping)]

    def account(self) -> dict:
        return dict((self.rest.get(path_of("account")) or {}).get("account") or {})

    def balance(self) -> dict:
        return dict(self.rest.get(path_of("balance")) or {})

    def droplets(self, gpus: bool = False) -> list[dict]:
        """Every Droplet (`gpus`: every GPU Droplet, which the list gives apart: type=gpus)."""
        return self.every("droplets", "droplets", {"type": "gpus"} if gpus else None)

    def droplet(self, droplet_id) -> dict:
        return dict((self.rest.get(path_of("droplet", droplet_id=droplet_id)) or {}).get("droplet") or {})

    def domains(self) -> list[dict]:
        return self.every("domains", "domains")

    def records(self, domain: str, rtype: str | None = None, name: str | None = None) -> list[dict]:
        """A domain's records; `rtype` and `name` (the record's full name: home.example.com) narrow them."""
        return self.every("records", "domain_records", {"type": rtype, "name": name}, domain_name=domain)

    def firewalls(self) -> list[dict]:
        return self.every("firewalls", "firewalls")

    def volumes(self) -> list[dict]:
        return self.every("volumes", "volumes")

    def ssh_keys(self) -> list[dict]:
        return self.every("keys", "ssh_keys")

    def reserved_ips(self) -> list[dict]:
        return self.every("reserved_ips", "reserved_ips")

    def count(self, path: str, key: str, params: Mapping | None = None) -> str:
        """How many of a kind the account holds, in one request of one item (meta.total), as words: "3", "1+"."""
        data = self.rest.get(path, {"per_page": 1, **(params or {})}) or {}
        total = (data.get("meta") or {}).get("total") if isinstance(data, Mapping) else None
        if isinstance(total, int):
            return f"{total:,}"
        items = data.get(key) if isinstance(data, Mapping) else None
        n = len(items) if isinstance(items, list) else 0
        more = bool(((data.get("links") or {}).get("pages") or {}).get("next")) if isinstance(data, Mapping) else False
        return f"{n:,}+" if more else f"{n:,}"

    # -- the free changes ----------------------------------------------------------------------------------------------
    def power(self, droplet_id, action: str) -> dict:
        """A Droplet's power action (one of POWER, nothing else): DigitalOcean's action as it answered (in-progress)."""
        if action not in POWER:
            raise ValueError(f"{action!r} is not one of this plugin's Droplet actions: {', '.join(POWER)}")
        data = self.rest.post(path_of("droplet_action", droplet_id=droplet_id), {"type": action}) or {}
        return dict(data.get("action") or {})

    def create_record(self, domain: str, body: Mapping) -> dict:
        data = self.rest.post(path_of("record_create", domain_name=domain), dict(body)) or {}
        return dict(data.get("domain_record") or {})

    def update_record(self, domain: str, record_id, body: Mapping) -> dict:
        data = self.rest.put(path_of("record_update", domain_name=domain, domain_record_id=record_id), dict(body)) or {}
        return dict(data.get("domain_record") or {})

    def delete_record(self, domain: str, record_id) -> None:
        self.rest.delete(path_of("record_delete", domain_name=domain, domain_record_id=record_id))

    def add_rules(self, firewall_id: str, inbound: list[dict] = (), outbound: list[dict] = ()) -> None:
        self.rest.post(path_of("rules_add", firewall_id=firewall_id), _rules_body(inbound, outbound))

    def remove_rules(self, firewall_id: str, inbound: list[dict] = (), outbound: list[dict] = ()) -> None:
        self.rest.delete(path_of("rules_remove", firewall_id=firewall_id), json=_rules_body(inbound, outbound))

    def add_key(self, name: str, public_key: str) -> dict:
        data = self.rest.post(path_of("key_add"), {"name": name, "public_key": public_key}) or {}
        return dict(data.get("ssh_key") or {})

    def delete_key(self, identifier: str) -> None:
        """An SSH key deleted by its ID or its fingerprint."""
        self.rest.delete(path_of("key_delete", ssh_key_identifier=identifier))


def _rules_body(inbound, outbound) -> dict:
    out = {}
    if inbound:
        out["inbound_rules"] = [dict(r) for r in inbound]
    if outbound:
        out["outbound_rules"] = [dict(r) for r in outbound]
    if not out:
        raise ValueError("no rule given")
    return out
