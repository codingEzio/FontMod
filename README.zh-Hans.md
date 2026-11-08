# FontMod — 仅工具源代码

[English](README.md) · [简体中文](README.zh-Hans.md) · [繁體中文](README.zh-Hant.md) · [Español](README.es.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

本仓库包含工具及许可声明，不包含源字体或图像。请依 [TOOL-INPUTS.md](TOOL-INPUTS.md) 的路径和哈希自备有权使用的输入。

运行 `./fontmod source-check`、`./fontmod setup`，再运行 `./fontmod build --departure-build /path/to/build`。setup 需要网络；输入缺失或哈希不符时构建失败。完整混合字体保留 Nerd 字形；第三方图案和商标权仍待确认。本工具发布不授权发布生成的字体。见[许可范围](LICENSE-SCOPE.md)与[交付说明](RELEASE.md)。

可选的 RysaMix 与 Glyphgrove 工具使用外部输入，见 [TOOL-INPUTS.md](TOOL-INPUTS.md)。字体及衍生作品的许可独立于工具许可。
