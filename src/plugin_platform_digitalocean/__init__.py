"""DigitalOcean for Liminal (the user, 2026-11-11: "ALSO i would like to add two new plugins, Digital Ocean and LINODE"; on
what they change: "Free changes only"): the account through DigitalOcean's API v2, everything it holds shown (the account
and its balance, the Droplets with their prices, the domains and their records, the cloud firewalls and their rules, the
volumes, the SSH keys, the reserved IPs, and how many of the other kinds it holds) and only what costs nothing changed,
each change confirmed on the page first: a Droplet powered on, shut down or rebooted (a hard power-off or power cycle asked
twice: unsaved data is lost), a DNS record set or removed (every other record kept), a cloud firewall's rule added or
removed (a risky one asked twice), an SSH key added or removed; and Dynamic DNS, keeping hosts at this network's public
IPv4 address through DigitalOcean's DNS. Nothing that starts a charge: no Droplet, volume, snapshot, backup or reserved
IP is made, nothing is resized or destroyed. A powered-off Droplet still bills, and the page says so.

Its settings are pairs asked of the login of the app it is attached to (settings.py: DIGITALOCEAN_TOKEN,
DIGITALOCEAN_DDNS_HOSTS, DIGITALOCEAN_DDNS_MINUTES), never a file of its own. While attached to the platform app it reads
the account every quarter of an hour and keeps the Dynamic DNS hosts every few minutes in a thread of its own; detached,
nothing of it runs. Its status is what was read last (no request is made to answer it): the platform's page draws its
tables, its actions (Refresh, Update DNS now) and its forms. What it attaches to is its API card (card.py: plugin API 2.2).

    python -m plugin_platform_digitalocean status | servers | domains | records DOMAIN | ddns [--now] | firewalls | keys
        | power NAME on|off|reboot|hard-off|cycle | set DOMAIN NAME TYPE DATA [--ttl N] ... | remove DOMAIN NAME TYPE [DATA]
"""
from __future__ import annotations

import base64
import binascii
import re
import threading
import time

from liminal_libs.machines.ddns import Keeper
from liminal_libs.machines.plugin import MachinePlugin
from liminal_libs.machines.rest import RestError

from . import ddns as ddns_mod
from . import firewall as fwmod
from . import page
from . import records as recmod
from . import settings as settings_mod
from .api import COUNTS, HARD, POWER, DigitalOceanApi
from .card import APIS, NAME as API_NAME, READ_SCOPES, TOKENS, WRITE_SCOPES
from .errors import Refusal
from .page import ACCEPT_HARD, ACCEPT_RISKY, BILLING, plural, when
from .settings import DDNS_HOSTS, KEYS, NAMES, TOKEN, Config

__version__ = "0.1.0"
REFRESH_S = 900.0  # the account read again at most this often while attached (or by Refresh)
CONFIG_S = 30.0  # the settings asked of the login again after this long
RETRY_S = 900.0  # a read that failed is taken as untried after this long while detached: attached again, it is tried again
ZONES_MAX = 12  # the domains whose records a refresh reads (the rest: `records DOMAIN`)
SOON_S = 30.0  # the Droplets read again this long after a power action, while attached
SCOPES_WORDS = (f"Custom Scopes limited to the reads ({', '.join(READ_SCOPES)}) and the free changes' writes "
                f"({', '.join(WRITE_SCOPES)})")
NOT_SET = f"not set up: {TOKEN}, a personal access token made at {TOKENS} (Generate New Token; {SCOPES_WORDS})"
PARTS = {  # a part of a refresh: its words, the scope a token needs to read it
    "account": ("the account", "account:read"), "balance": ("the balance", "billing:read"),
    "droplets": ("the Droplets", "droplet:read"), "gpus": ("the GPU Droplets", "droplet:read"),
    "domains": ("the domains", "domain:read"),
    "records": ("the records", "domain:read"), "firewalls": ("the cloud firewalls", "firewall:read"),
    "volumes": ("the volumes", "block_storage:read"), "keys": ("the SSH keys", "ssh_key:read"),
    "reserved": ("the reserved IPs", "reserved_ip:read"),
}
LABELS = {"ratelimit-limit": "Rate limit (an hour)", "ratelimit-remaining": "Requests left this hour",
          "ratelimit-reset": "Its oldest request expires"}
KEY_TYPES = ("ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521",
             "sk-ssh-ed25519@openssh.com", "sk-ecdsa-sha2-nistp256@openssh.com")
FINGERPRINT = re.compile(r"^(?:[0-9a-f]{2}:){15}[0-9a-f]{2}$|^\d+$")  # an SSH key's (MD5, as DigitalOcean gives it) or its ID
DOMAIN = re.compile(r"^(?=.{3,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$")


def shorten(text, most: int = 200) -> str:
    t = " ".join(str(text).split())
    return t if len(t) <= most else t[: most - 1] + "…"


def with_gpus(droplets: list[dict], gpus: list[dict] | None) -> list[dict]:
    """The Droplets, then the GPU Droplets not among them."""
    seen = {d.get("id") for d in droplets}
    return droplets + [g for g in (gpus or []) if g.get("id") not in seen]


def public_key_of(value) -> str:
    """A public key as typed (one line: its type, its base64 key, a comment), checked; ValueError when it is none (a
    private key is refused without a word of it said back)."""
    text = str(value or "")
    if "PRIVATE KEY" in text.upper():
        raise Refusal("that is a private key: only a public key (the .pub file's one line) is added, and the private key "
                      "is never typed here")
    k = " ".join(text.split())
    parts = k.split(" ", 2)
    if len(parts) < 2 or parts[0] not in KEY_TYPES:
        raise ValueError(f"not a public key: one line as ssh-keygen writes it ({', '.join(KEY_TYPES[:2])} …)")
    try:
        blob = base64.b64decode(parts[1], validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("not a public key: its key is not base64") from None
    size = int.from_bytes(blob[:4], "big") if len(blob) >= 4 else -1
    if size != len(parts[0]) or blob[4:4 + size].decode("ascii", "replace") != parts[0]:
        raise ValueError(f"not a public key: its key is not one of {parts[0]}")
    return k


class _Runtime:
    """What the plugin read and holds, shared by its copies (the registry's with_ makes them)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.config: tuple[float, Config] | None = None
        self.api: tuple[str, DigitalOceanApi] | None = None
        self.clear()
        self.api_ok: bool | None = None  # the last refresh's outcome (None: none yet)
        self.api_error = ""
        self.api_error_at: float | None = None
        self.api_print = ""  # the settings that outcome is of
        self.ddns_print = ""
        self.ddns_at: float | None = None
        self.keeper: Keeper | None = None
        self.worker: threading.Thread | None = None
        self.stop: threading.Event | None = None
        self.wake = threading.Event()
        self.refreshing = threading.Lock()
        self.soon: float | None = None  # when the Droplets are read again (a power action asked: monotonic time)

    def clear(self) -> None:
        """What was read, forgotten (another token)."""
        self.account: dict | None = None
        self.balance: dict | None = None
        self.droplets: list[dict] | None = None
        self.domains: list[dict] | None = None
        self.records: dict[str, list | str] = {}
        self.firewalls: list[dict] | None = None
        self.volumes: list[dict] | None = None
        self.keys: list[dict] | None = None
        self.reserved: list[dict] | None = None
        self.counts: dict[str, str] = {}
        self.troubles: dict[str, str] = {}
        self.refreshed_at: float | None = None


class DigitalOceanPlugin(MachinePlugin):
    """DigitalOcean: the account through its API, its free changes confirmed, Dynamic DNS; reading in the background while
    attached."""

    name = "digitalocean"
    title = "DigitalOcean"
    about = ("Your DigitalOcean account through its API: Droplets with their prices, domains and records, cloud firewalls, "
             "volumes, SSH keys and reserved IPs; only free changes, each confirmed; Dynamic DNS through its DNS")
    api = "2.2"
    order = 760
    ICON = "digitalocean"  # DigitalOcean's mark (liminal-libs 1.49.0's icons.js)
    HOOKS = (*MachinePlugin.HOOKS, "refresh", "droplets", "domains", "records", "firewalls", "ssh_keys", "balance", "power",
             "set_record", "remove_record", "add_firewall_rule", "remove_firewall_rule", "add_ssh_key", "remove_ssh_key",
             "ddns_update")
    keys = KEYS
    signup = TOKENS
    limits = ("DigitalOcean's API: 5,000 requests an hour and 250 a minute per token; a refresh asks about 20 to 30 every "
              "quarter of an hour, a Dynamic DNS check one a host")
    apis = APIS

    def __init__(self, transport=None, public=None, clock=None, sleep=None):
        self._transport = transport  # (method, url, headers, body, timeout) -> (status, headers, body): a test's; else HTTPS
        self._public = public  # () -> (address, whose): a test's; else DNS asked (PUBLIC_IPV4)
        self._clock = clock or time.time
        self._sleep = sleep or time.sleep
        self._rt = _Runtime()

    # -- the settings, the API, the keeper --------------------------------------------------------------------------------
    def config(self, fresh: bool = False) -> Config:
        """The settings, asked of the login (the attached app's, else the environment's); kept CONFIG_S."""
        now = time.monotonic()
        with self._rt.lock:
            kept = self._rt.config
        if kept is not None and not fresh and now - kept[0] < CONFIG_S:
            return kept[1]
        cfg = settings_mod.read(self.login)
        with self._rt.lock:
            self._rt.config = (now, cfg)
        return cfg

    def settings_changed(self) -> None:
        """Its settings were just entered (the platform's Settings…, kept through the login): read anew at once."""
        with self._rt.lock:
            self._rt.config = None

    def client(self) -> DigitalOceanApi:
        """The API with the token as it is set (ValueError when it is not)."""
        cfg = self.config()
        if not cfg.api_ready:
            raise ValueError("DigitalOcean's API is not set up: " + NOT_SET)
        with self._rt.lock:
            held = self._rt.api
        if held is not None and held[0] == cfg.api_print:
            return held[1]
        made = DigitalOceanApi(cfg.token, transport=self._transport, clock=self._clock, sleep=self._sleep)
        with self._rt.lock:
            if self._rt.api is not None and self._rt.api[0] != cfg.api_print:
                self._rt.clear()  # another token: what the last one read is not this one's
            self._rt.api = (cfg.api_print, made)
        return made

    def keeper(self) -> Keeper:
        with self._rt.lock:
            if self._rt.keeper is None:
                self._rt.keeper = Keeper(read=lambda h: ddns_mod.read(self.client(), h), write=self._ddns_write,
                                         servers=ddns_mod.PUBLIC_IPV4, public=self._public, clock=self._clock)
            return self._rt.keeper

    def _ddns_write(self, host, ip: str) -> str:
        done = ddns_mod.write(self.client(), host, ip)
        self._reread_records(host.zone)
        return done

    def zones(self) -> list[str] | None:
        """The account's domains by name, as last read (None: not read yet)."""
        with self._rt.lock:
            domains = self._rt.domains
        return None if domains is None else [str(d.get("name") or "").lower() for d in domains if d.get("name")]

    # -- the hooks: reading -----------------------------------------------------------------------------------------------
    def present(self) -> bool:
        """Whether anything of it is set."""
        return bool(self.config().present)

    def refresh(self) -> dict:
        """The account read again now (the page's Refresh): what the status shows until the next."""
        cfg = self.config(fresh=True)
        if not cfg.api_ready:
            raise ValueError("DigitalOcean's API is not set up: " + NOT_SET)
        if not self._rt.refreshing.acquire(timeout=120):
            raise RuntimeError("a refresh is under way")
        try:
            return self._refresh(cfg)
        finally:
            self._rt.refreshing.release()

    def _trouble(self, part: str, e: RestError) -> str:
        words, scope = PARTS.get(part, (part, ""))
        if e.status == 403 and scope:
            return f"{words}: not readable with this token (it needs {scope})"
        return f"{words}: {e}"

    def _refresh(self, cfg: Config) -> dict:
        now = self._clock()
        troubles: dict[str, str] = {}
        try:
            api = self.client()
            try:
                account = api.account()
            except RestError as e:
                if e.status != 403:
                    raise
                account, troubles["account"] = None, self._trouble("account", e)

            def part(name, read):  # a part that cannot be read is said, the rest read all the same
                try:
                    return read()
                except RestError as e:
                    troubles[name] = self._trouble(name, e)
                    return None
            balance = part("balance", api.balance)
            droplets = part("droplets", api.droplets)
            if droplets is not None:  # the GPU Droplets, listed apart: a trouble with them hides none of the others
                droplets = with_gpus(droplets, part("gpus", lambda: api.droplets(gpus=True)))
            domains = part("domains", api.domains)
            records: dict[str, list | str] = {}
            for d in (domains or [])[:ZONES_MAX]:
                zone = str(d.get("name") or "").lower()
                try:
                    records[zone] = api.records(zone)
                except RestError as e:
                    records[zone] = self._trouble("records", e)
            for d in (domains or [])[ZONES_MAX:]:
                zone = str(d.get("name") or "").lower()
                records[zone] = f"not read with the rest (more than {ZONES_MAX} domains): records {zone}"
            firewalls = part("firewalls", api.firewalls)
            volumes = part("volumes", api.volumes)
            keys = part("keys", api.ssh_keys)
            reserved = part("reserved", api.reserved_ips)
            counts: dict[str, str] = {}
            unread: list[str] = []
            for what, path, key, params, scope in COUNTS:
                try:
                    counts[what] = api.count(path, key, params)
                except RestError as e:
                    counts[what] = f"needs {scope}" if e.status == 403 else "not read"
                    unread.append(scope if e.status == 403 else f"{what.lower()}: {e}")
            if unread:
                troubles["counts"] = "not counted: " + ", ".join(unread)
            read = [x for x in (account, balance, droplets, domains, firewalls, volumes, keys, reserved) if x is not None]
            if not read:
                raise RestError("nothing could be read: " + "; ".join(troubles.values()), 403)
        except (RestError, ValueError) as e:
            with self._rt.lock:
                self._rt.api_ok, self._rt.api_error, self._rt.api_error_at = False, str(e), now
                self._rt.api_print = cfg.api_print
            raise
        with self._rt.lock:
            rt = self._rt
            rt.account, rt.balance, rt.droplets, rt.domains = account, balance, droplets, domains
            rt.records, rt.firewalls, rt.volumes, rt.keys, rt.reserved = records, firewalls, volumes, keys, reserved
            rt.counts, rt.troubles, rt.refreshed_at = counts, troubles, now
            rt.api_ok, rt.api_error, rt.api_error_at, rt.api_print = True, "", None, cfg.api_print
        return {"droplets": len(droplets or []), "domains": len(domains or []), "firewalls": len(firewalls or []),
                "refreshedAt": when(now)}

    def droplets(self) -> list[dict]:
        """The Droplets and the GPU Droplets, read now."""
        api = self.client()
        found = api.droplets()
        try:
            found = with_gpus(found, api.droplets(gpus=True))
        except RestError:
            pass  # the Droplets all the same; a refresh says the GPU Droplets' trouble
        with self._rt.lock:
            self._rt.droplets = found
        return found

    def domains(self) -> list[dict]:
        """The domains on DigitalOcean's DNS, read now."""
        found = self.client().domains()
        with self._rt.lock:
            self._rt.domains = found
        return found

    def records(self, domain: str) -> list[dict]:
        """A domain's records, read now."""
        d = self._domain(domain)
        return self._reread_records(d, raise_=True)

    def firewalls(self) -> list[dict]:
        """The cloud firewalls, read now."""
        found = self.client().firewalls()
        with self._rt.lock:
            self._rt.firewalls = found
        return found

    def ssh_keys(self) -> list[dict]:
        """The SSH keys, read now."""
        found = self.client().ssh_keys()
        with self._rt.lock:
            self._rt.keys = found
        return found

    def balance(self) -> dict:
        """The balance, read now."""
        found = self.client().balance()
        with self._rt.lock:
            self._rt.balance = found
        return found

    def _reread_records(self, domain: str, raise_: bool = False):
        try:
            found = self.client().records(domain)
        except RestError:
            if raise_:
                raise
            return None
        with self._rt.lock:
            self._rt.records[domain.lower()] = found
        return found

    def _reread_droplets(self) -> None:
        try:
            self.droplets()
        except (RestError, ValueError):
            pass

    def _domain(self, domain: str) -> str:
        """One of the account's domains (as last read; read now when none was), lowercase; Refusal when it is not one."""
        d = str(domain or "").strip().lower().rstrip(".")
        if not DOMAIN.match(d):
            raise ValueError(f"{str(domain).strip()!r} is not a domain name")
        zones = self.zones()
        if zones is None or d not in zones:
            zones = [str(x.get("name") or "").lower() for x in self.domains()]
        if d not in zones:
            raise Refusal(f"{d} is not one of the account's domains on DigitalOcean's DNS")
        return d

    # -- the hooks: the free changes ------------------------------------------------------------------------------------
    def power(self, droplet_id, name=None, action: str = "shutdown", accept_hard: bool = False) -> dict:
        """A Droplet powered on, shut down, rebooted, powered off or power cycled (POWER, nothing else), the Droplet read
        again first (its name, its state, not locked); a hard one (power_off, power_cycle) refused unless accepted
        (`accept_hard`: the page's second confirmation)."""
        act = str(action or "").strip().lower()
        if act not in POWER:
            raise ValueError(f"{action!r} is none of this plugin's Droplet actions: {', '.join(POWER)}")
        try:
            did = int(str(droplet_id).strip())
        except ValueError:
            raise ValueError(f"{droplet_id!r} is not a Droplet's ID") from None
        api = self.client()
        d = api.droplet(did)
        real = str(d.get("name") or did)
        if name not in (None, "") and str(name) != real:
            raise Refusal(f"Droplet {did} is named {real} now, not {name}: nothing asked (the page is read again)")
        if d.get("locked"):
            raise Refusal(f"{real} is locked: an action is under way on it; ask again once it is done")
        state = str(d.get("status") or "")
        allowed = page.ACTIONS_BY_STATE.get(state, ())
        title = page.POWER[act][0]
        if act not in allowed:
            can = ", ".join(page.POWER[a][0].lower() for a in allowed) or "nothing"
            raise Refusal(f"{real} is {page.STATES.get(state, state or 'in no known state')}: it can be {can} here, not "
                          f"{title.lower()}")
        if act in HARD and not accept_hard:
            raise Refusal(f"{title} cuts {real}'s power at once: unsaved data is lost (whatever it has not written to "
                          "disk). DigitalOcean advises a shutdown first and a power-off only when that does not work; it "
                          "is asked only once that is accepted (accept_hard)", accept=ACCEPT_HARD)
        got = api.power(did, act)
        with self._rt.lock:
            for x in self._rt.droplets or []:
                if x.get("id") == did:
                    x["locked"] = True
            self._rt.soon = time.monotonic() + SOON_S
        self._rt.wake.set()
        lines = [f"DigitalOcean's action {got.get('id')}: {got.get('status') or 'asked'}"
                 + (f", started {got.get('started_at')}" if got.get("started_at") else ""),
                 "the Droplets are read again in half a minute (or by Refresh)"]
        if act in ("shutdown", "power_off"):
            lines.append(BILLING)
        return {"said": f"{title.lower()} asked for {real}", "lines": lines, "ok": got.get("status") != "errored",
                "action": got}

    def set_record(self, domain: str, name: str, rtype: str, data: str, ttl=None, priority=None, port=None, weight=None,
                   flags=None, tag=None) -> dict:
        """A record set in `domain` (records.plan_set over the records at its name read now): made, or changed in place;
        every other record is kept, since none is sent."""
        d = self._domain(domain)
        n = recmod.relative_name(name, d)
        api = self.client()
        at_name = api.records(d, None, recmod.full_name(n, d))
        default = next((int(x.get("ttl")) for x in (self._held("domains") or []) if str(x.get("name")).lower() == d
                        and isinstance(x.get("ttl"), int)), recmod.TTL_DEFAULT)
        change = recmod.plan_set(d, at_name, n, rtype, data, ttl=ttl, priority=priority, port=port, weight=weight,
                                 flags=flags, tag=tag, default_ttl=default)
        if change.op == "none":
            return {"domain": d, "said": change.said, "lines": [], "ok": True, "changed": False}
        got = api.create_record(d, change.body) if change.op == "create" else api.update_record(d, change.record_id, change.body)
        self._reread_records(d)
        return {"domain": d, "said": change.said, "ok": True, "changed": True, "record": got,
                "lines": [f"record {got.get('id') or change.record_id}: {recmod.said(got or change.body)}",
                          f"every other record of {d} is kept as it was (none was sent)"]}

    def remove_record(self, domain: str, name: str, rtype: str, data=None, record_id=None) -> dict:
        """A record removed from `domain` (records.pick_removal over the records at its name read now: the one named by
        its data, or its ID with its data), the rest kept."""
        d = self._domain(domain)
        n = recmod.relative_name(name, d)
        t = str(rtype or "").strip().upper()
        if t not in recmod.TYPES and t != "SOA":
            raise ValueError(f"{rtype!r} is no record type here: {', '.join(recmod.TYPES)}")
        api = self.client()
        at_name = api.records(d, t, recmod.full_name(n, d))
        r = recmod.pick_removal(d, at_name, n, t, data, record_id)
        api.delete_record(d, r["id"])
        self._reread_records(d)
        return {"domain": d, "said": f"removed {recmod.said(r)}", "ok": True, "changed": True,
                "lines": [f"record {r['id']} deleted; every other record of {d} is kept as it was"]}

    def _firewall(self, api: DigitalOceanApi, firewall_id, name=None) -> dict:
        """A firewall read now (the list: its rules as they are), by its ID; Refusal when it is gone or renamed."""
        found = api.firewalls()
        with self._rt.lock:
            self._rt.firewalls = found
        fid = str(firewall_id or "").strip()
        fw = next((f for f in found if str(f.get("id")) == fid), None)
        if fw is None:
            raise Refusal(f"no cloud firewall {fid} in the account any more")
        if name not in (None, "") and str(name) != str(fw.get("name")):
            raise Refusal(f"firewall {fid} is named {fw.get('name')} now, not {name}: nothing sent (the page is read again)")
        return dict(fw)

    def _known_droplets(self) -> list[dict]:
        held = self._held("droplets")
        return held if held is not None else self.droplets()

    def add_firewall_rule(self, firewall_id, firewall=None, direction: str = "inbound", protocol: str = "tcp", ports=None,
                          action: str = "allow", addresses=None, droplets=None, tags=None, accept_risky: bool = False) -> dict:
        """A rule added to a cloud firewall (POST its rules: the others, its Droplets and tags kept); a risky one
        (firewall.risk_of_add: SSH or every port open to the whole internet, a deny over SSH) refused unless accepted."""
        api = self.client()
        fw = self._firewall(api, firewall_id, firewall)
        known = self._known_droplets() if droplets and not all(x.isdigit() for x in fwmod.split_list(droplets)) else []
        rule = fwmod.rule_from(direction, protocol, ports, action, addresses, droplets, tags, known)
        d = str(direction).strip().lower()
        key = fwmod.key_of(d, rule)
        if any(fwmod.key_of(d, r) == key for r in fw.get(fwmod.rules_key(d)) or []):
            return {"said": f"{fw.get('name')} holds this rule already: nothing sent", "lines": [key], "ok": True,
                    "changed": False}
        risk = fwmod.risk_of_add(d, rule, fw)
        if risk and not accept_risky:
            raise Refusal(f"{key}: {risk}. It is added only once that is accepted (accept_risky)", accept=ACCEPT_RISKY)
        api.add_rules(fw["id"], [rule] if d == "inbound" else [], [rule] if d == "outbound" else [])
        self._reread_firewalls()
        return {"said": f"added to {fw.get('name')}: {key}", "ok": True, "changed": True, "rule": rule,
                "lines": [*([f"accepted: {risk}"] if risk else []),
                          f"{fw.get('name')}'s other rules, Droplets and tags are kept as they were (none was sent)"]}

    def remove_firewall_rule(self, firewall_id, firewall=None, direction: str = "inbound", rule: str = "",
                             accept_risky: bool = False) -> dict:
        """A rule removed from a cloud firewall (DELETE its rules, the rule sent as it was read just now: the others kept);
        the one letting SSH in to the firewall's Droplets refused unless accepted (firewall.risk_of_remove)."""
        d = str(direction or "").strip().lower()
        if d not in fwmod.DIRECTIONS:
            raise ValueError(f"the direction is {' or '.join(fwmod.DIRECTIONS)}")
        api = self.client()
        fw = self._firewall(api, firewall_id, firewall)
        r = fwmod.find(fw, d, str(rule or "").strip())
        risk = fwmod.risk_of_remove(d, r, fw)
        if risk and not accept_risky:
            raise Refusal(f"{rule}: {risk}. It is removed only once that is accepted (accept_risky)", accept=ACCEPT_RISKY)
        api.remove_rules(fw["id"], [r] if d == "inbound" else [], [r] if d == "outbound" else [])
        self._reread_firewalls()
        return {"said": f"removed from {fw.get('name')}: {fwmod.key_of(d, r)}", "ok": True, "changed": True,
                "lines": [*([f"accepted: {risk}"] if risk else []),
                          f"{fw.get('name')}'s other rules, Droplets and tags are kept as they were (none was sent)"]}

    def _reread_firewalls(self) -> None:
        try:
            self.firewalls()
        except (RestError, ValueError):
            pass

    def add_ssh_key(self, name: str, public_key: str) -> dict:
        """A public key added to the account's SSH keys (new Droplets can be made with it; none is changed)."""
        n = str(name or "").strip()
        if not n or len(n) > 255 or any(ord(c) < 32 for c in n):
            raise ValueError("a key's name is one line of at most 255 characters")
        k = public_key_of(public_key)
        got = self.client().add_key(n, k)
        self._reread_keys()
        return {"said": f"added the SSH key {got.get('name') or n}", "ok": True, "changed": True, "key": got,
                "lines": [f"its fingerprint: {got.get('fingerprint')}", "new Droplets can be made with it; no Droplet made "
                          "so far is changed"]}

    def remove_ssh_key(self, fingerprint: str, name=None) -> dict:
        """An SSH key deleted from the account by its fingerprint (the key shown is the key deleted): the Droplets made with
        it keep it."""
        fp = str(fingerprint or "").strip().lower()
        if not FINGERPRINT.match(fp):
            raise ValueError(f"{fingerprint!r} is not an SSH key's fingerprint (aa:bb:… sixteen pairs) nor its ID")
        self.client().delete_key(fp)
        self._reread_keys()
        return {"said": f"removed the SSH key {name or fp}", "ok": True, "changed": True,
                "lines": [f"{fp} deleted from the account", "the Droplets made with it keep it (their authorized_keys); "
                          "new Droplets can no longer be given it"]}

    def _reread_keys(self) -> None:
        try:
            self.ssh_keys()
        except (RestError, ValueError):
            pass

    def ddns_update(self, force: bool = True) -> list[dict]:
        """A Dynamic DNS pass now (the page's Update DNS now: `force`, every host's record set whether it differs or not;
        the command line's `ddns` without --now sets only where it differs)."""
        cfg = self.config(fresh=True)
        if not cfg.ddns_ready:
            raise ValueError(f"Dynamic DNS is not set up: {TOKEN} and {DDNS_HOSTS}")
        zones = self.zones()
        if zones is None:
            zones = [str(x.get("name") or "").lower() for x in self.domains()]
        hosts, wrong = cfg.ddns_hosts(zones)
        if not hosts:
            raise ValueError("no Dynamic DNS host is in the account's domains: " + ("; ".join(wrong) or "none is set"))
        out = self.keeper().run_pass(hosts, force=bool(force))
        with self._rt.lock:
            self._rt.ddns_print, self._rt.ddns_at = cfg.ddns_print, self._clock()
        return out

    # -- attached: the reading in the background ----------------------------------------------------------------------------
    def attach(self, app, login=None) -> dict:
        """Attached by the platform: its settings asked of the platform's login from now on; the account read and the
        Dynamic DNS hosts kept in the background."""
        interface = super().attach(app, login)
        with self._rt.lock:
            self._rt.config = None
        self._start()
        return interface

    def detach(self) -> None:
        """Detached (the platform ending, the plugin disabled or not valid): the background reading ends."""
        self._stop()
        super().detach()
        with self._rt.lock:
            self._rt.config = None

    @property
    def working(self) -> bool:
        with self._rt.lock:
            t = self._rt.worker
        return t is not None and t.is_alive()

    def _start(self) -> None:
        with self._rt.lock:
            if self._rt.worker is not None and self._rt.worker.is_alive():
                return
            stop = threading.Event()
            t = threading.Thread(target=self._work, args=(stop,), name="digitalocean", daemon=True)
            self._rt.worker, self._rt.stop = t, stop
            self._rt.wake.clear()
        t.start()

    def _stop(self) -> None:
        with self._rt.lock:
            t, stop = self._rt.worker, self._rt.stop
            self._rt.worker = self._rt.stop = None
        if stop is not None:
            stop.set()
            self._rt.wake.set()
        if t is not None and t is not threading.current_thread():
            t.join(timeout=10)

    def _work(self, stop: threading.Event) -> None:
        """The background: the account read every REFRESH_S, the Droplets again soon after a power action, the Dynamic DNS
        hosts checked every DIGITALOCEAN_DDNS_MINUTES once the account's domains are known; nothing for what is not set."""
        next_api = next_ddns = 0.0
        while not stop.is_set():
            now = time.monotonic()
            cfg = None
            try:
                cfg = self.config()
                if cfg.api_ready and now >= next_api:
                    next_api = now + REFRESH_S
                    if self._rt.refreshing.acquire(blocking=False):  # Refresh asked meanwhile: that one is enough
                        try:
                            self._refresh(cfg)
                        except Exception:  # noqa: BLE001 - kept as its outcome (api_error), shown by the status
                            pass
                        finally:
                            self._rt.refreshing.release()
                with self._rt.lock:
                    soon = self._rt.soon
                if cfg.api_ready and soon is not None and time.monotonic() >= soon:
                    with self._rt.lock:
                        self._rt.soon = None
                    self._reread_droplets()
                zones = self.zones()
                if cfg.ddns_ready and zones is not None and now >= next_ddns:
                    next_ddns = now + cfg.minutes * 60.0
                    hosts, _ = cfg.ddns_hosts(zones)
                    if hosts:
                        try:
                            self.keeper().run_pass(hosts, force=False, wait=0.5)
                            with self._rt.lock:
                                self._rt.ddns_print, self._rt.ddns_at = cfg.ddns_print, self._clock()
                        except Exception:  # noqa: BLE001 - a pass under way (Update DNS now), or its trouble kept by the hosts
                            pass
            except Exception:  # noqa: BLE001 - the background never ends on a trouble; the status says it
                pass
            with self._rt.lock:
                soon = self._rt.soon
            due = [t for t, on in ((next_api, cfg is not None and cfg.api_ready),
                                   (next_ddns, cfg is not None and cfg.ddns_ready and self.zones() is not None),
                                   (soon or 0.0, soon is not None)) if on]
            wait = min([60.0, *(t - time.monotonic() for t in due)])
            self._rt.wake.wait(max(1.0, wait))
            self._rt.wake.clear()

    # -- what the platform's page shows ------------------------------------------------------------------------------------
    def _held(self, what: str):
        with self._rt.lock:
            return getattr(self._rt, what)

    def api_facts(self) -> dict:
        """What the API's answers said (plugin API 2.2): the requests made, the last answer, the rate limit left, when the
        account was read; asking nothing."""
        with self._rt.lock:
            held, refreshed = self._rt.api, self._rt.refreshed_at
        facts = held[1].rest.facts(LABELS) if held is not None else {"Requests": "none yet"}
        reset = facts.get(LABELS["ratelimit-reset"])
        if reset:
            try:
                facts[LABELS["ratelimit-reset"]] = time.strftime("%b %d %H:%M:%S", time.localtime(float(reset)))
            except (TypeError, ValueError, OverflowError, OSError):
                pass
        facts["Account read"] = when(refreshed) if refreshed else "not yet"
        facts["Read"] = "every quarter of an hour while attached, and by Refresh"
        return {API_NAME: facts}

    def status(self) -> dict:
        """What was read last, asking nothing of DigitalOcean: the settings set (by name), the summary, valid (the token
        set and the last read worked or is untried) and why not, the facts, the tables, the actions and the forms."""
        cfg = self.config()
        if not cfg.present:
            return {"present": False, "valid": False, "why": NOT_SET, "summary": "not set up",
                    "settingsNotSet": ", ".join(NAMES), "tables": [], "actions": [], "forms": []}
        rt, now, attached = self._rt, self._clock(), self.app is not None
        with rt.lock:
            account, balance, droplets, domains = rt.account, rt.balance, rt.droplets, rt.domains
            records, firewalls, volumes, keys, reserved = dict(rt.records), rt.firewalls, rt.volumes, rt.keys, rt.reserved
            counts, troubles, refreshed_at = dict(rt.counts), dict(rt.troubles), rt.refreshed_at
            api_ok, api_error, api_error_at, api_print = rt.api_ok, rt.api_error, rt.api_error_at, rt.api_print
            keeper, held = rt.keeper, rt.api
        out: dict = {"present": True}
        settings_set = ", ".join(n for n in NAMES if n in cfg.present)
        missing = [n for n in NAMES if n not in cfg.present]
        if not cfg.api_ready:
            return {"present": True, "valid": False, "why": "; ".join(cfg.incomplete) + f" ({NOT_SET})",
                    "summary": "set up halfway", "settingsSet": settings_set, "settingsNotSet": ", ".join(missing),
                    "tables": [], "actions": [], "forms": []}
        works = api_ok if api_print == cfg.api_print else None
        if works is False and not attached and api_error_at is not None and now - api_error_at >= RETRY_S:
            works = None  # tried again once the platform attaches it
        if held is None or held[0] != cfg.api_print:  # nothing read yet with this token (another's is not its to show)
            account = balance = droplets = domains = firewalls = volumes = keys = reserved = refreshed_at = None
            records, counts, troubles = {}, {}, {}
        zones = None if domains is None else [str(d.get("name") or "").lower() for d in domains]
        hosts, wrong = cfg.ddns_hosts(zones) if cfg.ddns_ready and zones is not None else ([], [])
        states = {s.fqdn: s for s in (keeper.states() if keeper is not None else [])}
        failed = [f"Dynamic DNS: {s.fqdn}: {s.result}" for h in hosts for s in [states.get(h.fqdn)] if s and s.ok is False]
        notes = [*cfg.problems, *(f"Dynamic DNS: {w}" for w in wrong), *troubles.values(), *failed]
        valid = works is not False
        out["valid"] = valid
        out["summary"] = self._summary(works, api_error, attached, droplets, domains, balance, hosts, states, cfg)
        if not valid:
            out["why"] = f"the API: {api_error}" + ("" if TOKENS in api_error else f" (a token is made at {TOKENS})")
        elif notes:
            out["problem"] = "; ".join(notes)
        if account:
            out["account"] = str(account.get("email") or account.get("uuid") or "–") + \
                (f" · team {(account.get('team') or {}).get('name')}" if (account.get("team") or {}).get("name") else "")
            status = str(account.get("status") or "")
            out["accountStatus"] = status + (f": {account.get('status_message')}" if status != "active" and
                                             account.get("status_message") else "")
            if account.get("droplet_limit") is not None:
                out["dropletLimit"] = f"{account.get('droplet_limit'):,}" if isinstance(account.get("droplet_limit"), int) \
                    else str(account.get("droplet_limit"))
        if balance:
            out["balance"] = (f"{page.money(balance.get('month_to_date_usage'))} used this month · month-to-date balance "
                              f"{page.money(balance.get('month_to_date_balance'))} · before this month "
                              f"{page.money(balance.get('account_balance'))}")
            if balance.get("generated_at"):
                out["balance"] += f" (as of {str(balance['generated_at'])[:16].replace('T', ' ')} UTC)"
        if droplets:
            out["dropletsAMonth"] = f"≈ {page.money(page.monthly_total(droplets))} at their sizes' prices"
        out["poweredOffDroplets"] = "still billed: DigitalOcean bills a Droplet until it is destroyed"
        if refreshed_at:
            out["readAt"] = when(refreshed_at)
        out["settingsSet"] = settings_set
        if missing:
            out["settingsNotSet"] = ", ".join(missing)
        out["tokenScopes"] = SCOPES_WORDS
        if held is not None:
            limits = held[1].rest.seen.limits
            left, most = limits.get("ratelimit-remaining"), limits.get("ratelimit-limit")
            if left and most:
                num = (lambda v: f"{int(v):,}" if str(v).isdigit() else str(v))
                out["rateLimit"] = f"{num(left)} of {num(most)} requests left this hour"
        if cfg.ddns_ready:
            out["ddnsEvery"] = f"every {cfg.minutes:g} min" + ("" if attached else ", once attached")
        writable = works is True
        out["tables"] = self._tables(cfg, writable, attached, droplets, domains, records, firewalls, volumes, keys,
                                     reserved, counts, hosts, refreshed_at, zones)
        out["forms"] = self._forms(writable, droplets, domains, records, firewalls, keys)
        out["actions"] = [{"hook": "refresh", "args": [], "title": "Refresh",
                           "note": "the account read again now (about 20 to 30 requests)"}] + \
                         ([{"hook": "ddns_update", "args": [], "title": "Update DNS now",
                            "note": "every Dynamic DNS host's A record set now to this network's address"}]
                          if cfg.ddns_ready else [])
        return out

    def _summary(self, works, error, attached, droplets, domains, balance, hosts, states, cfg) -> str:
        bits = []
        if works is True:
            ds = droplets or []
            on = sum(1 for d in ds if d.get("status") == "active")
            off = sum(1 for d in ds if d.get("status") == "off")
            head = plural(len(ds), "Droplet") + (f" ({on} on, {off} off)" if ds else "")
            bits.append(head)
            if domains is not None:
                bits.append(plural(len(domains), "domain"))
            if balance:
                bits.append(f"{page.money(balance.get('month_to_date_usage'))} used this month")
        elif works is None:
            bits.append("reading the account…" if attached else "the account is read once attached")
        else:
            bits.append(f"the API: {shorten(error or 'failed', 100)}")
        if cfg.ddns_ready and works is not False:
            mine = [states[h.fqdn] for h in hosts if h.fqdn in states]
            if len(hosts) == 1 and mine and mine[0].ok:
                bits.append(f"{mine[0].fqdn} at {mine[0].address}")
            elif any(s.ok is not None for s in mine):
                bits.append(f"Dynamic DNS: {sum(1 for s in mine if s.ok)} of {plural(len(hosts), 'host')} current")
            elif hosts:
                bits.append("Dynamic DNS: the first check is under way" if attached else "Dynamic DNS: checked once attached")
        return " · ".join(bits)

    def _tables(self, cfg, writable, attached, droplets, domains, records, firewalls, volumes, keys, reserved, counts,
                hosts, read_at, zones) -> list[dict]:
        out = []
        names = page.droplet_names(droplets or [])
        if cfg.ddns_ready:
            table = self.keeper().table(hosts, cfg.minutes, attached)
            if zones is None:
                table["empty"] = "The hosts are checked once the account's domains are read."
            elif not hosts:
                table["empty"] = f"None of the hosts in {DDNS_HOSTS} is in the account's domains."
            out.append(table)
        if droplets is not None:
            out.append(page.droplets_table(droplets, read_at, writable))
        if domains is not None:
            out.append(page.domains_table(domains, records))
            for d in domains:
                zone = str(d.get("name") or "").lower()
                if zone in records:
                    out.append(page.records_table(zone, records[zone], writable and isinstance(records[zone], list), read_at))
        if firewalls is not None:
            out.append(page.firewalls_table(firewalls, names))
            out += [page.rules_table(fw, names, writable) for fw in firewalls]
        if volumes is not None:
            out.append(page.volumes_table(volumes, names))
        if keys is not None:
            out.append(page.keys_table(keys, writable))
        if reserved is not None:
            out.append(page.reserved_table(reserved))
        if counts:
            out.append(page.counts_table(counts))
        return out

    def _forms(self, writable, droplets, domains, records, firewalls, keys) -> list[dict]:
        if not writable:
            return []
        out = [f for d in (droplets or []) for f in [page.power_form(d)] if f]
        for d in domains or []:
            zone = str(d.get("name") or "").lower()
            if isinstance(records.get(zone), list):
                out += page.record_forms(zone, d.get("ttl") if isinstance(d.get("ttl"), int) else None)
        for fw in firewalls or []:
            out += page.firewall_forms(fw)
        if keys is not None:
            out += page.key_forms()
        return out


MACHINE = DigitalOceanPlugin()
