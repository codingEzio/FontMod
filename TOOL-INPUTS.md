# FontMod tool-only candidate

This local candidate contains no font binaries or specimen artwork. It does not grant rights to any inputs or derived font. Before building, independently obtain permission for your intended use, then provide these exact pinned files at their paths:

- `sources/Cubic_11.ttf` and `sources/Doto-Variable.ttf`: URLs and SHA-256 in `sources/catalog.json`.
- `sources/Noto3D-64.ttf`: URL and SHA-256 in `sources/emoji3d.json`.
- `sources/geist-mixed/GeistMono-Variable.ttf`, `GeistPixel-Variable.ttf`, `SymbolsNerdFontMono-Regular.ttf`: exact SHA-256 and origin in `sources/geist-mixed/sources.json`.
- A separately produced DeparturePixelZh build with its provenance, both TTFs, OFL, notice and complete Licenses directory; pass its path using `--departure-build`. `dependencies/` contains source snapshots, not font inputs.

`./fontmod source-check` checks this tool payload and any supplied inputs. `./fontmod setup` installs pinned Python dependencies; it needs network. Then `./fontmod build --departure-build /path/to/your/build` fails when input files are missing or mismatched. Actual font production and redistribution remain subject to the applicable font, artwork and trademark rights. `release-check --publication` remains blocked by unresolved Font Logos and Material Design rights. Never assume the package supplies permission.

## External inputs and optional local profiles

Set `FONTMOD_INPUT_ROOT` to an external directory containing the `sources/` layout listed above. Font binaries are read there; text manifests and licenses remain in this checkout. Omitting it retains the existing checkout-relative input paths. Input hashes remain mandatory.

Before a final build, create an external output directory and link it as `Final` in the checkout, for example `mkdir -p /path/to/private-output && ln -s /path/to/private-output Final`. Builds reject a checkout-local `Final`; selected bundles default to its `Bundles/` subdirectory and also require external output.

The optional `rysamix` profile also expects `sources/rysana-mono/recipe.json`, its two pinned source fonts and `LICENSE.txt` under that external root. Provide MiSans using `--misans-source`; the private recipe and any derived outputs stay outside the checkout. Example: `./fontmod build --profile rysamix --misans-source /path/to/font.ttf --output /path/to/new-candidate`. The same profile supports check, deep check, web bundle, native verification and explicit installation. MiSans modification and redistribution rights are not granted by this tool.

`./fontmod glyphgrove --inputs /path/to/inputs --recipe /path/to/recipe.json --output /path/to/new-candidate` uses a separately supplied recipe and hash-checked inputs. Neither profile grants rights to generated fonts or Nerd artwork. See `scripts/glyphgrove/THIRD-PARTY-NOTICES.md`; distribution remains subject to rights review.
