# Homebrew Tap for Klaus

This directory contains the Homebrew formula for distributing Klaus on macOS.

## Setting Up the Tap

1. Create a new GitHub repo named `homebrew-klaus` under your account.
2. Copy `klaus.rb` into `Formula/klaus.rb` in that repo.
3. Create a tagged release on the main Klaus repo (`git tag v0.1.0 && git push --tags`).
4. Download the release tarball and generate the SHA256:

   ```
   curl -L -o Klaus-0.1.0.tar.gz https://github.com/<user>/Klaus/archive/refs/tags/v0.1.0.tar.gz
   shasum -a 256 Klaus-0.1.0.tar.gz
   ```

5. Replace `PLACEHOLDER_SHA256` in the formula with the real hash.
6. Push the tap repo.

## Installing

```
brew tap <user>/klaus
brew install klaus
```

## Updating

When you release a new version, update `url` and `sha256` in the formula and push to the tap repo. Users update with `brew upgrade klaus`.
