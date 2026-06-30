import Foundation
import AVFoundation
import Vision
import CoreGraphics

struct SubtitleHit: Codable {
    let time: Double
    let text: String
    let confidence: Float
    let bbox: [Double]
}

func die(_ message: String) -> Never {
    FileHandle.standardError.write((message + "\n").data(using: .utf8)!)
    exit(1)
}

let args = CommandLine.arguments
guard args.count >= 3 else {
    die("Usage: swift ocr_burned_subtitles.swift <input.mp4> <output.jsonl> [interval_seconds]")
}

let input = URL(fileURLWithPath: args[1])
let output = URL(fileURLWithPath: args[2])
let interval = args.count >= 4 ? (Double(args[3]) ?? 1.0) : 1.0

let asset = AVURLAsset(url: input)
let generator = AVAssetImageGenerator(asset: asset)
generator.appliesPreferredTrackTransform = true
generator.requestedTimeToleranceBefore = CMTime(seconds: 0.08, preferredTimescale: 600)
generator.requestedTimeToleranceAfter = CMTime(seconds: 0.08, preferredTimescale: 600)
generator.maximumSize = CGSize(width: 1080, height: 1920)

let duration = CMTimeGetSeconds(asset.duration)
if !duration.isFinite || duration <= 0 {
    die("Could not read video duration")
}

FileManager.default.createFile(atPath: output.path, contents: nil)
let handle = try FileHandle(forWritingTo: output)
defer { try? handle.close() }
let encoder = JSONEncoder()

func recognize(_ image: CGImage, at time: Double) throws -> [SubtitleHit] {
    let width = image.width
    let height = image.height
    let cropRect = CGRect(
        x: Int(Double(width) * 0.05),
        y: Int(Double(height) * 0.58),
        width: Int(Double(width) * 0.90),
        height: Int(Double(height) * 0.28)
    )
    guard let cropped = image.cropping(to: cropRect) else { return [] }

    var hits: [SubtitleHit] = []
    let request = VNRecognizeTextRequest { request, _ in
        guard let observations = request.results as? [VNRecognizedTextObservation] else { return }
        for observation in observations {
            guard let candidate = observation.topCandidates(1).first else { continue }
            let text = candidate.string
                .replacingOccurrences(of: "\n", with: " ")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if text.isEmpty { continue }
            if text.contains("抖音") || text.contains("587911") || text.contains("@") { continue }
            if text.count <= 1 { continue }
            let b = observation.boundingBox
            hits.append(SubtitleHit(
                time: time,
                text: text,
                confidence: candidate.confidence,
                bbox: [b.origin.x, b.origin.y, b.size.width, b.size.height]
            ))
        }
    }
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    let handler = VNImageRequestHandler(cgImage: cropped, options: [:])
    try handler.perform([request])
    return hits
}

var t = 0.0
var count = 0
while t <= duration {
    autoreleasepool {
        do {
            let time = CMTime(seconds: t, preferredTimescale: 600)
            let image = try generator.copyCGImage(at: time, actualTime: nil)
            let hits = try recognize(image, at: t)
            for hit in hits {
                if let data = try? encoder.encode(hit) {
                    handle.write(data)
                    handle.write("\n".data(using: .utf8)!)
                }
            }
            count += 1
            if count % 100 == 0 {
                FileHandle.standardError.write("processed \(count) frames at \(String(format: "%.1f", t))s\n".data(using: .utf8)!)
            }
        } catch {
            FileHandle.standardError.write("frame \(String(format: "%.2f", t)) failed: \(error)\n".data(using: .utf8)!)
        }
    }
    t += interval
}
