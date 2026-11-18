#!/usr/bin/env python3
"""Helpers for the composite Action (action.yml). Standard library only; acts on the current checkout.

  action_prepare.py foreign OWNER/REPO   print "true" when docs/images/.showcase.json provably came from another
                                         repository (a template's sidecar, or another recorded repository id;
                                         $GITHUB_REPOSITORY_ID), and then remove the copied icon (assets/icon.png
                                         whose sha256 is the one that sidecar recorded). A sidecar that only names
                                         another slug (a rename or transfer) prints "false" and keeps every file.
  action_prepare.py foreign OWNER/REPO NAME  check a canonical banner or card without removing the icon
  action_prepare.py staged             report whether local output still carries a staged proposal
  action_prepare.py staged-index       check staged sidecar blobs before a grouped Git commit
  action_prepare.py commit-index MODE INDEX SNAPSHOT REF MESSAGE [PATH...]  check an index copy and commit its tree
  action_prepare.py drop NAME            remove docs/images/NAME and its sidecar record (the sidecar too when empty)
  action_prepare.py summary META_JSON    append the describe and topics proposals to $GITHUB_STEP_SUMMARY
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryFile

# Keep direct and runpy entry points equivalent when the caller's CWD is a target checkout.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ctshowcase.fingerprint import ART_NAMES, output_records, read_sidecar, replace_bytes, sidecar_lock  # noqa: E402

IMAGES = Path("docs/images")
SIDECAR = IMAGES / ".showcase.json"
TEMPLATE_REPO = "CompleteTech-LLC/completetech-repo-template"  # intake.TEMPLATE_REPO, the `new --template` default
COMMIT_HOOKS = ("pre-commit", "prepare-commit-msg", "commit-msg", "post-commit")


def _sidecar() -> dict:
    return read_sidecar(IMAGES)


def _recorded_ids(data: dict) -> set[str]:
    """Repository IDs attached to the canonical banner and card artifacts."""
    return {str(record["repository_id"]) for name, record in output_records(data).items()
            if name in ART_NAMES and isinstance(record, dict) and not record.get("exempt")
            and record.get("repository_id") is not None}


def foreign(full_name: str, artifact: str | None = None) -> bool:
    """True only when the art provably came from another repository; then a copied icon is removed (decision 12).

    Proof is a template's sidecar (its recorded type is `template`, or it names the template repository) or a recorded
    repository id other than $GITHUB_REPOSITORY_ID. A sidecar that only names another slug is this repository's own
    art after a rename, a transfer or an org rename (the slug is not an identity): nothing is removed and the
    fingerprint, which changed with the slug, regenerates it. A template repository is never foreign to itself."""
    data = _sidecar()
    if os.environ.get("SHOWCASE_IS_TEMPLATE") == "true":
        return False
    rid = (os.environ.get("GITHUB_REPOSITORY_ID") or "").strip()
    if artifact is not None:
        record = output_records(data).get(artifact)
        if rid and isinstance(record, dict) and not record.get("exempt"):
            artifact_id = record.get("repository_id")
            if artifact_id is not None:
                return str(artifact_id) != rid

    inp = data.get("inputs") or {}
    if not isinstance(inp, dict) or not inp:
        return False
    named = f"{inp.get('owner')}/{inp.get('repo')}"
    ids = _recorded_ids(data)
    if rid and ids and ids == {rid}:
        return False  # the same repository under another name
    if named.lower() == full_name.lower():
        return False
    template = inp.get("type") == "template" or named.lower() == TEMPLATE_REPO.lower()
    other_id = bool(rid and ids and rid not in ids)
    if artifact is not None:
        return template or other_id
    icon = Path("assets/icon.png")
    copied = icon.is_file() and inp.get("icon_sha256") and \
        hashlib.sha256(icon.read_bytes()).hexdigest() == inp["icon_sha256"]
    if not (template or other_id):
        print(f"::notice title=CompleteTech Showcase::docs/images/.showcase.json names {named}, not {full_name} (a rename "
              "or transfer?); kept the art" + (" and assets/icon.png" if copied else "") + ", which regenerate under "
              "this name", file=sys.stderr)
        return False
    if copied:
        icon.unlink()  # another repository's icon must never stand for this one (decision 12)
        print(f"::notice title=CompleteTech Showcase::removed the icon copied from {named}", file=sys.stderr)
    return True



def _has_staged_provenance(data) -> bool:
    outputs = data.get("outputs") if isinstance(data, dict) else None
    if not isinstance(outputs, dict):
        return True  # unreadable provenance cannot authorize publication
    return any(not isinstance(record, dict) or "staged_description" in record for record in outputs.values())


def has_staged_outputs() -> bool:
    # The grouped commit includes nested art and the two root Markdown files.
    candidates = {SIDECAR, Path(SIDECAR.name), *IMAGES.rglob(SIDECAR.name)}
    return any(_has_staged_provenance(read_sidecar(path.parent)) for path in candidates
               if path.exists() or path.is_symlink())


def has_staged_index(*, allow_icon_removal: bool = False, snapshot: str | None = None, parent: str | None = None) -> bool:
    """Check the exact index and prevent grouped commits from including unrelated files."""
    env = {**os.environ, "GIT_INDEX_FILE": snapshot} if snapshot else None
    baseline = [parent] if parent else []
    changes = subprocess.run(["git", "diff", "--cached", "--name-status", "--no-renames",
                              "--ignore-submodules=none", "-z", *baseline],
                             check=True, capture_output=True, timeout=30, env=env)
    columns = changes.stdout.split(b"\0")
    for status, path in zip(columns[::2], columns[1::2]):
        if path.startswith(b"docs/images/") or path in (b"docs/images", b"README.md", b"CONTRIBUTING.md"):
            continue
        if allow_icon_removal and status == b"D" and path == b"assets/icon.png":
            continue
        return True  # the bare git commit would include these pre-existing staged changes
    result = subprocess.run(["git", "ls-files", "--stage", "-z", "--", IMAGES.as_posix(), SIDECAR.name],
                            check=True, capture_output=True, timeout=30, env=env)
    for item in result.stdout.split(b"\0"):
        if not item:
            continue
        stat_info, path = item.split(b"\t", 1)
        if path.rsplit(b"/", 1)[-1] != os.fsencode(SIDECAR.name):
            continue
        _, blob, stage = stat_info.split()
        if stage != b"0":
            return True
        stored = subprocess.run(["git", "cat-file", "blob", blob.decode("ascii")],
                                check=True, capture_output=True, timeout=30)
        try:
            data = json.loads(stored.stdout)
        except ValueError:
            return True
        if _has_staged_provenance(data):
            return True
    return False


def _index_contents(index: Path) -> bytes | None:
    try:
        return index.read_bytes()
    except FileNotFoundError:
        return None


def _head_ref() -> str:
    result = subprocess.run(["git", "symbolic-ref", "--quiet", "--no-recurse", "HEAD"],
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 1:
        return "HEAD"
    result.check_returncode()
    return result.stdout.strip()


def _ref_oid(ref: str) -> str:
    result = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
                            capture_output=True, text=True, timeout=30)
    if result.returncode not in (0, 1):
        result.check_returncode()
    return result.stdout.strip()


def _git_operation_in_progress(git_dir: Path) -> bool:
    # A generated one-parent commit cannot participate in a caller's Git operation.
    return any((git_dir / name).exists() for name in (
        "MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-apply", "rebase-merge", "sequencer",
    ))


def _has_commit_hooks() -> bool:
    # Porcelain hooks may modify the candidate or enforce local policy.
    hook_path = subprocess.check_output(["git", "rev-parse", "--git-path", "hooks"], timeout=30)
    hooks = Path(os.fsdecode(hook_path.removesuffix(b"\n").removesuffix(b"\r")))
    if any(os.access(hooks / name, os.X_OK) for name in COMMIT_HOOKS):
        return True
    # Git versions with named config hooks can run commands outside core.hooksPath.
    config = subprocess.run(["git", "config", "--null", "--get-regexp", r"^hook\..+\.event$"],
                            capture_output=True, timeout=30)
    if config.returncode not in (0, 1):
        config.check_returncode()
    events = {record.partition(b"\n")[2] for record in config.stdout.split(b"\0")}
    return any(name.encode("ascii") in events for name in COMMIT_HOOKS)


def _exit_for_signal(signum, _frame):
    raise SystemExit(128 + signum)


def _stop_ref_update(transaction: subprocess.Popen) -> None:
    if transaction.poll() is None:
        transaction.terminate()
        try:
            transaction.wait(timeout=5)
        except subprocess.TimeoutExpired:
            transaction.kill()
            transaction.wait()


def _update_head(ref: str, parent: str, commit: str, subject: str,
                 index: Path, snapshot: Path, recover_index: Callable[[subprocess.Popen], None]) -> bool:
    """Hold Git's HEAD lock from the symbolic-ref check through index installation."""
    command = ["git", "update-ref", "-m", f"commit: {subject}", "--stdin"]
    # A dereferencing update of HEAD locks both HEAD and its current branch.
    option = "option no-deref\n" if ref == "HEAD" else ""
    # Git's stdin protocol needs LF even on Windows, where text pipes translate newlines.
    with (
        TemporaryFile(mode="w+t", encoding="utf-8", errors="replace") as errors,
        ThreadPoolExecutor(max_workers=1) as reader,
        subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors) as transaction,
    ):
        try:
            transaction.stdin.write(f"{option}update HEAD {commit} {parent}\nprepare\n".encode("ascii"))
            transaction.stdin.flush()
            prepared = reader.submit(transaction.stdout.readline).result(timeout=30)
            if prepared.rstrip(b"\r\n") != b"prepare: ok":
                transaction.communicate(timeout=30)
                if _head_ref() != ref or _ref_oid("HEAD") != parent:
                    return False
                errors.seek(0)
                raise RuntimeError(f"Could not prepare the Git ref update: {errors.read().strip()}")
            if _head_ref() != ref:
                transaction.communicate(b"abort\n", timeout=30)
                return False
            # Keep index.lock present while installing the checked index. If
            # Git fails to commit, restore the former index under the same lock.
            try:
                os.replace(snapshot, index)
                transaction.communicate(b"commit\n", timeout=30)
                if transaction.returncode:
                    errors.seek(0)
                    raise RuntimeError(f"Could not commit the Git ref update: {errors.read().strip()}")
            except BaseException:
                recover_index(transaction)
                raise
            return True
        finally:
            _stop_ref_update(transaction)


def prepare_commit_index(index: Path, snapshot: Path, ref: str, message: str, paths: list[str], *,
                         allow_icon_removal: bool = False) -> str:
    """Commit the checked tree against its checked parent, then install the successful index."""
    env = {**os.environ, "GIT_INDEX_FILE": str(snapshot)}
    git_dir = Path(subprocess.check_output(["git", "rev-parse", "--absolute-git-dir"],
                                           text=True, timeout=30).rstrip("\n"))
    with sidecar_lock(SIDECAR):
        if _git_operation_in_progress(git_dir):
            return "busy"
        parent = subprocess.check_output(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
                                         text=True, timeout=30).strip()
        original = _index_contents(index)
        if original is None:
            snapshot.unlink()
            subprocess.run(["git", "read-tree", "--empty"], check=True, timeout=30, env=env)
        else:
            snapshot.write_bytes(original)
        staged = subprocess.check_output(["git", "diff", "--cached", "--name-only", "--no-renames",
                                          "--ignore-submodules=none", "-z", parent],
                                         timeout=30, env=env)
        staged_tree = subprocess.check_output(["git", "write-tree"], text=True, timeout=30, env=env).strip() \
            if staged else None
        if paths:
            subprocess.run(["git", "add", "--", *paths], check=True, timeout=30, env=env)
        if allow_icon_removal:
            subprocess.run(["git", "rm", "-q", "--cached", "--", "assets/icon.png"], check=True, timeout=30, env=env)
        if has_staged_index(allow_icon_removal=allow_icon_removal, snapshot=str(snapshot), parent=parent) \
                or has_staged_outputs():
            return "blocked"
        tree = subprocess.check_output(["git", "write-tree"], text=True, timeout=30, env=env).strip()
        if staged_tree and staged_tree != tree:
            restaged = subprocess.check_output(["git", "diff", "--name-only", "--no-renames",
                                                 "--ignore-submodules=none", "-z", staged_tree, tree],
                                               timeout=30, env=env)
            if set(staged.rstrip(b"\0").split(b"\0")).intersection(restaged.rstrip(b"\0").split(b"\0")):
                return "blocked"
        parent_tree = subprocess.check_output(["git", "rev-parse", f"{parent}^{{tree}}"],
                                             text=True, timeout=30).strip()
    if tree == parent_tree:
        return "unchanged"

    # Take the same lock as Git index writers and compare the original
    # bytes before installing the candidate. Keep it through ref update.
    lock = index.with_name(index.name + ".lock")
    try:
        lock.touch(mode=0o600, exist_ok=False)
    except FileExistsError:
        return "changed"
    release_lock = True
    try:
        if _head_ref() != ref or _index_contents(index) != original:
            return "changed"
        if _git_operation_in_progress(git_dir):
            return "busy"
        if _has_commit_hooks():
            return "hooks"
        original_mode = stat.S_IMODE(index.stat().st_mode) if original is not None else None
        sign = subprocess.check_output(["git", "config", "--type=bool", "--default=false", "--get", "commit.gpgSign"],
                                       text=True, timeout=30).strip()
        command = ["git", "commit-tree", tree, "-p", parent, "-m", message]
        if sign == "true":
            command.append("-S")
        commit = subprocess.check_output(command, text=True, timeout=30).strip()
        subject = message.split("\n", 1)[0]
        # Retain the original bytes in the lock file for recovery after an interrupted process.
        if original is not None and original_mode is not None:
            lock.write_bytes(original)
            lock.chmod(original_mode)
            snapshot.chmod(original_mode)

        def recover_index(transaction: subprocess.Popen) -> None:
            nonlocal release_lock
            # Consuming the lock releases it. If the outcome cannot be verified
            # or restoration fails, preserve it for recovery.
            release_lock = False
            try:
                _stop_ref_update(transaction)
                if snapshot.exists() or _ref_oid(ref) == commit:
                    release_lock = True
                elif original is None:
                    index.unlink()
                    release_lock = True
                else:
                    os.replace(lock, index)
            except (OSError, subprocess.SubprocessError) as error:
                raise RuntimeError(f"Could not recover the Git index. Its recovery lock remains at {lock}") from error

        return commit if _update_head(ref, parent, commit, subject, index, snapshot, recover_index) else "changed"
    finally:
        if release_lock:
            lock.unlink(missing_ok=True)


def drop(name: str) -> None:
    with sidecar_lock(SIDECAR):
        p = IMAGES / name
        if p.is_file():
            p.unlink()
        data = _sidecar()
        if not data:
            return
        outs = dict(output_records(data))
        outs.pop(name, None)
        if outs:
            data["outputs"] = outs
            replace_bytes(SIDECAR, (json.dumps(data, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
        else:
            SIDECAR.unlink()


def summary(meta: str) -> None:
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    script = Path(__file__).resolve().parent / "showcase.py"
    lines = ["## CompleteTech Showcase: proposals", "",
             "The Action never edits the About box. Apply these by hand (or through the estate orchestrator).", ""]
    for cmd in ("describe", "topics"):
        p = subprocess.run([sys.executable, str(script), "--meta", meta, "--repo-dir", ".", cmd, "--gh"] if cmd == "topics"
                           else [sys.executable, str(script), "--meta", meta, "--repo-dir", ".", cmd],
                           capture_output=True, text=True, encoding="utf-8")
        try:
            r = json.loads(p.stdout)
        except ValueError:
            lines += [f"- `{cmd}`: no result ({p.stderr.strip()[:200]})"]
            continue
        if cmd == "describe":
            if r.get("action") == "keep":
                lines.append("- **Description:** passes the standard.")
            elif r.get("action") == "edit":
                lines.append(f"- **Description:** suggested edit: `{r.get('proposed') or r.get('text')}`")
            else:
                tpl = r.get("template") or ""
                lines.append("- **Description:** needs a new sentence" + (f" (template: `{tpl}`)" if tpl else "") + ".")
        else:
            if r.get("result") == "pass":
                lines.append("- **Topics:** match the standard.")
            else:
                lines.append(f"- **Topics:** proposed `{' '.join(r.get('proposed') or [])}`")
                if r.get("gh"):
                    lines += ["", "```bash", r["gh"], "```"]
    text = "\n".join(lines) + "\n"
    if target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(text)
    else:
        reconfigure = getattr(sys.stdout, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors=sys.stdout.errors)
        sys.stdout.write(text)


if __name__ == "__main__":
    if sys.argv[1:] == ["staged"]:
        print("true" if has_staged_outputs() else "false")
        sys.exit(0)
    if len(sys.argv) >= 7 and sys.argv[1] == "commit-index" and sys.argv[2] in ("keep-icon", "icon-removal"):
        signal.signal(signal.SIGTERM, _exit_for_signal)
        result = prepare_commit_index(Path(sys.argv[3]), Path(sys.argv[4]), sys.argv[5], sys.argv[6], sys.argv[7:],
                                      allow_icon_removal=sys.argv[2] == "icon-removal")
        print(result)
        sys.exit(0)
    if sys.argv[1:] in (["staged-index"], ["staged-index", "icon-removal"]):
        print("true" if has_staged_index(allow_icon_removal=len(sys.argv) == 3) else "false")
        sys.exit(0)
    if not (len(sys.argv) == 3 and sys.argv[1] in ("foreign", "drop", "summary")
            or len(sys.argv) == 4 and sys.argv[1] == "foreign" and sys.argv[3] in ART_NAMES):
        sys.exit(__doc__)
    if sys.argv[1] == "foreign":
        print("true" if foreign(*sys.argv[2:]) else "false")
    elif sys.argv[1] == "drop":
        drop(sys.argv[2])
    else:
        summary(sys.argv[2])
