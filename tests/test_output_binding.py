"""Synthetic directory-redirection and transaction regressions; no live services."""
from __future__ import annotations

import os
import stat
from dataclasses import FrozenInstanceError

import pytest

from ctshowcase import output_binding as B
from ctshowcase.errors import ShowcaseError
from ctshowcase.fingerprint import WRITE_SCRATCH_PREFIX


def files(directory):
    return {p.name: (p.read_bytes(), stat.S_IMODE(p.stat().st_mode)) for p in directory.iterdir() if p.is_file()}


def fixture(tmp_path, *, existing=True, count=3):
    out, external = tmp_path / "out", tmp_path / "authored"
    out.mkdir()
    external.mkdir()
    outputs = []
    for index in range(count):
        name = f"chart-{index}.md"
        path = out / name
        if existing:
            path.write_bytes(f"Old {index}\r\n".encode())
            path.chmod(0o640 if os.name != "nt" else 0o666)
        (external / name).write_bytes(f"Authored {index}\r\n".encode())
        outputs.append((path, f"New {index}\n".encode()))
    (external / "unrelated.txt").write_bytes(b"Unrelated authored content")
    return out, external, outputs


def redirect(out, external):
    moved = out.with_name("moved-original")
    out.rename(moved)
    try:
        out.symlink_to(external, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        moved.rename(out)
        pytest.skip(f"directory symlinks unavailable: {exc}")
    return moved


def assert_clean(directory):
    assert not [p for p in directory.rglob("*") if p.name.startswith(WRITE_SCRATCH_PREFIX)]


@pytest.mark.parametrize("existing", [False, True])
def test_normal_writes_repeat_and_preserve_existing_modes(tmp_path, existing):
    out, external, outputs = fixture(tmp_path, existing=existing)
    protected = files(external)
    for _ in range(2):
        bindings = B.capture_output_bindings(path for path, _ in outputs)
        B.write_bound_outputs(outputs, bindings=bindings)
        assert {p.name: p.read_bytes() for p, _ in outputs} == {p.name: data for p, data in outputs}
        if existing and os.name != "nt":
            assert {stat.S_IMODE(p.stat().st_mode) for p, _ in outputs} == {0o640}
        assert files(external) == protected
        assert_clean(out)


def test_capture_is_immutable_and_never_creates_missing_parents(tmp_path):
    path = tmp_path / "missing" / "nested" / "chart.md"
    binding = B.capture_output_bindings([path])[path]
    assert binding.file_state is None
    assert binding.parents[-1] == (path.parent, None)
    assert not path.parent.exists()
    with pytest.raises(FrozenInstanceError):
        binding.absolute = tmp_path / "other"


def test_missing_parents_normal_success(tmp_path):
    paths = [tmp_path / "missing" / "nested" / f"chart-{i}.md" for i in range(3)]
    B.write_bound_outputs([(p, b"new") for p in paths], bindings=B.capture_output_bindings(paths))
    assert [p.read_bytes() for p in paths] == [b"new"] * 3
    assert_clean(tmp_path)


def test_subset_of_captured_paths_leaves_optional_output_unchanged(tmp_path):
    out, _, outputs = fixture(tmp_path)
    bindings = B.capture_output_bindings(p for p, _ in outputs)
    old = outputs[-1][0].read_bytes()
    B.write_bound_outputs(outputs[:-1], bindings=bindings)
    assert outputs[-1][0].read_bytes() == old
    assert_clean(out)


@pytest.mark.parametrize("existing", [False, True])
def test_ancestor_swap_after_capture_before_preparation(tmp_path, existing):
    out, external, outputs = fixture(tmp_path, existing=existing)
    before, protected = files(out), files(external)
    bindings = B.capture_output_bindings(p for p, _ in outputs)
    moved = redirect(out, external)
    with pytest.raises(ShowcaseError):
        B.write_bound_outputs(outputs, bindings=bindings)
    assert files(moved) == before
    assert files(external) == protected
    assert_clean(moved)


def test_real_directory_substitution_is_not_adopted(tmp_path):
    out, external, outputs = fixture(tmp_path, existing=False)
    bindings = B.capture_output_bindings(p for p, _ in outputs)
    moved = out.with_name("moved-original")
    out.rename(moved)
    out.mkdir()
    before = files(out)
    with pytest.raises(ShowcaseError):
        B.write_bound_outputs(outputs, bindings=bindings)
    assert files(out) == before == {}
    assert files(moved) == {}
    assert_clean(tmp_path)


@pytest.mark.skipif(os.name != "posix", reason="Windows guards intentionally prohibit acquired directory renames")
@pytest.mark.parametrize("when", ["before-first", "after-first", "after-last"])
@pytest.mark.parametrize("existing", [False, True])
def test_swaps_around_actual_replacements_roll_back_original_directory(tmp_path, monkeypatch, when, existing):
    out, external, outputs = fixture(tmp_path, existing=existing)
    before, protected = files(out), files(external)
    bindings = B.capture_output_bindings(p for p, _ in outputs)
    original = B._replace
    moved = None
    count = 0

    def replace(backend, source_dir, source, destination_dir, destination):
        nonlocal count, moved
        if source == "output":
            count += 1
            if when == "before-first" and count == 1:
                moved = redirect(out, external)
        original(backend, source_dir, source, destination_dir, destination)
        if source == "output" and ((when == "after-first" and count == 1)
                                    or (when == "after-last" and count == len(outputs))):
            moved = redirect(out, external)

    monkeypatch.setattr(B, "_replace", replace)
    with pytest.raises(ShowcaseError):
        B.write_bound_outputs(outputs, bindings=bindings)
    assert moved is not None
    assert files(moved) == before
    assert files(external) == protected
    assert_clean(moved)


def test_missing_parents_ancestor_swap_does_not_create_external_directories(tmp_path):
    parent = tmp_path / "original"
    parent.mkdir()
    external = tmp_path / "authored"
    external.mkdir()
    (external / "authored.txt").write_bytes(b"sentinel")
    path = parent / "missing" / "nested" / "chart.md"
    binding = B.capture_output_bindings([path])
    protected = files(external)
    moved = redirect(parent, external)
    with pytest.raises(ShowcaseError):
        B.write_bound_outputs([(path, b"new")], bindings=binding)
    assert not (external / "missing").exists()
    assert files(external) == protected
    assert list(moved.iterdir()) == []


@pytest.mark.parametrize("existing", [False, True])
def test_normal_commit_failure_restores_every_file(tmp_path, monkeypatch, existing):
    out, _, outputs = fixture(tmp_path, existing=existing)
    before = files(out)
    bindings = B.capture_output_bindings(p for p, _ in outputs)
    original = B._replace

    def replace(backend, source_dir, source, destination_dir, destination):
        if source == "output" and destination == outputs[1][0].name:
            raise OSError("synthetic second-replacement failure")
        original(backend, source_dir, source, destination_dir, destination)

    monkeypatch.setattr(B, "_replace", replace)
    with pytest.raises(OSError, match="synthetic second-replacement failure"):
        B.write_bound_outputs(outputs, bindings=bindings)
    assert files(out) == before
    assert_clean(out)


def test_obstructed_rollback_preserves_authored_leaf_and_original_backup(tmp_path, monkeypatch):
    out, _, outputs = fixture(tmp_path)
    before = files(out)
    bindings = B.capture_output_bindings(p for p, _ in outputs)
    original = B._replace

    def replace(backend, source_dir, source, destination_dir, destination):
        if source == "output" and destination == outputs[1][0].name:
            authored = out / "concurrent.md"
            authored.write_bytes(b"New concurrent authored content")
            authored.replace(outputs[0][0])
            raise OSError("synthetic failure with concurrent leaf")
        original(backend, source_dir, source, destination_dir, destination)

    monkeypatch.setattr(B, "_replace", replace)
    with pytest.raises(ShowcaseError, match="rollback incomplete; recovery retained"):
        B.write_bound_outputs(outputs, bindings=bindings)
    assert outputs[0][0].read_bytes() == b"New concurrent authored content"
    backups = list(out.glob(WRITE_SCRATCH_PREFIX + "*/original"))
    assert len(backups) == 1 and backups[0].read_bytes() == before[outputs[0][0].name][0]
    assert outputs[1][0].read_bytes() == before[outputs[1][0].name][0]


def test_failed_rollback_preserves_backup(tmp_path, monkeypatch):
    out, _, outputs = fixture(tmp_path)
    original_bytes = outputs[0][0].read_bytes()
    bindings = B.capture_output_bindings(p for p, _ in outputs)
    original = B._replace

    def replace(backend, source_dir, source, destination_dir, destination):
        if source == "original" or (source == "output" and destination == outputs[1][0].name):
            raise OSError("synthetic commit/rollback failure")
        original(backend, source_dir, source, destination_dir, destination)

    monkeypatch.setattr(B, "_replace", replace)
    with pytest.raises(ShowcaseError, match="rollback incomplete; recovery retained"):
        B.write_bound_outputs(outputs, bindings=bindings)
    backups = list(out.glob(WRITE_SCRATCH_PREFIX + "*/original"))
    assert len(backups) == 1 and backups[0].read_bytes() == original_bytes


def test_exception_immediately_after_successful_replace_is_rolled_back(tmp_path, monkeypatch):
    out, _, outputs = fixture(tmp_path)
    before = files(out)
    bindings = B.capture_output_bindings(p for p, _ in outputs)
    original = B._replace

    def replace(backend, source_dir, source, destination_dir, destination):
        original(backend, source_dir, source, destination_dir, destination)
        if source == "output":
            raise OSError("synthetic exception just after publication")

    monkeypatch.setattr(B, "_replace", replace)
    with pytest.raises(OSError, match="synthetic exception just after publication"):
        B.write_bound_outputs(outputs, bindings=bindings)
    assert files(out) == before
    assert_clean(out)


def test_failed_transaction_removes_empty_parents_it_created(tmp_path, monkeypatch):
    first = tmp_path / "new" / "nested" / "first.md"
    second = first.with_name("second.md")
    bindings = B.capture_output_bindings([first, second])
    original = B._replace

    def replace(backend, source_dir, source, destination_dir, destination):
        if source == "output" and destination == second.name:
            raise OSError("synthetic failure")
        original(backend, source_dir, source, destination_dir, destination)

    monkeypatch.setattr(B, "_replace", replace)
    with pytest.raises(OSError, match="synthetic failure"):
        B.write_bound_outputs([(first, b"first"), (second, b"second")], bindings=bindings)
    assert not (tmp_path / "new").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX scratch-entry substitution regression")
def test_cleanup_does_not_remove_substituted_authored_empty_directory(tmp_path, monkeypatch):
    out, _, outputs = fixture(tmp_path, count=1)
    bindings = B.capture_output_bindings(p for p, _ in outputs)
    remove = B._Posix.remove_directory
    retained = out / "retained-original-scratch"
    authored = []

    def substitute_then_remove(backend, directory):
        if directory.path.name.startswith(WRITE_SCRATCH_PREFIX):
            # Reproduce substitution immediately before the removal helper:
            # its fd still holds the original, now renamed, empty directory.
            directory.path.rename(retained)
            directory.path.mkdir()
            info = directory.path.lstat()
            authored.append((directory.path, info.st_dev, info.st_ino))
        return remove(backend, directory)

    monkeypatch.setattr(B._Posix, "remove_directory", substitute_then_remove)
    with pytest.raises(ShowcaseError, match="scratch cleanup incomplete"):
        B.write_bound_outputs(outputs, bindings=bindings)
    assert len(authored) == 1
    path, device, inode = authored[0]
    info = path.lstat()
    assert path.is_dir() and (info.st_dev, info.st_ino) == (device, inode)
    assert list(path.iterdir()) == []
    assert retained.is_dir() and list(retained.iterdir()) == []
    assert outputs[0][0].read_bytes() == outputs[0][1]


def test_private_and_append_options(tmp_path):
    first, queue = tmp_path / "private.md", tmp_path / "queue.jsonl"
    queue.write_bytes(b"old\n")
    bindings = B.capture_output_bindings([first, queue])
    B.write_bound_outputs([(first, b"private")], bindings=bindings,
                          append_output=(queue, b"new\n"), private=True)
    assert first.read_bytes() == b"private" and queue.read_bytes() == b"old\nnew\n"
    if os.name != "nt":
        assert stat.S_IMODE(first.stat().st_mode) == 0o600
    assert_clean(tmp_path)


def test_snapshot_mismatch_refuses_without_writing(tmp_path):
    out, _, outputs = fixture(tmp_path)
    before = files(out)
    bindings = B.capture_output_bindings(p for p, _ in outputs)
    with pytest.raises(ShowcaseError, match="README inputs changed"):
        B.write_bound_outputs(outputs, bindings=bindings, snapshots={outputs[0][0]: b"wrong"})
    assert files(out) == before
    assert_clean(out)


def test_existing_leaf_change_after_capture_is_not_adopted(tmp_path):
    out, _, outputs = fixture(tmp_path)
    bindings = B.capture_output_bindings(p for p, _ in outputs)
    outputs[0][0].write_bytes(b"New authored input")
    before = files(out)
    with pytest.raises(ShowcaseError):
        B.write_bound_outputs(outputs, bindings=bindings)
    assert files(out) == before
    assert_clean(out)


def test_uncaptured_or_duplicate_outputs_refused(tmp_path):
    first, other = tmp_path / "first.md", tmp_path / "other.md"
    bindings = B.capture_output_bindings([first])
    for outputs in ([(other, b"new")], [(first, b"one"), (first, b"two")]):
        with pytest.raises(ShowcaseError):
            B.write_bound_outputs(outputs, bindings=bindings)
    assert list(tmp_path.iterdir()) == []


def test_windows_protect_failure_closes_guard_even_if_delete_fails():
    from types import SimpleNamespace
    backend = object.__new__(B._Windows)
    closed = []
    backend.k = SimpleNamespace(CloseHandle=lambda handle: closed.append(handle))
    backend._relative = lambda *args, **kwargs: 71

    def fail_identity(_):
        raise OSError("synthetic identity failure")

    def fail_delete(_):
        raise OSError("synthetic guard deletion failure")

    backend._directory_identity = fail_identity
    backend._delete_handle = fail_delete
    with pytest.raises(OSError, match="synthetic guard deletion failure"):
        backend.protect_scratch(SimpleNamespace(handle=11))
    assert closed == [71]


def test_windows_unprotect_failure_still_closes_guard():
    from types import SimpleNamespace
    backend = object.__new__(B._Windows)
    closed = []
    backend.k = SimpleNamespace(CloseHandle=lambda handle: closed.append(handle))

    def fail_delete(_):
        raise OSError("synthetic guard deletion failure")

    backend._delete_handle = fail_delete
    with pytest.raises(OSError, match="synthetic guard deletion failure"):
        backend.unprotect_scratch(71)
    assert closed == [71]


def test_windows_native_mutations_use_handles_and_utf16_leaf_names():
    """Portable ABI contract check; this does not substitute for native Windows CI."""
    import ctypes as c
    from types import SimpleNamespace

    class Status(c.Structure):
        _fields_ = [("Status", c.c_void_p), ("Information", c.c_size_t)]

    class Rename(c.Structure):
        _fields_ = [("ReplaceIfExists", c.c_ubyte), ("RootDirectory", c.c_void_p),
                    ("FileNameLength", c.c_uint32), ("FileName", c.c_uint16 * 1)]

    class Basic(c.Structure):
        _fields_ = [("CreationTime", c.c_longlong), ("LastAccessTime", c.c_longlong),
                    ("LastWriteTime", c.c_longlong), ("ChangeTime", c.c_longlong),
                    ("Attributes", c.c_uint32)]

    class HandleOnly:
        def __init__(self, handle):
            self.handle = handle

        @property
        def path(self):
            raise AssertionError("native content mutation must not resolve a lexical path")

    calls, opened, closed, deleted = [], [], [], []
    backend = object.__new__(B._Windows)
    backend.c, backend.Status, backend.Rename, backend.Basic, backend.Tag = c, Status, Rename, Basic, object()
    backend.k = SimpleNamespace(CloseHandle=lambda handle: closed.append(handle))
    backend.msvcrt = SimpleNamespace(get_osfhandle=lambda fd: fd + 100)
    backend._info = lambda *args: SimpleNamespace(Attributes=0x21)  # readonly + archive

    def relative(parent, name, **kwargs):
        opened.append((parent.handle, name, kwargs))
        return 71

    def native_set(handle, status, pointer, length, kind):
        if kind == 10:
            value = c.cast(pointer, c.POINTER(Rename)).contents
            name = c.string_at(c.addressof(pointer._obj) + Rename.FileName.offset,
                               value.FileNameLength).decode("utf-16-le")
            assert length >= c.sizeof(Rename) + value.FileNameLength
            calls.append((kind, handle, value.RootDirectory, value.ReplaceIfExists, name))
        else:
            value = c.cast(pointer, c.POINTER(Basic)).contents
            calls.append((kind, handle, value.Attributes, value.CreationTime, value.LastAccessTime,
                          value.LastWriteTime, value.ChangeTime))
        return 0

    backend._relative = relative
    backend._delete_handle = lambda handle: deleted.append(handle)
    backend.n = SimpleNamespace(NtSetInformationFile=native_set)
    source, target = HandleOnly(11), HandleOnly(22)
    backend.replace(source, "output", target, "chart-雪-🧭.md")
    backend.chmod(target, "ignored", 5, 0o600)
    backend.chmod(target, "ignored", 5, 0o400)
    backend.unlink(target, "chart.md")
    assert calls == [(10, 71, 22, 1, "chart-雪-🧭.md"),
                     (4, 105, 0x20, 0, 0, 0, 0), (4, 105, 0x21, 0, 0, 0, 0)]
    assert opened == [(11, "output", {"access": 0x80 | 0x10000}),
                      (22, "chart.md", {"access": 0x80 | 0x10000})]
    assert deleted == [71] and closed == [71, 71]


@pytest.mark.skipif(os.name != "nt", reason="native Windows DOS-device alias contract")
def test_windows_root_alias_rebind_cannot_redirect_commit_or_cleanup(tmp_path, monkeypatch):
    import ctypes as c
    from ctypes import wintypes as w
    from pathlib import Path

    out, external, outputs = fixture(tmp_path)
    before, protected = files(out), files(external)
    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.DefineDosDeviceW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR]
    kernel.DefineDosDeviceW.restype = w.BOOL
    kernel.QueryDosDeviceW.argtypes = [w.LPCWSTR, w.LPWSTR, w.DWORD]
    kernel.QueryDosDeviceW.restype = w.DWORD
    drive = None
    for letter in reversed("PQRSTUVWXYZ"):
        buffer = c.create_unicode_buffer(32768)
        if not kernel.QueryDosDeviceW(letter + ":", buffer, len(buffer)) and c.get_last_error() == 2:
            drive = letter + ":"
            break
    if drive is None:
        pytest.skip("no unused temporary drive alias")
    original_target = "\\??\\" + str(out)
    external_target = "\\??\\" + str(external)
    active = []

    def define(target):
        if not kernel.DefineDosDeviceW(0x1 | 0x8, drive, target):
            raise c.WinError(c.get_last_error())
        active.append(target)

    try:
        try:
            define(original_target)
        except OSError as exc:
            pytest.skip(f"temporary DOS-device alias unavailable: {exc}")
        aliased = [(Path(drive + "\\") / path.name, data) for path, data in outputs]
        bindings = B.capture_output_bindings(path for path, _ in aliased)
        replace = B._replace
        rebound = False

        def rebind_then_replace(backend, source_dir, source, destination_dir, destination):
            nonlocal rebound
            if source == "output" and not rebound:
                define(external_target)  # Push a new mapping without moving any guarded directory.
                rebound = True
            replace(backend, source_dir, source, destination_dir, destination)

        monkeypatch.setattr(B, "_replace", rebind_then_replace)
        with pytest.raises(ShowcaseError):
            B.write_bound_outputs(aliased, bindings=bindings)
        assert rebound
        assert files(out) == before and files(external) == protected
        assert_clean(out)
        assert_clean(external)
    finally:
        for target in reversed(active):
            # Exact-match removal touches only aliases this test established.
            if not kernel.DefineDosDeviceW(0x1 | 0x2 | 0x4 | 0x8, drive, target):
                raise c.WinError(c.get_last_error())


@pytest.mark.skipif(os.name != "nt", reason="native Windows directory-handle contract")
def test_windows_guards_prevent_acquired_directory_rename(tmp_path, monkeypatch):
    out, _, outputs = fixture(tmp_path)
    original = B._replace
    attempted = []

    def replace(backend, source_dir, source, destination_dir, destination):
        if source == "output":
            with pytest.raises(OSError):
                out.rename(out.with_name("must-not-move"))
            attempted.append(True)
        original(backend, source_dir, source, destination_dir, destination)

    monkeypatch.setattr(B, "_replace", replace)
    B.write_bound_outputs(outputs, bindings=B.capture_output_bindings(p for p, _ in outputs))
    assert attempted and [p.read_bytes() for p, _ in outputs] == [data for _, data in outputs]
    assert_clean(out)
