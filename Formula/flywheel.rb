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
  url "https://files.pythonhosted.org/packages/5d/03/53b9277371307e7b65a7cc7fd0e33c7dd35a64e4081e7c9cac9f55eaf405/flywheel_verify-1.9.0.tar.gz"
  sha256 "a98047c20b6e77ea7a94c47c6b50f4e8d5958c41f27f6426b77671f8ff4d1151"
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
