import base64
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


@pytest.mark.parametrize("exit_code", [0, 37, -2147024891])
def test_runner_retains_exact_exit_code_and_streams(tmp_path, exit_code):
    child = (
        "[Console]::Out.WriteLine('synthetic-out'); "
        f"[Console]::Error.WriteLine('synthetic-err'); exit {exit_code}"
    )
    encoded = base64.b64encode(child.encode("utf-16-le")).decode()
    source = (ROOT / "scripts/run_fp001d_offline.ps1").as_posix().replace("'", "''")
    run = tmp_path.as_posix().replace("'", "''")
    # Extract only Execute via the PowerShell parser. Never evaluate the acceptance script body.
    script = f"""
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile('{source}',[ref]$tokens,[ref]$errors)
if($errors){{throw 'parse failure'}}
$function=$ast.Find({{param($n)
    $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Execute'
}},$true)
. ([scriptblock]::Create($function.Extent.Text))
function Isolated {{}}
function Budget {{}}
function SizeOf {{return 0}}
function UTC {{[DateTime]::UtcNow.ToString('o')}}
$Run='{run}'; $Restore=$Run; $ExecutionStarted=[DateTime]::UtcNow
try {{
    $result=Execute 'synthetic' '{POWERSHELL}' '-NoProfile -EncodedCommand {encoded}'
    Write-Output "RESULT=$result"
}}
catch {{ Write-Output "ERROR=$($_.Exception.Message)" }}
"""
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    if exit_code == 0:
        assert "RESULT=0" in result.stdout
    else:
        assert f"failed with exit {exit_code}" in result.stdout
    assert (tmp_path / "synthetic.stdout.txt").read_text().strip() == "synthetic-out"
    assert (tmp_path / "synthetic.stderr.txt").read_text().strip() == "synthetic-err"
    assert f"END synthetic exit={exit_code}" in (tmp_path / "restoration.txt").read_text(
        encoding="utf-8-sig"
    )
