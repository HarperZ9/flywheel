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
  url "https://files.pythonhosted.org/packages/c5/78/36ca2ef83c668c90d39fb827c8b600ef793e50b955e64546852f34a0ad7d/flywheel_verify-1.8.0.tar.gz"
  sha256 "f4d13aa796a466a84b988b5d02a726df29c273996ae166848c518bb013b8a6c5"
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
