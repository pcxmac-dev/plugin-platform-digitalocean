"""What the plugin attaches to (plugin API 2.2, liminal_libs.sources.apis): DigitalOcean's public API v2, as its own pages
said it on 2026-11-11 (https://docs.digitalocean.com/reference/api/reference/ and the pages linked below): every part of its
reference, the calls the plugin makes and what for, the API's other notable calls (those that change something, and those
that start or raise a charge), its limits and what of it costs money.

This module is the API's card: it names every call, the billable ones too. Nowhere else in the package does a billable
call's path or action appear (tests/test_contract.py checks the client's source for them)."""
from __future__ import annotations

from liminal_libs.sources.apis import Api, Area, Call, Link

VERIFIED = "2026-11-11"
DOCS = "https://docs.digitalocean.com/reference/api/"
REFERENCE = "https://docs.digitalocean.com/reference/api/reference/"
LIMITS = "https://docs.digitalocean.com/reference/api/reference/public-apis/"
TOKEN_HOWTO = "https://docs.digitalocean.com/reference/api/create-personal-access-token/"
SCOPES_PAGE = "https://docs.digitalocean.com/reference/api/scopes/"
TOKENS = "https://cloud.digitalocean.com/account/api/tokens"  # where a personal access token is made
PRICING = "https://www.digitalocean.com/pricing"
DROPLET_PRICING = "https://docs.digitalocean.com/products/droplets/details/pricing/"
VOLUME_PRICING = "https://docs.digitalocean.com/products/volumes/details/pricing/"
RESERVED_IP_PRICING = "https://docs.digitalocean.com/products/networking/reserved-ips/details/pricing/"
STATUS = "https://status.digitalocean.com/"
NAME = "DigitalOcean API"

# the token's scopes the plugin needs (https://docs.digitalocean.com/reference/api/scopes/): every read it makes, and the
# writes of its free changes alone; a token made with Custom Scopes limited to these is the one to make
READ_SCOPES = ("account:read", "billing:read", "droplet:read", "domain:read", "firewall:read", "block_storage:read",
               "ssh_key:read", "reserved_ip:read", "tag:read", "image:read", "snapshot:read", "kubernetes:read",
               "load_balancer:read", "database:read", "app:read", "project:read", "vpc:read")
WRITE_SCOPES = ("droplet:update", "domain:create", "domain:update", "domain:delete", "firewall:update", "ssh_key:create",
                "ssh_key:delete")
SCOPES = READ_SCOPES + WRITE_SCOPES


def _ref(slug: str) -> str:
    return f"{REFERENCE}{slug}/"


# every part of the reference, in its own order (its index, read 2026-11-11): (name, its page, what it is, what the plugin
# does with it). The Inference APIs first: a service of their own at inference.do-ai.run, with keys of their own.
_AREAS = (
    ("Agent Inference", "agent-inference", "Asking an agent of DigitalOcean's agent platform (one of the Inference APIs, "
     "served apart from this API at inference.do-ai.run with a key of its own)", ""),
    ("Batch Inference", "batch-inference", "Batches of model requests run later, their results fetched (Inference APIs)", ""),
    ("Embeddings", "embeddings", "Text embeddings from a hosted model (Inference APIs)", ""),
    ("Serverless Inference", "serverless-inference", "Chat, messages, images, speech and video from hosted models, "
     "OpenAI-style (Inference APIs)", ""),
    ("1-Click Applications", "1-click-applications", "The Marketplace's 1-Click apps, and installing them on Kubernetes", ""),
    ("Account", "account", "Who the token belongs to: the email, the account's status, its team and its Droplet limit",
     "the account's facts on the page (its email, status, team and Droplet limit)"),
    ("Action Gateway", "action-gateway", "Tools, connections and MCP servers that AI agents reach through DigitalOcean's "
     "gateway", ""),
    ("Action Gateway Data Plane", "action-gateway-data-plane", "Invoking the gateway's tools and code, and their approvals", ""),
    ("Actions", "actions", "Every action taken on the account's resources: what, on what, its status and when", ""),
    ("Add-Ons", "add-ons", "The Marketplace's SaaS add-ons and their plans", ""),
    ("Agent Platform API", "agent-platform-api", "Building GenAI agents: models, knowledge bases, guardrails, evaluations", ""),
    ("Apps", "apps", "App Platform: apps, their deployments, logs, alerts and instance sizes", "counted (Also in the account)"),
    ("Billing", "billing", "The balance, the billing history, invoices and spending insights",
     "the balance on the page: the month's usage and balance so far"),
    ("Block Storage", "block-storage", "Volumes: network disks attached to Droplets, and their snapshots",
     "the Volumes table (read only: none is made, resized or deleted here)"),
    ("Block Storage Actions", "block-storage-actions", "Attaching, detaching and resizing volumes", ""),
    ("BYOIP Prefixes", "byoip-prefixes", "Bringing your own IP address ranges to DigitalOcean", ""),
    ("CDN Endpoints", "cdn-endpoints", "The Spaces CDN: its endpoints and their cache", ""),
    ("Certificates", "certificates", "TLS certificates for load balancers and the CDN, uploaded or Let's Encrypt's", ""),
    ("Container Registries", "container-registries", "The account's container registries: repositories, tags, garbage "
     "collection", ""),
    ("Container Registry", "container-registry", "The single-registry calls of the container registry, kept for older "
     "callers", ""),
    ("Databases", "databases", "Managed databases: clusters, users, pools, replicas, backups, their firewalls",
     "counted (Also in the account)"),
    ("Dedicated Inference", "dedicated-inference", "GPU endpoints dedicated to one model, their accelerators and tokens", ""),
    ("Domain Records", "domain-records", "A domain's DNS records, read, made, changed and deleted one at a time",
     "each domain's records table; Set a record… (made, or changed in place) and Remove, every other record kept; the "
     "Dynamic DNS hosts' A records"),
    ("Domains", "domains", "The domains DigitalOcean's DNS serves",
     "the Domains table; the zones whose hosts Dynamic DNS keeps (none is added or deleted here)"),
    ("Droplet Actions", "droplet-actions", "What can be done to a Droplet: power, reboot, snapshot, resize, rebuild, "
     "backups, a password reset", "Power…: power on, shut down, reboot, power off and power cycle, each confirmed (the "
     "hard two asked twice); nothing else"),
    ("Droplet Autoscale Pools", "droplet-autoscale-pools", "Pools of Droplets that grow and shrink with their load", ""),
    ("Droplets", "droplets", "Virtual machines: made, listed, destroyed; their backups, snapshots, kernels, firewalls, "
     "neighbors", "the Droplets table: state, region, size, addresses, price a month and an hour, made (none is made, "
     "resized or destroyed here)"),
    ("Firewalls", "firewalls", "Cloud firewalls: rules on inbound and outbound traffic, applied to Droplets by ID or tag",
     "the Cloud firewalls table and each one's rules; Add a rule… and Remove, the risky ones asked twice"),
    ("Floating IP Actions", "floating-ip-actions", "Assigning floating IPs (reserved IPs' older name)", ""),
    ("Floating IPs", "floating-ips", "Reserved IPs under their older name, kept for older callers", ""),
    ("Functions", "functions", "Serverless functions: namespaces, triggers and keys", ""),
    ("Harness Runtime", "harness-runtime", "A runtime for AI agents: sessions, templates, triggers and workspaces", ""),
    ("Harness Runtime Workspaces [Public Preview]", "harness-runtime-workspaces-public-preview",
     "The agent runtime's workspaces (in public preview)", ""),
    ("Image Actions", "image-actions", "Converting images, and copying them to other regions", ""),
    ("Images", "images", "Distribution, application and custom images; backups and snapshots as images",
     "the custom images counted (Also in the account)"),
    ("Insights", "insights", "Observability: metrics, logs and traces queried; dashboards, alert rules, notification "
     "channels", ""),
    ("Kubernetes", "kubernetes", "Managed Kubernetes: clusters, node pools, upgrades, kubeconfig",
     "counted (Also in the account)"),
    ("Load Balancers", "load-balancers", "Load balancers, their forwarding rules and Droplets", "counted (Also in the account)"),
    ("MicroVMs [Public Preview]", "microvms-public-preview", "Small virtual machines with checkpoints, exec and a console "
     "(in public preview)", ""),
    ("Monitoring", "monitoring", "Droplet, app and load balancer metrics, alert policies and log sinks", ""),
    ("NFS", "nfs", "Managed NFS shares and their snapshots", ""),
    ("NFS Actions", "nfs-actions", "Actions on an NFS share", ""),
    ("Organizations", "organizations", "An organization's teams", ""),
    ("Partner Network Connect", "partner-network-connect", "Private links to other networks through DigitalOcean's "
     "partners", ""),
    ("Project Resources", "project-resources", "What belongs to a project, and moving resources into one", ""),
    ("Projects", "projects", "Projects grouping the account's resources", "counted (Also in the account)"),
    ("Regions", "regions", "The datacenter regions and what each offers", ""),
    ("Reserved IP Actions", "reserved-ip-actions", "Assigning and unassigning reserved IPs", ""),
    ("Reserved IPs", "reserved-ips", "Public IPv4 addresses kept apart from any one Droplet",
     "the Reserved IPs table (read only: none is reserved, assigned or released here)"),
    ("Reserved IPv6", "reserved-ipv6", "Public IPv6 addresses kept apart from any one Droplet", ""),
    ("Reserved IPv6 Actions", "reserved-ipv6-actions", "Assigning reserved IPv6 addresses", ""),
    ("Security", "security", "Security scans of the account's resources and their findings; secrets", ""),
    ("Signals", "signals", "AI agents' sessions and dialogues, their exports and deletions, and the consent to collect "
     "them", ""),
    ("Sizes", "sizes", "The Droplet plans and their prices an hour and a month", ""),
    ("Snapshots", "snapshots", "Snapshots of Droplets and volumes", "counted (Also in the account)"),
    ("Spaces Keys", "spaces-keys", "Access keys for Spaces object storage", ""),
    ("SSH Keys", "ssh-keys", "The public keys new Droplets can be made with",
     "the SSH keys table; Add a key… and Remove, each confirmed"),
    ("Tags", "tags", "Tags grouping resources, and tagging them", ""),
    ("Uptime", "uptime", "Uptime checks of addresses, their state and alerts", ""),
    ("Vector Databases", "vector-databases", "Managed vector databases, their backups and credentials", ""),
    ("VPC NAT Gateways", "vpc-nat-gateways", "NAT gateways giving a VPC's Droplets a way out", ""),
    ("VPC Peerings", "vpc-peerings", "Private links between VPCs", ""),
    ("VPC Routes [Public Preview]", "vpc-routes-public-preview", "A VPC's routes (in public preview)", ""),
    ("VPC Subnets [Public Preview]", "vpc-subnets-public-preview", "A VPC's subnets (in public preview)", ""),
    ("VPCs", "vpcs", "A region's private networks, their members and peerings", "counted (Also in the account)"),
)
AREA_PAGE = {name: _ref(slug) for name, slug, _, _ in _AREAS}


def _call(name: str, area: str, about: str, used: str = "", writes: bool = False, costs: bool = False) -> Call:
    return Call(name=name, about=about, area=area, used=used, docs=AREA_PAGE[area], writes=writes, costs=costs)


_CALLS = (
    # -- the calls the plugin makes (api.ENDPOINTS: the test compares them) --------------------------------------------
    _call("GET /v2/account", "Account", "The token's account: email, status, team, limits", "the account's facts"),
    _call("GET /v2/customers/my/balance", "Billing", "The balance: the month's usage, the balance before it, the total "
          "so far, when it was worked out", "the balance fact"),
    _call("GET /v2/droplets", "Droplets", "Every Droplet, a page at a time (type=gpus: the GPU Droplets)",
          "the Droplets table (the Droplets, then the GPU Droplets)"),
    _call("GET /v2/droplets/{droplet_id}", "Droplets", "One Droplet as it is now",
          "Power…: the Droplet read again before its action is asked (its name, its state, not locked)"),
    _call("POST /v2/droplets/{droplet_id}/actions", "Droplet Actions", "An action on a Droplet, by its type",
          "Power…: power_on, shutdown, reboot, power_off, power_cycle (no other type is ever sent)", writes=True),
    _call("GET /v2/domains", "Domains", "The domains on DigitalOcean's DNS", "the Domains table; Dynamic DNS's zones"),
    _call("GET /v2/domains/{domain_name}/records", "Domain Records", "A domain's records (type= and name=, the full "
          "name, narrow it)", "each domain's records table; read again before each change; Dynamic DNS's check"),
    _call("POST /v2/domains/{domain_name}/records", "Domain Records", "A record made", "Set a record… (a new one); "
          "Dynamic DNS (a host's first A record)", writes=True),
    _call("PUT /v2/domains/{domain_name}/records/{domain_record_id}", "Domain Records", "A record changed in place",
          "Set a record… (the host's record of its type changed); Dynamic DNS (a host's A record set to this network's "
          "address)", writes=True),
    _call("DELETE /v2/domains/{domain_name}/records/{domain_record_id}", "Domain Records", "A record deleted",
          "Remove (a record's own)", writes=True),
    _call("GET /v2/firewalls", "Firewalls", "The cloud firewalls, their rules, Droplets, tags and pending changes",
          "the Cloud firewalls table and each one's rules; read again before each change"),
    _call("POST /v2/firewalls/{firewall_id}/rules", "Firewalls", "Rules added to a firewall (inbound_rules, "
          "outbound_rules), the others kept", "Add a rule…", writes=True),
    _call("DELETE /v2/firewalls/{firewall_id}/rules", "Firewalls", "Rules removed from a firewall, the others kept",
          "Remove (a rule as it was read)", writes=True),
    _call("GET /v2/volumes", "Block Storage", "The volumes", "the Volumes table"),
    _call("GET /v2/account/keys", "SSH Keys", "The account's SSH keys (10 lists a minute at most)", "the SSH keys table"),
    _call("POST /v2/account/keys", "SSH Keys", "An SSH key added (name, public_key)", "Add a key…", writes=True),
    _call("DELETE /v2/account/keys/{ssh_key_identifier}", "SSH Keys", "An SSH key deleted, by its ID or fingerprint",
          "Remove (by its fingerprint: the key shown is the key deleted)", writes=True),
    _call("GET /v2/reserved_ips", "Reserved IPs", "The reserved IPv4 addresses and the Droplets they are assigned to",
          "the Reserved IPs table"),
    _call("GET /v2/kubernetes/clusters", "Kubernetes", "The Kubernetes clusters", "counted (Also in the account)"),
    _call("GET /v2/load_balancers", "Load Balancers", "The load balancers", "counted (Also in the account)"),
    _call("GET /v2/databases", "Databases", "The database clusters", "counted (Also in the account)"),
    _call("GET /v2/apps", "Apps", "The App Platform apps", "counted (Also in the account)"),
    _call("GET /v2/snapshots", "Snapshots", "The Droplet and volume snapshots", "counted (Also in the account)"),
    _call("GET /v2/images", "Images", "Images (private=true: the account's own)", "the custom images counted"),
    _call("GET /v2/projects", "Projects", "The projects", "counted (Also in the account)"),
    _call("GET /v2/vpcs", "VPCs", "The VPCs", "counted (Also in the account)"),
    # -- the rest worth knowing: never made here ------------------------------------------------------------------------
    _call("POST /v2/droplets", "Droplets", "A Droplet made: billed from then until it is destroyed", writes=True, costs=True),
    _call("DELETE /v2/droplets/{droplet_id}", "Droplets", "A Droplet destroyed (the only way its billing ends)", writes=True),
    _call("DELETE /v2/droplets/{droplet_id}/destroy_with_associated_resources/dangerous", "Droplets",
          "A Droplet destroyed with its volumes, snapshots and reserved IPs", writes=True),
    _call("GET /v2/droplets/{droplet_id}/firewalls", "Droplets", "The firewalls applied to a Droplet"),
    _call("GET /v2/droplets/{droplet_id}/actions/{action_id}", "Droplet Actions", "An action's status: in-progress, "
          "completed, errored"),
    _call("POST /v2/droplets/{droplet_id}/actions (enable_backups)", "Droplet Actions", "Backups turned on: 20% (weekly) "
          "or 30% (daily) of the Droplet's price", writes=True, costs=True),
    _call("POST /v2/droplets/{droplet_id}/actions (change_backup_policy)", "Droplet Actions", "Weekly or daily backups "
          "(daily costs more)", writes=True, costs=True),
    _call("POST /v2/droplets/{droplet_id}/actions (snapshot)", "Droplet Actions", "A snapshot taken: billed by its size "
          "each month", writes=True, costs=True),
    _call("POST /v2/droplets/{droplet_id}/actions (resize)", "Droplet Actions", "A Droplet resized to another plan (a "
          "larger disk cannot be undone)", writes=True, costs=True),
    _call("POST /v2/droplets/{droplet_id}/actions (rebuild)", "Droplet Actions", "A Droplet rebuilt from an image: its "
          "disk replaced", writes=True),
    _call("POST /v2/droplets/{droplet_id}/actions (restore)", "Droplet Actions", "A Droplet restored from one of its "
          "backups", writes=True),
    _call("POST /v2/droplets/{droplet_id}/actions (password_reset)", "Droplet Actions", "The root password reset and "
          "emailed", writes=True),
    _call("POST /v2/droplets/actions", "Droplet Actions", "An action on every Droplet of a tag", writes=True),
    _call("GET /v2/sizes", "Sizes", "Every Droplet plan with its price an hour and a month"),
    _call("GET /v2/regions", "Regions", "The regions and what each offers"),
    _call("POST /v2/domains", "Domains", "A domain added to DigitalOcean's DNS (free)", writes=True),
    _call("DELETE /v2/domains/{domain_name}", "Domains", "A domain deleted with all its records", writes=True),
    _call("PATCH /v2/domains/{domain_name}/records/{domain_record_id}", "Domain Records", "A record changed, only the "
          "attributes given", writes=True),
    _call("POST /v2/firewalls", "Firewalls", "A cloud firewall made (free)", writes=True),
    _call("PUT /v2/firewalls/{firewall_id}", "Firewalls", "A firewall replaced whole: what is not given is reset",
          writes=True),
    _call("DELETE /v2/firewalls/{firewall_id}", "Firewalls", "A firewall deleted", writes=True),
    _call("POST /v2/firewalls/{firewall_id}/droplets", "Firewalls", "Droplets added to a firewall", writes=True),
    _call("POST /v2/firewalls/{firewall_id}/tags", "Firewalls", "Tags added to a firewall", writes=True),
    _call("PUT /v2/account/keys/{ssh_key_identifier}", "SSH Keys", "An SSH key renamed", writes=True),
    _call("POST /v2/volumes", "Block Storage", "A volume made: billed by its size, attached or not", writes=True, costs=True),
    _call("POST /v2/volumes/{volume_id}/actions", "Block Storage Actions", "A volume attached, detached or resized (a "
          "larger one costs more)", writes=True, costs=True),
    _call("POST /v2/volumes/{volume_id}/snapshots", "Block Storage", "A volume's snapshot taken: billed by its size",
          writes=True, costs=True),
    _call("POST /v2/reserved_ips", "Reserved IPs", "An IPv4 address reserved: billed while it is not assigned",
          writes=True, costs=True),
    _call("POST /v2/reserved_ips/{reserved_ip}/actions", "Reserved IP Actions", "A reserved IP assigned or unassigned",
          writes=True),
    _call("GET /v2/customers/my/invoices", "Billing", "The invoices, and the month's preview"),
    _call("GET /v2/customers/my/billing_history", "Billing", "Charges, payments and credits"),
    _call("POST /v2/kubernetes/clusters", "Kubernetes", "A Kubernetes cluster made: its nodes are Droplets, billed",
          writes=True, costs=True),
    _call("POST /v2/load_balancers", "Load Balancers", "A load balancer made: billed monthly", writes=True, costs=True),
    _call("POST /v2/databases", "Databases", "A database cluster made: billed by its plan", writes=True, costs=True),
    _call("POST /v2/apps", "Apps", "An app made: billed by its components' plans", writes=True, costs=True),
    _call("GET /v2/monitoring/metrics/droplet/cpu", "Monitoring", "A Droplet's CPU use over time"),
    _call("GET /v2/actions", "Actions", "Every action taken on the account's resources"),
)

API = Api(
    name=NAME,
    maker="DigitalOcean",
    about=("DigitalOcean's public API is the control plane of a DigitalOcean account: what its control panel shows and does, "
           "from Droplets, volumes and networks to DNS, cloud firewalls, managed databases, Kubernetes and App Platform, as "
           "JSON over HTTPS. A personal access token, holding only the scopes it was made with, proves who asks. This plugin "
           "reads the account and makes only the changes that cost nothing, each one confirmed on the page first."),
    kind="rest",
    base="https://api.digitalocean.com/v2",
    version="v2 (its OpenAPI specification's 2.0)",
    auth=("a personal access token (Applications & API > Tokens > Generate New Token) sent as Authorization: Bearer; its "
          "scopes are fixed when it is made: Full Access (api:write), Read Only (api:read) or Custom Scopes "
          "(resource:action, such as droplet:read or domain:update), and a call outside them answers 403"),
    limits=("5,000 requests an hour and 250 a minute per token (headers ratelimit-limit, ratelimit-remaining, "
            "ratelimit-reset; past them a 429 too_many_requests, with retry-after on a burst); listing SSH keys 10 "
            "requests per 60 s; CDN endpoints 5 per 10 s; lists 20 a page unless per_page says, at most 200"),
    costs=("asking costs nothing; what the API makes or keeps bills: a Droplet until it is destroyed, powered off too "
           "(bundled-plan CPU and GPU Droplets alike), volumes $0.10 per GiB a month attached or not, snapshots $0.06 "
           "per GiB a month, backups 20% (weekly) or 30% (daily) of the Droplet's price, a reserved IPv4 address $5.00 a "
           "month while not assigned, outbound transfer past the pooled allowance $0.01 per GiB, and load balancers, "
           "Kubernetes, databases and apps by their plans (DigitalOcean's pricing pages, read 2026-11-11). This plugin "
           "starts none of it"),
    links=(
        Link("API overview", DOCS, "docs"),
        Link("API reference", REFERENCE, "reference"),
        Link("Rate limits, pagination and errors", LIMITS, "limits"),
        Link("Making a personal access token", TOKEN_HOWTO, "auth"),
        Link("The token's scopes", SCOPES_PAGE, "auth"),
        Link("Pricing", PRICING, "pricing"),
        Link("Droplet pricing (billed while powered off)", DROPLET_PRICING, "pricing"),
        Link("Volume pricing", VOLUME_PRICING, "pricing"),
        Link("Reserved IP pricing", RESERVED_IP_PRICING, "pricing"),
        Link("DigitalOcean's status", STATUS, "status"),
        Link("Release notes", "https://docs.digitalocean.com/release-notes/", "changelog"),
        Link("Cloud firewall deny rules (August 2026)", "https://docs.digitalocean.com/notes/2026/firewalls-deny-rules/",
             "changelog"),
        Link("OpenAPI specification", "https://github.com/digitalocean/openapi", "spec"),
        Link("Tokens in the control panel", TOKENS, "console"),
        Link("doctl, the command line", "https://docs.digitalocean.com/reference/doctl/", "tool"),
        Link("PyDo, the Python client", "https://docs.digitalocean.com/reference/pydo/", "sdk"),
        Link("Managing DNS records", "https://docs.digitalocean.com/products/networking/dns/how-to/manage-records/", "guide"),
        Link("Cloud firewalls", "https://docs.digitalocean.com/products/networking/firewalls/", "guide"),
        Link("SSH keys on a team", "https://docs.digitalocean.com/platform/teams/how-to/upload-ssh-keys/", "guide"),
    ),
    areas=tuple(Area(name, about, _ref(slug), covered) for name, slug, about, covered in _AREAS),
    calls=_CALLS,
    verified=VERIFIED,
)
APIS = (API,)
