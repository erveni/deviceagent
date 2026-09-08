import Foundation
import Vision
import AppKit

// OCR one image via Apple Vision. Prints recognized text (one line per observation).
func ocr(_ path: String) -> String {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        return ""
    }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = true
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    try? handler.perform([req])
    var lines: [String] = []
    for obs in (req.results ?? []) {
        if let top = obs.topCandidates(1).first { lines.append(top.string) }
    }
    return lines.joined(separator: "\n")
}

let args = Array(CommandLine.arguments.dropFirst())
for path in args {
    print("@@@FILE\t\(path)")
    print(ocr(path))
    print("@@@END")
}
