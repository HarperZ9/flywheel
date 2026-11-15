"""`articulate --version` prints the installed package version and exits 0."""
import subprocess
import sys

import pytest

import articulate
from articulate import cli


@pytest.mark.parametrize("flag", ["--version", "-V"])
def test_version_flag_prints_package_version(flag, capsys):
    assert cli.main([flag]) == 0
    assert capsys.readouterr().out.strip() == f"articulate {articulate.__version__}"


def test_version_flag_from_a_subprocess():
    result = subprocess.run([sys.executable, "-m", "articulate.cli", "--version"],
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert result.stdout.strip() == f"articulate {articulate.__version__}"


def test_help_lists_the_version_flag(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "--version" in capsys.readouterr().out
