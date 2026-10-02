#!/usr/bin/env python3
"""Deterministic Paperclip process-adapter bridge onto NightCrew claims.

One invocation is one bounded tick. NightCrew's atomic claim stays the only
execution ownership; this bridge keeps a durable local ledger so a restart,
a lost HTTP response or a provider quota wait never becomes a duplicate
dispatch. It never merges, releases or deploys, and never calls a model unless
it already holds a job to run. A tick only claims or launches when the config
sets dispatch_enabled to true; otherwise (or with --observe) it makes GET
requests only. See docs/runbooks/paperclip-bridge.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BLOCKED = 3
DEFAULT_QUOTA_EXIT = 75  # EX_TEMPFAIL: the launcher's "provider unavailable" signal.
ACTIVE_STATES = ("claimed", "launching", "running", "waiting_provider", "ready_for_review", "blocked")
SUPPORTED_KINDS = ("issue", "maintenance")
RECEIPT_PHASES = ("ready_for_review", "done")
TEMPLATE_FIELD = re.compile(r"\{([a-z_]+)\}")


class BridgeError(Exception):
    """A configuration or boundary violation that must stop the tick."""


def utcnow() -> dt.datetime:
    """Return the current aware UTC time."""
    return dt.datetime.now(dt.timezone.utc)


def iso(moment: dt.datetime) -> str:
    """Render a timestamp the same way everywhere in the ledger."""
    return moment.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def parse_time(value) -> dt.datetime | None:
    """Parse an ISO timestamp, returning None when absent or malformed."""
    if not isinstance(value, str):
        return None
    try:
        moment = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    return moment


class RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect: urllib would otherwise replay the bearer token to the Location host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Stop the request instead of following it anywhere, including the same host."""
        fp.close()
        raise BridgeError(f"refused HTTP {code} redirect from the NightCrew API")


class Api:
    """Host-scoped NightCrew client; the token is only ever sent to api_base."""

    def __init__(self, base_url: str, token: str, timeout: int = 30):
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise BridgeError("api_base must be an http(s) URL")
        self.base_url = base_url.rstrip("/")
        self.netloc = parsed.netloc
        self._token = token
        self.timeout = timeout
        # An empty ProxyHandler ignores *_proxy variables, which would hand a
        # plain-http Authorization header to whatever proxy the environment names.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), RefuseRedirects())

    def request(self, method: str, path: str, body=None):
        """Perform one request and return (status, decoded JSON or None)."""
        url = self.base_url + path
        # Guard against a crafted path escaping the configured host with the token.
        if urllib.parse.urlparse(url).netloc != self.netloc:
            raise BridgeError("request escaped the configured API host")
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", "Bearer " + self._token)
        request.add_header("Accept", "application/json")
        request.add_header("Content-Type", "application/json")
        try:
            response = self._opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            # Older Pythons surface some 3xx codes (e.g. 308) as errors rather than redirects.
            if 300 <= error.code < 400:
                error.close()
                raise BridgeError(f"refused HTTP {error.code} redirect from the NightCrew API") from None
            raise
        with response:
            payload = response.read()
            if not payload:
                return response.status, None
            return response.status, json.loads(payload)

    def me(self) -> dict:
        """Return the worker's registered identity and served repositories."""
        return self.request("GET", "/worker/me")[1]

    def held(self) -> list:
        """Return the jobs NightCrew says this worker currently holds."""
        return self.request("GET", "/worker/jobs")[1]["data"]

    def claim(self) -> dict | None:
        """Atomically claim the next non-PR job, or None when nothing is due."""
        status, payload = self.request("POST", "/claim-next")
        if status == 204 or payload is None:
            return None
        return payload["data"]

    def status(self, job: dict, status: str, receipt: dict) -> dict:
        """Report a held job's transition with its structured receipt."""
        body = {"status": status, "receipt": receipt}
        if job.get("claim_token"):
            body["claim_token"] = job["claim_token"]
        return self.request("PATCH", f"/jobs/{job['id']}/status", body)[1]


def load_token(config: dict) -> str:
    """Read the worker token from a file or environment without echoing it."""
    if config.get("token_file"):
        return Path(config["token_file"]).expanduser().read_text(encoding="utf-8").strip()
    if config.get("token_env") and os.environ.get(config["token_env"]):
        return os.environ[config["token_env"]]
    raise BridgeError("no NightCrew token configured (token_file or token_env)")


def load_config(path: Path) -> dict:
    """Load and validate the explicit repository/provider allowlist."""
    config = json.loads(path.read_text(encoding="utf-8"))
    for key in ("api_base", "worker_id", "state_dir", "repositories", "providers"):
        if not config.get(key):
            raise BridgeError(f"config is missing {key}")
    for repo, settings in config["repositories"].items():
        if not Path(settings.get("worktree", "")).is_absolute():
            raise BridgeError(f"{repo}: worktree must be an absolute path")
        if not settings.get("providers"):
            raise BridgeError(f"{repo}: providers must be a non-empty list")
        for provider in settings["providers"]:
            if provider not in config["providers"]:
                raise BridgeError(f"{repo}: provider {provider} is not declared")
            argv = settings.get("launch", {}).get(provider)
            if not isinstance(argv, list) or not argv or not all(isinstance(part, str) for part in argv):
                raise BridgeError(f"{repo}: launch.{provider} must be a non-empty argv list")
    return config


class Ledger:
    """Durable bridge state written atomically (temp file, fsync, rename)."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict:
        """Read the ledger, starting empty on first use."""
        if not self.path.exists():
            return {"version": 1, "jobs": {}, "providers": {}, "intent": None, "halt": None}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, state: dict) -> None:
        """Persist the whole ledger so a crash leaves the old or new copy, never half."""
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)
        directory = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def acquire_lock(path: Path) -> int | None:
    """Take the per-worker flock; children inherit it so a live descendant usually blocks overlap.

    Inheritance is best effort: a nested tool that closes its descriptors drops
    the lock while still running, so holding it never proves descendants dead.
    """
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(descriptor)
        return None
    os.set_inheritable(descriptor, True)
    return descriptor


def git_revision(worktree: str) -> str:
    """Return the worktree's checked-out revision."""
    result = subprocess.run(["git", "-C", worktree, "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True)
    return result.stdout.strip()


def worktree_fingerprint(worktree: str) -> dict:
    """Digest HEAD-relative changes and untracked files so unrecorded dirty drift is detectable."""
    def git(*arguments) -> bytes:
        return subprocess.run(["git", "-C", worktree, *arguments], capture_output=True, check=True).stdout

    status = git("status", "--porcelain=v1", "-z", "--untracked-files=all")
    digest = hashlib.sha256()
    digest.update(status)
    digest.update(b"\0diff\0")
    digest.update(git("diff", "--binary", "--no-ext-diff", "--no-textconv", "HEAD"))
    for name in sorted(git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0")):
        if not name:
            continue
        path = Path(worktree) / os.fsdecode(name)
        digest.update(b"\0untracked\0" + name + b"\0")
        if path.is_symlink():
            digest.update(os.fsencode(os.readlink(path)))
        elif path.is_file():
            digest.update(path.read_bytes())
    return {"clean": status == b"", "digest": digest.hexdigest()}


def pid_alive(pid) -> bool:
    """Report whether a recorded process still exists."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def process_group_members(pgid) -> list[int] | None:
    """Live (non-zombie) members of a process group, or None when /proc cannot say."""
    if not isinstance(pgid, int) or pgid <= 0:
        return []
    proc = Path("/proc")
    if not (proc / "self" / "stat").is_file():
        return None
    members = []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # The command name may contain spaces or parentheses; fields resume after the last ')'.
        fields = stat[stat.rfind(")") + 2:].split()
        if len(fields) > 2 and fields[2] == str(pgid) and fields[0] not in ("Z", "X"):
            members.append(int(entry.name))
    return members


def group_alive(pgid) -> bool:
    """Whether anything that could still act remains in a launcher's process group.

    Without /proc the only probe is killpg(0), which also counts zombies; an
    unknown answer is treated as alive so cleanup is never claimed unproven.
    """
    members = process_group_members(pgid)
    if members is not None:
        return bool(members)
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def launcher_alive(pid) -> bool:
    """A recorded launcher is gone only when both its pid and its session's process group are gone."""
    return pid_alive(pid) or group_alive(pid)


def validation_problem(validation) -> str | None:
    """Return why validation evidence is insufficient: it must list each command run and its zero exit."""
    if not isinstance(validation, dict) or validation.get("passed") is not True:
        return "validation_not_passed"
    commands = validation.get("commands")
    if not isinstance(commands, list) or not commands:
        return "validation_commands_missing"
    for entry in commands:
        if not isinstance(entry, dict) or not isinstance(entry.get("command"), str) or not entry["command"].strip():
            return "validation_commands_missing"
        # bool is an int subclass: exit_code=False must not pass as 0.
        if type(entry.get("exit_code")) is not int or entry["exit_code"] != 0:
            return "validation_command_failed"
    return None


class Bridge:
    """One bounded reconcile-then-act pass over the durable ledger."""

    def __init__(self, config: dict, api, lock_fd: int | None, now=utcnow, revision=git_revision,
            alive=launcher_alive, group_alive=group_alive, fingerprint=worktree_fingerprint):
        self.config = config
        self.api = api
        self.lock_fd = lock_fd
        self.now = now
        self.revision = revision
        self.alive = alive
        self.group_alive = group_alive
        self.fingerprint = fingerprint
        self.state_dir = Path(config["state_dir"]).expanduser()
        self.ledger = Ledger(self.state_dir / "ledger.json")
        self.state = self.ledger.load()

    def save(self) -> None:
        """Persist the in-memory ledger."""
        self.ledger.save(self.state)

    def result(self, status: str, **fields) -> tuple[int, dict]:
        """Build the single stdout JSON object Paperclip's process adapter reads."""
        blocked = status in ("blocked", "halted")
        payload = {"status": status, "worker_id": self.config["worker_id"], **fields}
        return (EXIT_BLOCKED if blocked else EXIT_OK), payload

    # -- reconciliation -------------------------------------------------

    def halt(self, reason: str, **evidence) -> tuple[int, dict]:
        """Fail closed: record an ambiguity that stops all claiming until cleared."""
        self.state["halt"] = {"reason": reason, "at": iso(self.now()), **evidence}
        self.save()
        return self.result("halted", reason=reason, evidence=evidence)

    def check_registration(self) -> tuple[int, dict] | None:
        """Refuse to act unless NightCrew's registration matches the local allowlist."""
        identity = self.api.me()
        served = sorted(identity.get("served_repos") or [])
        configured = sorted(self.config["repositories"])
        if identity.get("worker_id") != self.config["worker_id"] or served != configured:
            return self.halt("registration_mismatch", registered_worker=identity.get("worker_id"),
                served_repos=served, configured_repos=configured)
        return None

    def reconcile(self) -> tuple[int, dict] | None:
        """Match the ledger against NightCrew's view of this worker's claims."""
        held = {str(job["id"]): job for job in self.api.held()}
        jobs = self.state["jobs"]
        for job_id, record in jobs.items():
            if record["state"] not in ACTIVE_STATES:
                continue
            if job_id not in held:
                # NightCrew no longer lists it as ours: never act on it again.
                reason = "claim no longer held in NightCrew"
                if record["state"] == "ready_for_review":
                    # A human or another tool moved it on; the bridge has no merge evidence to verify.
                    reason = "claim no longer held in NightCrew after ready_for_review; outcome not verified by bridge"
                record.update(state="lost", reason=reason, at=iso(self.now()))
                continue
            record["server_status"] = held[job_id]["status"]
            if record["state"] in ("launching", "running"):
                if self.alive(record.get("pid")):
                    # The lock can be dropped by a descendant that closed its fds; a
                    # surviving launcher group means the attempt may still be writing.
                    self.save()
                    return self.halt("launcher_still_alive", job_id=job_id, pid=record.get("pid"),
                        log=record.get("log_path"))
                if Path(record.get("receipt_path", "")).is_file():
                    # The exit code died with the old tick; the receipt alone must prove the phase.
                    self.classify(record, 0)
                    continue
                self.save()
                return self.halt("unexpected_process_death", job_id=job_id, provider=record.get("provider"),
                    pid=record.get("pid"), log=record.get("log_path"))
        unknown = [job for job_id, job in held.items() if job_id not in jobs]
        intent = self.state.get("intent")
        if unknown and intent and len(unknown) == 1:
            # The claim committed but its response was lost: adopt, never re-claim.
            self.state["intent"] = None
            self.adopt(unknown[0], source="reconciled_lost_claim_response")
            unknown = []
        if unknown:
            self.save()
            return self.halt("unknown_held_job", job_ids=[job["id"] for job in unknown])
        self.state["intent"] = None
        self.save()
        return None

    def adopt(self, job: dict, source: str) -> dict:
        """Record a freshly claimed job, rejecting anything this bridge must not run."""
        record = {"id": job["id"], "repo": job["repo"], "kind": job["kind"], "reference": job.get("reference"),
            "server_status": job.get("status", "claimed"), "claim_token": job.get("claim_token"),
            "state": "claimed", "attempts": 0, "source": source, "claimed_at": iso(self.now()),
            "phase": None, "revision": None, "provider": None, "handoffs": []}
        reason = None
        if job["repo"] not in self.config["repositories"]:
            reason = "repository_not_configured"
        elif job.get("contested"):
            reason = "contested_job_rejected"
        elif job["kind"] not in SUPPORTED_KINDS:
            reason = "unsupported_job_kind"
        elif job.get("worker_id") not in (None, self.config["worker_id"]):
            reason = "ownership_mismatch"
        if reason:
            # Hold without executing: a human decides, the bridge never guesses.
            record.update(state="blocked", reason=reason)
        self.state["jobs"][str(job["id"])] = record
        self.save()
        return record

    # -- provider availability ------------------------------------------

    def provider_ready(self, provider: str) -> bool:
        """A provider is eligible when declared, enabled and past any cooldown."""
        settings = self.config["providers"].get(provider)
        if not settings or settings.get("enabled") is False:
            return False
        until = parse_time(self.state["providers"].get(provider, {}).get("unavailable_until"))
        return until is None or until <= self.now()

    def next_retry(self, providers) -> str | None:
        """Earliest time any of the given providers comes back."""
        times = [parse_time(self.state["providers"].get(name, {}).get("unavailable_until")) for name in providers]
        times = [moment for moment in times if moment is not None]
        if not times:
            return None
        return iso(min(times))

    # -- acting ----------------------------------------------------------

    def tick(self) -> tuple[int, dict]:
        """Run exactly one bounded reconcile-and-act step."""
        stopped = self.check_registration()
        if stopped:
            return stopped
        if self.state.get("halt"):
            return self.result("halted", reason=self.state["halt"]["reason"], evidence=self.state["halt"])
        stopped = self.reconcile()
        if stopped:
            return stopped
        jobs = self.state["jobs"].values()
        for record in jobs:
            if record["state"] == "claimed":
                return self.dispatch(record, self.first_ready(record["repo"]))
        for record in jobs:
            if record["state"] == "waiting_provider":
                handoff = record.get("handoff")
                provider = record["provider"]
                if provider is None:
                    # Never started (adopted while starved): any configured provider may begin it.
                    provider = self.first_ready(record["repo"])
                if handoff:
                    provider = handoff["to_provider"]
                if provider is not None and self.provider_ready(provider):
                    return self.dispatch(record, provider, handoff=handoff)
        return self.claim_new()

    def first_ready(self, repo: str) -> str | None:
        """The first eligible provider in the repository's configured order."""
        for provider in self.config["repositories"][repo]["providers"]:
            if self.provider_ready(provider):
                return provider
        return None

    def claim_new(self) -> tuple[int, dict]:
        """Claim new work only when every served repository has an eligible provider."""
        active = [record for record in self.state["jobs"].values() if record["state"] in ACTIVE_STATES]
        waiting = [record["id"] for record in active if record["state"] == "waiting_provider"]
        if len(active) >= int(self.config.get("max_held_jobs", 3)):
            return self.result("idle", reason="max_held_jobs", waiting_jobs=waiting)
        starved = [repo for repo in self.config["repositories"] if self.first_ready(repo) is None]
        if starved:
            providers = {name for repo in starved for name in self.config["repositories"][repo]["providers"]}
            status = "providers_unavailable"
            if len(starved) == len(self.config["repositories"]):
                status = "all_providers_unavailable"
            return self.result(status, repositories=starved, next_retry_at=self.next_retry(providers),
                waiting_jobs=waiting)
        # Write the intent before the claim so a lost response is adopted, not repeated.
        self.state["intent"] = {"action": "claim", "at": iso(self.now())}
        self.save()
        job = self.api.claim()
        self.state["intent"] = None
        if job is None:
            self.save()
            return self.result("idle", reason="nothing_due", waiting_jobs=waiting)
        record = self.adopt(job, source="claim")
        if record["state"] == "blocked":
            return self.result("blocked", job_id=record["id"], reason=record["reason"])
        return self.dispatch(record, self.first_ready(record["repo"]))

    def dispatch(self, record: dict, provider: str | None, handoff: dict | None = None) -> tuple[int, dict]:
        """Launch the configured launcher for one held job and classify its outcome."""
        repo = self.config["repositories"][record["repo"]]
        if provider is None:
            record.update(state="waiting_provider", provider=record.get("provider"))
            self.save()
            return self.result("waiting_provider", job_id=record["id"],
                next_retry_at=self.next_retry(repo["providers"]))
        revision = self.revision(repo["worktree"])
        if record.get("revision") and revision != record["revision"]:
            record.update(state="blocked", reason="revision_changed_while_waiting",
                expected_revision=record["revision"], found_revision=revision)
            self.save()
            return self.result("blocked", job_id=record["id"], reason=record["reason"])
        checkpoint = record.get("checkpoint_digest")
        if checkpoint and self.fingerprint(repo["worktree"])["digest"] != checkpoint:
            # Same HEAD is not enough: uncommitted checkpoint work must be exactly what was left.
            record.update(state="blocked", reason="worktree_changed_while_waiting")
            self.save()
            return self.result("blocked", job_id=record["id"], reason=record["reason"])
        if handoff:
            refusal = self.handoff_refusal(record, handoff)
            if refusal:
                record.update(handoff=None, handoff_rejection={"reason": refusal, "at": iso(self.now())})
                self.save()
                return self.result("blocked", job_id=record["id"], reason=refusal)
        if record.get("server_status") == "claimed":
            self.api.status(record, "running", {"bridge": "started", "provider": provider})
            record["server_status"] = "running"
        record["attempts"] += 1
        receipts = self.state_dir / "receipts"
        logs = self.state_dir / "logs"
        receipts.mkdir(parents=True, exist_ok=True)
        logs.mkdir(parents=True, exist_ok=True)
        receipt_path = receipts / f"{record['id']}-{record['attempts']}.json"
        log_path = logs / f"{record['id']}-{record['attempts']}.log"
        receipt_path.unlink(missing_ok=True)
        phase = record.get("phase") or repo.get("phase", "implement")
        if handoff:
            record["handoffs"].append({**handoff, "executed_at": iso(self.now())})
            record["handoff"] = None
        # A fresh nonce per attempt binds the receipt to this launch, so a stale
        # receipt from an earlier attempt (or another ledger) can never prove it.
        nonce = secrets.token_hex(16)
        record.update(state="launching", provider=provider, revision=revision, phase=phase,
            receipt_path=str(receipt_path), log_path=str(log_path), exit_code=None, attempt_nonce=nonce,
            checkpoint_digest=None)
        self.save()
        fields = {"job_id": str(record["id"]), "repo": record["repo"], "reference": str(record.get("reference") or ""),
            "kind": record["kind"], "provider": provider, "worktree": repo["worktree"], "revision": revision,
            "phase": phase, "receipt_path": str(receipt_path), "resume": "1" if record["attempts"] > 1 else "0",
            "attempt": str(record["attempts"]), "attempt_nonce": nonce}
        argv = [TEMPLATE_FIELD.sub(lambda match: fields.get(match.group(1), match.group(0)), part)
            for part in repo["launch"][provider]]
        environment = {key: value for key, value in os.environ.items() if key != self.config.get("token_env")}
        environment.update({"NIGHTCREW_BRIDGE_RECEIPT": str(receipt_path), "NIGHTCREW_BRIDGE_JOB": str(record["id"]),
            "NIGHTCREW_BRIDGE_ATTEMPT": str(record["attempts"]), "NIGHTCREW_BRIDGE_ATTEMPT_NONCE": nonce,
            "NIGHTCREW_BRIDGE_REPO": record["repo"], "NIGHTCREW_BRIDGE_WORKTREE": repo["worktree"]})
        with log_path.open("ab") as log:
            process = subprocess.Popen(argv, cwd=repo["worktree"], stdout=log, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, env=environment, pass_fds=(self.lock_fd,), start_new_session=True)
            record.update(state="running", pid=process.pid, started_at=iso(self.now()))
            self.save()
            try:
                exit_code = process.wait(timeout=int(self.config.get("timeout_seconds", 3600)))
            except subprocess.TimeoutExpired:
                if not self.terminate(process):
                    # Releasing the lock now could let the next tick start beside a survivor.
                    record.update(state="blocked", reason="launcher_timeout_cleanup_unproven")
                    return self.halt("launcher_cleanup_unproven", job_id=record["id"], pgid=process.pid,
                        log=record["log_path"])
                record.update(state="blocked", reason="launcher_timeout", pid=None)
                self.save()
                return self.result("blocked", job_id=record["id"], reason="launcher_timeout")
        if not self.group_settled(process.pid, float(self.config.get("descendant_grace_seconds", 5))):
            # The launcher exited but left descendants behind in its group; they may still write.
            record.update(state="blocked", reason="launcher_descendants_alive", exit_code=exit_code)
            return self.halt("launcher_descendants_alive", job_id=record["id"], pgid=process.pid,
                log=record["log_path"])
        record["exit_code"] = exit_code
        return self.classify(record, exit_code)

    def group_settled(self, pgid: int, seconds: float) -> bool:
        """Wait up to `seconds` for a launcher's process group to have no live member."""
        deadline = time.monotonic() + seconds
        while self.group_alive(pgid):
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)
        return True

    def terminate(self, process) -> bool:
        """Signal the launcher's whole group; True only once no live member remains.

        The launcher returning is not enough: descendants that ignore SIGTERM
        stay in the group, so each signal waits for the group itself to empty.
        """
        grace = float(self.config.get("terminate_grace_seconds", 10))
        for sent in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(process.pid, sent)
            except (ProcessLookupError, PermissionError):
                pass
            deadline = time.monotonic() + grace
            while True:
                # Reap the launcher so its zombie never counts as a live member.
                process.poll()
                if not self.group_alive(process.pid):
                    return True
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.05)
        return False

    def classify(self, record: dict, exit_code: int) -> tuple[int, dict]:
        """Separate provider quota from task failure, and never infer done from exit 0."""
        receipt = None
        path = Path(record.get("receipt_path") or "")
        if path.is_file():
            try:
                receipt = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                receipt = None
        if not isinstance(receipt, dict):
            receipt = None
        record["pid"] = None
        provider = record["provider"]
        quota_exit = int(self.config["providers"][provider].get("quota_exit_code", DEFAULT_QUOTA_EXIT))
        if exit_code == quota_exit or (receipt and receipt.get("status") == "provider_unavailable"):
            return self.wait_for_provider(record, receipt)
        if exit_code != 0:
            evidence = {"bridge": "task_failed", "provider": provider, "exit_code": exit_code, "log": record["log_path"]}
            self.api.status(record, "failed", evidence)
            record.update(state="failed", reason="launcher_failed", exit_code=exit_code)
            self.save()
            return self.result("failed", job_id=record["id"], exit_code=exit_code)
        problem = self.receipt_problem(record, receipt)
        if problem:
            record.update(state="blocked", reason=problem)
            self.save()
            return self.result("blocked", job_id=record["id"], reason=problem)
        if receipt["phase"] == "ready_for_review":
            # Review is Gitea's gate: keep the claim, never mark the issue done here.
            record.update(state="ready_for_review", phase="ready_for_review", receipt=receipt)
            self.save()
            return self.result("ready_for_review", job_id=record["id"], revision=receipt["revision"])
        self.api.status(record, "done", {"bridge": "phase_done", "provider": provider, **receipt})
        record.update(state="done", phase="done", receipt=receipt)
        self.save()
        return self.result("done", job_id=record["id"], revision=receipt["revision"])

    def receipt_problem(self, record: dict, receipt: dict | None) -> str | None:
        """Return why an exit-0 receipt is insufficient, or None when it proves the phase."""
        if receipt is None:
            return "exit_zero_without_receipt"
        if str(receipt.get("job_id")) != str(record["id"]):
            return "receipt_job_mismatch"
        nonce = record.get("attempt_nonce")
        if str(receipt.get("attempt")) != str(record["attempts"]) or not nonce or receipt.get("attempt_nonce") != nonce:
            return "receipt_attempt_mismatch"
        repo = self.config["repositories"][record["repo"]]
        if receipt.get("repo") != record["repo"]:
            return "receipt_repository_mismatch"
        worktree = repo["worktree"]
        if os.path.realpath(str(receipt.get("worktree") or "")) != os.path.realpath(worktree):
            return "receipt_worktree_mismatch"
        if receipt.get("phase") not in RECEIPT_PHASES:
            return "receipt_phase_unrecognised"
        problem = validation_problem(receipt.get("validation"))
        if problem:
            return "receipt_" + problem
        if receipt.get("revision") != self.revision(worktree):
            return "receipt_revision_mismatch"
        if not self.fingerprint(worktree)["clean"]:
            # A phase is proven at a revision only if nothing unrecorded sits beside it.
            return "receipt_worktree_dirty"
        if receipt["phase"] == "done" and repo.get("done_supported") is not True:
            # PATCH done closes the Gitea issue; an AI-written phase alone must never do that.
            return "done_requires_audited_launcher"
        return None

    def wait_for_provider(self, record: dict, receipt: dict | None) -> tuple[int, dict]:
        """Persist a provider cooldown and keep the claim until reset or explicit handoff."""
        provider = record["provider"]
        retry_at = None
        if receipt:
            retry_at = parse_time(receipt.get("retry_at"))
        if retry_at is None:
            cooldown = int(self.config["providers"][provider].get("cooldown_seconds", 3600))
            retry_at = self.now() + dt.timedelta(seconds=cooldown)
        self.state["providers"][provider] = {"unavailable_until": iso(retry_at), "reason": "quota",
            "job_id": record["id"]}
        worktree = self.config["repositories"][record["repo"]]["worktree"]
        phase = record["phase"]
        if receipt and receipt.get("phase"):
            phase = receipt["phase"]
        fingerprint = self.fingerprint(worktree)
        record.update(state="waiting_provider", retry_at=iso(retry_at), phase=phase,
            revision=self.revision(worktree), checkpoint_log=record["log_path"],
            checkpoint_digest=fingerprint["digest"], checkpoint_clean=fingerprint["clean"])
        self.save()
        return self.result("waiting_provider", job_id=record["id"], provider=provider, next_retry_at=iso(retry_at))

    # -- explicit handoff -------------------------------------------------

    def handoff_refusal(self, record: dict, evidence: dict) -> str | None:
        """Return why a provider change is not allowed, or None when it is proven safe."""
        repo = self.config["repositories"][record["repo"]]
        target = evidence.get("to_provider")
        if record["state"] != "waiting_provider":
            return "job_not_waiting_provider"
        if repo.get("handoff_supported") is not True:
            return ("handoff_unsupported_by_launcher: " + record["repo"] + " launcher rejects implicit provider "
                "changes; resume with " + str(record["provider"]) + " after " + str(record.get("retry_at"))
                + " or configure an audited launcher with handoff_supported=true")
        if evidence.get("from_provider") != record["provider"] or target == record["provider"]:
            return "handoff_provider_mismatch"
        if target not in repo["providers"] or not self.provider_ready(target):
            return "handoff_target_not_eligible"
        if self.alive(record.get("pid")):
            return "handoff_old_process_alive"
        if os.path.realpath(evidence.get("worktree", "")) != os.path.realpath(repo["worktree"]):
            return "handoff_worktree_mismatch"
        if evidence.get("revision") != record.get("revision") or evidence.get("revision") != self.revision(repo["worktree"]):
            return "handoff_revision_mismatch"
        if evidence.get("phase") != record.get("phase"):
            return "handoff_phase_mismatch"
        if str(evidence.get("attempt")) != str(record.get("attempts")):
            return "handoff_attempt_mismatch"
        checkpoint = record.get("checkpoint_digest")
        if not checkpoint or evidence.get("worktree_digest") != checkpoint:
            return "handoff_worktree_state_mismatch"
        if self.fingerprint(repo["worktree"])["digest"] != checkpoint:
            # HEAD alone misses uncommitted edits made after the checkpoint was recorded.
            return "handoff_worktree_state_mismatch"
        if validation_problem(evidence.get("validation")):
            return "handoff_validation_not_recorded"
        return None

    def record_handoff(self, job_id: str, evidence: dict) -> tuple[int, dict]:
        """Validate and durably record an explicit, evidence-backed provider handoff."""
        record = self.state["jobs"].get(str(job_id))
        if record is None:
            return self.result("blocked", job_id=job_id, reason="handoff_unknown_job")
        refusal = self.handoff_refusal(record, evidence)
        if refusal:
            record["handoff_rejection"] = {"reason": refusal, "at": iso(self.now()), "evidence": evidence}
            self.save()
            return self.result("blocked", job_id=record["id"], reason=refusal)
        record.update(handoff={**evidence, "recorded_at": iso(self.now())}, handoff_rejection=None)
        self.save()
        return self.result("handoff_recorded", job_id=record["id"], to_provider=evidence["to_provider"])


def job_id_key(job: dict) -> tuple:
    """Order job ids numerically when possible so observation output is stable."""
    identifier = str(job.get("id"))
    if identifier.isdigit():
        return (0, int(identifier), identifier)
    return (1, 0, identifier)


def observe(config: dict, api, reason: str) -> tuple[int, dict]:
    """GET-only probe of identity and held jobs; never claims, reports status, launches or writes."""
    identity = api.me()
    held = api.held()
    served = sorted(identity.get("served_repos") or [])
    configured = sorted(config["repositories"])
    matches = identity.get("worker_id") == config["worker_id"] and served == configured
    # Read-only: a missing ledger reads as empty and is not created.
    ledger = Ledger(Path(config["state_dir"]).expanduser() / "ledger.json").load()
    known = ledger.get("jobs") or {}
    halt = ledger.get("halt")
    halt_reason = None
    if isinstance(halt, dict):
        halt_reason = halt.get("reason")
    # claim_token is a fence secret: only non-sensitive fields are echoed.
    held_jobs = [{"id": job.get("id"), "repo": job.get("repo"), "kind": job.get("kind"), "status": job.get("status"),
        "reference": job.get("reference"), "worker_id": job.get("worker_id"), "in_ledger": str(job.get("id")) in known}
        for job in sorted(held, key=job_id_key)]
    local_jobs = [{"id": record.get("id"), "state": record.get("state"), "provider": record.get("provider")}
        for record in sorted(known.values(), key=job_id_key) if record.get("state") in ACTIVE_STATES]
    payload = {"status": "observed", "mode": "observe", "observe_reason": reason, "worker_id": config["worker_id"],
        "dispatch_enabled": config.get("dispatch_enabled") is True,
        "registration": {"matches": matches, "registered_worker": identity.get("worker_id"),
            "served_repos": served, "configured_repos": configured},
        "held_jobs": held_jobs, "unknown_held_jobs": [job["id"] for job in held_jobs if not job["in_ledger"]],
        "ledger_active_jobs": local_jobs, "halt_reason": halt_reason}
    if matches:
        return EXIT_OK, payload
    return EXIT_BLOCKED, payload


def run(arguments, api=None, now=utcnow, revision=git_revision, alive=launcher_alive,
        group_alive=group_alive) -> tuple[int, dict]:
    """Load config, take the worker lock and run one command."""
    config = load_config(Path(arguments.config).expanduser())
    if arguments.command == "tick":
        reason = None
        if getattr(arguments, "observe", False):
            reason = "observe_flag"
        elif config.get("dispatch_enabled") is not True:
            # Live dispatch must be opted into explicitly; anything else only looks.
            reason = "dispatch_not_enabled"
        if reason:
            if api is None:
                api = Api(config["api_base"], load_token(config))
            return observe(config, api, reason)
    state_dir = Path(config["state_dir"]).expanduser()
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_fd = acquire_lock(state_dir / "bridge.lock")
    if lock_fd is None:
        # Another tick, or a descendant it launched, still owns this worker.
        return EXIT_OK, {"status": "busy", "worker_id": config["worker_id"]}
    try:
        if api is None:
            api = Api(config["api_base"], load_token(config))
        bridge = Bridge(config, api, lock_fd, now=now, revision=revision, alive=alive, group_alive=group_alive)
        if arguments.command == "handoff":
            evidence = json.loads(Path(arguments.evidence).read_text(encoding="utf-8"))
            evidence["to_provider"] = arguments.to
            return bridge.record_handoff(arguments.job, evidence)
        if arguments.command == "clear-halt":
            bridge.state["halt"] = None
            bridge.state.setdefault("cleared_halts", []).append({"at": iso(now()), "note": arguments.note})
            bridge.save()
            return bridge.result("halt_cleared")
        return bridge.tick()
    finally:
        os.close(lock_fd)


def main(argv=None) -> int:
    """CLI entry point; prints exactly one JSON object for Paperclip."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["tick", "handoff", "clear-halt"])
    parser.add_argument("--config", required=True)
    parser.add_argument("--job")
    parser.add_argument("--to")
    parser.add_argument("--evidence")
    parser.add_argument("--note", default="")
    parser.add_argument("--observe", action="store_true",
        help="GET-only probe: no claim, status change, launch or ledger write")
    arguments = parser.parse_args(argv)
    if arguments.command == "handoff" and not (arguments.job and arguments.to and arguments.evidence):
        parser.error("handoff requires --job, --to and --evidence")
    if arguments.observe and arguments.command != "tick":
        parser.error("--observe only applies to tick")
    try:
        code, payload = run(arguments)
    except (BridgeError, OSError, ValueError, KeyError, urllib.error.URLError, subprocess.CalledProcessError) as error:
        # Error text never includes the token: it is only held in a request header.
        code, payload = EXIT_ERROR, {"status": "error", "reason": type(error).__name__, "detail": str(error)[:300]}
    print(json.dumps(payload, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
