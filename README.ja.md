# FontMod — ツールのソースのみ

[English](README.md) · [简体中文](README.zh-Hans.md) · [繁體中文](README.zh-Hant.md) · [Español](README.es.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

このリポジトリにはツールとライセンス通知が含まれ、フォントや画像は含まれません。[TOOL-INPUTS.md](TOOL-INPUTS.md) のパスとハッシュに一致する、使用権のある入力をご用意ください。

`./fontmod source-check`、`./fontmod setup`、`./fontmod build --departure-build /path/to/build` を実行します。setup はネット接続が必要です。入力がない場合やハッシュが違う場合、ビルドは失敗します。Nerd 字形は保持されます。第三者の図形と商標の権利は未確認で、このツールの公開は生成フォントの公開を許可するものではありません。[ライセンス](LICENSE-SCOPE.md)・[英語の案内](RELEASE.en.md)。

setup 後に `./fontmod prepare-emoji /path/to/Noto-3D-128.ttf /path/to/input-root/sources/Noto3D-64.ttf` で Emoji 入力を用意します。両方のハッシュを検証し、既存ファイルは上書きしません。

任意の RysaMix と Glyphgrove ツールは外部入力を使用します。[TOOL-INPUTS.md](TOOL-INPUTS.md) を参照してください。フォントと派生物のライセンスはツールとは別です。
