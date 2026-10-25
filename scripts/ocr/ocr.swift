import Foundation
import Vision
import AppKit
// 用法：ocr <图片目录>，逐张输出 JSON 行：文件名、文字、置信度、框（归一化，原点左下）
let dir = CommandLine.arguments[1]
let files = (try? FileManager.default.contentsOfDirectory(atPath: dir))?.filter { $0.hasSuffix(".png") }.sorted() ?? []
for f in files {
    let url = URL(fileURLWithPath: dir).appendingPathComponent(f)
    guard let img = NSImage(contentsOf: url), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate; req.usesLanguageCorrection = false
    try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
    for o in (req.results ?? []) {
        guard let c = o.topCandidates(1).first else { continue }
        let b = o.boundingBox
        let d: [String: Any] = ["f": f, "t": c.string, "c": c.confidence, "x": b.minX, "y": b.minY, "w": b.width, "h": b.height]
        if let j = try? JSONSerialization.data(withJSONObject: d), let s = String(data: j, encoding: .utf8) { print(s) }
    }
}
