"""Exercise the real pip Windows guard without installing any package."""
import os
import subprocess
import sys
from pathlib import Path


def test_probe_module_entry_allows_windows_pip_self_update(tmp_path):
    lock = tmp_path / "requirements.lock"
    lock.write_text("pip==25.1.1 --hash=sha256:" + "0" * 64 + "\n")
    code = r"""
import sys, socket
import runpy
from pip._internal.utils import misc
from pip._internal.exceptions import CommandError
from scripts import offline_runtime_probe as probe
misc.WINDOWS = True
sys.argv = ['pip']
try:
    misc.protect_pip_from_modification_on_windows(True)
except CommandError:
    pass
else:
    raise AssertionError('negative control did not trigger Windows guard')
class Checked(BaseException):
    pass
def check_entry(event, args):
    filename = getattr(args[0], 'co_filename', '').replace(chr(92), '/')
    if event != 'exec' or not filename.endswith('pip/__main__.py'):
        return
    misc.protect_pip_from_modification_on_windows(True)
    assert '--no-index' in sys.argv
    assert '--require-hashes' in sys.argv
    assert '--only-binary=:all:' in sys.argv
    try:
        sys.audit('socket.connect', None, ('127.0.0.1', 9))
    except RuntimeError as error:
        assert 'offline probe denied' in str(error)
    else:
        raise AssertionError('network audit hook missing')
    print('WINDOWS_GUARD_AND_OFFLINE_HOOK_PASS')
    raise Checked()
def run_entry(name, *, run_name, alter_sys=False):
    assert name == 'pip' and run_name == '__main__' and alter_sys
    with runpy._ModifiedArgv0('pip/__main__.py'):
        check_entry('exec', (compile('', 'pip/__main__.py', 'exec'),))
probe.runpy.run_module = run_entry
try:
    probe.main(['install', '--wheelhouse', sys.argv[1], '--lock', sys.argv[2]])
except Checked:
    pass
"""
    # Preserve arguments separately: the negative control deliberately changes argv.
    code = code.replace("sys.argv = ['pip']", "paths = sys.argv[1:]; sys.argv = ['pip']")
    code = code.replace("sys.argv[1], '--lock', sys.argv[2]", "paths[0], '--lock', paths[1]")
    result = subprocess.run(
        [
            os.environ.get('FP001D_TEST_PYTHON', sys.executable),
            '-c', code, str(tmp_path), str(lock),
        ],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "WINDOWS_GUARD_AND_OFFLINE_HOOK_PASS" in result.stdout







