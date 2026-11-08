import AppKit
import CoreText
import Foundation

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}
guard CommandLine.arguments.count == 2 else { fail("Pass the RysaMix native manifest") }
let manifest = URL(fileURLWithPath: CommandLine.arguments[1])
let entries = try JSONSerialization.jsonObject(with: Data(contentsOf: manifest)) as! [[String: Any]]
var reports: [[String: Any]] = []
for entry in entries {
    let family = entry["family"] as! String
    let name = entry["name"] as! String
    let hanRatio = entry["hanRatio"] as! Double
    let expectedURL = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Fonts/" + name + ".ttf").standardizedFileURL
    let members = NSFontManager.shared.availableMembers(ofFontFamily: family) ?? []
    guard members.count >= 2 else { fail("Family not visible to AppKit: \(family)") }
    let base = CTFontCreateWithName(name as CFString, 32, nil)
    guard (CTFontCopyAttribute(base, kCTFontURLAttribute) as? URL)?.standardizedFileURL == expectedURL,
          let axes = CTFontCopyVariationAxes(base) as? [[CFString: Any]],
          let axis = axes.first,
          let identifier = axis[kCTFontVariationAxisIdentifierKey] as? NSNumber,
          let defaultValue = axis[kCTFontVariationAxisDefaultValueKey] as? NSNumber,
          let minimum = axis[kCTFontVariationAxisMinimumValueKey] as? NSNumber,
          let maximum = axis[kCTFontVariationAxisMaximumValueKey] as? NSNumber,
          minimum.intValue == 100, defaultValue.intValue == 400, maximum.intValue == 900 else {
        fail("Wrong installed font or variation axis: \(name)")
    }
    var widths: [CGFloat] = []
    var variations: [[String: Any]] = []
    for weight in [100, 400, 700, 900] {
        let settings = [identifier: NSNumber(value: weight)] as CFDictionary
        let attrs = [kCTFontVariationAttribute: settings] as CFDictionary
        let descriptor = CTFontDescriptorCreateCopyWithAttributes(CTFontCopyFontDescriptor(base), attrs)
        let font = CTFontCreateWithFontDescriptor(descriptor, 32, nil)
        let actual = (CTFontCopyVariation(font) as? [NSNumber: NSNumber])?[identifier]?.intValue ?? defaultValue.intValue
        guard actual == weight,
              (CTFontCopyAttribute(font, kCTFontURLAttribute) as? URL)?.standardizedFileURL == expectedURL else {
            fail("Wrong variation or resolved file: \(name) \(weight)")
        }
        var chars: [UniChar] = [65, 0x4e2d]
        var glyphs = [CGGlyph](repeating: 0, count: chars.count)
        guard CTFontGetGlyphsForCharacters(font, &chars, &glyphs, chars.count), !glyphs.contains(0) else {
            fail("Missing mixed-text glyph: \(name) \(weight)")
        }
        var advances = [CGSize](repeating: .zero, count: chars.count)
        _ = CTFontGetAdvancesForGlyphs(font, .horizontal, &glyphs, &advances, glyphs.count)
        guard abs(advances[1].width - advances[0].width * hanRatio) < 0.01 else {
            fail("Chinese advance does not match recipe: \(name) \(weight)")
        }
        var glyph = glyphs[0]
        let bounds = CTFontGetBoundingRectsForGlyphs(font, .horizontal, &glyph, nil, 1)
        widths.append(bounds.width)
        variations.append(["weight": weight, "postScript": CTFontCopyPostScriptName(font) as String,
                           "latinAdvance": advances[0].width, "chineseAdvance": advances[1].width,
                           "latinOutlineWidth": bounds.width])
    }
    guard widths[0] != widths[3] else { fail("Variable outlines did not change: \(name)") }
    reports.append(["family": family, "postScript": name, "file": expectedURL.path,
                    "appKitMemberCount": members.count, "variations": variations])
}
let result: [String: Any] = ["result": "pass", "scope": "installed AppKit families and Core Text weight instances",
                             "os": ProcessInfo.processInfo.operatingSystemVersionString, "fonts": reports]
let data = try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys])
FileHandle.standardOutput.write(data)
print("")
