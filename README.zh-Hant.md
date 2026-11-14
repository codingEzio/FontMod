# FontMod — 僅工具原始碼

[English](README.md) · [简体中文](README.zh-Hans.md) · [繁體中文](README.zh-Hant.md) · [Español](README.es.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

本儲存庫包含工具及授權聲明，不含來源字型或圖像。請依 [TOOL-INPUTS.md](TOOL-INPUTS.md) 的路徑與雜湊自備有權使用的輸入。

執行 `./fontmod source-check`、`./fontmod setup`，再執行 `./fontmod build --departure-build /path/to/build`。setup 需要網路；輸入缺少或雜湊不符時建置失敗。完整混合字型保留 Nerd 字形；第三方圖案及商標權仍待確認。本工具發布不授權發布產出的字型。見 [授權範圍](LICENSE-SCOPE.md)與[交付說明](RELEASE.zh-Hant.md)。

setup 後執行 `./fontmod prepare-emoji /path/to/Noto-3D-128.ttf /path/to/input-root/sources/Noto3D-64.ttf` 來準備 Emoji 輸入；命令會驗證兩個檔案的雜湊，且不會覆蓋現有檔案。

可選的 RysaMix 與 Glyphgrove 工具使用外部輸入，見 [TOOL-INPUTS.md](TOOL-INPUTS.md)。字型及衍生作品的授權獨立於工具授權。
