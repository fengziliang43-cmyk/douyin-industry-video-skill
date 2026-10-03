// OCR burned-in subtitles from a video with macOS AVFoundation + Vision (no installs, macOS 13+).
//
// Usage:
//   swift ocr_burned_subtitles.swift <input.mp4> <output.jsonl> [interval] [options]
// Options:
//   --interval S        seconds between OCR frames (default 0.4)
//   --band auto         default: find the subtitle band from ~40 sample frames; if no clear band,
//                       fall back to the orientation preset
//   --band preset       landscape 0.70-1.00, portrait 0.55-0.90 of frame height
//   --band full         whole frame (slides, on-screen text)
//   --band TOP:BOTTOM   fractions of frame height measured from the top, e.g. 0.84:1.0
//   --start S --end S   only this time window
//   --langs zh-Hans,en-US
// Output JSONL: first line {"meta": {...}}, then one object per recognized text box:
//   {"time": t, "text": s, "confidence": c, "bbox": [x, y, w, h]}
//   bbox is normalized to the full frame, origin top-left. Frames are never downscaled.
import Foundation
import AVFoundation
import Vision
import CoreGraphics

struct Hit: Codable {
    let time: Double
    let text: String
    let confidence: Float
    let bbox: [Double]
}

struct Meta: Codable {
    let version: Int
    let video: String
    let width: Int
    let height: Int
    let orientation: String
    let duration: Double
    let start: Double
    let end: Double
    let interval: Double
    let band: [Double]
    let bandSource: String
    let coords: String
}

struct MetaLine: Codable { let meta: Meta }

struct Box {
    let text: String
    let confidence: Float
    let x: Double, y: Double, w: Double, h: Double
}

let usage = "Usage: swift ocr_burned_subtitles.swift <input.mp4> <output.jsonl> [interval] [--interval S] [--band auto|preset|full|TOP:BOTTOM] [--start S] [--end S] [--langs zh-Hans,en-US]"

func log(_ message: String) {
    FileHandle.standardError.write((message + "\n").data(using: .utf8)!)
}

func die(_ message: String) -> Never {
    log(message)
    exit(1)
}

var positional: [String] = []
var options: [String: String] = [:]
var index = 1
let argv = CommandLine.arguments
while index < argv.count {
    let arg = argv[index]
    if arg.hasPrefix("--") {
        guard index + 1 < argv.count else { die("Missing value for \(arg)\n\(usage)") }
        options[String(arg.dropFirst(2))] = argv[index + 1]
        index += 2
    } else {
        positional.append(arg)
        index += 1
    }
}
guard positional.count >= 2 else { die(usage) }
for key in options.keys where !["interval", "band", "start", "end", "langs"].contains(key) {
    die("Unknown option --\(key)\n\(usage)")
}

func number(_ value: String?, _ name: String) -> Double? {
    guard let value = value else { return nil }
    guard let parsed = Double(value) else { die("\(name) needs a number, got \(value)") }
    return parsed
}

let inputPath = positional[0]
let outputPath = positional[1]
let interval = number(options["interval"], "--interval") ?? number(positional.count >= 3 ? positional[2] : nil, "interval") ?? 0.4
guard interval > 0 else { die("interval must be > 0") }
let languages = (options["langs"] ?? "zh-Hans,en-US").split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }
let bandArg = options["band"] ?? "auto"

let asset = AVURLAsset(url: URL(fileURLWithPath: inputPath))
let generator = AVAssetImageGenerator(asset: asset)
generator.appliesPreferredTrackTransform = true
generator.requestedTimeToleranceBefore = CMTime(seconds: 0.05, preferredTimescale: 600)
generator.requestedTimeToleranceAfter = CMTime(seconds: 0.05, preferredTimescale: 600)

let duration: Double
do {
    duration = try await asset.load(.duration).seconds
} catch {
    die("Could not open video \(inputPath): \(error)")
}
guard duration.isFinite, duration > 0 else { die("Could not read video duration: \(inputPath)") }
let start = max(0, number(options["start"], "--start") ?? 0)
let end = min(duration, number(options["end"], "--end") ?? duration)
guard end > start else { die("Empty time window \(start)-\(end)") }

func frame(at seconds: Double) async throws -> CGImage {
    try await generator.image(at: CMTime(seconds: seconds, preferredTimescale: 600)).image
}

// OCR rows top..bottom of the image (fractions from the top); boxes are returned in full-frame coordinates.
func recognize(_ image: CGImage, top: Double, bottom: Double) throws -> [Box] {
    let height = Double(image.height)
    let y0 = (top * height).rounded(.down)
    let y1 = (bottom * height).rounded(.up)
    guard let crop = image.cropping(to: CGRect(x: 0, y: y0, width: Double(image.width), height: max(1, y1 - y0))) else { return [] }
    let cropTop = y0 / height
    let cropHeight = Double(crop.height) / height
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = languages
    try VNImageRequestHandler(cgImage: crop, options: [:]).perform([request])
    var boxes: [Box] = []
    for observation in request.results ?? [] {
        guard let candidate = observation.topCandidates(1).first else { continue }
        let text = candidate.string.replacingOccurrences(of: "\n", with: " ").trimmingCharacters(in: .whitespacesAndNewlines)
        if text.isEmpty { continue }
        let b = observation.boundingBox  // normalized to the crop, origin bottom-left
        boxes.append(Box(text: text, confidence: candidate.confidence,
                         x: b.origin.x, y: cropTop + (1 - b.origin.y - b.size.height) * cropHeight,
                         w: b.size.width, h: b.size.height * cropHeight))
    }
    return boxes
}

func presetBand(width: Int, height: Int) -> (Double, Double) {
    width > height ? (0.70, 1.0) : (0.55, 0.90)
}

// OCR reads the same text a little differently from frame to frame: treat readings within
// 30% edit distance as the same text.
func sameText(_ a: String, _ b: String) -> Bool {
    let x = Array(a), y = Array(b)
    let longest = max(x.count, y.count)
    if x.isEmpty || y.isEmpty || abs(x.count - y.count) * 10 > longest * 3 { return false }
    var prev = Array(0...y.count)
    var cur = Array(repeating: 0, count: y.count + 1)
    for i in 1...x.count {
        cur[0] = i
        for j in 1...y.count {
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x[i - 1] == y[j - 1] ? 0 : 1))
        }
        swap(&prev, &cur)
    }
    return prev[y.count] * 10 <= longest * 3
}

func addDistinct(_ list: inout [String], _ key: String) {
    if !list.contains(where: { sameText($0, key) }) { list.append(key) }
}

// A subtitle row is a horizontally centered line that has text in almost every sampled frame and
// says something different each time. Score each 1%-high row (smoothed over its neighbours) by
// distinct texts x share of samples with text, then keep the best row plus nearby strong rows
// (e.g. the English line of bilingual subtitles). Screen text, titles and watermarks lose on one
// of the two counts.
func detectBand() async -> (Double, Double)? {
    let span = end - start
    let samples = max(8, min(40, Int(span / 2)))
    var observations: [(frame: Int, bin: Int, key: String, top: Double, bottom: Double, h: Double)] = []
    var framesWithText: [String: Int] = [:]
    for k in 0..<samples {
        let t = start + span * (Double(k) + 0.5) / Double(samples)
        guard let image = try? await frame(at: t) else { continue }
        autoreleasepool {
            guard let boxes = try? recognize(image, top: 0, bottom: 1) else { return }
            var seenHere = Set<String>()
            for b in boxes {
                let key = String(b.text.lowercased().filter { !$0.isWhitespace && !$0.isPunctuation })
                guard key.count >= 2, abs(b.x + b.w / 2 - 0.5) <= 0.2, b.h >= 0.012, b.h <= 0.12 else { continue }
                observations.append((k, min(99, max(0, Int((b.y + b.h / 2) * 100))), key, b.y, b.y + b.h, b.h))
                if seenHere.insert(key).inserted { framesWithText[key, default: 0] += 1 }
            }
        }
    }
    let staticLimit = max(3, samples * 3 / 10)  // on screen in >30% of samples: watermark or title
    let moving = observations.filter { framesWithText[$0.key, default: 0] <= staticLimit }
    var frames = Array(repeating: Set<Int>(), count: 100)
    var texts = Array(repeating: [String](), count: 100)
    for o in moving {
        frames[o.bin].insert(o.frame)
        addDistinct(&texts[o.bin], o.key)
    }
    var scores = Array(repeating: 0.0, count: 100)
    var coverage = Array(repeating: 0.0, count: 100)
    for bin in 0..<100 {
        let near = max(0, bin - 1)...min(99, bin + 1)
        var covered = Set<Int>()
        var distinct: [String] = []
        for n in near {
            covered.formUnion(frames[n])
            for key in texts[n] { addDistinct(&distinct, key) }
        }
        coverage[bin] = Double(covered.count) / Double(samples)
        scores[bin] = Double(distinct.count) * coverage[bin]
    }
    guard let peak = scores.max(), peak >= 2 else { return nil }
    var groups: [(lo: Int, hi: Int, score: Double)] = []
    for bin in 0..<100 where scores[bin] >= peak * 0.3 {
        if let last = groups.last, bin - last.hi <= 2 {
            groups[groups.count - 1] = (last.lo, bin, max(last.score, scores[bin]))
        } else {
            groups.append((bin, bin, scores[bin]))
        }
    }
    guard let best = groups.max(by: { $0.score < $1.score }),
          coverage[best.lo...best.hi].max()! >= 0.5 else { return nil }  // no continuous text row
    let centre = Double(best.lo + best.hi + 1) / 200
    let chosen = groups.filter { $0.score >= best.score * 0.5 && abs(Double($0.lo + $0.hi + 1) / 200 - centre) <= 0.15 }
    let inBand = moving.filter { o in chosen.contains { o.bin >= $0.lo && o.bin <= $0.hi } }
    guard !inBand.isEmpty else { return nil }
    // Vision misses styled subtitles when the crop hugs the text, so leave 1.5 line heights of
    // room on each side and keep the band at least 15% of the frame high.
    let heights = inBand.map { $0.h }.sorted()
    let margin = max(0.03, heights[heights.count / 2] * 1.5)
    var top = max(0, inBand.map { $0.top }.min()! - margin)
    var bottom = min(1, inBand.map { $0.bottom }.max()! + margin)
    if bottom - top < 0.15 {
        let mid = min(max((top + bottom) / 2, 0.075), 0.925)
        top = mid - 0.075
        bottom = mid + 0.075
    }
    return (top, bottom)
}

let firstFrame: CGImage
do {
    firstFrame = try await frame(at: start)
} catch {
    die("Could not decode a frame from \(inputPath): \(error)")
}
let width = firstFrame.width
let height = firstFrame.height
let orientation = width > height ? "landscape" : (width < height ? "portrait" : "square")

var band: (Double, Double)
var bandSource: String
switch bandArg {
case "auto":
    let began = Date()
    if let detected = await detectBand() {
        band = detected
        bandSource = "auto"
    } else {
        band = presetBand(width: width, height: height)
        bandSource = "preset (auto found no clear subtitle band)"
    }
    log(String(format: "band detection took %.0fs", Date().timeIntervalSince(began)))
case "preset":
    band = presetBand(width: width, height: height)
    bandSource = "preset"
case "full":
    band = (0, 1)
    bandSource = "full"
default:
    let parts = bandArg.split(separator: ":").compactMap { Double($0) }
    guard parts.count == 2, parts[0] >= 0, parts[1] <= 1, parts[0] < parts[1] else {
        die("--band must be auto, preset, full or TOP:BOTTOM within 0...1, got \(bandArg)")
    }
    band = (parts[0], parts[1])
    bandSource = "manual"
}
band = ((band.0 * 1000).rounded() / 1000, (band.1 * 1000).rounded() / 1000)
log("frame \(width)x\(height) \(orientation); OCR band \(band.0)-\(band.1) of height (\(bandSource)); every \(interval)s from \(start)s to \(String(format: "%.1f", end))s")

FileManager.default.createFile(atPath: outputPath, contents: nil)
guard let handle = FileHandle(forWritingAtPath: outputPath) else { die("Cannot write \(outputPath)") }
let encoder = JSONEncoder()
encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
func writeLine<T: Encodable>(_ value: T) {
    if let data = try? encoder.encode(value) {
        handle.write(data)
        handle.write("\n".data(using: .utf8)!)
    }
}
writeLine(MetaLine(meta: Meta(version: 2, video: inputPath, width: width, height: height, orientation: orientation,
                              duration: duration, start: start, end: end, interval: interval,
                              band: [band.0, band.1], bandSource: bandSource,
                              coords: "bbox = [x, y, w, h] normalized to the full frame, origin top-left")))

// On busy frames Vision sometimes reads nothing in one crop yet reads the same subtitle in another.
// When the band shows no centered text, re-read that frame with a half-frame-high crop around the
// band, then with the whole frame, and keep what lies in the band. After 25 failed re-reads in a
// row (a video or stretch without subtitles) it stops re-reading until subtitle text shows up again.
let mid = (band.0 + band.1) / 2
let retryCrops = band == (0, 1) ? [] : [(max(0, min(mid - 0.25, 0.5)), min(1, max(mid + 0.25, 0.5))), (0.0, 1.0)]
func inBand(_ b: Box) -> Bool {
    let cy = b.y + b.h / 2
    return cy >= band.0 - 0.02 && cy <= band.1 + 0.02
}
func hasSubtitle(_ boxes: [Box]) -> Bool {
    boxes.contains { $0.text.count >= 2 && abs($0.x + $0.w / 2 - 0.5) <= 0.2 && inBand($0) }
}

let began = Date()
var frames = 0
var hits = 0
var reread = 0
var recovered = 0
var failedRereads = 0
var t = start
while t <= end + 1e-6 {
    do {
        let image = try await frame(at: t)
        try autoreleasepool {
            var boxes = try recognize(image, top: band.0, bottom: band.1)
            if hasSubtitle(boxes) {
                failedRereads = 0
            } else if !retryCrops.isEmpty && failedRereads < 25 {
                reread += 1
                var found = false
                for crop in retryCrops {
                    let wider = try recognize(image, top: crop.0, bottom: crop.1).filter(inBand)
                    if hasSubtitle(wider) {
                        boxes = wider
                        found = true
                        break
                    }
                }
                if found { recovered += 1; failedRereads = 0 } else { failedRereads += 1 }
            }
            for b in boxes {
                writeLine(Hit(time: (t * 1000).rounded() / 1000, text: b.text, confidence: b.confidence, bbox: [b.x, b.y, b.w, b.h]))
                hits += 1
            }
        }
        frames += 1
        if frames % 200 == 0 {
            log(String(format: "%d frames, at %.0fs, %.0fs elapsed", frames, t, Date().timeIntervalSince(began)))
        }
    } catch {
        log(String(format: "frame %.2fs failed: %@", t, String(describing: error)))
    }
    t += interval
}
try? handle.close()
log(String(format: "done: %d frames, %d text boxes, %.0fs; %d frames without subtitle text re-read, %d recovered",
           frames, hits, Date().timeIntervalSince(began), reread, recovered))
