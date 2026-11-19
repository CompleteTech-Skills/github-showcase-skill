"""Regression controls for the independent provenance fixture's process boundary.

Every denied launch is harmless even if the guard regresses: it can only echo a
synthetic sentinel or start this Python interpreter without the fixture guard.
The Windows startfile cases emit audit events; they never open a native app.
"""
import subprocess
import sys

import pytest

from test_provenance_contract_independent import Sandbox

SENTINEL = "fixture-native-sentinel"
PYTHON_CHILD = f"[sys.executable, '-S', '-c', {('print(' + repr(SENTINEL) + ')')!r}]"
AUDIT_CHILD = f"import sys; sys.audit('socket.connect',None,('synthetic.invalid',0)); print('{SENTINEL}')"


@pytest.mark.parametrize("code,events", [
    (f"import os; os.system('echo {SENTINEL}')", ("os.system",)),
    (f"import os,sys; os.execv(sys.executable,{PYTHON_CHILD})", ("os.exec",)),
    (f"import os,sys; raise SystemExit(os.spawnv(os.P_WAIT,sys.executable,{PYTHON_CHILD}))",
     ("os.exec", "os.spawn")),
    (f"import subprocess,sys; subprocess.run({PYTHON_CHILD},check=True)", ("subprocess.Popen",)),
    ("import os,subprocess,sys; env=dict(os.environ); env.pop('PYTHONPATH'); "
     f"subprocess.run([sys.executable,'-c',\"print('{SENTINEL}')\"],env=env,check=True)",
     ("subprocess.Popen",)),
    ("import os,subprocess,sys; os.environ['PYTHONPATH']=''; "
     f"subprocess.run([sys.executable,'-c',\"print('{SENTINEL}')\"],check=True)",
     ("subprocess.Popen",)),
    ("import os,subprocess,sys; os.putenv('PYTHONPATH',''); "
     f"subprocess.run([sys.executable,'-c',\"print('{SENTINEL}')\"],check=True)",
     ("subprocess.Popen",)),
    ("import os,subprocess,sys; os.unsetenv('PYTHONPATH'); "
     f"subprocess.run([sys.executable,'-c',\"print('{SENTINEL}')\"],check=True)",
     ("subprocess.Popen",)),
    ("import os,subprocess,sys; env=dict(os.environ); env['pythonpath']=env.pop('PYTHONPATH'); "
     f"subprocess.run([sys.executable,'-c',{AUDIT_CHILD!r}],env=env,check=True)",
     ("subprocess.Popen", "socket.connect")),
    ("import os,subprocess,sys; env=dict(os.environ); env.pop('CONTRACT_TRIPWIRE'); "
     f"subprocess.run([sys.executable,'-c',\"import os; os.system('echo {SENTINEL}')\"],env=env,check=True)",
     ("os.system",)),
    ("import subprocess,sys; "
     f"sys.audit('subprocess.Popen',sys.executable,subprocess.list2cmdline({PYTHON_CHILD}),None,None); "
     f"print('{SENTINEL}')", ("subprocess.Popen",)),
    (f"import sys; sys.audit('os.startfile','synthetic-unopened-file',None); print('{SENTINEL}')",
     ("os.startfile",)),
    ("import sys; sys.audit('os.startfile/2','synthetic-unopened-file',None,None,None,None); "
     f"print('{SENTINEL}')", ("os.startfile/2",)),
], ids=["shell", "exec", "spawn", "python-without-site", "python-without-guard-path",
        "mutated-parent-guard-path", "native-putenv", "native-unsetenv", "case-sensitive-guard-path",
        "fixed-tripwire-path", "windows-command-line-audit",
        "windows-startfile-audit", "windows-startfile-2-audit"])
def test_fixture_refuses_native_launch_before_execution(tmp_path, code, events):
    box = Sandbox(tmp_path)
    result = subprocess.run([sys.executable, "-c", code], cwd=box.repo, env=box.env,
                            capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode != 0, "forbidden native launch must fail"
    assert SENTINEL not in result.stdout, "forbidden child or shell must never execute"
    assert box.tripwire.exists(), "refusal must retain evidence of the attempted launch"
    recorded = box.tripwire.read_text(encoding="utf-8").splitlines()
    assert any(event in recorded for event in events), "the native launch must be refused by its audit event"


def test_fixture_preserves_a_guarded_python_child(tmp_path):
    box = Sandbox(tmp_path)
    code = ("import subprocess,sys; "
            f"subprocess.run([sys.executable,'-B','-c',\"print('{SENTINEL}')\"],check=True)")
    result = subprocess.run([sys.executable, "-c", code], cwd=box.repo, env=box.env,
                            capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == SENTINEL
    box.no_network()


@pytest.mark.parametrize("operation", ["os.putenv('PYTHONPATH','')", "os.unsetenv('PYTHONPATH')"])
def test_fixture_preserves_an_explicit_guarded_environment_after_native_change(tmp_path, operation):
    box = Sandbox(tmp_path)
    child = f"import sys; assert 'sitecustomize' in sys.modules; print('{SENTINEL}')"
    code = (f"import os,subprocess,sys; {operation}; "
            f"subprocess.run([sys.executable,'-c',{child!r}],env=dict(os.environ),check=True)")
    result = subprocess.run([sys.executable, "-c", code], cwd=box.repo, env=box.env,
                            capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == SENTINEL
    box.no_network()


def test_fixture_accepts_the_windows_subprocess_audit_shape(tmp_path):
    """Model Windows' None executable/string command line without launching an app."""
    box = Sandbox(tmp_path)
    code = """import importlib,sitecustomize,subprocess,sys
class WindowsAuditPopen:
    def __init__(self,args,*a,**kw):
        sys.audit('subprocess.Popen',None,subprocess.list2cmdline(args),kw.get('cwd'),kw.get('env'))
        print('modeled-windows-launch-accepted')
subprocess.Popen = WindowsAuditPopen
importlib.reload(sitecustomize)
subprocess.Popen([sys.executable,'-B','-c',"print('synthetic-unused-code')"])
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=box.repo, env=box.env,
                            capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "modeled-windows-launch-accepted"
    box.no_network()
