"""Portable, selected-style exports from the custom preview catalog.

No font geometry is changed. A variable binary is shared by its selected CSS
presets; upstream license and distribution restrictions remain attached.
"""
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import uuid
import zipfile

import font_preview
from fontTools.ttLib import TTFont


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def catalog(root, include_archived=False):
    from final_cli import entries
    extras = entries()
    for item in extras:
        item['file'] = str(root / item['file']) if not Path(item['file']).is_absolute() else item['file']
    result = font_preview.prepare_local(root, [], extras)
    return json.loads(Path(result['catalogFile']).read_text())['families']


def select_styles(entry, names):
    available = {style['name']: style for style in entry['styles']}
    requested = list(available) if not names or names == ['all'] else names
    unknown = set(requested) - set(available)
    if unknown:
        raise ValueError('Unknown variants: ' + ', '.join(sorted(unknown)) + '; available: ' + ', '.join(available))
    if len(requested) != len(set(requested)):
        raise ValueError('Duplicate variants are not allowed')
    return [available[name] for name in requested]


def source_package(root, entry):
    """Resolve producer-owned notices and verify its existing output contract."""
    file = Path(entry['sourceFile'])
    if entry.get('bundleAdapter') == 'final':
        report = json.loads((root / 'Final/provenance.json').read_text())
        if not any(a['woff2'] == file.name and a['woff2Sha256'] == entry['sha256'] for a in report['assets']):
            raise ValueError('Final font provenance differs')
        return file.parent, root, file.parent / 'licenses', report
    # FontMod applies its symbol aliases; its derived hashes differ from producer hashes.
    directory = root / 'Final/departure-package'
    report = json.loads((directory / 'provenance.json').read_text())
    if report['files'].get(file.name) != entry['sha256']:
        raise ValueError('DeparturePixelZh derived hash mismatch')
    return directory, root, directory / 'Licenses', report


def copy_checked(source, destination, expected=None):
    expected = expected or sha(source)
    shutil.copyfile(source, destination)
    if sha(destination) != expected or sha(source) != expected:
        raise ValueError('Asset changed during export: ' + source.name)


def slug(value):
    return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')


def portable_provenance(value, owner, field=None):
    import font_mixed_support as delivery
    if isinstance(value, dict):
        return {key: portable_provenance(item, owner, key) for key, item in value.items()}
    if isinstance(value, list):
        return [portable_provenance(item, owner, field) for item in value]
    # This upstream field is an archive-member suffix, not a host filesystem path.
    if field == 'member_suffix' and isinstance(value, str) and re.fullmatch(r'/[^/]+\.(?:ttf|otf)', value):
        return value
    return delivery.portable_record(value, owner)


def export(root, entry, styles, destination, target='both', matches=(), asset_path='fonts/custom', archive=False):
    import font_mixed_support as delivery
    if target not in {'web', 'extension', 'both'}:
        raise ValueError('Target must be web, extension, or both')
    if not re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*', asset_path):
        raise ValueError('Extension asset path must be a relative directory without dots or traversal')
    for match in matches:
        if not re.fullmatch(r'https?://(?:\*\.)?[A-Za-z0-9.-]+(?::[0-9]+)?/[^\s]*', match):
            raise ValueError('Use explicit http(s) origins for --match, e.g. https://example.com/*')
    source, owner, licenses, provenance = source_package(root, entry)
    if licenses is not None and (not licenses.is_dir() or not any(p.is_file() for p in licenses.rglob('*')) or not (source / 'NOTICE.md').is_file()):
        raise ValueError('Missing complete source licenses/NOTICE')
    destination = Path(destination).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('Export destination already exists; choose a new directory: ' + str(destination))
    zip_path = destination.with_name(destination.name + '.zip')
    if archive and zip_path.exists():
        raise ValueError('ZIP already exists: ' + str(zip_path))
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='delete_after_use_bundle_', dir=destination.parent))
    try:
        (stage / 'fonts').mkdir()
        if licenses is None:
            (stage / 'licenses').mkdir()
            copy_checked(source / provenance['licenseFile'], stage / 'licenses' / provenance['licenseFile'])
            (stage / 'NOTICE.md').write_text('Original Geist WOFF2, unchanged. Source URL and SHA-256 are recorded in source-provenance.json. Preserve the accompanying SIL Open Font License.\n')
        else:
            shutil.copytree(licenses, stage / 'licenses')
        for original in (licenses.rglob('*') if licenses is not None else []):
            if original.is_file() and sha(original) != sha(stage / 'licenses' / original.relative_to(licenses)):
                raise ValueError('License copy mismatch')
        if licenses is not None:
            copy_checked(source / 'NOTICE.md', stage / 'NOTICE.md')
        if (source / 'OFL.txt').is_file():
            copy_checked(source / 'OFL.txt', stage / 'OFL.txt')
        write(stage / 'source-provenance.json', portable_provenance(provenance, owner))
        if (source / 'name-change.json').is_file():
            copy_checked(source / 'name-change.json', stage / 'name-change.json')
        rights = json.loads((root / 'RELEASE-RIGHTS.json').read_text())
        for name in ['THIRD-PARTY-NOTICES.md', 'RELEASE-RIGHTS.json', 'notices/Cubic11Naming.txt']:
            notice_target = stage / name
            notice_target.parent.mkdir(parents=True, exist_ok=True)
            copy_checked(root / name, notice_target)
        files = entry.get('fontFiles') or [{'fontUrl': entry['fontUrl'], 'sha256': entry['sha256']}]
        portable_files = []
        for item in files:
            original = (root / '.cache/FontPreview' / item['fontUrl']).resolve(strict=True)
            if sha(original) != item['sha256']:
                raise ValueError('Font hash mismatch: ' + original.name)
            with original.open('rb') as handle:
                signature = handle.read(4)
            if signature != b'wOF2':
                raise ValueError('Only source-derived WOFF2 is exported')
            with TTFont(original, lazy=True) as font:
                actual_family = font['name'].getDebugName(16) or font['name'].getDebugName(1)
                if actual_family != entry['family']:
                    raise ValueError('Font family identity mismatch')
            url = 'fonts/' + original.name
            copy_checked(original, stage / url, item['sha256'])
            portable_files.append({'fontUrl': url, **{k: item[k] for k in ('unicodeRange', 'sha256') if k in item}})
        alias = 'Bundled-' + re.sub(r'[^A-Za-z0-9-]', '-', entry.get('bundleName', entry['family']))
        rules = []
        weights=[style["coordinates"]["wght"] for style in entry["styles"] if "wght" in style["coordinates"]]
        declared_weight=(f"{min(weights):g} {max(weights):g}" if weights and min(weights)!=max(weights) else str(entry["metadataWeight"]))
        for item in portable_files:
            ranges = '\n  unicode-range: ' + item['unicodeRange'] + ';' if 'unicodeRange' in item else ''
            rules.append('@font-face {\n  font-family: ' + json.dumps(alias) + ';\n  src: url(' + json.dumps(item['fontUrl']) + ') format("woff2");\n  font-style: normal; font-weight: ' + ('100 900' if any(a.get('tag')=='wght' for a in entry.get('axes',[])) else str(entry['metadataWeight'])) + ';\n  font-display: swap;' + ranges + '\n}')
        classes = []
        for style in styles:
            name = 'fontmod-' + slug(entry.get('bundleName', entry['family'])) + '-' + slug(style['name'])
            if name in classes:
                raise ValueError('Variant CSS class collision')
            classes.append(name)
            coordinates = ', '.join(json.dumps(axis) + ' ' + str(value) for axis, value in style['coordinates'].items()) or 'normal'
            rules.append('.' + name + ' {\n  font-family: ' + json.dumps(alias) + ', system-ui, sans-serif;\n  font-weight: ' + str(entry['metadataWeight']) + '; font-style: normal;\n  font-synthesis: none;\n  font-variation-settings: ' + coordinates + ';\n}')
        css = '\n\n'.join(rules) + '\n'
        (stage / 'fonts.css').write_text(css)
        if target in {'extension', 'both'}:
            (stage / 'extension-fonts.js').write_text('const css = ' + json.dumps(css) + ';\nexport function fontCSS(runtime, basePath = ' + json.dumps(asset_path) + ') {\n  return css.replace(/url\\("([^"\\n]+)"\\)/g, (_, path) => "url(" + JSON.stringify(runtime.getURL(basePath.replace(/\\/$/, "") + "/" + path)) + ")");\n}\n')
            write(stage / 'manifest.fragment.json', {'web_accessible_resources': [{'resources': [asset_path + '/fonts/*.woff2'], 'matches': list(matches) or ['https://example.invalid/*']}]})
        preview = dict(entry, fontUrl=portable_files[0]['fontUrl'], styles=styles, label=entry['family'])
        for key in ['sourceFile', 'packageDirectory', 'sha256', 'bytes', 'installationStatus']:
            preview.pop(key, None)
        if entry.get('fontFiles'):
            preview['fontFiles'] = portable_files
        font_preview.write_catalog(stage / 'preview_catalog.json', [preview])
        shutil.copyfile(root / 'templates/web_bundle/preview.html', stage / 'preview.html')
        examples = ''.join('<section><h2>' + html.escape(style['name']) + '</h2><p id="example-' + str(index) + '" class="' + classes[index] + '">中文 English 0123 😀 · A small detail changes the rhythm.</p></section>' for index, style in enumerate(styles))
        (stage / 'example.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + html.escape(entry['family']) + '</title><link rel="stylesheet" href="fonts.css"><style>:root{color-scheme:light dark;background:Canvas;color:CanvasText}body{margin:24px;font:16px/1.8 system-ui}h1{overflow-wrap:anywhere;font-size:clamp(1.25rem,4vw,2rem);line-height:1.35}section{padding:12px;border-top:1px solid}p{font-size:24px;overflow-wrap:anywhere}@media(max-width:480px){body{margin:16px}section{padding:12px 0}}</style><h1>' + html.escape(entry['family']) + '</h1>' + examples)
        restricted = entry.get('distribution') == 'restricted'
        permission = 'PRIVATE EXPERIMENT ONLY. Source permission restrictions remain; no combined redistribution license is granted.\n' if restricted else 'Preserve NOTICE, original licenses, source provenance and bundle.json when embedding or redistributing.\n'
        manifest = {'schemaVersion': 1, 'font': entry.get('bundleName', entry['family']), 'family': entry['family'], 'styles': styles,
                    'publicReleaseStatus': rights['status'], 'familyRightsStatus': rights['familyStatus'][entry['family']],
                    'cssClasses': dict(zip([s['name'] for s in styles], classes)), 'target': target,
                    'fontFamilyAlias': alias, 'variableBinaryPolicy': 'Source WOFF2 retained byte-for-byte; CSS exposes selected named presets only. Other source axes/instances remain in the binary.',
                    'distribution': 'restricted-private-experiment' if restricted else 'source-licenses-retained',
                    'extensionAssetPath': asset_path if target != 'web' else None,
                    'fontBytes': sum((stage / item['fontUrl']).stat().st_size for item in portable_files),
                    'sourceFontSha256': entry['sha256'], 'sourceProject': owner.name,
                    'files': {str(p.relative_to(stage)): sha(p) for p in sorted(stage.rglob('*')) if p.is_file()}}
        usage = '\n'.join('<p class="' + css_class + '">中文 English 0123 😀</p>' for css_class in classes)
        translations = {
            'README.md': ('字体包', '把整个目录复制进网页资源目录，然后引用 fonts.css。样式见下方 CSS 类。', '扩展：把目录复制到 ' + asset_path + '，通过 extension-fonts.js 的 fontCSS(chrome.runtime) 生成内容脚本 CSS；将 manifest.fragment.json 合并到扩展清单。未指定 --match 时 example.invalid 是占位来源，需替换为真实目标站点。', '可变 WOFF2 只保存一份；选择只限制生成的 CSS 预设，不裁剪原始轴、字形或语言。预览页须经 HTTP 打开。'),
            'README.zh-Hant.md': ('字體包', '將整個目錄複製到網頁資源目錄，再引用 fonts.css。樣式見下方 CSS 類別。', '擴充套件：將目錄複製到 ' + asset_path + '，使用 extension-fonts.js 的 fontCSS(chrome.runtime) 產生內容指令碼 CSS；合併 manifest.fragment.json。未指定 --match 時須將 example.invalid 換成實際目標網站。', '可變 WOFF2 僅保存一份；選擇僅限制 CSS 預設，不裁剪原始軸、字形或語言。預覽頁須透過 HTTP 開啟。'),
            'README.en.md': ('Font bundle', 'Copy this complete directory to your web assets and include fonts.css. Use the selected CSS classes below.', 'Extension: copy the directory to ' + asset_path + ', generate content CSS with fontCSS(chrome.runtime) from extension-fonts.js, and merge manifest.fragment.json. Without --match, example.invalid is a placeholder: replace it with your actual target origins.', 'One source variable WOFF2 is shared by all selected CSS presets. Original axes, glyphs and languages are not removed. Serve the preview over HTTP.')}
        for filename, (title, web, extension, policy) in translations.items():
            localized_permission = permission
            if filename == 'README.md':
                localized_permission = '仅限本机实验。保留来源的许可限制，不授予合并字体再分发许可。\n' if restricted else '嵌入或分发时保留 NOTICE、原始许可、来源记录和 bundle.json。\n'
            elif filename == 'README.zh-Hant.md':
                localized_permission = '僅限本機實驗。保留來源的授權限制，不授予合併字體再散布授權。\n' if restricted else '嵌入或散布時保留 NOTICE、原始授權、來源記錄與 bundle.json。\n'
            status_note = {
                'README.md': '公开家族名称避开已声明的保留名。RELEASE-RIGHTS.json 记录核对状态；组件归属、改动说明和具体条件见 THIRD-PARTY-NOTICES.md。\n',
                'README.zh-Hant.md': '公開家族名稱避開已聲明的保留名。RELEASE-RIGHTS.json 記錄核對狀態；元件歸屬、改動說明與具體條件見 THIRD-PARTY-NOTICES.md。\n',
                'README.en.md': 'Public family names avoid the declared reserved names. RELEASE-RIGHTS.json records the review status; THIRD-PARTY-NOTICES.md records attribution, modifications and specific conditions.\n'}[filename]
            localized_permission += '\n' + status_note
            text = '# ' + title + ' · ' + entry['family'] + '\n\n' + localized_permission + '\n' + (web + '\n\n' if target != 'extension' else '') + (extension + '\n\n' if target != 'web' else '') + policy + '\n\n```html\n<link rel="stylesheet" href="fonts.css">\n' + usage + '\n```\n'
            if target != 'web':
                text += '\n```js\n// Import through the extension’s existing module/build entry.\nimport { fontCSS } from "./' + asset_path + '/extension-fonts.js";\nconst style = document.createElement("style");\nstyle.textContent = fontCSS(chrome.runtime);\ndocument.documentElement.append(style);\n```\n'
            (stage / filename).write_text(text)
        # README files are also part of the checked portable inventory.
        manifest['files'].update({p.name: sha(p) for p in stage.glob('README*')})
        write(stage / 'bundle.json', manifest)
        for filename, digest in manifest['files'].items():
            if sha(stage / filename) != digest:
                raise ValueError('Export readback failed: ' + filename)
        if destination.exists():
            raise ValueError('Export destination was created by another process')
        os.rename(stage, destination)
        receipt = {'directory': str(destination), 'family': entry['family'], 'variants': [s['name'] for s in styles], 'target': target, 'fontFiles': len(portable_files), 'fontBytes': manifest['fontBytes'], 'distribution': manifest['distribution'], 'readbackVerified': True}
        if archive:
            with zipfile.ZipFile(zip_path, 'x', compression=zipfile.ZIP_STORED) as package:
                for file in sorted(destination.rglob('*')):
                    if file.is_file():
                        package.write(file, file.relative_to(destination))
            with zipfile.ZipFile(zip_path) as package:
                expected = manifest['files'] | {'bundle.json': sha(destination / 'bundle.json')}
                if set(package.namelist()) != set(expected) or any(hashlib.sha256(package.read(name)).hexdigest() != digest for name, digest in expected.items()):
                    raise ValueError('ZIP readback failed')
            receipt.update(zip=str(zip_path), zipSha256=sha(zip_path), zipReadbackVerified=True)
        return receipt
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def run(root, args):
    entries = catalog(root, include_archived=args.include_archived)
    if args.list_fonts:
        return [{'font': e.get('bundleName', e['family']), 'variants': [s['name'] for s in e['styles']],
                 'woff2Bytes': e.get('webBytes', e['bytes']), 'fontFiles': len(e.get('fontFiles', [e['fontUrl']])),
                 'distribution': e.get('distribution', 'source-licenses-retained')} for e in entries]
    interactive = not args.font and sys.stdin.isatty()
    if not args.font:
        if not interactive:
            raise ValueError('Use bundle --list-fonts, then --font NAME --variants NAME,NAME; or run bundle in a terminal for interactive selection')
        for number, entry in enumerate(entries, 1):
            web_bytes = entry.get('webBytes', entry['bytes'])
            print(f"{number:2}. {entry.get('bundleName', entry['family'])} · {web_bytes / 1000000:.2f} MB · {len(entry['styles'])} styles" + (' [PRIVATE EXPERIMENT]' if entry.get('distribution') == 'restricted' else ''), file=sys.stderr)
        try:
            index = int(input('Font / 字体编号: ')) - 1
        except ValueError:
            raise ValueError('Enter a font number')
        if not 0 <= index < len(entries):
            raise ValueError('Font number is out of range')
        entry = entries[index]
    else:
        found = [e for e in entries if e.get('bundleName', e['family']) == args.font]
        if not found:
            raise ValueError('Unknown custom font; run bundle --list-fonts')
        entry = found[0]
    names = [s.strip() for s in args.variants.split(',')] if args.variants else None
    if interactive and names is None and len(entry['styles']) > 1:
        available = [s['name'] for s in entry['styles']]
        print('Variants / 样式: ' + ', '.join(available), file=sys.stderr)
        choice = input('Variants, comma-separated / 样式逗号分隔 [all]: ').strip()
        names = [value.strip() for value in choice.split(',')] if choice else None
    styles = select_styles(entry, names)
    target = args.target or (input('Target / 用途 [web/extension/both, default both]: ').strip() if interactive else '') or 'both'
    suffix = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    destination = args.output or root / 'Deliveries/CustomBundles' / (slug(entry.get('bundleName', entry['family'])) + '-' + suffix)
    return export(root, entry, styles, destination, target, args.match, args.asset_path, args.zip)
