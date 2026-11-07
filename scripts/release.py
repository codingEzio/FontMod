"""Explicit local release packaging and standard-library archive readback.

No font build, installation, network request or Git mutation is performed.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import zipfile

import maintenance


def rename_font(source, destination, previous, family):
    """Change existing identity strings; prove every non-name table unchanged."""
    from fontTools.ttLib import TTFont
    before = TTFont(source, lazy=True, recalcTimestamp=False)
    if before['name'].getDebugName(1) != previous:
        raise ValueError('Candidate family differs: ' + source.name)
    tables = {tag: before.getTableData(tag) for tag in before.keys() if tag != 'GlyphOrder'}
    for record in before['name'].names:
        text = record.toUnicode()
        if previous in text:
            record.string = text.replace(previous, family)
    before.save(destination)
    after = TTFont(destination, lazy=True, recalcTimestamp=False)
    if set(before.keys()) != set(after.keys()):
        raise ValueError('Naming conversion changed table inventory')
    compared = []
    for tag, data in tables.items():
        if tag == 'name':
            continue
        current = after.getTableData(tag)
        if tag == 'head':
            # File-level checkSumAdjustment changes when the name table changes.
            current = current[:8] + b'\0' * 4 + current[12:]
            data = data[:8] + b'\0' * 4 + data[12:]
        if current != data:
            raise ValueError('Naming conversion changed table: ' + tag + ' / ' + source.name)
        compared.append(tag)
    for identifier in [1, 3, 4, 6, 16]:
        values = [r.toUnicode() for r in after['name'].names if r.nameID == identifier]
        if not values or any(previous in v for v in values):
            raise ValueError('Old primary name remains')
    return {'file': destination.name, 'previousFamily': previous, 'family': family,
            'sourceSha256': sha(source), 'sha256': sha(destination),
            'unchangedTables': compared, 'headDifference': 'checkSumAdjustment only'}


def rename_candidate(root, source_final, destination):
    """Create a fresh metadata-only naming candidate. Never alter source fonts."""
    import copy as values
    import font_pack
    source_final, destination = Path(source_final), Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('Candidate destination already exists')
    original = json.loads((source_final / 'provenance.json').read_text())
    recipe = json.loads((root / 'final_fonts.json').read_text())
    expected = values.deepcopy(original['recipe'])
    if len(expected['fonts']) != 5 or len(recipe['fonts']) != 5:
        raise ValueError('Naming conversion requires the five verified mixed families')
    mapping = {}
    reserved = json.loads((root / 'RELEASE-RIGHTS.json').read_text())['reservedPrimaryNames']
    for old, new in zip(expected['fonts'], recipe['fonts']):
        previous = old['family']
        if previous.replace('ZhCubic11', 'Zh') != new['family'] or previous == new['family']:
            raise ValueError('Candidate only supports the owner-approved minimal naming change')
        if any(word.casefold() in new['family'].casefold() for word in reserved):
            raise ValueError('Candidate primary name contains a reserved source name')
        mapping[previous] = new['family']
        old['family'] = new['family']
    if expected != recipe:
        raise ValueError('Candidate recipe changes more than names; run a full source build')
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='delete_after_use_names_', dir=destination.parent))
    try:
        changes = []
        report = values.deepcopy(original)
        report['recipe'] = recipe
        for asset in report['assets']:
            previous = asset['family']
            family = mapping[previous]
            for extension in ['ttf', 'woff2']:
                source = source_final / asset[extension]
                if sha(source) != asset[extension + 'Sha256']:
                    raise ValueError('Source mixed font differs')
                target = stage / (family + '.' + extension)
                changes.append(rename_font(source, target, previous, family))
                asset[extension] = target.name
                asset[extension + 'Sha256'] = sha(target)
                asset[extension + 'Bytes'] = target.stat().st_size
            asset['family'] = family
        common = ['NOTICE.md', 'emoji-preparation.json', 'Emoji3D-Production.ttf']
        common += [p.relative_to(source_final).as_posix() for name in ['licenses', 'departure-package']
                   for p in (source_final / name).rglob('*') if p.is_file()]
        common += [name + extension for name in ['DeparturePixelZh-Regular', 'DeparturePixelZhCompact-Regular']
                   for extension in ['.ttf', '.woff2']]
        for name in common:
            copy(source_final / name, stage / name)
        (stage / 'web').mkdir()
        web = json.loads((source_final / 'web/provenance.json').read_text())
        web['recipe'] = recipe
        for asset in web['assets']:
            previous = asset['family']
            family = mapping.get(previous)
            for extension in ['ttf', 'woff2']:
                source = source_final / 'web' / asset[extension]
                if sha(source) != asset[extension + 'Sha256']:
                    raise ValueError('Source platform font differs')
                target = stage / 'web' / ((family + '.' + extension) if family else asset[extension])
                if family:
                    changes.append(rename_font(source, target, previous, family))
                else:
                    copy(source, target)
                asset[extension] = target.name
                asset[extension + 'Sha256'] = sha(target)
                asset[extension + 'Bytes'] = target.stat().st_size
            if family:
                asset['family'] = family
                asset['sourceSha256'] = next(a['ttfSha256'] for a in report['assets'] if a['family'] == family)
        name_report = {'scope': 'Public primary names only; no glyph/axis/metric/source changes.',
                       'sourceProvenanceSha256': sha(source_final / 'provenance.json'), 'fonts': changes}
        report['publicNaming'] = {'receipt': 'name-change.json', 'sourceProvenanceSha256': name_report['sourceProvenanceSha256']}
        write(stage / 'name-change.json', name_report)
        write(stage / 'provenance.json', report)
        write(stage / 'web/provenance.json', web)
        font_pack.build(stage)
        stage.rename(destination)
        return {'result': 'pass', 'renamedFiles': len(changes),
                'nonNameTables': 'byte-identical; head checksum adjustment only', 'via': 'rebuilt and byte-reconstructed'}
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def files(root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Missing or unsafe package directory: ' + str(root))
    result = []
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Release cannot contain symlinks: ' + str(path))
        if path.is_file():
            result.append({'path': path.relative_to(root).as_posix(), 'sha256': sha(path),
                           'bytes': path.stat().st_size, 'mode': stat.S_IMODE(path.stat().st_mode)})
    return sorted(result, key=lambda item: item['path'])


def safe_name(name):
    path = Path(name)
    if path.is_absolute() or '..' in path.parts or path.as_posix() != name:
        raise ValueError('Unsafe release path: ' + name)
    return path


def copy(source, destination, expected=None):
    if source.is_symlink() or not source.is_file():
        raise ValueError('Missing or unsafe release input: ' + str(source))
    expected = expected or sha(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    if sha(source) != expected or sha(destination) != expected:
        raise ValueError('Release input changed: ' + str(source))


def verify(directory):
    """Verify exact unpacked and ZIP inventories. Hashes do not prove authorship."""
    directory = Path(directory).absolute()
    manifest = json.loads((directory / 'release-manifest.json').read_text())
    expected_top = {'release-manifest.json', 'SHA256SUMS', *manifest['entryFiles']}
    for item in manifest['packages']:
        name = str(safe_name(item['directory']))
        archive_name = str(safe_name(item['archive']))
        expected_top.update([name, archive_name])
        if files(directory / name) != item['files']:
            raise ValueError('Package directory differs: ' + name)
        archive = directory / archive_name
        if archive.is_symlink() or sha(archive) != item['sha256']:
            raise ValueError('Package archive differs: ' + archive_name)
        with zipfile.ZipFile(archive) as zipped:
            infos = zipped.infolist()
            if sorted(i.filename for i in infos) != [f['path'] for f in item['files']]:
                raise ValueError('Archive inventory differs: ' + archive_name)
            for info, record in zip(sorted(infos, key=lambda i: i.filename), item['files']):
                if (hashlib.sha256(zipped.read(info)).hexdigest() != record['sha256']
                        or stat.S_IMODE(info.external_attr >> 16) != record['mode']):
                    raise ValueError('Archive byte/mode differs: ' + info.filename)
    for name, digest in manifest['entryFiles'].items():
        if sha(directory / safe_name(name)) != digest:
            raise ValueError('Release entry differs: ' + name)
    sums = ''.join(p['sha256'] + '  ' + p['archive'] + '\n' for p in manifest['packages'])
    if (directory / 'SHA256SUMS').read_text() != sums:
        raise ValueError('Checksum list differs')
    if {p.name for p in directory.iterdir()} != expected_top:
        raise ValueError('Unexpected release entry')
    return {'result': 'pass', 'archives': len(manifest['packages']),
            'files': sum(len(p['files']) for p in manifest['packages']),
            'publicReleaseStatus': manifest.get('rightsReview', {}).get('status', 'not-recorded'),
            'recipeVersion': manifest['recipeVersion'], 'sourceRevision': manifest['sourceRevision']}


def check_rights_hold(directory):
    """Check the verified candidate's recorded rights hold, not publication authority."""
    directory = Path(directory).absolute()
    manifest = json.loads((directory / 'release-manifest.json').read_text())
    review = manifest.get('rightsReview')
    entries = manifest.get('entryFiles', {})
    rights_path = directory / 'RELEASE-RIGHTS.json'
    if not isinstance(review, dict) or entries.get('RELEASE-RIGHTS.json') != sha(rights_path):
        raise ValueError('Missing or unbound rights review')
    rights = json.loads(rights_path.read_text())
    decisions = rights.get('blockingDecisions')
    if (not isinstance(decisions, list) or any(not isinstance(x, dict) or not isinstance(x.get('id'), str)
            or not x['id'] for x in decisions)):
        raise ValueError('Invalid rights decisions')
    if review.get('sha256') != sha(rights_path) or review.get('status') != rights.get('status') or review.get('blockingDecisions') != [x['id'] for x in decisions]:
        raise ValueError('Rights review differs from candidate')
    if decisions:
        raise ValueError('Unresolved rights decisions: ' + ', '.join(x['id'] for x in decisions))


def check_dependencies(root, departure_build=None):
    policy = json.loads((root / 'release-dependencies.json').read_text())
    count = 0
    for record in policy['sources']:
        directory = root / 'dependencies' / record['name']
        for item in record['files']:
            path = directory / safe_name(item['path'])
            if (path.is_symlink() or sha(path) != item['sha256']
                    or stat.S_IMODE(path.stat().st_mode) != item['mode']):
                raise ValueError('Dependency source differs: ' + record['name'] + '/' + item['path'])
            count += 1
    derived = policy['derivedRecipe']
    expected = prepare_departure_recipe(root / derived['upstreamPath'])
    if ((root / derived['path']).read_bytes() != expected
            or hashlib.sha256(expected).hexdigest() != derived['sha256']):
        raise ValueError('FontMod document-only Departure recipe differs')
    output_count = 0
    if departure_build is not None:
        for name, digest in policy['departureFontHashes'].items():
            if sha(Path(departure_build) / name) != digest:
                raise ValueError('Rebuilt Departure font differs: ' + name)
            output_count += 1
    return {'result': 'pass', 'dependencies': len(policy['sources']), 'files': count,
            'derivedRecipe': 'documents only; other fields identical',
            'rebuiltFontHashes': output_count, 'identity': 'source hashes; original Git history excluded'}


def prepare_departure_recipe(upstream):
    recipe = json.loads(upstream.read_text())
    recipe['documents'] = ['NOTICE.md', 'OFL.txt']
    return (json.dumps(recipe, ensure_ascii=False, indent=2) + '\n').encode()


def export(root, destination, revision, dependency_roots):
    if not re.fullmatch(r'[0-9a-f]{40}', revision or ''):
        raise ValueError('release-export requires the exact --source-revision (40 hex characters)')
    root = Path(root)
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('Release output already exists; choose a new directory')
    import font_bundle
    destination.parent.mkdir(parents=True, exist_ok=True)
    # collect also checks source pins, notices, syntax and selected private patterns.
    source_files, modes = maintenance.collect()
    deps = json.loads((root / 'release-dependencies.json').read_text())
    stage = Path(tempfile.mkdtemp(prefix='delete_after_use_release_', dir=destination.parent))
    try:
        source = stage / 'fontmod-source'
        source.mkdir()
        for name, data in source_files.items():
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(modes[name])
        write(source / 'source-receipt.json', {'sourceRevision': revision,
              'historyIncluded': False, 'files': files(source)})
        for record, dependency_root in zip(deps['sources'], dependency_roots):
            dependency_root = Path(dependency_root)
            for item in record['files']:
                name = safe_name(item['path'])
                original = dependency_root / name
                if stat.S_IMODE(original.stat().st_mode) != item['mode']:
                    raise ValueError('Dependency mode differs: ' + str(original))
                target = source / 'dependencies' / record['name'] / name
                copy(original, target, item['sha256'])
        derived = deps['derivedRecipe']
        prepared = prepare_departure_recipe(source / derived['upstreamPath'])
        if hashlib.sha256(prepared).hexdigest() != derived['sha256']:
            raise ValueError('Prepared Departure recipe differs')
        (source / derived['path']).write_bytes(prepared)
        # All selected dependency text must pass the same public-pattern checks.
        for path in (source / 'dependencies').rglob('*'):
            if path.is_file():
                try:
                    text = path.read_text()
                except UnicodeDecodeError:
                    continue
                for category, pattern in maintenance.PATTERNS.items():
                    if pattern.search(text):
                        raise ValueError(category + ': ' + str(path.relative_to(source)))
        report = json.loads((root / 'Final/provenance.json').read_text())
        departure = json.loads((root / 'Final/departure-package/provenance.json').read_text())
        final = root / 'Final'
        # The five mixed faces carry these exact raw/component notices.
        notices = [root / name for name in json.loads((root / 'release-files.json').read_text())['requiredNotices']
                   if name.startswith('sources/')]
        if {p.name for p in (final / 'licenses').iterdir()} != {p.name for p in notices}:
            raise ValueError('Mixed font notice inventory differs')
        for original in notices:
            if sha(final / 'licenses' / original.name) != sha(original):
                raise ValueError('Mixed font notice differs: ' + original.name)
        # Departure keeps its independent producer terms and naming notices.
        departure_notices = []
        for item in deps['sources'][0]['files']:
            name = item['path']
            if name in {'NOTICE.md', 'OFL.txt'} or name.startswith('licenses/'):
                retained = final / 'departure-package' / (name.replace('licenses/', 'Licenses/', 1))
                if sha(retained) != item['sha256']:
                    raise ValueError('Departure notice differs: ' + name)
                departure_notices.append(retained)
        common = [final / 'NOTICE.md', final / 'provenance.json', final / 'emoji-preparation.json']
        if report.get('publicNaming'):
            common.append(final / report['publicNaming']['receipt'])
        common += [final / 'licenses' / p.name for p in notices]
        common += departure_notices + [final / 'departure-package/provenance.json']
        if {p.relative_to(final / 'departure-package').as_posix() for p in (final / 'departure-package').rglob('*') if p.is_file()} != {p.relative_to(final / 'departure-package').as_posix() for p in departure_notices} | {'provenance.json'}:
            raise ValueError('Departure notice inventory differs')
        native = [final / a['ttf'] for a in report['assets']]
        for name in ['DeparturePixelZh-Regular.ttf', 'DeparturePixelZhCompact-Regular.ttf']:
            if sha(final / name) != departure['files'][name]:
                raise ValueError('Departure derived output differs: ' + name)
            native.append(final / name)
        platform = [final / 'web/provenance.json', final / 'via-font-pack.js', final / 'via-font-pack.json']
        web = json.loads((final / 'web/provenance.json').read_text())
        if web['recipe'] != report['recipe']:
            raise ValueError('Platform recipe differs')
        for asset in web['assets']:
            for extension in ['ttf', 'woff2']:
                if sha(final / 'web' / asset[extension]) != asset[extension + 'Sha256']:
                    raise ValueError('Platform font differs: ' + asset[extension])
                platform.append(final / 'web' / asset[extension])
        via = json.loads((final / 'via-font-pack.json').read_text())
        if sha(final / 'via-font-pack.js') != via['sha256']:
            raise ValueError('VIA script differs')
        for name, selected in [('fontmod-native', native), ('fontmod-platform', platform)]:
            target = stage / name
            for path in selected + common:
                dest = target / path.relative_to(final)
                if path.suffix == '.json':
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    write(dest, font_bundle.portable_provenance(json.loads(path.read_text()), root))
                else:
                    copy(path, dest)
            for doc in ['LICENSE', 'LICENSE-SCOPE.md', 'RELEASE.md', 'RELEASE.zh-Hant.md', 'RELEASE.en.md']:
                copy(root / doc, target / doc.replace('RELEASE.', 'README.'))
            for doc in ['THIRD-PARTY-NOTICES.md', 'RELEASE-RIGHTS.json', 'notices/Cubic11Naming.txt']:
                copy(root / doc, target / doc)
        families = []
        catalog = font_bundle.catalog(root)
        if len(catalog) != 7:
            raise ValueError('The release requires exactly seven current families')
        for entry in catalog:
            name = 'fontmod-' + font_bundle.slug(entry['family'])
            font_bundle.export(root, entry, font_bundle.select_styles(entry, ['all']), stage / name)
            families.append({'directory': name, 'family': entry['family']})
        packages = []
        for directory in sorted(p for p in stage.iterdir() if p.is_dir()):
            inventory = files(directory)
            archive = directory.with_suffix('.zip')
            with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_STORED) as zipped:
                for item in inventory:
                    zipped.write(directory / item['path'], item['path'])
            packages.append({'directory': directory.name, 'archive': archive.name,
                             'sha256': sha(archive), 'bytes': archive.stat().st_size, 'files': inventory})
        entry_files = {}
        for language in ['md', 'zh-Hant.md', 'en.md']:
            name = 'README.' + language
            copy(root / ('RELEASE.' + language), stage / name)
            entry_files[name] = sha(stage / name)
        for name in ['THIRD-PARTY-NOTICES.md', 'RELEASE-RIGHTS.json']:
            copy(root / name, stage / name)
            entry_files[name] = sha(stage / name)
        rights = json.loads((root / 'RELEASE-RIGHTS.json').read_text())
        manifest = {'schemaVersion': 1, 'status': 'local-candidate-only', 'sourceRevision': revision,
                    'recipeVersion': report['version'], 'recipeSha256': sha(root / 'final_fonts.json'),
                    'fontBuildProvenanceSha256': sha(final / 'provenance.json'),
                    'dependencySources': [{k: v for k, v in r.items() if k != 'files'} for r in deps['sources']],
                    'derivedDependencyRecipe': deps['derivedRecipe'],
                    'rightsReview': {'status': rights['status'], 'sha256': sha(root / 'RELEASE-RIGHTS.json'),
                                     'blockingDecisions': [v['id'] for v in rights['blockingDecisions']]},
                    'families': families, 'entryFiles': entry_files, 'packages': packages,
                    'limits': ['Original Git history excluded; no publication or installation.',
                               'Dependency source-only rebuild uses explicit development mode; not original Git pin attestation.',
                               'Installed applications, Safari and Android are unverified.',
                               'Preserved source/component terms are not a universal legal clearance.']}
        write(stage / 'release-manifest.json', manifest)
        (stage / 'SHA256SUMS').write_text(''.join(p['sha256'] + '  ' + p['archive'] + '\n' for p in packages))
        result = verify(stage)
        stage.rename(destination)
        return result
    finally:
        if stage.exists():
            shutil.rmtree(stage)
