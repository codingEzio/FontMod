# FontMod tool-only candidate

This local candidate contains no font binaries or specimen artwork. It does not grant rights to any inputs or derived font. Before building, independently obtain permission for your intended use, then provide these exact pinned files at their paths:

- `sources/Cubic_11.ttf` and `sources/Doto-Variable.ttf`: URLs and SHA-256 in `sources/catalog.json`.
- `sources/Noto3D-64.ttf`: URL and SHA-256 in `sources/emoji3d.json`.
- `sources/geist-mixed/GeistMono-Variable.ttf`, `GeistPixel-Variable.ttf`, `SymbolsNerdFontMono-Regular.ttf`: exact SHA-256 and origin in `sources/geist-mixed/sources.json`.
- A separately produced DeparturePixelZh build with its provenance, both TTFs, OFL, notice and complete Licenses directory; pass its path using `--departure-build`. `dependencies/` contains source snapshots, not font inputs.

`./fontmod source-check` checks this tool payload and any supplied inputs. `./fontmod setup` installs pinned Python dependencies; it needs network. Then `./fontmod build --departure-build /path/to/your/build` fails when input files are missing or mismatched. Actual font production and redistribution remain subject to the applicable font, artwork and trademark rights. `release-check --publication` remains blocked by unresolved Font Logos and Material Design rights. Never assume the package supplies permission.
