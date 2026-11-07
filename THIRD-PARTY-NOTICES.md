# Font and dependency notices

This record describes the exact inputs used by FontMod recipe 1.1.0. It does
not replace the original license texts. FontMod's original tooling is MIT;
source fonts, generated font software, icons and dependency source snapshots
keep the grants below. The merged font software is distributed under OFL-1.1
with the retained component terms. Existing CC BY rights in icon material are
not removed by the OFL statement. No source author endorses this derivative.

## Text and emoji sources

| Input / attribution | Exact source record | Grant and naming conditions |
| --- | --- | --- |
| Geist Mono; Copyright 2024 The Geist Project Authors | vercel/geist-font a73329da8fc62afc917f796555202e4997f79b7c; `sources/geist-mixed/sources.json` | OFL-1.1; no RFN declaration in the pinned license |
| Geist Pixel; Copyright 2026 The Geist Project Authors | google/fonts c180a5f9711fb8ec0070fab5ad89c30f231f6e22; same source record | OFL-1.1; no RFN declaration in the pinned license |
| Doto; Copyright 2024 The Doto Project Authors (Oliver Lalan project) | google/fonts 9710da1eacb3be272583c3224dcb70f9da6eadbb; `sources/catalog.json` | OFL-1.1; no RFN declaration in the pinned license |
| Cubic 11; ACh / Cubic 11 Project Authors; inherited JF Dot M+H 12, M+ FONTS PROJECT and COZ notices | ACh-K/Cubic-11 4c566f7d6cc5c05ee360fe9cff56b5da1fcafd4d; `sources/catalog.json` | OFL-1.1; the pinned upstream README reserves **Cubic** and **俐方體** |
| Noto 3D Emoji; Copyright 2022 Google Inc. | googlefonts/noto-emoji v2026-09-24-unicode18_0; `sources/emoji3d.json` | OFL-1.1; no RFN declaration in the pinned 3D font license |
| Departure Mono; Copyright 2022–2024 Helena Zhang | DepartureMono 1.500 upstream archive; minimum dependency recipe | OFL-1.1; no RFN declaration in its bundled license |

The source records include source URLs, revisions, font hashes and license hashes.
Cubic's upstream README is preserved in the Departure license closure as
`Cubic11Naming.txt`; the same declaration applies to every mixed FontMod face
using that source. Original source names in this notice acknowledge provenance.
They are not alternate family names or CSS aliases for the derived fonts.

The two original Departure input variants use their own names, DeparturePixelZh
and DeparturePixelZh Compact. The retained producer NOTICE calls its Cubic input
"1.500". The pinned source file actually reports embedded version **1.451**;
SHA-256 `0193f5f033612496df6b45ee92ac3b335bc6a5a24ff95da55ca87b33e57dcf62` is
its identity. Treat this paragraph as the correction. The original source NOTICE
and its hash are preserved; its version label is not evidence of another input.

## Nerd Fonts Symbols Mono 3.5.1 components

The complete Symbols input is pinned to SHA-256
`fe471e538392f51910faab985fa8e192a39dd3426125edd15b71b3680df0e749`.
Nerd Fonts' own source README/audit identifies the components below. "Symbols
Only: MIT" covers Nerd Fonts' original work; it does not replace component terms.

| Component / attribution and source | Retained notice | Terms |
| --- | --- | --- |
| Nerd Fonts original work; Ryan L McIntyre | NerdFonts.txt, NerdSymbols.txt | MIT; retain copyright/permission text |
| Codicons; Microsoft, https://github.com/microsoft/vscode-codicons | Codicons.txt, NerdSymbolsReadme.txt | CC BY 4.0; attribution, license link and changes notice |
| Devicons / Devicon; konpa and contributors, https://github.com/devicons/devicon | Devicons.txt, DeviconsLegacy.txt | MIT; retain both current and legacy notices |
| Font Awesome; Fonticons, Inc., https://github.com/FortAwesome/Font-Awesome | FontAwesome.txt, FontAwesome7.txt | Nerd Fonts uses SVG-derived CC BY 4.0 icons; original font packages also carry OFL with RFN Font Awesome |
| Font Awesome Extension; André Luiz Gava, https://github.com/AndreLZGava/font-awesome-extension | FontAwesomeExtension.txt | MIT |
| Font Logos; Lukas W / contributors, https://github.com/lukas-w/font-logos | FontLogos.txt, NerdFontsAudit.txt | Conflicting descriptions; see the open review below |
| Hack extra glyphs; Chris Simpkins, Bitstream and GNOME notices, https://github.com/source-foundry/Hack | HackExtraGlyphs.txt | MIT and retained Bitstream Vera terms; modified names must not contain Bitstream or Vera |
| Material Design; Pictogrammers / Templarian, https://github.com/Templarian/MaterialDesign-Font | MaterialDesign.txt, Apache2.txt | Apache-2.0 for the font; retain notices and identify changes |
| Octicons; GitHub Inc., https://github.com/primer/octicons | Octicons.txt | MIT |
| Seti/original icons; Jesse Weed, https://github.com/jesseweed/seti-ui | Seti.txt | MIT |
| Pomicons; Gabriele Lana, https://github.com/gabrielelana/pomicons | Pomicons.txt | OFL-1.1; RFN Pomicons |
| IEC power symbols; Joe Loughry, https://github.com/jloughry/Unicode | PowerSymbolsIEC.txt | MIT |
| Powerline extra symbols; Ryan L McIntyre, https://github.com/ryanoasis/powerline-extra-symbols | PowerlineExtra.txt | MIT |
| Powerline; Kim Silkebækken and contributors, https://github.com/powerline/powerline | PowerlineSymbols.txt | Retained permissive copyright/permission notice |
| Weather Icons; Lukas Bischoff and Erik Flowers, https://github.com/erikflowers/weather-icons | WeatherIcons.txt, WeatherIconsCredit.txt | OFL-1.1 for font; the supplied OFL header contains unfilled template RFN placeholders, so no concrete RFN is inferred from them |

The retained Font Logos 1.3.0 license is Unlicense, while the retained Nerd
Fonts 3.5.1 glyph summary and audit describe Font Logos as unlicensed. The
versioned [upstream license](https://raw.githubusercontent.com/lukas-w/font-logos/v1.3.0/LICENSE)
and [Nerd Fonts glyph summary](https://raw.githubusercontent.com/ryanoasis/nerd-fonts/v3.5.1/src/glyphs/README.md)
record these conflicting descriptions. Preserve both records; the reason for
the discrepancy is not established. The [Font Logos README](https://raw.githubusercontent.com/lukas-w/font-logos/v1.3.0/README.md)
also reserves trademark owners' rights. These records do not establish clearance
for every glyph or grant trademark rights; the release decision remains open.

Keep all notices, not just the table. They are in `licenses/` for mixed kits,
`departure-package/Licenses/` for Departure's retained producer package, and the
corresponding `sources/` or `dependencies/` paths in the source ZIP. Departure
family kits expose the same producer notices in their own `licenses/` directory.

Earlier modifications also need attribution: Nerd Fonts repaired two Codicons
glyphs and generated its Font Awesome font from selected SVGs. The pinned
[Codicons note](https://github.com/ryanoasis/nerd-fonts/blob/b894ea7803af6aade63d60a4381e006098ec9c4d/src/glyphs/codicons/README.md)
and [Font Awesome note](https://github.com/ryanoasis/nerd-fonts/blob/b894ea7803af6aade63d60a4381e006098ec9c4d/src/glyphs/font-awesome/README.md)
record those changes. The latter identifies 6.5.1.custom2 plus one 7.3.1 solid
fa-volume glyph; it is not the complete Font Awesome 6.5.1 or 7.3.1 repertoire.

FontMod merges selected text sources, normalizes UPEM, retains original Cubic
geometry in its mixed faces, changes Doto Latin vertical geometry at HGHT
105/110/115/120 (default 110), preserves code weight variation, adds U+EA00 as
an alias of Nerd U+F099, and merges the retained Noto cmap/GSUB repertoire.
Emoji PNGs are resampled with alpha at 28 PPEM. Web adapters split outline text
and Emoji3D; Android uses CBDT instead of sbix. These are modified works, not
unchanged upstream icons/fonts. Departure retains its separately documented
monospaced fitting and 95% CJK scale; FontMod adds its symbol alias afterward.

## Distribution conditions and remaining decisions

OFL permits use, modification, embedding and redistribution, with its notices,
license continuity, RFN and no-standalone-sale conditions. CC BY 4.0 permits
adaptation and redistribution with attribution, license notice and indication
of changes. MIT and the retained permissive notices require their copyright and
permission texts. Apache-2.0 requires the license, retained notices and a changes
statement. The actual texts remain authoritative. Do not imply endorsement or
claim rights to brand marks: trademark rights are not granted by these licenses.

The five mixed primary names use Zh without the reserved Cubic string. No
RFN-containing aliases are provided. `RELEASE-RIGHTS.json` records the reviewed
naming policy and retained conditions.
An archive/hash check proves measured file contents; publication remains a
separate action. Original source names in attribution/provenance remain valid.

## Minimum dependency source closure

`release-dependencies.json` records 43 exact upstream files (29 font-source and
14 builder files), their modes/hashes, excluded original paths, and one derived
recipe. Font source includes its original recipe, builder-version, OFL, NOTICE
and all 25 component license files. These are font-software source/notice inputs
under the project's OFL/component grants. The builder's code, required README,
pyproject, lock file and MIT license remain under its MIT grant.

Unneeded social artwork, specimens, agent instructions, tests and maintenance
material are excluded from this new package. No new grant is assumed for those
excluded assets. The full earlier 84-file candidate remains preserved privately.

`recipe.fontmod.json` changes only `documents` to NOTICE.md/OFL.txt. Every other
parsed field equals the pinned original recipe; that original file and hash are
included. This avoids making unrelated artwork a rebuild dependency. The
source-only builder uses its explicit development mode; the output is checked
by complete font hashes, not claimed as original producer Git-release approval.

## Documentation specimens

`assets/fontmod-specimen.png` is an unedited browser rendering of the exact
public-name platform fonts listed in `assets/fontmod-specimen-source.json`.
The original HTML layout is project documentation under MIT. Font glyphs and
Emoji3D retain the component grants above; this screenshot adds no replacement
font license. `assets/fontmod-icon.svg` contains the outline of F from the
verified GeistMixCode web font at weight900, derived from Geist Mono. Its metadata records
the exact source hash and retained Geist OFL notice. No font binary is embedded
in the SVG or copied into the source screenshot folder.
