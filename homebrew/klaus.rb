# Homebrew formula for Klaus
#
# To use this formula, create a tap repo (homebrew-klaus) containing this file
# at Formula/klaus.rb, then:
#
#   brew tap <your-github-user>/klaus
#   brew install klaus
#
# Before publishing, update the `url` to point to a tagged release tarball and
# regenerate the sha256 with:
#
#   shasum -a 256 Klaus-0.1.0.tar.gz

class Klaus < Formula
  desc "Voice-powered research assistant for physical books and papers"
  homepage "https://github.com/bgigurtsis/Klaus"
  url "https://github.com/bgigurtsis/Klaus/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "23b5681ec359b38b9fc093207016f7ffa5b3def4786063f21239ed39f590b8a0"
  license "MIT"

  depends_on "python@3.12"
  depends_on "portaudio"
  depends_on "rust" => :build

  def install
    python3 = Formula["python@3.12"].opt_bin/"python3.12"
    system python3, "-m", "venv", libexec
    system libexec/"bin/pip", "install", "--no-binary", "jiter", buildpath
    bin.install_symlink libexec/"bin/klaus"
  end

  def caveats
    <<~EOS
      Start Klaus with:
        klaus

      On first launch a setup wizard will guide you through API keys,
      camera selection, and voice model download.

      Global hotkeys require Accessibility permission:
        System Settings > Privacy & Security > Accessibility
    EOS
  end

  test do
    assert_match "usage", shell_output("#{bin}/klaus --help 2>&1", 2)
  end
end
