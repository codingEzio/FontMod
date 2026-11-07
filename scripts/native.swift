import AppKit
import CoreText
import CryptoKit

// Verify the real Core Text identity, normal-style lookup and glyph provider.
let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
let mode = CommandLine.arguments.dropFirst().first ?? "bundled"
guard CommandLine.arguments.count >= 3 else { fatalError("Pass the verified native manifest") }
let manifestURL = URL(fileURLWithPath: CommandLine.arguments[2])
let entries = try JSONSerialization.jsonObject(with: Data(contentsOf: manifestURL)) as! [[String: Any]]
let names = entries.map { $0["name"] as! String }
let installDirectory = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Fonts")
func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}
func sha(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
var reports: [[String: Any]] = []
var fonts: [CTFont] = []
for (index, name) in names.enumerated() {
    let entry = entries[index]
    let expectedFamily = entry["family"] as? String ?? name
    let source = URL(fileURLWithPath: entry["file"] as! String)
    let expectedSHA = entry["sha256"] as! String
    guard sha(try Data(contentsOf: source)) == expectedSHA else { fail("Source changed after manifest verification") }
    let url = mode == "bundled" ? source : installDirectory.appendingPathComponent(name + ".ttf")
    if mode == "install" {
        let bytes = try Data(contentsOf: source)
        try FileManager.default.createDirectory(at: installDirectory, withIntermediateDirectories: true)
        if FileManager.default.fileExists(atPath: url.path) {
            if sha(try Data(contentsOf: url)) != sha(bytes) {
                guard let prior = entry["replaceSha256"] as? String, sha(try Data(contentsOf: url)) == prior else { fail("Existing font differs from authorized replacement: \(url.path)") }
                var removalError: Unmanaged<CFError>?
                CTFontManagerUnregisterFontsForURL(url as CFURL, .user, &removalError)
                try bytes.write(to: url, options: .atomic)
            }
        } else {
            try bytes.write(to: url, options: .atomic)
        }
        guard sha(try Data(contentsOf: url)) == sha(bytes) else { fail("Install readback mismatch") }
    }
    if mode == "bundled" || mode == "install" {
        var error: Unmanaged<CFError>?
        let scope: CTFontManagerScope = mode == "bundled" ? .process : .user
        if !CTFontManagerRegisterFontsForURL(url as CFURL, scope, &error) {
            let detail = error?.takeRetainedValue()
            if detail.map({ CFErrorGetCode($0) }) != CTFontManagerError.alreadyRegistered.rawValue {
                fail("Font registration failed: \(String(describing: detail))")
            }
        }
    }
    let font = CTFontCreateWithName(name as CFString, 32, nil)
    let actualName = CTFontCopyPostScriptName(font) as String
    let actualFamily = CTFontCopyFamilyName(font) as String
    let actualURL = CTFontCopyAttribute(font, kCTFontURLAttribute) as? URL
    guard actualName == name, actualFamily == expectedFamily, actualURL?.standardizedFileURL == url.standardizedFileURL else {
        fail("Wrong resolved font: \(name), \(actualName), \(String(describing: actualURL))")
    }
    guard !CTFontGetSymbolicTraits(font).contains(.traitBold) else { fail("Unexpected bold trait") }
    let sample = entry["sample"] as! [String: Any]
    let text = sample["mixed"] as! NSString
    let requireMixed = sample["requireMixedCoverage"] as! Bool
    let attributed = NSAttributedString(string: text as String, attributes: [.font: font])
    let line = CTLineCreateWithAttributedString(attributed)
    var runs: [[String: Any]] = []
    for run in CTLineGetGlyphRuns(line) as! [CTRun] {
        let range = CTRunGetStringRange(run)
        let selected = (CTRunGetAttributes(run) as NSDictionary)[kCTFontAttributeName] as! CTFont
        let part = text.substring(with: NSRange(location: range.location, length: range.length))
        let selectedName = CTFontCopyPostScriptName(selected) as String
        if (requireMixed || part.unicodeScalars.contains(where: { $0.value < 128 && CharacterSet.alphanumerics.contains($0) })) && selectedName != name {
            fail("Latin text fell back: \(part), \(selectedName)")
        }
        runs.append(["text": part, "postScript": selectedName])
    }
    var probes: [[String: Any]] = []
    for probe in entry["probes"] as? [[String: Any]] ?? [] {
        let value = probe["text"] as! String
        let line = CTLineCreateWithAttributedString(NSAttributedString(string: value, attributes: [.font: font]))
        var count = 0
        for run in CTLineGetGlyphRuns(line) as! [CTRun] {
            let selected = (CTRunGetAttributes(run) as NSDictionary)[kCTFontAttributeName] as! CTFont
            guard CTFontCopyPostScriptName(selected) as String == name else { fail("Probe fell back: \(value)") }
            let n = CTRunGetGlyphCount(run)
            var glyphs = [CGGlyph](repeating: 0, count: n)
            CTRunGetGlyphs(run, CFRange(location: 0, length: 0), &glyphs)
            guard n > 0, !glyphs.contains(0) else { fail("Missing probe glyph: \(value)") }
            count += n
        }
        guard count > 0 else { fail("Empty probe: \(value)") }
        if let expected = probe["glyphCount"] as? Int, count != expected { fail("Wrong probe glyph count: \(value)") }
        probes.append(["text": value, "glyphCount": count, "postScript": name])
    }
    guard sha(try Data(contentsOf: url)) == expectedSHA else { fail("Resolved file differs from verified artifact") }
    fonts.append(font)
    reports.append(["requested": name, "family": actualFamily, "postScript": actualName,
                    "file": url.path, "sha256": sha(try Data(contentsOf: url)), "boldTrait": false, "runs": runs, "probes": probes])
}
if mode == "bundled" {
    // Measure the real font's line boxes: taller outlines also have taller
    // ascenders/descenders, so a fixed 73-point step overlaps sample rows.
    var groups: [[NSAttributedString]] = []
    var width: CGFloat = 1320
    var height: CGFloat = 32
    for (index, font) in fonts.enumerated() {
        var lines = [NSAttributedString(string: names[index], attributes: [.font: NSFont.systemFont(ofSize: 22, weight: .semibold), .foregroundColor: NSColor.black])]
        for (row, size) in [18.0, 32.0, 64.0].enumerated() {
            let samples = entries[index]["sample"] as! [String: Any]
            let fullSample = samples[row == 0 ? "latin" : "mixed"] as! String
            let sample = row == 2 ? String(fullSample.prefix(20)) : fullSample
            let displayFont = CTFontCreateCopyWithAttributes(font, size, nil, nil)
            lines.append(NSAttributedString(string: sample, attributes: [.font: displayFont, .foregroundColor: NSColor.black]))
        }
        for line in lines {
            width = max(width, ceil(line.size().width) + 64)
            height += ceil(line.size().height) + 16
        }
        height += 32
        groups.append(lines)
    }
    let image = NSImage(size: NSSize(width: width, height: height))
    image.lockFocus()
    NSColor(calibratedWhite: 0.96, alpha: 1).setFill()
    NSRect(x: 0, y: 0, width: width, height: height).fill()
    var top = height - 32
    for lines in groups {
        for line in lines {
            let size = line.size()
            top -= ceil(size.height)
            line.draw(at: NSPoint(x: 32, y: top))
            top -= 16
        }
        top -= 32
    }
    image.unlockFocus()
    let bitmap = NSBitmapImageRep(data: image.tiffRepresentation!)!
    let folder = root.appendingPathComponent("Evidence/previews")
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    // A comparison owns its own output instead of replacing another group's
    // historical all-fonts preview.
    let imageName = names.joined(separator: "--")
    try bitmap.representation(using: .png, properties: [:])!.write(to: folder.appendingPathComponent(imageName + ".png"))
}
let data = try JSONSerialization.data(withJSONObject: ["mode": mode, "os": ProcessInfo.processInfo.operatingSystemVersionString, "fonts": reports], options: [.prettyPrinted, .sortedKeys])
FileHandle.standardOutput.write(data)
print("")
