# FontMod — tool-only source

[English](README.md) · [简体中文](README.zh-Hans.md) · [繁體中文](README.zh-Hant.md) · [Español](README.es.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

This repository includes tooling and notices; it excludes source fonts and artwork. Supply inputs you have rights to use, at the exact paths and hashes in [TOOL-INPUTS.md](TOOL-INPUTS.md).

Run `./fontmod source-check`, then `./fontmod setup` and `./fontmod build --departure-build /path/to/build`. `setup` needs network. Build fails on missing or mismatched pinned inputs. The full mixed font retains Nerd glyphs; third-party artwork and trademark rights remain unresolved. Publication of generated fonts is not authorized by this tool release. See [license scope](LICENSE-SCOPE.md) and [release guide](RELEASE.en.md).

After setup, prepare the pinned emoji input with `./fontmod prepare-emoji /path/to/Noto-3D-128.ttf /path/to/input-root/sources/Noto3D-64.ttf`. It checks both hashes and never overwrites an existing file.

Optional local RysaMix and Glyphgrove tooling accepts separately supplied private inputs; see [TOOL-INPUTS.md](TOOL-INPUTS.md). Source and derived font rights remain separate from the tool license.
