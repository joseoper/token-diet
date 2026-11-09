class TokenDiet < Formula
  include Language::Python::Virtualenv

  desc "Audit token footprint and detect silent context leaks in AI agent workflows"
  homepage "https://github.com/joseoper/token-diet"
  url "https://github.com/joseoper/token-diet/archive/refs/tags/v0.2.3.tar.gz"
  sha256 "e6324d54c083acf5895dc48283f7e3b29c85f401e0b33822ecf357b66a3335ac"
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
