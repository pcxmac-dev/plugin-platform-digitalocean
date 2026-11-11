"""Stand-ins for DigitalOcean and DNS: the tests never reach DigitalOcean, a resolver or the network. `FakeDigitalOcean` is
the API as a RestClient transport (an account in memory, its answers in the shapes DigitalOcean's reference shows: one
object under its singular key, a list under its plural key with links.pages and meta.total, an error as {"id",
"message"}, a DELETE answered 204, the rate limit's headers); `Pairs` is a Login holding pairs by name. This network's
address is given to the Keeper directly (its `public`): no name server is asked."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
from urllib.parse import parse_qsl, urlencode, urlsplit

import pytest

import liminal_libs.dns as dns_mod
import liminal_libs.machines.rest as rest_mod
from liminal_libs.apps import Login, Unauthorized, pair_name
from plugin_platform_digitalocean import DigitalOceanPlugin
from plugin_platform_digitalocean.settings import NAMES

TOKEN = "dop_v1_" + "0123456789abcdef" * 4  # a stand-in token (no account's)
HOME = "93.184.216.34"  # this network's public address in the tests
WEB, DB = 3164444, 3164450  # the Droplets' IDs
WEB_FW, DB_FW = "bb4b2611-3d72-467b-8602-280330ecd65c", "fb6045f1-cf1d-4ca3-bfac-18832663025b"
RESET = "1762871000"


def ed25519(seed: bytes = b"\x01" * 32, comment: str = "me@laptop") -> str:
    """A well-formed ssh-ed25519 public key line (its blob: the type's name, then 32 bytes)."""
    blob = len(b"ssh-ed25519").to_bytes(4, "big") + b"ssh-ed25519" + (32).to_bytes(4, "big") + seed
    return f"ssh-ed25519 {base64.b64encode(blob).decode()} {comment}"


def fingerprint(public_key: str) -> str:
    digest = hashlib.md5(base64.b64decode(public_key.split()[1])).hexdigest()
    return ":".join(digest[i:i + 2] for i in range(0, 32, 2))


def droplet(did, name, status, size, monthly, hourly, v4, v6=None, tags=(), memory=1024, vcpus=1, disk=25, locked=False):
    return {"id": did, "name": name, "memory": memory, "vcpus": vcpus, "disk": disk, "locked": locked, "status": status,
            "created_at": "2025-03-01T10:00:00Z", "features": ["ipv6"] if v6 else [], "backup_ids": [], "snapshot_ids": [],
            "image": {"name": "24.04 (LTS) x64", "distribution": "Ubuntu", "slug": "ubuntu-24-04-x64"},
            "size": {"slug": size, "memory": memory, "vcpus": vcpus, "disk": disk, "transfer": 1.0,
                     "price_monthly": monthly, "price_hourly": hourly},
            "size_slug": size,
            "networks": {"v4": [{"ip_address": v4, "netmask": "255.255.240.0", "gateway": "203.0.113.1", "type": "public"},
                                {"ip_address": f"10.110.0.{did % 200}", "netmask": "255.255.240.0", "gateway": "10.110.0.1",
                                 "type": "private"}],
                         "v6": [{"ip_address": v6, "netmask": 64, "gateway": "2001:db8::1", "type": "public"}] if v6 else []},
            "region": {"name": "New York 3", "slug": "nyc3"}, "tags": list(tags), "volume_ids": [],
            "vpc_uuid": "5a4981aa-9653-4bd1-bef5-d6bff52042e4"}


def record(rid, rtype, name, data, ttl=1800, priority=None, port=None, weight=None, flags=None, tag=None):
    return {"id": rid, "type": rtype, "name": name, "data": data, "priority": priority, "port": port, "ttl": ttl,
            "weight": weight, "flags": flags, "tag": tag}


class FakeDigitalOcean:
    """DigitalOcean's API in memory; every request kept (`requests`: method, path, query, json)."""

    def __init__(self, token: str = TOKEN):
        self.token = token
        self.requests: list[dict] = []
        self.account = {"droplet_limit": 25, "floating_ip_limit": 3, "email": "sammy@example.com", "name": "Sammy",
                        "uuid": "b6fr89dbf6d9156cace5f3c78dc9851d957381ef", "email_verified": True, "status": "active",
                        "status_message": " ", "team": {"uuid": "5df3e3004a17e242b7c20ca6c9fc25b701a47ece", "name": "My Team"}}
        self.balance = {"month_to_date_balance": "23.44", "account_balance": "12.23", "month_to_date_usage": "11.21",
                        "generated_at": "2026-11-11T12:00:00Z"}
        self.droplets = [droplet(WEB, "web-1", "active", "s-1vcpu-1gb", 6, 0.00893, "203.0.113.10", "2001:db8::10", ("web",)),
                         droplet(DB, "db-1", "off", "s-2vcpu-4gb", 24, 0.03571, "203.0.113.11", memory=4096, vcpus=2, disk=80)]
        self.gpus: list[dict] = []
        self.gpu_error: tuple[int, dict] | None = None  # the GPU Droplets' list answered with this
        self.domains = [{"name": "example.com", "ttl": 1800, "zone_file": "$ORIGIN example.com.\n"},
                        {"name": "example.net", "ttl": 3600, "zone_file": ""}]
        self.records = {
            "example.com": [record(10, "SOA", "@", "1800"), record(11, "NS", "@", "ns1.digitalocean.com"),
                            record(12, "NS", "@", "ns2.digitalocean.com"), record(13, "NS", "@", "ns3.digitalocean.com"),
                            record(14, "A", "@", "203.0.113.10"), record(15, "A", "www", "203.0.113.10", ttl=3600),
                            record(16, "MX", "@", "mail.example.com", priority=10, ttl=14400),
                            record(17, "TXT", "@", "v=spf1 -all"), record(18, "TXT", "_dmarc", "v=DMARC1; p=none"),
                            record(19, "CNAME", "blog", "www.example.com.")],
            "example.net": [record(30, "SOA", "@", "1800"), record(31, "NS", "@", "ns1.digitalocean.com")],
        }
        self.firewalls = [
            {"id": WEB_FW, "name": "web", "status": "succeeded", "created_at": "2025-03-02T10:00:00Z", "pending_changes": [],
             "droplet_ids": [WEB], "tags": [],
             "inbound_rules": [{"protocol": "tcp", "ports": "22", "sources": {"addresses": ["0.0.0.0/0", "::/0"]}},
                               {"protocol": "tcp", "ports": "443", "sources": {"addresses": ["0.0.0.0/0", "::/0"]}}],
             "outbound_rules": [{"protocol": "tcp", "ports": "0", "destinations": {"addresses": ["0.0.0.0/0", "::/0"]}},
                                {"protocol": "icmp", "ports": "0", "destinations": {"addresses": ["0.0.0.0/0", "::/0"]}}]},
            {"id": DB_FW, "name": "db", "status": "succeeded", "created_at": "2025-03-02T11:00:00Z", "pending_changes": [],
             "droplet_ids": [DB], "tags": ["db"],
             "inbound_rules": [{"protocol": "tcp", "ports": "5432", "action": "allow", "sources": {"tags": ["web"]}},
                               {"protocol": "tcp", "ports": "22", "action": "allow",
                                "sources": {"addresses": ["198.51.100.7"]}}],
             "outbound_rules": []},
        ]
        self.volumes = [{"id": "506f78a4-e098-11e5-ad9f-000f53306ae1", "name": "data", "size_gigabytes": 100,
                         "region": {"slug": "nyc3", "name": "New York 3"}, "droplet_ids": [DB],
                         "description": "the database's disk", "filesystem_type": "ext4", "filesystem_label": "data",
                         "created_at": "2025-03-03T10:00:00Z", "tags": []},
                        {"id": "7724db7c-e098-11e5-b522-000f53304e51", "name": "spare", "size_gigabytes": 10,
                         "region": {"slug": "nyc3", "name": "New York 3"}, "droplet_ids": [], "description": "",
                         "filesystem_type": "", "filesystem_label": "", "created_at": "2025-03-04T10:00:00Z", "tags": []}]
        laptop = ed25519(b"\x02" * 32, "sammy@laptop")
        self.keys = [{"id": 512189, "fingerprint": fingerprint(laptop), "public_key": laptop, "name": "laptop"}]
        self.reserved = [{"ip": "198.51.100.20", "region": {"slug": "nyc3", "name": "New York 3"},
                          "droplet": {"id": WEB, "name": "web-1"}, "locked": False,
                          "project_id": "746c6152-2fa2-11ed-92d3-27aaa54e4988"},
                         {"ip": "198.51.100.21", "region": {"slug": "nyc3", "name": "New York 3"}, "droplet": None,
                          "locked": False, "project_id": "746c6152-2fa2-11ed-92d3-27aaa54e4988"}]
        self.totals = {"kubernetes_clusters": 1, "load_balancers": 0, "databases": 2, "apps": 3, "snapshots": 4,
                       "images": 1, "projects": 2, "vpcs": 1}
        self.forbidden: set[str] = set()  # paths answered 403 (a token without their scope)
        self.fail: dict[tuple[str, str], tuple[int, dict]] = {}  # (method, path) -> (status, body)
        self.down = False  # every request fails to connect
        self.echo_token = False  # a 401's message holds the token (to see it scrubbed)
        self.remaining = 5000
        self.next_id = 1000

    # -- what the tests read -------------------------------------------------------------------------------------------
    def calls(self) -> list[tuple[str, str]]:
        return [(r["method"], r["path"]) for r in self.requests]

    def writes(self) -> list[dict]:
        return [r for r in self.requests if r["method"] != "GET"]

    def rows(self, domain="example.com") -> list[tuple]:
        return [(r["name"], r["type"], r["data"]) for r in self.records[domain]]

    def fw(self, fid=WEB_FW) -> dict:
        return next(f for f in self.firewalls if f["id"] == fid)

    # -- the transport -----------------------------------------------------------------------------------------------------
    def __call__(self, method, url, headers, body, timeout):
        parts = urlsplit(url)
        assert parts.scheme == "https" and parts.netloc == "api.digitalocean.com", f"asked {url}"
        if self.down:
            raise ConnectionError(f"no route to api.digitalocean.com (sent {headers.get('Authorization')})")
        query = dict(parse_qsl(parts.query))
        data = json.loads(body) if body else None
        self.requests.append({"method": method, "path": parts.path, "query": query, "json": data,
                              "auth": headers.get("Authorization"), "type": headers.get("Content-Type")})
        self.remaining -= 1
        if headers.get("Authorization") != f"Bearer {self.token}":
            words = "Unable to authenticate you" + (f" ({headers.get('Authorization')})" if self.echo_token else "")
            return self.answer(401, {"id": "Unauthorized", "message": words})
        path = parts.path
        assert path.startswith("/v2/"), path
        if (method, path) in self.fail:
            return self.answer(*self.fail[(method, path)])
        if path in self.forbidden:
            return self.answer(403, {"id": "forbidden", "message": "You do not have access for the attempted action."})
        return self.route(method, path[3:], query, data)

    def answer(self, status: int, data=None):
        headers = {"Content-Type": "application/json; charset=utf-8", "ratelimit-limit": "5000",
                   "ratelimit-remaining": str(self.remaining), "ratelimit-reset": RESET}
        return status, headers, (b"" if data is None else json.dumps(data).encode())

    def paged(self, path: str, key: str, items: list, query: dict):
        per_page = int(query.get("per_page", 20))
        page = int(query.get("page", 1))
        shown = items[(page - 1) * per_page: page * per_page]
        out = {key: copy.deepcopy(shown), "links": {}, "meta": {"total": len(items)}}
        if page * per_page < len(items):
            more = {k: v for k, v in query.items() if k not in ("page", "per_page")}
            out["links"]["pages"] = {"next": f"https://api.digitalocean.com/v2{path}?"
                                             + urlencode({**more, "page": page + 1, "per_page": per_page}),
                                     "last": f"https://api.digitalocean.com/v2{path}?page={len(items) // per_page + 1}"}
        return self.answer(200, out)

    def not_found(self):
        return self.answer(404, {"id": "not_found", "message": "The resource you were accessing could not be found."})

    def route(self, method: str, p: str, query: dict, data):
        seg = p.strip("/").split("/")
        if (method, p) == ("GET", "/account"):
            return self.answer(200, {"account": self.account})
        if (method, p) == ("GET", "/customers/my/balance"):
            return self.answer(200, self.balance)
        if (method, p) == ("GET", "/droplets"):
            if query.get("type") == "gpus" and self.gpu_error:
                return self.answer(*self.gpu_error)
            return self.paged(p, "droplets", self.gpus if query.get("type") == "gpus" else self.droplets, query)
        if seg[0] == "droplets" and len(seg) == 2 and method == "GET":
            d = next((x for x in self.droplets + self.gpus if str(x["id"]) == seg[1]), None)
            return self.answer(200, {"droplet": d}) if d else self.not_found()
        if seg[0] == "droplets" and len(seg) == 3 and seg[2] == "actions" and method == "POST":
            d = next((x for x in self.droplets if str(x["id"]) == seg[1]), None)
            if d is None:
                return self.not_found()
            self.next_id += 1
            return self.answer(201, {"action": {"id": self.next_id, "status": "in-progress", "type": data["type"],
                                                "started_at": "2026-11-11T12:30:00Z", "completed_at": None,
                                                "resource_id": d["id"], "resource_type": "droplet",
                                                "region": {"slug": "nyc3"}, "region_slug": "nyc3"}})
        if (method, p) == ("GET", "/domains"):
            return self.paged(p, "domains", self.domains, query)
        if seg[0] == "domains" and len(seg) >= 3 and seg[2] == "records":
            domain = seg[1]
            if domain not in self.records:
                return self.not_found()
            held = self.records[domain]
            if len(seg) == 3 and method == "GET":
                found = [r for r in held if (not query.get("type") or r["type"] == query["type"])
                         and (not query.get("name") or (domain if r["name"] == "@" else f"{r['name']}.{domain}") == query["name"])]
                return self.paged(p, "domain_records", found, query)
            if len(seg) == 3 and method == "POST":
                assert data.get("type"), "a record's type is required"
                if data["type"] == "CNAME" and not str(data.get("data")).endswith(".") and data.get("data") != "@":
                    return self.answer(422, {"id": "unprocessable_entity", "message": "Data needs to end with a dot (.)"})
                self.next_id += 1
                made = {**record(self.next_id, data["type"], data.get("name"), data.get("data")),
                        **{k: data[k] for k in ("priority", "port", "ttl", "weight", "flags", "tag") if k in data}}
                held.append(made)
                return self.answer(201, {"domain_record": made})
            r = next((x for x in held if str(x["id"]) == seg[3]), None) if len(seg) == 4 else None
            if r is None:
                return self.not_found()
            if method == "PUT":
                assert data.get("type") == r["type"], "PUT gives the record's type"
                r.update({k: v for k, v in data.items() if k != "id"})
                return self.answer(200, {"domain_record": r})
            if method == "DELETE":
                held.remove(r)
                return self.answer(204)
        if (method, p) == ("GET", "/firewalls"):
            return self.paged(p, "firewalls", self.firewalls, query)
        if seg[0] == "firewalls" and len(seg) == 3 and seg[2] == "rules" and method in ("POST", "DELETE"):
            fw = next((f for f in self.firewalls if f["id"] == seg[1]), None)
            if fw is None:
                return self.not_found()
            assert data and set(data) <= {"inbound_rules", "outbound_rules"}, data
            for k in ("inbound_rules", "outbound_rules"):
                for rule in data.get(k) or []:
                    if method == "POST":
                        fw[k] = [*(fw.get(k) or []), rule]
                    elif rule in (fw.get(k) or []):
                        fw[k] = [x for x in fw[k] if x != rule]
                    else:
                        return self.answer(404, {"id": "not_found", "message": "rule not found"})
            return self.answer(204)
        if (method, p) == ("GET", "/volumes"):
            return self.paged(p, "volumes", self.volumes, query)
        if (method, p) == ("GET", "/account/keys"):
            return self.paged(p, "ssh_keys", self.keys, query)
        if (method, p) == ("POST", "/account/keys"):
            assert set(data) == {"name", "public_key"}, data
            self.next_id += 1
            made = {"id": self.next_id, "fingerprint": fingerprint(data["public_key"]), "public_key": data["public_key"],
                    "name": data["name"]}
            self.keys.append(made)
            return self.answer(201, {"ssh_key": made})
        if seg[0] == "account" and len(seg) == 3 and seg[1] == "keys" and method == "DELETE":
            k = next((x for x in self.keys if str(x["id"]) == seg[2] or x["fingerprint"] == seg[2]), None)
            if k is None:
                return self.not_found()
            self.keys.remove(k)
            return self.answer(204)
        if (method, p) == ("GET", "/reserved_ips"):
            return self.paged(p, "reserved_ips", self.reserved, query)
        counted = {"/kubernetes/clusters": "kubernetes_clusters", "/load_balancers": "load_balancers",
                   "/databases": "databases", "/apps": "apps", "/snapshots": "snapshots", "/images": "images",
                   "/projects": "projects", "/vpcs": "vpcs"}
        if method == "GET" and p in counted:
            key = counted[p]
            items = [{"id": i} for i in range(self.totals[key])]
            if key == "databases":  # the databases' list: no pages, no total
                return self.answer(200, {"databases": items})
            if key == "images":
                assert query.get("private") == "true", "the account's own images"
            return self.paged(p, key, items, query)
        return self.not_found()


class Pairs(Login):
    """A login holding pairs by name (the login app's store, as the Login interface asks it)."""

    NAMESPACE = "test"

    def __init__(self, values: dict[str, str]):
        self.pairs = {pair_name(k): v for k, v in values.items()}
        self.asked: list[str] = []

    def user(self) -> dict:
        return {"name": "tester"}

    def vector(self, name: str) -> str:
        self.asked.append(name)
        if name not in self.pairs:
            raise Unauthorized(f"no {name}", 404)
        return self.pairs[name]

    def names(self) -> set[str]:
        return set(self.pairs)


def settings_of(token: bool = True, ddns: bool = False, **more) -> dict[str, str]:
    out = {}
    if token:
        out["DIGITALOCEAN_TOKEN"] = TOKEN
    if ddns:
        out["DIGITALOCEAN_DDNS_HOSTS"] = "home.example.com"
    out.update(more)
    return out


@pytest.fixture(autouse=True)
def _no_digitalocean_no_network(monkeypatch):
    """No test reaches DigitalOcean, a name server or this machine's settings: the library's HTTPS and DNS refused, every
    DIGITALOCEAN_ variable cleared."""
    def refused(*a, **k):
        raise AssertionError("a test reached for the network")
    monkeypatch.setattr(rest_mod, "_requests_transport", refused)
    monkeypatch.setattr(dns_mod, "query", refused)
    for n in NAMES:
        monkeypatch.delenv(n, raising=False)


@pytest.fixture
def env(monkeypatch):
    """Sets the plugin's variables (the EnvironmentLogin's: what the platform reads today)."""
    def put(values: dict[str, str]):
        for k, v in values.items():
            monkeypatch.setenv(k, v)
    return put


@pytest.fixture
def made():
    """A plugin over the stand-ins: (plugin, fake DigitalOcean); this network's address HOME unless `public` says."""
    def make(fake: FakeDigitalOcean | None = None, public=None):
        fake = fake or FakeDigitalOcean()
        p = DigitalOceanPlugin(transport=fake, public=public or (lambda: (HOME, "OpenDNS")), sleep=lambda s: None)
        return p, fake
    return make
