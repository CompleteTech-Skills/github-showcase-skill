"""Bind an opt-in output transaction to checked directory objects.

This protects against directory redirection and rolls back ordinary commit failures.
It is not a multi-file atomic filesystem primitive or a compare-and-swap protocol
against arbitrary concurrent writers of the individual leaf files.
"""
from __future__ import annotations

import errno
import os
import secrets
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

from .errors import CHECK_FAILED, ShowcaseError
from .fingerprint import WRITE_SCRATCH_PREFIX

FileState = tuple[int, ...]
DirectoryIdentity = tuple[int, int]


def _changed(detail="output changed during generation"):
    return ShowcaseError(detail, log="formatter-source-changed", code=CHECK_FAILED)


def _invalid(detail):
    return ShowcaseError(detail, log="formatter-output")


def _state(info) -> FileState:
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or getattr(info, "st_file_attributes", 0) & 0x400):
        raise _invalid("bound outputs must be unlinked regular files")
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)


def _identity(info) -> DirectoryIdentity:
    if (not stat.S_ISDIR(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & 0x400):
        raise _invalid("bound output ancestors must be real directories")
    return info.st_dev, info.st_ino


@dataclass(frozen=True)
class OutputBinding:
    absolute: Path
    file_state: FileState | None
    parents: tuple[tuple[Path, DirectoryIdentity | None], ...]


@dataclass
class _Directory:
    path: Path
    handle: int
    identity: DirectoryIdentity
    parent: _Directory | None = None
    created: bool = False
    closed: bool = False


class _Posix:
    def __init__(self):
        if (not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY")
                or not {os.open, os.mkdir, os.stat, os.unlink, os.rmdir, os.rename}.issubset(os.supports_dir_fd)):
            raise _invalid("this platform cannot safely bind output directories")

    def directory(self, path, parent=None, *, create=False):
        name = path.name if parent else os.fspath(path)
        kwargs = {"dir_fd": parent.handle} if parent else {}
        if create:
            os.mkdir(name, mode=0o700, **kwargs)
        handle = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, **kwargs)
        try:
            return _Directory(path, handle, _identity(os.fstat(handle)), parent, create)
        except BaseException:
            os.close(handle)
            raise

    def file_state(self, directory, name):
        try:
            return _state(os.stat(name, dir_fd=directory.handle, follow_symlinks=False))
        except FileNotFoundError:
            return None

    check_directory = directory

    def open_file(self, directory, name, *, create=False):
        flags = os.O_RDWR | os.O_NOFOLLOW
        if create:
            flags |= os.O_CREAT | os.O_EXCL
        return os.open(name, flags, 0o666, dir_fd=directory.handle)

    def chmod(self, directory, name, handle, mode):
        os.fchmod(handle, mode)

    def replace(self, source_dir, source, destination_dir, destination):
        os.replace(source, destination, src_dir_fd=source_dir.handle, dst_dir_fd=destination_dir.handle)

    def unlink(self, directory, name):
        os.unlink(name, dir_fd=directory.handle)

    def remove_directory(self, directory):
        # The parent handle protects ancestor traversal, not this final entry.
        # Refuse an already substituted entry. This check/rmdir pair is not a
        # conditional atomic removal against arbitrary concurrent leaf writers.
        info = os.stat(directory.path.name, dir_fd=directory.parent.handle, follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != directory.identity:
            raise OSError(errno.ESTALE, "bound directory changed; refusing to remove replacement")
        os.rmdir(directory.path.name, dir_fd=directory.parent.handle)

    def close(self, directory):
        if not directory.closed:
            os.close(directory.handle)
            directory.closed = True

    def protect_scratch(self, directory):
        return None

    def unprotect_scratch(self, handle):
        pass


class _Windows:
    """Root guards and native handle-relative operations after root acquisition.

    Share masks exclude deletion, so acquired directory names cannot be moved.
    Attribute-only access bypasses share masks: therefore an empty directory is
    NOT considered stable solely because of its guard. Scratch is created relative to its
    parent handle, then receives a held, undeletable sentinel through that handle.
    The held child chain keeps the publication directories nonempty, which
    prevents setting a directory reparse point. Content mutations never resolve
    the DOS/UNC spelling again, including when a root alias itself is rebound.
    """
    def __init__(self):
        import ctypes as c
        from ctypes import wintypes as w
        import msvcrt
        self.c, self.w, self.msvcrt = c, w, msvcrt
        self.k = c.WinDLL("kernel32", use_last_error=True)
        self.n = c.WinDLL("ntdll")

        class Unicode(c.Structure):
            _fields_ = [("Length", w.USHORT), ("MaximumLength", w.USHORT), ("Buffer", w.LPWSTR)]

        class Attributes(c.Structure):
            _fields_ = [("Length", w.ULONG), ("RootDirectory", w.HANDLE),
                        ("ObjectName", c.POINTER(Unicode)), ("Attributes", w.ULONG),
                        ("SecurityDescriptor", w.LPVOID), ("SecurityQualityOfService", w.LPVOID)]

        class Status(c.Structure):
            _fields_ = [("Status", c.c_void_p), ("Information", c.c_size_t)]

        class FileId(c.Structure):
            _fields_ = [("VolumeSerialNumber", c.c_ulonglong), ("Identifier", c.c_ubyte * 16)]

        class Tag(c.Structure):
            _fields_ = [("Attributes", w.DWORD), ("Tag", w.DWORD)]

        class Rename(c.Structure):
            _fields_ = [("ReplaceIfExists", c.c_ubyte), ("RootDirectory", w.HANDLE),
                        ("FileNameLength", w.ULONG), ("FileName", w.WCHAR * 1)]

        class Basic(c.Structure):
            _fields_ = [("CreationTime", c.c_longlong), ("LastAccessTime", c.c_longlong),
                        ("LastWriteTime", c.c_longlong), ("ChangeTime", c.c_longlong),
                        ("Attributes", w.ULONG)]

        self.Unicode, self.Attributes, self.Status = Unicode, Attributes, Status
        self.FileId, self.Tag, self.Rename, self.Basic = FileId, Tag, Rename, Basic
        self.k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID,
                                       w.DWORD, w.DWORD, w.HANDLE]
        self.k.CreateFileW.restype = w.HANDLE
        self.k.CloseHandle.argtypes = [w.HANDLE]
        self.k.CloseHandle.restype = w.BOOL
        self.k.GetFileInformationByHandleEx.argtypes = [w.HANDLE, c.c_int, w.LPVOID, w.DWORD]
        self.k.GetFileInformationByHandleEx.restype = w.BOOL
        self.k.SetFileInformationByHandle.argtypes = [w.HANDLE, c.c_int, w.LPVOID, w.DWORD]
        self.k.SetFileInformationByHandle.restype = w.BOOL
        self.n.NtCreateFile.argtypes = [c.POINTER(w.HANDLE), w.DWORD, c.POINTER(Attributes),
                                      c.POINTER(Status), w.LPVOID, w.ULONG, w.ULONG, w.ULONG,
                                      w.ULONG, w.LPVOID, w.ULONG]
        self.n.NtCreateFile.restype = c.c_long
        self.n.NtSetInformationFile.argtypes = [w.HANDLE, c.POINTER(Status), w.LPVOID, w.ULONG, c.c_int]
        self.n.NtSetInformationFile.restype = c.c_long
        self.n.RtlNtStatusToDosError.argtypes = [c.c_long]
        self.n.RtlNtStatusToDosError.restype = w.ULONG

    def _info(self, handle, kind, structure):
        info = structure()
        if not self.k.GetFileInformationByHandleEx(handle, kind, self.c.byref(info), self.c.sizeof(info)):
            raise self.c.WinError(self.c.get_last_error())
        return info

    def _directory_identity(self, handle):
        attrs = self._info(handle, 9, self.Tag).Attributes  # FileAttributeTagInfo
        if not attrs & 0x10 or attrs & 0x400:
            raise _invalid("bound output ancestors must be real directories")
        info = self._info(handle, 18, self.FileId)  # FileIdInfo, no truncated file IDs
        return info.VolumeSerialNumber, int.from_bytes(bytes(info.Identifier), "little")

    def _relative(self, parent, name, *, directory=False, create=False, access=0x80, share=7):
        # RootDirectory prevents re-resolution of the original absolute pathname.
        text = self.c.create_unicode_buffer(name)
        length = len(name.encode("utf-16-le"))
        value = self.Unicode(length, length + 2, self.c.cast(text, self.w.LPWSTR))
        attrs = self.Attributes(self.c.sizeof(self.Attributes), parent.handle,
                                self.c.pointer(value), 0x40 | 0x1000, None, None)  # CASE_INSENSITIVE, DONT_REPARSE
        result, status = self.w.HANDLE(), self.Status()
        options = 0x00200000 | 0x20 | (0x1 if directory else 0x40)  # OPEN_REPARSE_POINT, SYNCHRONOUS_IO_NONALERT
        code = self.n.NtCreateFile(self.c.byref(result), access | 0x100000, self.c.byref(attrs),
                                   self.c.byref(status), None, 0, share, 2 if create else 1,
                                   options, None, 0)  # FILE_CREATE or FILE_OPEN
        if code < 0:
            raise self.c.WinError(self.n.RtlNtStatusToDosError(code))
        return result.value

    def directory(self, path, parent=None, *, create=False):
        if parent is None:
            if create:
                raise _invalid("cannot create an output filesystem root")
            # Root anchor only; all descendant acquisition is handle-relative.
            handle = self.k.CreateFileW(str(path), 0x80 | 0x20, 3, None, 3, 0x02000000 | 0x00200000, None)
            if handle == self.c.c_void_p(-1).value:
                raise self.c.WinError(self.c.get_last_error())
        else:
            handle = self._relative(parent, path.name, directory=True, create=create,
                                    access=0x80 | 0x20 | (0x10000 if create else 0), share=3)
        try:
            return _Directory(path, handle, self._directory_identity(handle), parent, create)
        except BaseException:
            self.k.CloseHandle(handle)
            raise

    def check_directory(self, path, parent=None):
        if parent is None:
            return self.directory(path)
        # A created directory guard owns DELETE access for safe cleanup. Permit
        # that existing access without weakening the original no-delete guard.
        handle = self._relative(parent, path.name, directory=True, share=7)
        try:
            return _Directory(path, handle, self._directory_identity(handle), parent)
        except BaseException:
            self.k.CloseHandle(handle)
            raise

    def _fd(self, handle):
        try:
            return self.msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
        except BaseException:
            self.k.CloseHandle(handle)
            raise

    def file_state(self, directory, name):
        try:
            handle = self._relative(directory, name)
        except FileNotFoundError:
            return None
        fd = self._fd(handle)
        try:
            if self._info(handle, 9, self.Tag).Attributes & 0x400:
                raise _invalid("bound outputs must be unlinked regular files")
            return _state(os.fstat(fd))
        finally:
            os.close(fd)

    def open_file(self, directory, name, *, create=False):
        return self._fd(self._relative(directory, name, create=create, access=0x80000000 | 0x40000000))

    def chmod(self, directory, name, handle, mode):
        # Match Python's Windows chmod semantics without resolving a path: only
        # the readonly attribute changes; timestamps and other attributes stay.
        native = self.msvcrt.get_osfhandle(handle)
        attrs = self._info(native, 9, self.Tag).Attributes & ~0x80  # NORMAL is valid only alone.
        attrs = attrs & ~1 if mode & stat.S_IWRITE else attrs | 1
        value = self.Basic()
        value.Attributes = attrs or 0x80
        self._set_info(native, 4, value)  # FileBasicInformation; zero times leave them unchanged.

    def _set_info(self, handle, kind, value):
        status = self.Status()
        code = self.n.NtSetInformationFile(handle, self.c.byref(status), self.c.byref(value),
                                         self.c.sizeof(value), kind)
        if code < 0:
            raise self.c.WinError(self.n.RtlNtStatusToDosError(code))

    def replace(self, source_dir, source, destination_dir, destination):
        handle = self._relative(source_dir, source, access=0x80 | 0x10000)
        try:
            name = destination.encode("utf-16-le")
            # The documented allocation includes the structure plus name bytes.
            buffer = self.c.create_string_buffer(self.c.sizeof(self.Rename) + len(name))
            value = self.Rename.from_buffer(buffer)
            value.ReplaceIfExists = 1
            value.RootDirectory = destination_dir.handle
            value.FileNameLength = len(name)
            self.c.memmove(self.c.addressof(buffer) + self.Rename.FileName.offset, name, len(name))
            self._set_info(handle, 10, buffer)  # FileRenameInformation, destination relative to held handle.
        finally:
            self.k.CloseHandle(handle)

    def unlink(self, directory, name):
        handle = self._relative(directory, name, access=0x80 | 0x10000)
        try:
            self._delete_handle(handle)
        finally:
            self.k.CloseHandle(handle)

    def _delete_handle(self, handle):
        flag = self.c.c_ubyte(1)  # FILE_DISPOSITION_INFO.DeleteFile is BOOLEAN.
        if not self.k.SetFileInformationByHandle(handle, 4, self.c.byref(flag), self.c.sizeof(flag)):
            raise self.c.WinError(self.c.get_last_error())

    def remove_directory(self, directory):
        self._delete_handle(directory.handle)
        self.close(directory)

    def close(self, directory):
        if not directory.closed:
            if not self.k.CloseHandle(directory.handle):
                raise self.c.WinError(self.c.get_last_error())
            directory.closed = True

    def protect_scratch(self, directory):
        # Attribute-only opens bypass sharing. A held child makes scratch nonempty.
        handle = self._relative(directory, "guard", create=True, access=0x80 | 0x10000, share=1)
        try:
            self._directory_identity(directory.handle)
            current = self.check_directory(directory.path, directory.parent)
            try:
                if current.identity != directory.identity:
                    raise _changed("output scratch directory changed")
            finally:
                self.close(current)
        except BaseException:
            try:
                self._delete_handle(handle)
            finally:
                self.k.CloseHandle(handle)
            raise
        return handle

    def unprotect_scratch(self, handle):
        if handle is not None:
            try:
                self._delete_handle(handle)
            finally:
                self.k.CloseHandle(handle)


def _backend():
    if os.name == "nt":
        return _Windows()
    if os.name == "posix":
        return _Posix()
    raise _invalid("this platform cannot safely bind output directories")


def _absolute(path):
    absolute = Path(path).absolute()
    if not absolute.name or absolute.name in (".", ".."):
        raise _invalid("bound output needs a file name")
    # Inspect the spelling before collapsing '..': never erase an input symlink.
    for parent in reversed(absolute.parents):
        try:
            _identity(parent.lstat())
        except FileNotFoundError:
            continue
    return Path(os.path.abspath(absolute))


def capture_output_bindings(paths: Iterable[Path]) -> dict[Path, OutputBinding]:
    """Capture original states without creating directories or following links."""
    backend = _backend()
    directories = {}
    bindings = {}
    absolute_paths = set()
    try:
        for original in map(Path, paths):
            if original in bindings:
                raise _invalid("bound output destinations must be distinct")
            absolute = _absolute(original)
            if absolute in absolute_paths:
                raise _invalid("bound output destinations must be distinct")
            absolute_paths.add(absolute)
            parents, parent, missing = [], None, False
            for path in reversed(absolute.parents):
                if path not in directories:
                    try:
                        directories[path] = None if missing else backend.directory(path, parent)
                    except FileNotFoundError:
                        directories[path] = None
                directory = directories[path]
                missing = directory is None
                parents.append((path, None if missing else directory.identity))
                parent = directory
            state = None if missing else backend.file_state(parent, absolute.name)
            bindings[original] = OutputBinding(absolute, state, tuple(parents))
        return bindings
    except OSError as exc:
        raise _invalid("cannot safely inspect output directories") from exc
    finally:
        for directory in reversed(list(directories.values())):
            if directory is not None:
                backend.close(directory)


@dataclass
class _Scratch:
    directory: _Directory
    guard: int | None = None
    names: set[str] = field(default_factory=set)
    preserve: bool = False


@dataclass
class _Prepared:
    original: Path
    binding: OutputBinding
    parent: _Directory
    scratch: _Scratch
    replacement: FileState
    had_original: bool


def _assert_topology(backend, directories):
    for path, directory in directories.items():
        try:
            current = backend.check_directory(path, directory.parent)
            try:
                if current.identity != directory.identity:
                    raise _changed()
            finally:
                backend.close(current)
        except OSError as exc:
            raise _changed() from exc


def _write_file(backend, scratch, name, data, mode):
    fd = backend.open_file(scratch.directory, name, create=True)
    scratch.names.add(name)
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
        if mode is not None:
            backend.chmod(scratch.directory, name, fd, mode)
        return _state(os.fstat(fd))
    finally:
        os.close(fd)


def _read_original(backend, directory, name, initial):
    fd = backend.open_file(directory, name)
    try:
        if _state(os.fstat(fd)) != initial:
            raise _changed()
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read()
        if _state(os.fstat(fd)) != initial or backend.file_state(directory, name) != initial:
            raise _changed()
        return data
    finally:
        os.close(fd)


def _ours(current, prepared):
    # Rename may change ctime. All other recorded properties must still match.
    return current is not None and current[:5] == prepared[:5] and current[6:] == prepared[6:]


def _replace(backend, source_dir, source, destination_dir, destination):
    """One narrow commit/rollback boundary for fault-injection tests."""
    backend.replace(source_dir, source, destination_dir, destination)


def write_bound_outputs(outputs: list[tuple[Path, bytes]], *, bindings: Mapping[Path, OutputBinding],
                        repo_root: Path | None = None, snapshots: Mapping[Path, bytes | None] | None = None,
                        append_output: tuple[Path, bytes] | None = None, private: bool = False,
                        private_metadata: set[Path] | None = None) -> None:
    """Publish a subset of captured outputs, retaining recovery data if rollback is obstructed."""
    items = list(outputs) + ([append_output] if append_output else [])
    keys = [Path(path) for path, _ in items]
    if len(set(keys)) != len(keys) or any(path not in bindings for path in keys):
        raise _invalid("every output must have one original binding")
    snapshots, private_metadata = snapshots or {}, private_metadata or set()
    backend, directories, scratch_dirs, prepared, written = _backend(), {}, [], [], []
    committed = False
    try:
        # Bind all checked ancestors before creating scratch or reading originals.
        for original in keys:
            binding = bindings[original]
            if binding.absolute != Path(os.path.abspath(original)):
                raise _changed("bound output spelling or working directory changed")
            parent = None
            for path, expected in binding.parents:
                if path in directories:
                    directory = directories[path]
                    if expected is not None and directory.identity != expected:
                        raise _changed()
                    if expected is None and not directory.created:
                        raise _changed()
                else:
                    try:
                        directory = backend.directory(path, parent, create=expected is None)
                    except OSError as exc:
                        raise _changed() from exc
                    directories[path] = directory
                    if expected is not None and directory.identity != expected:
                        raise _changed()
                parent = directory
        _assert_topology(backend, directories)

        for original, data in items:
            original = Path(original)
            binding = bindings[original]
            parent = directories[binding.absolute.parent]
            append = append_output is not None and original == Path(append_output[0])
            if not append and repo_root is not None and not binding.absolute.is_relative_to(Path(repo_root).resolve()):
                raise _invalid("formatter destination must be inside the target checkout")
            if backend.file_state(parent, binding.absolute.name) != binding.file_state:
                raise _changed()
            work = backend.directory(parent.path / (WRITE_SCRATCH_PREFIX + secrets.token_hex(12)), parent, create=True)
            scratch = _Scratch(work)
            scratch_dirs.append(scratch)
            scratch.guard = backend.protect_scratch(work)
            _assert_topology(backend, directories)
            previous = None
            if binding.file_state is not None:
                previous = _read_original(backend, parent, binding.absolute.name, binding.file_state)
                _write_file(backend, scratch, "original", previous, stat.S_IMODE(binding.file_state[2]))
            if original in snapshots and previous != snapshots[original]:
                raise _changed("README inputs changed during formatting")
            mode = (0o600 if original in private_metadata or (private and binding.file_state is None)
                    else stat.S_IMODE(binding.file_state[2]) if binding.file_state is not None else None)
            state = _write_file(backend, scratch, "output", (previous or b"") + data if append else data, mode)
            prepared.append(_Prepared(original, binding, parent, scratch, state, previous is not None))
        try:
            for item in prepared:
                _assert_topology(backend, directories)
                if backend.file_state(item.parent, item.binding.absolute.name) != item.binding.file_state:
                    raise _changed()
                # Account for a fault injected immediately after a successful
                # replacement, before control returns to this transaction.
                written.append(item)
                _replace(backend, item.scratch.directory, "output", item.parent, item.binding.absolute.name)
                item.scratch.names.discard("output")
            _assert_topology(backend, directories)
            committed = True
        except (OSError, ShowcaseError) as exc:
            failed = []
            for item in reversed(written):
                try:
                    current = backend.file_state(item.parent, item.binding.absolute.name)
                    if current == item.binding.file_state:
                        continue  # The attempted replacement failed without changing this entry.
                    if not _ours(current, item.replacement):
                        raise _changed("another writer changed a published output")
                    if item.had_original:
                        _replace(backend, item.scratch.directory, "original", item.parent, item.binding.absolute.name)
                        item.scratch.names.discard("original")
                    else:
                        backend.unlink(item.parent, item.binding.absolute.name)
                except (OSError, ShowcaseError):
                    item.scratch.preserve = True
                    failed.append(item.scratch.directory.path.name)
            if failed:
                raise ShowcaseError("output rollback incomplete; recovery retained in the original bound directory: "
                                    + ", ".join(failed), log="formatter-rollback", code=CHECK_FAILED) from exc
            raise
    finally:
        cleanup_errors = []
        for scratch in reversed(scratch_dirs):
            try:
                if not scratch.preserve:
                    for name in list(scratch.names):
                        try:
                            backend.unlink(scratch.directory, name)
                        except FileNotFoundError:
                            pass  # A replacement may have succeeded before its caller raised.
                        scratch.names.discard(name)
                backend.unprotect_scratch(scratch.guard)
                if not scratch.preserve:
                    backend.remove_directory(scratch.directory)
            except OSError as exc:
                cleanup_errors.append(exc)
            finally:
                backend.close(scratch.directory)
        for directory in reversed(list(directories.values())):
            try:
                if directory.created and not committed:
                    try:
                        backend.remove_directory(directory)
                    except OSError:
                        pass  # Never recursively remove a directory that acquired other content.
            finally:
                backend.close(directory)
        if cleanup_errors:
            raise ShowcaseError("output scratch cleanup incomplete; retained files require review",
                                log="formatter-rollback", code=CHECK_FAILED) from cleanup_errors[0]
