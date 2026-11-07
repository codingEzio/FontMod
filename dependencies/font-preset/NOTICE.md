# DeparturePixelZh notices

DeparturePixelZh and DeparturePixelZh Compact are modified font families. They combine Departure Mono 1.500 (Helena Zhang, 2022–2024), Cubic 11 1.500 (ACh-K and contributors; derived from JF Dot M+H 12 and M+ Bitmap Fonts), and Nerd Fonts Symbols Mono 3.5.1. The derived font files are distributed under SIL Open Font License 1.1; preserve [OFL.txt](OFL.txt) and all files in [licenses/](licenses/) when redistributing or embedding them.

## License scope

The merged font software is distributed under SIL OFL 1.1 with the retained component terms. The CC BY 4.0, MIT, Apache-2.0, Unlicense, and other notices below continue to apply to their respective upstream material. Inclusion in this font does not replace those upstream grants. In particular, the OFL statement must not be read as removing the existing CC BY rights in the original icon material.

Changes include source-priority merging, conversion to TrueType outlines, monospaced fitting, metric normalization, 95% CJK optical scaling, a Compact cell grid with corresponding mark positioning, new family names, and selected private-use icon mappings. Departure Mono wins overlapping text characters. Cubic 11 supplies remaining Chinese coverage. Nerd Fonts Symbols Mono wins its private-use mappings. Emoji are not redistributed and remain platform fallback assets.

The original family names appear only to acknowledge sources. `Cubic` and `俐方體` are reserved by the Cubic 11 project; `Pomicons` and `Font Awesome` are reserved source names. Source authors and trademark owners do not endorse this modified family.

## Text sources

- `licenses/DepartureMono.txt`: Departure Mono 1.500, OFL-1.1. No Reserved Font Name is declared in its bundled license.
- `licenses/Cubic11.txt`: Cubic 11 1.500 and inherited M+ notices, OFL-1.1.
- `licenses/Cubic11Naming.txt`: Cubic 11's pinned reserved-name declaration.

## Nerd Fonts Symbols Mono 3.5.1

The icon input is Nerd Fonts release 3.5.1, commit `b894ea7803af6aade63d60a4381e006098ec9c4d`, archive SHA-256 `fdca3682534f6f65e1ccb2345b0362ccf67d9b8eca7c8025330946e93e2473bc`. `NerdSymbols.txt`, `NerdSymbolsReadme.txt`, `NerdFonts.txt`, and `NerdFontsAudit.txt` retain the pinned project notices and license audit.

| Component | Attribution and distribution record | Preserved notice |
| --- | --- | --- |
| Codicons | Microsoft; CC BY 4.0 | `Codicons.txt` |
| Devicons | Devicon contributors and legacy Devicons; MIT | `Devicons.txt`, `DeviconsLegacy.txt` |
| Extra glyphs | Source Foundry Hack contributors; MIT | `HackExtraGlyphs.txt` |
| Font Awesome 6.5.1.custom2 | Fonticons, Inc.; Nerd Fonts input includes a Font Awesome 7.3.1 solid `fa-volume` import/remix | `FontAwesome.txt`, `FontAwesome7.txt` |
| Font Awesome Extension | André Luiz Gava, 2017; MIT | `FontAwesomeExtension.txt` |
| Font Logos | Font Logos contributors; Unlicense | `FontLogos.txt` |
| Material Design Icons | Material Design Icons contributors; Apache-2.0 | `MaterialDesign.txt`, `Apache2.txt` |
| Octicons | GitHub; MIT | `Octicons.txt` |
| Seti | Jesse Weed and contributors; MIT | `Seti.txt`, `NerdFonts.txt` |
| Pomicons | Gabriele Lana; OFL-1.1 | `Pomicons.txt` |
| Powerline Extra | Powerline Extra Symbols contributors; MIT | `PowerlineExtra.txt` |
| Powerline Symbols | Powerline contributors; permissive notice | `PowerlineSymbols.txt` |
| Power Symbols IEC | Joe Loughry and contributors; MIT | `PowerSymbolsIEC.txt` |
| Weather Icons | Lukas Bischoff (original designs) and Erik Flowers (v1.1+ art); OFL-1.1 | `WeatherIcons.txt`, `WeatherIconsCredit.txt` |

Nerd Fonts also repaired the Codicons glyph outlines at U+EA91 and U+EBF0 before this project imported them. Both mappings remain in DeparturePixelZh and DeparturePixelZh Compact. This records those earlier modifications in addition to the merging, scaling, and remapping described above. The pinned [Nerd Fonts Codicons source note](https://github.com/ryanoasis/nerd-fonts/blob/b894ea7803af6aade63d60a4381e006098ec9c4d/src/glyphs/codicons/README.md) documents these repairs.

Nerd Fonts' Font Awesome source README identifies the base as 6.5.1.custom2 and states that it adds one Font Awesome 7.3.1 solid `fa-volume` glyph. The pinned Nerd source was imported or remixed, so this project records provenance instead of claiming that the raw SVG files are byte-identical. Font Awesome 7.3.1 tag commit: `14c65a3747d0f3b751f15831fc719236aea8729d`; Nerd's addition commit: `accc7ee60f7fe2f04c1b991284ba4cdbb9688f25`.

`WeatherIcons.txt` preserves the exact Nerd Fonts OFL input, including its template form. `WeatherIconsCredit.txt` preserves the Weather Icons 2.0.10 credit information required to identify Lukas Bischoff and Erik Flowers.

Brand marks remain trademarks of their respective owners. Their inclusion does not grant branding rights or imply endorsement.
