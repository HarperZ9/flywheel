# Homebrew formula for the flywheel command (PyPI distribution flywheel-verify).
#
#   brew tap HarperZ9/flywheel https://github.com/HarperZ9/flywheel
#   brew install flywheel
#
# The url and sha256 name the PyPI sdist of one release. They are rewritten by
# scripts/package_manager_bump.py after that release is on PyPI, and
# tests/test_package_manager_manifests.py checks them against pyproject.toml.
class Flywheel < Formula
  include Language::Python::Virtualenv

  desc "Run any model, keep a receipt you can recheck offline"
  homepage "https://github.com/HarperZ9/flywheel"
  url "https://files.pythonhosted.org/packages/58/d6/c18c0b4e2d42fc7700351e27f8e290513b97b9803eca4acc28afa0cfe7a2/flywheel_verify-2.0.0.tar.gz"
  sha256 "8359477372288e9bfedfc8b8e5fd16348052bfaea862d1112c26c69eeab07d4c"
  license "FSL-1.1-MIT"

  depends_on "python@3.13"

  # No resource blocks: flywheel-verify has zero runtime dependencies.

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "flywheel #{version}", shell_output("#{bin}/flywheel --version")
  end
end
