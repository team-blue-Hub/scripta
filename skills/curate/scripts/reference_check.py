#!/usr/bin/env python3
"""Reference check - turn a handbook checkout into a classified reference-
reachability report, with a non-zero exit on failures.

A reference that cannot be read must never be skipped silently. This script makes silence impossible - every citation is either
verified reachable, reported as a classified failure, marked
skipped-by-design (allowlisted, with a reason), or handed off as a
needs-agent-result row for a connector-only host this script cannot reach
over plain HTTP.

Classes:
  no-access   - a grant or allowlist entry is what's missing, not a fix to
                the citation. An authenticated GitHub 404 always lands here
                (never `gone`) unless compound evidence says otherwise.
  gone        - fix the citation. Only reached via compound GitHub evidence,
                and only for a target that lives inside a repo (a content
                path or an issue/PR number): that inner target 404s AND the
                repo itself answers 200 to the same credentials. A 404 on a
                repo or a user/org profile itself never upgrades - a private
                repo and a deleted one look identical from outside.
  transient   - retry, don't triage. Timeout / rate-limit / 5xx, retried
                once; a doubly-failed probe reports transient but does not
                by itself force a non-zero exit.
  unknown     - ambiguous evidence, said out loud: unsafe/unresolvable
                targets, unsupported schemes, cross-host redirects, and
                mixed GitHub compound evidence all land here.
  skipped-by-design - allowlisted, with its declared reason. Never silent,
                never an error, never affects the exit code.

Rules: a failure exits loudly non-zero (transient is the one carve-out); every
failure carries page:line, target, class, and identity; `gone` requires compound
evidence; the allowlist is never silent; SSO-gated hosts are never HTTP-probed.

Usage:
  python3 reference_check.py --path /path/to/handbook [--json] [--strict]
  python3 reference_check.py --path /path/to/handbook --inventory
  python3 reference_check.py --path /path/to/handbook --verify results.json

Storage-agnostic and stdlib-only, mirroring freshness_lint.py's shape:
finding dicts, argparse CLI, exit-code convention (0 clean, 1 errors or
strict warnings, 2 bad input / setup). Configure per handbook checkout with
an optional .references.json at the root:
  { "allowlist": [{"match": "<url-or-host>", "class": "sso"|"per-user"|
                    "retired-but-cited"|"other", "reason": "...", "owner": "..."}],
    "hostClasses": {"<host>": "connector-only"|"sso-gated"} }
A missing file is not an error: built-in host classes and an empty allowlist
apply, with one named warning line. Malformed JSON is a fatal, named config
error (exit 2) - never a silently empty allowlist.
"""

from __future__ import annotations

import argparse
import functools
import http.client
import ipaddress
import json
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

DEFAULT_TIMEOUT = 10  # seconds; keep probes small and polite

# Host classing - built-in defaults. A .references.json hostClasses
# block may EXTEND these (union), never drop them.
DEFAULT_CONNECTOR_HOSTS = frozenset({
    "notion.so", "app.notion.com", "notion.com",
    "zoom.us", "docs.zoom.us",
    "atlassian.net",
    "slack.com", "app.slack.com",
})
DEFAULT_SSO_HOSTS = frozenset({
    "zenlytic.com",
    "app.amplitude.com", "amplitude.com",
    "langfuse.com", "cloud.langfuse.com",
    "litellm.ai",
    "figma.com", "www.figma.com",
    "linear.app",
})

# Citation extraction: markdown links and bare URLs of any scheme (so the
# unsupported-scheme handling has something real to classify).
MD_LINK = re.compile(r"\[[^\]]*\]\((\S+?)\)")
BARE_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s<>\]\)]+")
TRAILING_PUNCT = ".,;:!?)'\"`"
HEADING = re.compile(r"^(#{1,6})\s")
ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})(?:-(\d{2}))?\b")

SKIP_DIRS = {".git", ".obsidian", ".claude", ".codex", ".gemini", ".opencode",
             "_export", "node_modules", "__pycache__", ".trash"}

OWNER_REPO_CHARS = re.compile(r"^[A-Za-z0-9._-]+$")

# How many slash-separated segments a branch name in a /blob/ or /tree/ URL may
# have before we stop offering longer cuts. Three covers `document/2026-08-24-x`
# and `renovate/npm/some-dep`; past that the walk costs more probes than it saves.
MAX_REF_SEGMENTS = 3


class ConfigError(Exception):
    """Malformed .references.json - always fatal, always named."""


# The only vocab a config is allowed to use. An unknown value (hostClasses or
# allowlist class) fails loudly with a named ConfigError, never silently.
VALID_HOST_CLASS_VALUES = {"sso-gated", "connector-only"}
VALID_ALLOWLIST_CLASSES = {"sso", "per-user", "retired-but-cited", "other"}


@dataclass
class Routing:
    """Where a citation target goes, decided without any network access."""
    action: str  # "skip" | "sso-error" | "needs-agent" | "probe-github" |
                 # "probe-plain" | "unknown"
    text: str = ""
    allow_entry: dict | None = None
    github_info: dict | None = None


@dataclass
class Context:
    github_login: str | None = None


# --------------------------------------------------------------------------
# Config loading
# --------------------------------------------------------------------------

def load_config(root: Path) -> tuple[dict, list[str]]:
    """Return (config, warning_lines). Raises ConfigError on malformed JSON."""
    cfg_path = root / ".references.json"
    warnings: list[str] = []
    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        warnings.append("no .references.json found — running with built-in "
                         "host classes and an empty allowlist")
        return {"allowlist": [], "hostClasses": {}}, warnings
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"malformed .references.json: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("malformed .references.json: top-level value must be an object")

    known_keys = {"allowlist", "hostClasses"}
    unknown = sorted(set(raw) - known_keys)
    if unknown:
        warnings.append(f"unknown key(s) in .references.json ignored: {', '.join(unknown)}")

    allowlist = raw.get("allowlist", [])
    host_classes = raw.get("hostClasses", {})
    if not isinstance(allowlist, list):
        raise ConfigError("malformed .references.json: 'allowlist' must be a list")
    if not isinstance(host_classes, dict):
        raise ConfigError("malformed .references.json: 'hostClasses' must be an object")

    # Unknown vocab (hostClasses value or allowlist class) is a named, fatal
    # error, never ignored.
    for host, cls in host_classes.items():
        if cls not in VALID_HOST_CLASS_VALUES:
            raise ConfigError(
                f"malformed .references.json: hostClasses['{host}'] = {cls!r} is not a "
                f"known class (expected one of {sorted(VALID_HOST_CLASS_VALUES)})")
    for entry in allowlist:
        cls = entry.get("class") if isinstance(entry, dict) else None
        if cls not in VALID_ALLOWLIST_CLASSES:
            raise ConfigError(
                f"malformed .references.json: allowlist entry for {entry.get('match') if isinstance(entry, dict) else entry!r} "
                f"has class {cls!r}, not a known class (expected one of {sorted(VALID_ALLOWLIST_CLASSES)})")

    # A bare, dotless host-form entry (e.g. "com" or "app") suffix-matches
    # far more than intended via _host_matches. A full URL/target form (has a
    # scheme prefix, e.g. "https://..." or "mailto:...") is exempt - it is
    # matched exactly, never by suffix.
    for entry in allowlist:
        match = str(entry.get("match", "")) if isinstance(entry, dict) else ""
        if match and not SCHEME_PREFIX.match(match) and "." not in match:
            raise ConfigError(
                f"malformed .references.json: allowlist match '{match}' has no dot - "
                f"a bare host fragment like this would match far more than intended")
    for host in host_classes:
        if "." not in host:
            raise ConfigError(
                f"malformed .references.json: hostClasses key '{host}' has no dot - "
                f"a bare host fragment like this would match far more than intended")

    return {"allowlist": allowlist, "hostClasses": host_classes}, warnings


def allowlist_lookup(url: str, host: str, allowlist: list[dict]) -> dict | None:
    for entry in allowlist:
        match = str(entry.get("match", ""))
        if not match:
            continue
        # A full target form (scheme prefix - "https://...", "mailto:...")
        # matches exactly, never by suffix. This also covers non-http(s)
        # schemes, which have no meaningful host to suffix-match on.
        if SCHEME_PREFIX.match(match):
            if url.rstrip("/") == match.rstrip("/"):
                return entry
        else:
            if _host_matches(host, {match.lower()}):
                return entry
    return None


# --------------------------------------------------------------------------
# Host classing
# --------------------------------------------------------------------------

def _host_matches(host: str, entries: frozenset[str] | set[str]) -> bool:
    return any(host == e or host.endswith("." + e) for e in entries)


def classify_host(host: str, sso_hosts, connector_hosts) -> str:
    host = (host or "").lower()
    if host == "github.com":
        return "github"
    if _host_matches(host, sso_hosts):
        return "sso-gated"
    if _host_matches(host, connector_hosts):
        return "connector-only"
    return "plain-web"


# --------------------------------------------------------------------------
# GitHub URL -> API endpoint mapping (strict, allowlist-of-shapes)
# --------------------------------------------------------------------------

def _safe_owner_repo(token: str) -> bool:
    if not token or not OWNER_REPO_CHARS.match(token):
        return False
    if token in (".", ".."):
        return False  # a path-traversal segment, not a real owner/repo/ref
    return True


def _safe_content_path(path: str) -> bool:
    if not path:
        return True  # root of the repo
    if path.startswith("-"):
        return False
    if re.search(r"[\s\x00-\x1f\x7f]", path):
        return False
    if any(seg == ".." for seg in path.split("/")):
        return False
    return True


def parse_github_target(url: str) -> dict | None:
    """Map a github.com URL to one of the known-safe `gh api` endpoint
    shapes, or None if it doesn't match one (never probed in that case)."""
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() != "github.com":
        return None

    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) == 0:
        return None  # bare github.com: unmappable

    if len(parts) == 1:
        # A user or org profile link (people pages cite these).
        login = parts[0]
        if not _safe_owner_repo(login):
            return None
        return {"kind": "profile", "owner": login, "repo": None,
                "endpoint": f"/users/{login}"}

    owner, repo = parts[0], parts[1]
    if not _safe_owner_repo(owner) or not _safe_owner_repo(repo):
        return None

    if len(parts) == 2:
        return {"kind": "repo", "owner": owner, "repo": repo,
                "endpoint": f"/repos/{owner}/{repo}"}

    if parts[2] in ("blob", "tree") and len(parts) >= 4:
        # `/blob/<ref>/<path>` carries no boundary between the two, and branch
        # names often have a slash in them (`document/…`, `feat/…`), so
        # cutting at the first slash is a guess. Offer every cut whose ref
        # segments and path are safe, shortest ref first; the prober asks
        # GitHub which of them is a real ref instead of assuming.
        last_cut = len(parts) if len(parts) == 4 else len(parts) - 1
        splits = []
        for cut in range(4, min(last_cut, 3 + MAX_REF_SEGMENTS) + 1):
            if not _safe_owner_repo(parts[cut - 1]):
                break  # a segment that cannot be part of a ref ends the walk
            path = "/".join(parts[cut:])
            if not _safe_content_path(path):
                continue
            ref = "/".join(parts[3:cut])
            splits.append({"ref": ref, "path": path,
                           "endpoint": f"/repos/{owner}/{repo}/contents/{path}?ref={ref}"})
        if not splits:
            return None
        return {"kind": "contents", "owner": owner, "repo": repo,
                "endpoint": splits[0]["endpoint"], "splits": splits}

    if parts[2] in ("issues", "pull") and len(parts) >= 4 and parts[3].isdigit():
        return {"kind": "issue", "owner": owner, "repo": repo,
                "endpoint": f"/repos/{owner}/{repo}/issues/{parts[3]}"}

    return None  # anything else: unmappable, never probed


# --------------------------------------------------------------------------
# GitHub probing (identity, compound-evidence "gone")
# --------------------------------------------------------------------------

def run_gh(args: list[str], timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Invoke `gh <args>` via list-argv subprocess (never shell=True)."""
    try:
        proc = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"returncode": None, "stdout": "", "stderr": "timeout"}
    except FileNotFoundError:
        return {"returncode": None, "stdout": "", "stderr": "gh-not-found"}
    return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


def fetch_github_identity() -> str | None:
    result = run_gh(["api", "user"])
    if result["returncode"] != 0:
        return None
    try:
        data = json.loads(result["stdout"])
    except json.JSONDecodeError:
        return None
    return data.get("login") if isinstance(data, dict) else None


def probe_github_endpoint(endpoint: str, timeout: float = DEFAULT_TIMEOUT) -> dict:
    result = run_gh(["api", "--method", "GET", "--", endpoint], timeout=timeout)
    stderr = result["stderr"] or ""
    if result["returncode"] == 0:
        return {"status": 200, "error": None}
    if stderr == "timeout":
        return {"status": None, "error": "timeout"}
    m = re.search(r"HTTP (\d{3})", stderr)
    if m:
        status = int(m.group(1))
        if status == 403 and "rate limit" in stderr.lower():
            return {"status": 403, "error": "rate-limit"}
        if status >= 500:
            return {"status": status, "error": "server-error"}
        return {"status": status, "error": None}
    return {"status": None, "error": "unknown-gh-failure", "detail": stderr.strip()[:200]}


def is_transient(result: dict) -> bool:
    if result.get("error") in ("timeout", "rate-limit", "server-error", "connection"):
        return True
    status = result.get("status")
    return status is not None and (status == 429 or status >= 500)


def probe_with_retry(fn, *args) -> dict:
    result = fn(*args)
    if not is_transient(result):
        return result
    return fn(*args)  # exactly one retry, whatever comes back is final


# One answer per (owner, repo) per run: several broken links into the same repo
# must not re-probe the identical parent endpoint. Cleared at the top of main().
_PARENT_PROBE_CACHE: dict[str, dict] = {}


def _probe_parent_repo(endpoint: str) -> dict:
    if endpoint not in _PARENT_PROBE_CACHE:
        _PARENT_PROBE_CACHE[endpoint] = probe_github_endpoint(endpoint)
    return _PARENT_PROBE_CACHE[endpoint]


def _check_gone_evidence(info: dict) -> tuple[str, str]:
    default = ("no-access", "GitHub 404 (possibly gone — GitHub does not distinguish)")
    owner, repo = info["owner"], info.get("repo")

    if info["kind"] in ("repo", "profile"):
        # A visible owner proves nothing about a 404ing repo: private repos are
        # hidden from listings, so "owner readable, repo absent" describes a
        # private repo and a deleted repo equally. Repo-level and profile-level
        # 404s never upgrade.
        return default

    # For a path inside a repo (contents, issue): if the repo itself answers 200
    # to the same credentials, the 404 on the inner target is decisive — we can
    # read the repo, and the thing it should contain is not there.
    parent = _probe_parent_repo(f"/repos/{owner}/{repo}")
    if parent.get("status") == 200:
        return "gone", "target 404s inside a repo these credentials can read"
    if parent.get("status") == 404:
        return default
    return "unknown", "mixed evidence: target 404 but parent status ambiguous — said out loud"


# One answer per (owner, repo, ref) per run. Nearly every citation points at
# `main`, so this is the difference between one ref lookup and one per link.
_REF_PROBE_CACHE: dict[str, dict] = {}


def _probe_ref(owner: str, repo: str, ref: str) -> dict:
    endpoint = f"/repos/{owner}/{repo}/commits/{ref}"
    if endpoint not in _REF_PROBE_CACHE:
        _REF_PROBE_CACHE[endpoint] = probe_with_retry(probe_github_endpoint, endpoint)
    return _REF_PROBE_CACHE[endpoint]


def _resolve_ref_split(info: dict) -> tuple[dict | None, dict | None]:
    """Ask GitHub which cut of a /blob/ URL is the real ref, shortest first.

    Guessing the boundary at the first slash reports a live file on a
    slash-named branch as `gone`, which is worse than the silence this check
    exists to remove. Returns `(split, transient)`: a transient answer stops
    the walk, because an unresolved ref must never harden into "missing".
    """
    for split in info["splits"]:
        result = _probe_ref(info["owner"], info["repo"], split["ref"])
        if is_transient(result):
            return None, result
        if result.get("status") == 200:
            return split, None
    return None, None


def classify_github(url: str, info: dict) -> dict:
    if info.get("splits"):
        split, transient = _resolve_ref_split(info)
        if transient is not None:
            return {"class": "transient",
                    "text": "GitHub ref lookup failed transiently (timeout/rate-limit/5xx) after one retry"}
        if split is None:
            tried = ", ".join(f"`{s['ref']}`" for s in info["splits"])
            return {"class": "unknown",
                    "text": f"no branch, tag or commit answers to {tried}, so which part of "
                            f"the URL is the ref stays unresolved — not called gone"}
        info = {**info, "endpoint": split["endpoint"]}
    result = probe_with_retry(probe_github_endpoint, info["endpoint"])
    if is_transient(result):
        return {"class": "transient",
                "text": "GitHub API probe failed transiently (timeout/rate-limit/5xx) after one retry"}
    status = result.get("status")
    if status == 200:
        return {"class": "ok", "text": ""}
    if status == 404:
        cls, text = _check_gone_evidence(info)
        return {"class": cls, "text": text}
    if status in (401, 403):
        return {"class": "no-access", "text": f"GitHub API returned {status} (auth/permission denied)"}
    return {"class": "unknown", "text": f"unexpected gh api result for {url}: {result}"}


# --------------------------------------------------------------------------
# Plain-web probing (safety-critical)
# --------------------------------------------------------------------------

REDIRECT_CODES = {301, 302, 303, 307, 308}


def _ip_is_safe(raw_ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(raw_ip.split("%")[0])  # strip an IPv6 zone id if present
    except ValueError:
        return False
    # Positive check, not a denylist: `is_global` excludes ranges no denylist
    # of ours tracks, notably CGNAT 100.64.0.0/10 — Tailscale tailnet space,
    # including the 100.100.100.100 MagicDNS resolver, on a laptop that is
    # plausibly on a tailnet. The explicit terms stay for the few addresses
    # `is_global` alone treats as global.
    return addr.is_global and not (addr.is_loopback or addr.is_link_local
                                   or addr.is_private or addr.is_reserved
                                   or addr.is_unspecified)


def _resolve_host(host: str) -> dict:
    """Resolve `host` exactly once and say which of three things happened: a temporary resolver hiccup (EAI_AGAIN) is transient and gets
    retried like any other flaky probe; a genuine non-existent name is a
    distinct, non-transient no-resolve result; only a name that actually
    resolved to a private/loopback/reserved address is unsafe. Collapsing
    all three into one "unsafe-target" verdict (the old behaviour) turned
    an ordinary DNS blip into a false, non-retried security finding.

    On success, returns one concrete safe IP to connect to - the same IP
    the safety check just examined, so nothing gets re-resolved (and
    potentially rebound to something else) between the check and the
    connect."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        if exc.errno == socket.EAI_AGAIN:
            return {"ok": False, "reason": "transient"}
        return {"ok": False, "reason": "no-resolve"}
    except OSError:
        # Not even a clean gaierror (e.g. a resolver-level EAI_SYSTEM) - a
        # plumbing hiccup, not evidence the target is unsafe.
        return {"ok": False, "reason": "transient"}
    if not infos:
        return {"ok": False, "reason": "no-resolve"}
    safe_ip = None
    for info in infos:
        raw_ip = info[4][0].split("%")[0]  # strip an IPv6 zone id if present
        if not _ip_is_safe(raw_ip):
            return {"ok": False, "reason": "unsafe"}
        if safe_ip is None:
            safe_ip = raw_ip
    return {"ok": True, "ip": safe_ip}


def _redirect_is_safe(original_url: str, location: str) -> bool:
    resolved = urljoin(original_url, location)
    orig_host = (urlparse(original_url).hostname or "").lower()
    new = urlparse(resolved)
    if new.scheme not in ("http", "https"):
        return False
    if (new.hostname or "").lower() != orig_host:
        return False
    return _resolve_host(new.hostname)["ok"]


class _UnsafeTargetError(Exception):
    """Raised by a pinned connection when the socket that actually got
    opened is not the address the safety check validated (DNS rebinding /
    resolve-then-connect TOCTOU)."""


def _connect_to_safe_ip(safe_ip: str, port: int, timeout, source_address):
    """The one seam that actually opens a TCP connection - a dedicated
    function so tests can pin exactly this call without faking a real
    socket end to end."""
    return socket.create_connection((safe_ip, port), timeout=timeout, source_address=source_address)


def _require_safe_peer(sock) -> None:
    peer_ip = sock.getpeername()[0]
    if not _ip_is_safe(peer_ip):
        sock.close()
        raise _UnsafeTargetError(f"post-connect peer {peer_ip} is not safe")


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """Connects to a pre-validated literal IP instead of letting the stdlib
    re-resolve `host` at connect time - closing the TOCTOU window a low-TTL
    DNS record could otherwise exploit. The Host header still carries
    the original `host` untouched."""

    def __init__(self, host, *args, safe_ip: str, **kwargs):
        super().__init__(host, *args, **kwargs)
        self._safe_ip = safe_ip

    def connect(self):
        self.sock = _connect_to_safe_ip(self._safe_ip, self.port, self.timeout, self.source_address)
        _require_safe_peer(self.sock)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """As `_PinnedHTTPConnection`, but wraps the pinned socket in TLS using
    the ORIGINAL hostname for SNI and certificate validation - only the
    transport address is pinned, never the identity being validated."""

    def __init__(self, host, *args, safe_ip: str, **kwargs):
        super().__init__(host, *args, **kwargs)
        self._safe_ip = safe_ip

    def connect(self):
        sock = _connect_to_safe_ip(self._safe_ip, self.port, self.timeout, self.source_address)
        _require_safe_peer(sock)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, safe_ip: str):
        super().__init__()
        self._safe_ip = safe_ip

    def http_open(self, req):
        return self.do_open(functools.partial(_PinnedHTTPConnection, safe_ip=self._safe_ip), req)


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, safe_ip: str):
        super().__init__()
        self._safe_ip = safe_ip

    def https_open(self, req):
        return self.do_open(functools.partial(_PinnedHTTPSConnection, safe_ip=self._safe_ip),
                             req, context=self._context)


def _open_url(request: urllib.request.Request, timeout: float, safe_ip: str):
    """The one seam that actually talks to the network. Redirects OFF, and
    the real connection is pinned to `safe_ip` - resolved once, right
    before this call - so resolving again inside urllib can never land on
    a different (possibly private) address than the one just validated"""
    opener = urllib.request.build_opener(_NoRedirect(), _PinnedHTTPHandler(safe_ip),
                                          _PinnedHTTPSHandler(safe_ip))
    return opener.open(request, timeout=timeout)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # tells urllib to raise HTTPError instead of following


def probe_http(url: str, timeout: float = DEFAULT_TIMEOUT, _hop: int = 0) -> dict:
    """Safely fetch `url`. Never sends cookies/credentials, never follows a
    redirect automatically except one same-host, re-validated hop. The host
    is resolved exactly once, up front, to a concrete IP that the actual
    connection is then pinned to."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return {"status": None, "error": "unsupported-scheme", "detail": parsed.scheme or "(none)"}

    host = parsed.hostname
    if not host:
        return {"status": None, "error": "unsafe-target", "detail": url}

    resolution = _resolve_host(host)
    if not resolution["ok"]:
        reason = resolution["reason"]
        if reason == "transient":
            return {"status": None, "error": "connection", "detail": f"temporary DNS failure resolving {host}"}
        if reason == "no-resolve":
            return {"status": None, "error": "no-resolve", "detail": f"{host} does not resolve"}
        return {"status": None, "error": "unsafe-target", "detail": host}
    safe_ip = resolution["ip"]

    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method,
                                      headers={"User-Agent": "scripta-reference-check/1.0"})
        try:
            resp = _open_url(req, timeout, safe_ip)
            try:
                return {"status": resp.status, "error": None}
            finally:
                resp.close()
        except _UnsafeTargetError as exc:
            return {"status": None, "error": "unsafe-target", "detail": str(exc)}
        except urllib.error.HTTPError as exc:
            if exc.code in REDIRECT_CODES:
                location = exc.headers.get("Location") if exc.headers else None
                resolved = urljoin(url, location) if location else None
                if resolved and _hop == 0 and _redirect_is_safe(url, resolved):
                    return probe_http(resolved, timeout=timeout, _hop=1)
                new_host = urlparse(resolved).hostname if resolved else "unknown"
                return {"status": exc.code, "error": "redirect", "detail": f"redirect-to:{new_host}"}
            if exc.code == 405 and method == "HEAD":
                continue  # fall back to GET
            return {"status": exc.code, "error": None}
        except socket.timeout:
            return {"status": None, "error": "timeout"}
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), socket.timeout):
                return {"status": None, "error": "timeout"}
            return {"status": None, "error": "connection", "detail": str(exc.reason)}
    return {"status": None, "error": "connection"}


def classify_plain_web(url: str) -> dict:
    result = probe_with_retry(probe_http, url)
    if is_transient(result):
        return {"class": "transient", "text": "HTTP probe failed transiently (timeout/5xx) after one retry"}
    err = result.get("error")
    status = result.get("status")
    if err == "unsafe-target":
        return {"class": "unknown", "text": f"unsafe-target: refused to probe ({result.get('detail', '')})"}
    if err == "no-resolve":
        return {"class": "no-access", "text": f"DNS: {result.get('detail', 'host does not resolve')}"}
    if err == "unsupported-scheme":
        return {"class": "unknown", "text": f"unsupported-scheme '{result.get('detail', '')}': not probed"}
    if err == "redirect":
        return {"class": "unknown", "text": result.get("detail", "redirect-to:unknown")}
    if status is not None and 200 <= status < 300:
        return {"class": "ok", "text": ""}
    if status is not None:
        return {"class": "no-access", "text": f"HTTP {status}"}
    return {"class": "unknown", "text": f"unclassified probe failure: {result}"}


# --------------------------------------------------------------------------
# Routing: decide what happens to a target with zero network access
# --------------------------------------------------------------------------

def route_target(url: str, allowlist: list[dict], sso_hosts, connector_hosts) -> Routing:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    allow_entry = allowlist_lookup(url, host, allowlist)

    if parsed.scheme not in ("http", "https"):
        # Consult the allowlist BEFORE rejecting the scheme: a
        # non-http(s) target (mailto:, a Slack deep link, etc.) still
        # deserves the "allowlist it" remedy, not a dead end.
        if allow_entry:
            return Routing("skip", allow_entry.get("reason", ""), allow_entry)
        return Routing("unknown", f"unsupported scheme '{parsed.scheme}' — not probed")

    host_class = classify_host(host, sso_hosts, connector_hosts)

    if host_class == "sso-gated":
        if allow_entry:
            return Routing("skip", allow_entry.get("reason", ""), allow_entry)
        return Routing("sso-error", "sso-gated host with no allowlist entry")

    if host_class == "connector-only":
        if allow_entry:
            return Routing("skip", allow_entry.get("reason", ""), allow_entry)
        return Routing("needs-agent", "connector-only host — agent must verify via its own MCP connector")

    if allow_entry and allow_entry.get("class") != "per-user":
        return Routing("skip", allow_entry.get("reason", ""), allow_entry)

    if host_class == "github":
        info = parse_github_target(url)
        if info is None:
            return Routing("unknown", "unmappable github URL — not probed", allow_entry)
        return Routing("probe-github", "", allow_entry, github_info=info)

    return Routing("probe-plain", "", allow_entry)


def _mk(cls: str, text: str, identity: str | None, allow_entry: dict | None) -> dict:
    return {
        "class": cls,
        "text": text,
        "identity": identity,
        "allowlist_status": allow_entry.get("class") if allow_entry else "none",
    }


def resolve_target(url: str, routing: Routing, ctx: Context) -> dict:
    if routing.action == "skip":
        return _mk("skipped-by-design", routing.text, None, routing.allow_entry)
    if routing.action == "sso-error":
        return _mk("sso-gated-no-allowlist", routing.text, None, None)
    if routing.action == "needs-agent":
        return _mk("needs-agent-result", routing.text, None, None)
    if routing.action == "unknown":
        return _mk("unknown", routing.text, None, routing.allow_entry)

    if routing.action == "probe-github":
        outcome = classify_github(url, routing.github_info)
        identity = ctx.github_login or "unknown-github-identity"
    elif routing.action == "probe-plain":
        outcome = classify_plain_web(url)
        identity = "anonymous HTTP"
    else:  # pragma: no cover - defensive
        raise AssertionError(f"unhandled routing action {routing.action!r}")

    cls, text = outcome["class"], outcome["text"]
    # per-user downgrades a failure this identity personally can't clear -
    # but "gone" is proven for EVERYONE (compound evidence), not this
    # identity's access, so it must never be swallowed into skipped.
    if routing.allow_entry and routing.allow_entry.get("class") == "per-user" and cls not in ("ok", "gone"):
        return _mk("skipped-by-design", routing.allow_entry.get("reason", ""), identity, routing.allow_entry)
    return _mk(cls, text, identity, routing.allow_entry)


# --------------------------------------------------------------------------
# Extraction (mirrors freshness_lint.py's walk and exempt-zone mechanics)
# --------------------------------------------------------------------------

def parse_frontmatter(lines: list[str]) -> tuple[dict, int]:
    if not lines or lines[0].strip() != "---":
        return {}, 0
    fm = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return fm, i + 1
        m = re.match(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$", line)
        if m:
            fm[m.group(1).strip().lower()] = m.group(2).strip().strip('"')
    return {}, 0


def _strip_trailing_punct(url: str) -> str:
    return url.rstrip(TRAILING_PUNCT)


SCHEME_PREFIX = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def _extract_urls(line: str) -> list[str]:
    urls = []
    spans = []
    for m in MD_LINK.finditer(line):
        dest = m.group(1)
        # Repo-relative links and same-page anchors are local navigation,
        # not external citations: only scheme-carrying destinations count.
        if SCHEME_PREFIX.match(dest):
            urls.append(_strip_trailing_punct(dest))
        spans.append(m.span(1))
    masked = line
    for start, end in sorted(spans, reverse=True):
        masked = masked[:start] + ("#" * (end - start)) + masked[end:]
    for m in BARE_URL.finditer(masked):
        urls.append(_strip_trailing_punct(m.group(0)))
    return urls


def extract_file_citations(path: Path, rel: str) -> tuple[list[tuple[str, int, str]], int]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return [], 0
    lines = text.splitlines()
    fm, body_start = parse_frontmatter(lines)

    # Whole-file exemptions, same as freshness_lint's FRESH-4. The page is
    # never scanned for live citations, but its URLs still count toward
    # exempt_count - otherwise they land in NO count at all, silently
    # breaking the "N citations in exempt zones" coverage boundary.
    if fm.get("freshness") == "snapshot" or ISO_DATE.search(path.stem):
        whole_file_exempt = sum(len(_extract_urls(line.strip())) for line in lines[body_start:])
        return [], whole_file_exempt

    citations: list[tuple[str, int, str]] = []
    exempt_count = 0
    in_fence = False
    dated_heading_level: int | None = None

    for lineno, line in enumerate(lines[body_start:], start=body_start + 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            exempt_count += len(_extract_urls(stripped))
            continue
        if not stripped:
            continue

        h = HEADING.match(stripped)
        if h:
            level = len(h.group(1))
            closes_dated_zone = dated_heading_level is not None and level <= dated_heading_level
            still_in_dated_zone = dated_heading_level is not None and not closes_dated_zone
            if closes_dated_zone:
                dated_heading_level = None
            heading_is_dated = bool(ISO_DATE.search(stripped))
            if heading_is_dated:
                dated_heading_level = level
            # A URL living directly on the heading line is still extracted: it
            # is never dropped, and lands wherever the rest of the line's
            # zone membership says it should.
            heading_urls = _extract_urls(stripped)
            if heading_urls:
                if heading_is_dated or still_in_dated_zone:
                    exempt_count += len(heading_urls)
                else:
                    for url in heading_urls:
                        citations.append((rel, lineno, url))
            continue
        if dated_heading_level is not None:
            exempt_count += len(_extract_urls(stripped))
            continue
        if stripped.lstrip().startswith(">"):
            exempt_count += len(_extract_urls(stripped))
            continue

        for url in _extract_urls(stripped):
            citations.append((rel, lineno, url))

    return citations, exempt_count


def extract_citations(root: Path, only: str | None = None) -> tuple[dict[str, list[tuple[str, int]]], int]:
    by_target: dict[str, list[tuple[str, int]]] = {}
    exempt_total = 0
    paths = [root / only] if only else sorted(root.rglob("*.md"))
    for path in paths:
        parts = path.relative_to(root).parts
        if any(part in SKIP_DIRS for part in parts):
            continue
        rel = str(path.relative_to(root))
        citations, exempt_count = extract_file_citations(path, rel)
        exempt_total += exempt_count
        for rel2, lineno, url in citations:
            by_target.setdefault(url, []).append((rel2, lineno))
    return by_target, exempt_total


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

CLASS_META = {
    "no-access": ("REF-1", "error"),
    "gone": ("REF-2", "error"),
    "unknown": ("REF-3", "error"),
    "transient": ("REF-4", "warning"),
    "skipped-by-design": ("REF-5", "info"),
    "needs-agent-result": ("REF-6", "info"),
    "sso-gated-no-allowlist": ("REF-7", "error"),
}


def build_report(findings: list[dict], exempt_count: int, github_login: str | None,
                  config_warnings: list[str]) -> dict:
    errors = sum(1 for f in findings if f["severity"] == "error")
    warnings = sum(1 for f in findings if f["severity"] == "warning")
    return {
        "errors": errors,
        "warnings": warnings,
        "findings": findings,
        "exempt_count": exempt_count,
        "identity": {"github": github_login},
        "config_warnings": config_warnings,
    }


def exit_code_for(report: dict, strict: bool) -> int:
    if report["errors"] or (strict and report["warnings"]):
        return 1
    return 0


def print_human_report(report: dict) -> None:
    findings = report["findings"]
    for w in report["config_warnings"]:
        print(f"warning: {w}")

    failures = [f for f in findings if f["error_class"] in ("no-access", "gone", "sso-gated-no-allowlist")]
    unknowns = [f for f in findings if f["error_class"] == "unknown"]
    transients = [f for f in findings if f["error_class"] == "transient"]
    skipped = [f for f in findings if f["error_class"] == "skipped-by-design"]
    needs_agent = [f for f in findings if f["error_class"] == "needs-agent-result"]

    if failures:
        print("\nFailures:")
        for f in failures:
            print(f"  [{f['rule']}] {f['file']}:{f['line']}  target={f['target']}  "
                  f"class={f['error_class']}  identity={f['identity']}  {f['text']}")
    if transients:
        print("\nTransient (retried once, not exit-affecting alone):")
        for f in transients:
            print(f"  {f['file']}:{f['line']}  target={f['target']}  {f['text']}")
    if unknowns:
        print("\nUnknown (ambiguous evidence):")
        for f in unknowns:
            print(f"  {f['file']}:{f['line']}  target={f['target']}  {f['text']}")
    if skipped:
        print("\nSkipped by design (allowlisted):")
        for f in skipped:
            print(f"  {f['file']}:{f['line']}  target={f['target']}  reason: {f['text']}")
    if needs_agent:
        print("\nNeeds agent result (connector-only, not probed by this script):")
        for f in needs_agent:
            print(f"  {f['file']}:{f['line']}  target={f['target']}")

    print(f"\n{report['exempt_count']} citation(s) in exempt zones, unchecked by design.")
    if report["identity"]["github"]:
        print(f"GitHub probes ran as {report['identity']['github']}.")
    print(f"\n{report['errors']} error(s), {report['warnings']} warning(s).")


# --------------------------------------------------------------------------
# CLI modes
# --------------------------------------------------------------------------

def build_routings(root: Path, only: str | None = None):
    """Load config, extract citations, and route every target - the one
    computation shared by the normal scan, --inventory, and --verify.
    This matters because --verify calls the exact same code the real scan
    uses, so the authoritative connector-only target set can never drift
    from (or be spoofed by) whatever a results file merely claims."""
    config, config_warnings = load_config(root)
    sso_hosts = set(DEFAULT_SSO_HOSTS)
    connector_hosts = set(DEFAULT_CONNECTOR_HOSTS)
    for host, cls in config["hostClasses"].items():
        if cls == "sso-gated":
            sso_hosts.add(host.lower())
        elif cls == "connector-only":
            connector_hosts.add(host.lower())
    allowlist = config["allowlist"]

    by_target, exempt_count = extract_citations(root, only)
    routings = {url: route_target(url, allowlist, sso_hosts, connector_hosts) for url in by_target}
    return routings, by_target, exempt_count, config_warnings, sso_hosts, connector_hosts


def cmd_inventory(by_target: dict, sso_hosts, connector_hosts, exempt_count: int,
                   config_warnings: list[str], as_json: bool) -> int:
    counts = {"github": 0, "plain-web": 0, "connector-only": 0, "sso-gated": 0, "unmappable-scheme": 0}
    for url in by_target:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            counts["unmappable-scheme"] += 1
            continue
        host = (parsed.hostname or "").lower()
        counts[classify_host(host, sso_hosts, connector_hosts)] += 1

    report = {"counts": counts, "unique_targets": len(by_target),
              "exempt_count": exempt_count, "config_warnings": config_warnings}
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        for k, v in counts.items():
            print(f"{k}: {v}")
        print(f"\n{len(by_target)} unique citation target(s); {exempt_count} in exempt "
              f"zones, unchecked by design.")
        for w in config_warnings:
            print(f"warning: {w}")
    return 0


# A filled connector row is only ever considered non-failing when its result
# is a dict without one of these classes, or a bare truthy value at all
# (backward-compat: the connector step may just write a truthy string like
# "verified reachable via MCP" - see module docstring's Usage section).
# transient and skipped-by-design/ok are the only classes allowed through.
VERIFY_FAILURE_CLASSES = {"no-access", "gone", "unknown", "sso-gated-no-allowlist"}


def cmd_verify(routings: dict, results_path: Path) -> int:
    """Close the connector-row check by script, not by agent diligence. `routings` is the
    SAME routing the current handbook checkout would produce in a real
    scan - never trusted from the results file itself - so this can catch
    both failure modes a hollow closure check missed: a row present but
    filled with a failing result, and a target quietly absent or
    mismatched between the handbook and the results file."""
    expected = {url for url, routing in routings.items() if routing.action == "needs-agent"}

    try:
        data = json.loads(results_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: could not read results file {results_path}: {exc}", file=sys.stderr)
        return 2

    findings = data.get("findings", []) if isinstance(data, dict) else []
    connector_rows = [f for f in findings if f.get("error_class") == "needs-agent-result"]
    seen_targets = {row.get("target") for row in connector_rows}

    problems: list[str] = []
    for target in sorted(expected - seen_targets):
        problems.append(f"expected connector-only target missing from results file: {target}")

    for row in connector_rows:
        target = row.get("target")
        if target not in expected:
            continue  # e.g. now allowlisted away since the results file was written - not this run's concern
        loc = f"{row.get('file')}:{row.get('line')}"
        result = row.get("result")
        if not result:
            problems.append(f"unfilled connector-only result: {target} (cited {loc})")
            continue
        cls = result.get("error_class", "unknown") if isinstance(result, dict) else "ok"
        if cls in VERIFY_FAILURE_CLASSES:
            problems.append(f"connector-only result failed verification: {target} class={cls} (cited {loc})")

    if problems:
        for p in problems:
            print(p)
        print(f"\n{len(problems)} connector-only problem(s) against {len(expected)} expected "
              f"target(s). Run is not closed.")
        return 1

    print(f"All {len(expected)} connector-only target(s) verified reachable "
          f"(transient/skipped-by-design allowed).")
    return 0


def main(argv: list[str]) -> int:
    _PARENT_PROBE_CACHE.clear()
    _REF_PROBE_CACHE.clear()
    ap = argparse.ArgumentParser(
        description="Check that every reference the handbook cites can actually be read"
    )
    ap.add_argument("--path", help="handbook checkout to scan (required, including for --verify)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--strict", action="store_true", help="warnings also fail the run")
    ap.add_argument("--inventory", action="store_true",
                     help="extraction-only: counts per host class, no probing, no network")
    ap.add_argument("--verify", metavar="RESULTS_JSON",
                     help="verify a previously emitted --json report has every connector-only "
                          "row present, filled, and non-failing; requires --path so the "
                          "authoritative connector-only target set is recomputed from the "
                          "handbook itself, never merely trusted from the results file")
    ap.add_argument("--only", metavar="RELPATH",
                     help="scan only this one file (a path relative to --path); "
                          "config still loads from the --path root")
    args = ap.parse_args(argv[1:])

    if not args.path:
        print("error: --path is required", file=sys.stderr)
        return 2

    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    only = None
    if args.only:
        target = (root / args.only).resolve()
        if not target.is_file() or root not in target.parents:
            print(f"error: --only file not found under {root}: {args.only}", file=sys.stderr)
            return 2
        only = str(target.relative_to(root))

    try:
        routings, by_target, exempt_count, config_warnings, sso_hosts, connector_hosts = build_routings(root, only)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.verify:
        return cmd_verify(routings, Path(args.verify).expanduser().resolve())

    if args.inventory:
        return cmd_inventory(by_target, sso_hosts, connector_hosts, exempt_count,
                              config_warnings, args.json)

    ctx = Context()
    if any(r.action == "probe-github" for r in routings.values()):
        # One call does both jobs: it fails exactly when gh is missing or
        # unauthenticated, and succeeds with the identity the probes run as.
        ctx.github_login = fetch_github_identity()
        if ctx.github_login is None:
            print("error: gh not installed / not authenticated — "
                  "GitHub targets cannot be verified", file=sys.stderr)
            return 2

    findings: list[dict] = []
    for url in sorted(by_target):
        outcome = resolve_target(url, routings[url], ctx)
        if outcome["class"] == "ok":
            continue
        rule, severity = CLASS_META[outcome["class"]]
        for file, line in by_target[url]:
            finding = {
                "rule": rule, "severity": severity, "file": file, "line": line,
                "text": outcome["text"], "target": url,
                "error_class": outcome["class"], "identity": outcome["identity"],
                "allowlist_status": outcome["allowlist_status"],
            }
            if outcome["class"] == "needs-agent-result":
                finding["result"] = None
            findings.append(finding)

    report = build_report(findings, exempt_count, ctx.github_login, config_warnings)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_human_report(report)

    return exit_code_for(report, args.strict)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
