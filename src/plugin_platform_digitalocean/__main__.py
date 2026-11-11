"""`python -m plugin_platform_digitalocean ...`: the plugin from the command line, its settings read from the environment
(an EnvironmentLogin: the variables as this shell has them).

    status                                   the account read, then the plugin's status (JSON)
    servers                                  the Droplets: state, region, size, addresses, prices
    domains                                  the domains on DigitalOcean's DNS
    records DOMAIN                           a domain's records
    firewalls                                the cloud firewalls and their rules
    keys                                     the account's SSH keys
    ddns [--now]                             a Dynamic DNS pass: a host of its own set where it differs (--now: every
                                             host of its own; one holding another address is left as it is)
    power NAME on|off|reboot|hard-off|cycle  a Droplet (by its name or ID) powered on, shut down, rebooted, powered off
                                             hard or power cycled; asks "yes" first, the hard ones twice
    set DOMAIN NAME TYPE DATA [--ttl N] [--priority N] [--port N] [--weight N] [--flags N] [--tag T]
                                             a record set, every other record kept; asks "yes" first, and again
                                             before what a record holds is replaced
    remove DOMAIN NAME TYPE [DATA]           a record removed, the rest kept; asks "yes" first

--json prints the answer as JSON. The cloud firewalls' rules and the SSH keys are changed from the platform's page."""
from __future__ import annotations

import argparse
import json
import sys

from liminal_libs.machines.rest import RestError

from . import MACHINE, page
from . import firewall as fwmod
from .api import HARD
from .errors import Refusal
from .page import ACCEPT_REPLACE
from .records import said

POWER_WORDS = {"on": "power_on", "off": "shutdown", "reboot": "reboot", "hard-off": "power_off", "cycle": "power_cycle"}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m plugin_platform_digitalocean",
                                description="DigitalOcean for Liminal: the account, its free changes, Dynamic DNS")
    p.add_argument("--json", action="store_true", help="print the answer as JSON")
    sub = p.add_subparsers(dest="what")
    sub.add_parser("status", help="the account read, then the plugin's status")
    sub.add_parser("servers", help="the Droplets")
    sub.add_parser("domains", help="the domains on DigitalOcean's DNS")
    r = sub.add_parser("records", help="a domain's records")
    r.add_argument("domain")
    sub.add_parser("firewalls", help="the cloud firewalls and their rules")
    sub.add_parser("keys", help="the account's SSH keys")
    d = sub.add_parser("ddns", help="a Dynamic DNS pass")
    d.add_argument("--now", action="store_true", help="every host's record set, whether it differs or not")
    w = sub.add_parser("power", help="a Droplet powered on, shut down, rebooted, powered off hard or power cycled")
    w.add_argument("droplet", help="its name or ID")
    w.add_argument("how", choices=list(POWER_WORDS))
    s = sub.add_parser("set", help="a record set, every other record kept")
    for a in ("domain", "name", "type", "data"):
        s.add_argument(a)
    for a in ("ttl", "priority", "port", "weight", "flags"):
        s.add_argument(f"--{a}", type=int)
    s.add_argument("--tag", choices=["issue", "issuewild", "iodef"], help="a CAA record's tag")
    m = sub.add_parser("remove", help="a record removed, the rest kept")
    for a in ("domain", "name", "type"):
        m.add_argument(a)
    m.add_argument("data", nargs="?")
    return p


def droplet_of(plugin, wanted: str) -> dict:
    """A Droplet by its ID or its name, read now (a name several share: refused)."""
    found = plugin.droplets()
    if wanted.isdigit():
        hit = [d for d in found if str(d.get("id")) == wanted]
    else:
        hit = [d for d in found if str(d.get("name") or "").lower() == wanted.lower()]
    if not hit:
        raise Refusal(f"no Droplet {wanted} in this account")
    if len(hit) > 1:
        raise Refusal(f"{len(hit)} Droplets are named {wanted}: give the one's ID ({', '.join(str(d.get('id')) for d in hit)})")
    return hit[0]


def main(argv: list[str] | None = None, plugin=None, out=None, err=None, ask=None) -> int:
    p = plugin if plugin is not None else MACHINE
    say = out or (lambda s: print(s))
    tell = err or (lambda s: print(s, file=sys.stderr))
    question = ask or (lambda prompt: input(prompt))
    args = parser().parse_args(sys.argv[1:] if argv is None else argv)
    what = args.what or "status"

    def confirmed(words: str) -> bool:
        return str(question(f"{words} Type yes to go on: ") or "").strip().lower() == "yes"
    try:
        if what == "status":
            if p.config().api_ready:
                try:
                    p.refresh()
                except RestError:
                    pass  # the status says it
            say(json.dumps(p.status(), indent=1))
            return 0
        if what == "servers":
            answer = p.droplets()
            lines = [f"{d.get('name'):<24} {page.STATES.get(d.get('status'), d.get('status')):<10} "
                     f"{(d.get('region') or {}).get('slug') or '–':<6} {d.get('size_slug') or '–':<18} "
                     f"{(page.addresses(d, 'v4') or ['–'])[0]:<16} {page.money((d.get('size') or {}).get('price_monthly'))}/month "
                     f"{page.money((d.get('size') or {}).get('price_hourly'), 5)}/hour" for d in answer]
            lines = (lines or ["no Droplets in this account"]) + [page.BILLING]
        elif what == "domains":
            answer = p.domains()
            lines = [f"{d.get('name'):<32} ttl {d.get('ttl')}" for d in answer] or ["no domains on DigitalOcean's DNS"]
        elif what == "records":
            answer = p.records(args.domain)
            lines = [f"  {r.get('name') or '@':<24} {r.get('type'):<6} {r.get('data')}  ttl {r.get('ttl')}"
                     + (f"  priority {r.get('priority')}" if r.get("type") in ("MX", "SRV") else "")
                     + (f"  [{r.get('id')}]" if r.get("id") else "") for r in answer] or ["no records"]
        elif what == "firewalls":
            answer = p.firewalls()
            lines = []
            for fw in answer:
                lines.append(f"{fw.get('name')} ({fw.get('status')}): applies to {fwmod.applies_to(fw) or 'no Droplet'}")
                for direction in fwmod.DIRECTIONS:
                    lines += [f"  {fwmod.key_of(direction, r)}" for r in fw.get(fwmod.rules_key(direction)) or []]
            lines = lines or ["no cloud firewalls"]
        elif what == "keys":
            answer = p.ssh_keys()
            lines = [f"{k.get('name'):<24} {k.get('fingerprint')}  [{k.get('id')}]" for k in answer] or ["no SSH keys"]
        elif what == "ddns":
            answer = p.ddns_update(force=args.now)
            lines = [f"{h['host']:<32} {h['address'] or '–':<16} {h['result']} (checked {page.when(h['checkedAt'])})"
                     for h in answer]
        elif what == "power":
            d = droplet_of(p, args.droplet)
            action = POWER_WORDS[args.how]
            title = page.POWER[action][0]
            if not confirmed(f"{title}: {d.get('name')} (ID {d.get('id')})? {page.BILLING}"):
                tell("not asked")
                return 1
            hard = action in HARD
            if hard and not confirmed(f"{title} cuts {d.get('name')}'s power at once: whatever it has not written to disk "
                                      "is lost. Really?"):
                tell("not asked")
                return 1
            answer = p.power(d.get("id"), d.get("name"), action, accept_hard=hard)
            lines = [answer["said"], *(f"  {x}" for x in answer["lines"])]
        elif what == "set":
            if not confirmed(f"{args.name} {args.type.upper()} {args.data} is set in {args.domain}, every other record "
                             "kept."):
                tell("not written")
                return 1
            asked = dict(ttl=args.ttl, priority=args.priority, port=args.port, weight=args.weight, flags=args.flags,
                         tag=args.tag)
            try:
                answer = p.set_record(args.domain, args.name, args.type, args.data, **asked)
            except Refusal as e:
                if e.accept != ACCEPT_REPLACE:
                    raise
                if not confirmed(f"{e} Replace it?"):  # the second yes: what the record holds now is named
                    tell("not written")
                    return 1
                answer = p.set_record(args.domain, args.name, args.type, args.data, **asked, accept_replace=True)
            lines = [f"{answer['domain']}: {answer['said']}", *(f"  {x}" for x in answer["lines"])]
        else:  # remove
            shown = said({"name": args.name, "type": args.type.upper(), "data": args.data or "(its one record)"})
            if not confirmed(f"{shown} is removed from {args.domain}, the rest kept."):
                tell("not removed")
                return 1
            answer = p.remove_record(args.domain, args.name, args.type, args.data)
            lines = [f"{answer['domain']}: {answer['said']}", *(f"  {x}" for x in answer["lines"])]
    except RestError as e:
        tell(f"digitalocean: {e}")
        return 1
    except (ValueError, RuntimeError) as e:  # a refusal (errors.Refusal), a setting not set, a pass under way
        tell(f"refused: {e}")
        return 1
    if args.json:
        say(json.dumps(answer, indent=1))
    else:
        for line in lines:
            say(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
