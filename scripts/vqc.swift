import Foundation
import Vision
import AppKit
for path in CommandLine.arguments.dropFirst() {
    guard let img = NSImage(contentsOfFile: path), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    let h = VNImageRequestHandler(cgImage: cg, options: [:])
    let tr = VNRecognizeTextRequest(); tr.recognitionLevel = .accurate; tr.usesLanguageCorrection = false
    let fr = VNDetectFaceRectanglesRequest()
    try? h.perform([tr, fr])
    var texts: [[String: Any]] = []
    for o in (tr.results ?? []) { if let c = o.topCandidates(1).first, c.confidence > 0.4 { texts.append(["s": c.string, "c": c.confidence, "x": o.boundingBox.minX, "y": o.boundingBox.minY, "w": o.boundingBox.width, "h": o.boundingBox.height]) } }
    var faces: [[String: Any]] = []
    for o in (fr.results ?? []) { faces.append(["roll": (o.roll?.doubleValue ?? 0), "x": o.boundingBox.minX, "y": o.boundingBox.minY, "w": o.boundingBox.width, "h": o.boundingBox.height]) }
    let d: [String: Any] = ["f": path, "t": texts, "fa": faces]
    if let data = try? JSONSerialization.data(withJSONObject: d), let s = String(data: data, encoding: .utf8) { print(s) }
}
