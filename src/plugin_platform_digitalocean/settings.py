"""The plugin's settings, read through the library's Login interface and nothing else (as every platform plugin's: the
user, 2026-11-08: "again, all the settings are stored on a login-app db"). Each setting is a pair named by its variable
(DIGITALOCEAN_TOKEN is the pair `digitalocean-token`: apps.authorization.pair_name), asked of the login of the app the
plugin is attached to: the platform's EnvironmentLogin today, the login app's pairs once the platform binds it. Not attached
(the command line), an EnvironmentLogin of its own. No settings file: a value is never written anywhere, never shown, and
only the names of the settings set are said."""
from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from liminal_libs.apps import EnvironmentLogin, Login
from liminal_libs.machines.ddns import MINUTES, Host, hosts_of, minutes_of
from liminal_libs.sources.keys import KeyVar

from .card import SCOPES, TOKENS

TOKEN = "DIGITALOCEAN_TOKEN"
DDNS_HOSTS = "DIGITALOCEAN_DDNS_HOSTS"
DDNS_MINUTES = "DIGITALOCEAN_DDNS_MINUTES"

KEYS = (
    KeyVar(TOKEN, label="Personal access token",
           hint=(f"{TOKENS}: Generate New Token, Custom Scopes limited to {', '.join(SCOPES)} (the reads, and the writes "
                 "of the free changes alone)")),
    KeyVar(DDNS_HOSTS, label="Dynamic DNS hosts", secret=False,
           hint=("optional: hosts kept at this network's public IPv4 address, comma separated, each in one of the account's "
                 "domains: home.example.com, @.example.com (the domain itself)")),
    KeyVar(DDNS_MINUTES, label="Dynamic DNS minutes", secret=False,
           hint="optional: minutes between Dynamic DNS checks, 1 to 1440 (5 unless set)"),
)
NAMES = tuple(k.name for k in KEYS)
TOKEN_FORM = re.compile(r"^[A-Za-z0-9_\-.]{20,}$")  # a token's characters (dop_v1_ and 64 hex digits today)


@dataclass(frozen=True)
class Config:
    """The settings as read (`present`: the names of those set; `problems`: what was set but could not be taken, in words
    that never hold the token)."""

    token: str = field(default="", repr=False)
    hosts: tuple[str, ...] = ()  # the Dynamic DNS hosts as typed (split against the account's domains once they are known)
    minutes: float = MINUTES[2]
    present: frozenset = frozenset()
    problems: tuple[str, ...] = ()

    @property
    def api_ready(self) -> bool:
        return bool(self.token)

    @property
    def ddns_ready(self) -> bool:
        """Dynamic DNS goes through DigitalOcean's DNS: the token and the hosts."""
        return bool(self.token and self.hosts)

    @property
    def incomplete(self) -> tuple[str, ...]:
        """What a part set halfway lacks, in words."""
        return (f"{DDNS_HOSTS} is set but {TOKEN} is not: Dynamic DNS goes through DigitalOcean's DNS, with the token",) \
            if self.hosts and not self.token else ()

    def ddns_hosts(self, zones: Iterable[str]) -> tuple[list[Host], list[str]]:
        """The Dynamic DNS hosts in the account's domains (`zones`), and in words the ones in none of them."""
        return hosts_of(",".join(self.hosts), zones)

    @property
    def secrets(self) -> tuple[str, ...]:
        """The values scrubbed from every message the plugin gives."""
        return (self.token,) if self.token else ()

    def print_of(self, *names: str) -> str:
        """A fingerprint of these settings' values (kept in memory to notice a change; never shown nor written)."""
        values = {TOKEN: self.token, DDNS_HOSTS: repr(self.hosts), DDNS_MINUTES: str(self.minutes)}
        return hashlib.sha256("\0".join(f"{n}={values[n]}" for n in names).encode("utf-8")).hexdigest()

    @property
    def api_print(self) -> str:
        return self.print_of(TOKEN)

    @property
    def ddns_print(self) -> str:
        return self.print_of(TOKEN, DDNS_HOSTS)


def parse(values: Mapping[str, str]) -> Config:
    """The settings from their values by variable (those not set left out or empty)."""
    v = {n: str(values.get(n) or "").strip() for n in NAMES}
    present = frozenset(n for n in NAMES if v[n])
    problems: list[str] = []
    token = v[TOKEN]
    if token and not TOKEN_FORM.match(token):
        problems.append(f"{TOKEN} does not look like a personal access token (letters, digits, _ and -, dop_v1_…): it is "
                        "sent as it is")
    minutes = minutes_of(v[DDNS_MINUTES])
    if v[DDNS_MINUTES]:
        try:
            float(v[DDNS_MINUTES])
        except ValueError:
            problems.append(f"{DDNS_MINUTES} is not a number of minutes: {MINUTES[2]:g} is used")
    hosts = tuple(h.strip() for h in re.split(r"[,;\s]+", v[DDNS_HOSTS]) if h.strip())
    return Config(token=token, hosts=hosts, minutes=minutes, present=present, problems=tuple(problems))


def read(login: Login | None = None) -> Config:
    """The settings as `login` furnishes them (the login of the app the plugin is attached to), else an EnvironmentLogin's:
    the variables set, by their pairs' names; a login that cannot be asked furnishes none, and says so."""
    asked = login if login is not None else EnvironmentLogin()
    try:
        values = asked.variables(NAMES)
    except Exception as e:  # noqa: BLE001 - a login that cannot be asked: nothing set, and why
        return Config(problems=(f"the settings could not be read from the login: {type(e).__name__}",))
    return parse(values)
