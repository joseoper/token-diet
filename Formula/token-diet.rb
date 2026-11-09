class TokenDiet < Formula
  include Language::Python::Virtualenv

  desc "Audit token footprint and detect silent context leaks in AI agent workflows"
  homepage "https://github.com/joseoper/token-diet"
  url "https://github.com/joseoper/token-diet/archive/refs/tags/v0.2.0.tar.gz"
  sha256 "8846093826b47d4a2928fa6abd673cb69d2520f3809b8127e3e1afa81ae73d69"
  license "MIT"
  head "https://github.com/joseoper/token-diet.git", branch: "main"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "TOKEN DIET", shell_output("#{bin}/token-diet --help")
  end
end
