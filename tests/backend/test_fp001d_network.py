import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.collect_runtime_evidence import validate_observations

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "case,expected",
    [
        ("unrouted-miniports", True),
        ("wifi-up", False),
        ("stale-default", False),
        ("routed-miniport", False),
        ("other-virtual-up", False),
        ("empty", False),
        ("ipv6-default", False),
    ],
)
def test_powershell_and_evidence_network_policy_agree(tmp_path, case, expected):
    adapters = [
        {
            "Name": "Wi-Fi",
            "InterfaceDescription": "Wi-Fi transport",
            "Status": "Disabled",
            "ifIndex": 7,
        },
        {
            "Name": "Bookkeeping",
            "InterfaceDescription": "WAN Miniport (IP)",
            "Status": "Up",
            "ifIndex": 19,
        },
    ]
    routes = []
    if case == "wifi-up":
        adapters[0]["Status"] = "Up"
    elif case == "stale-default":
        routes = [
            {"DestinationPrefix": "0.0.0.0/0", "InterfaceIndex": 7, "NextHop": "192.168.1.254"}
        ]
    elif case == "ipv6-default":
        routes = [{"DestinationPrefix": "::/0", "InterfaceIndex": 7, "NextHop": "fe80::1"}]
    elif case == "routed-miniport":
        routes = [{"DestinationPrefix": "10.0.0.0/8", "InterfaceIndex": 19, "NextHop": "0.0.0.0"}]
    elif case == "other-virtual-up":
        adapters[1]["InterfaceDescription"] = "Other virtual adapter"
    elif case == "empty":
        adapters = []
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps({"adapters": adapters, "routes": routes}))
    policy = (ROOT / "scripts/fp001d_network.ps1").as_posix().replace("'", "''")
    input_path = path.as_posix().replace("'", "''")
    command = (
        f". '{policy}'; $x=Get-Content -Raw -LiteralPath '{input_path}' | ConvertFrom-Json; "
        "Test-Fp001dNetworkState -Adapters @($x.adapters) -Routes @($x.routes) "
        "| ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        [
            r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["isolated"] is expected
    observations = [
        {
            "isolated": True,
            "adapters": adapters,
            "routes": routes,
            "timestamp": f"2026-09-29T15:00:0{i}Z",
        }
        for i in range(2)
    ]
    inference = {
        "generated_tokens": [[1]],
        "generated_token_count": 1,
        "output_sha256": hashlib.sha256(b"[[1]]").hexdigest(),
    }
    if expected:
        validate_observations(observations, inference)
    else:
        with pytest.raises(ValueError, match="network coverage"):
            validate_observations(observations, inference)
