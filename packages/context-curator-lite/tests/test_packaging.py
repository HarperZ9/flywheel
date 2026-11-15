from pathlib import Path
import shutil
import subprocess
import sys
import tarfile


def test_sdist_excludes_dirty_build_and_virtualenv_directories(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    dirty_roots = [
        ".tmp-pytest",
        ".venv-release-build",
        ".venv-wheel-test",
        "build",
    ]
    preexisting = {name: (repo_root / name).exists() for name in dirty_roots}
    marker_dirs: list[Path] = []

    try:
        for name in dirty_roots:
            marker = repo_root / name / "__packaging_test_leak__"
            marker.mkdir(parents=True, exist_ok=True)
            (marker / "leak.txt").write_text("must not ship\n", encoding="utf-8")
            marker_dirs.append(marker)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--sdist",
                "--no-isolation",
                "--outdir",
                str(tmp_path),
            ],
            cwd=repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        assert result.returncode == 0, result.stdout

        sdists = list(tmp_path.glob("context_curator_lite-0.2.0.tar.gz"))
        assert len(sdists) == 1
        with tarfile.open(sdists[0], "r:gz") as archive:
            names = archive.getnames()

        payload_names = [name.split("/", 1)[1] for name in names if "/" in name]
        for dirty_root in dirty_roots:
            assert not any(
                name == dirty_root or name.startswith(f"{dirty_root}/")
                for name in payload_names
            )
        assert "src/context_curator_lite/curator.py" in payload_names
        assert "tests/test_curator.py" in payload_names
    finally:
        for marker in marker_dirs:
            shutil.rmtree(marker, ignore_errors=True)
        for name, existed in preexisting.items():
            if not existed:
                shutil.rmtree(repo_root / name, ignore_errors=True)