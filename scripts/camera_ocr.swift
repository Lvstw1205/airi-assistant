import Foundation
import Vision
import ImageIO
import CoreGraphics

// Local text and retail barcode extraction. No images or observations written to disk.
do {
    let data = FileHandle.standardInput.readDataToEndOfFile()
    guard data.count > 0 && data.count <= 4 * 1024 * 1024 else {
        throw NSError(domain: "AIRI", code: 1)
    }
    let text = VNRecognizeTextRequest()
    text.recognitionLevel = .fast
    text.minimumTextHeight = 0.015
    text.usesCPUOnly = true
    text.recognitionLanguages = ["en-US", "fr-FR"]
    text.usesLanguageCorrection = false
    let barcode = VNDetectBarcodesRequest()
    barcode.usesCPUOnly = true
    barcode.symbologies = [.ean13, .ean8, .upce, .code128]
    try VNImageRequestHandler(data: data).perform([text, barcode])
    let lines: [[String: Any]] = (text.results ?? []).prefix(80).compactMap { result in
        guard let candidate = result.topCandidates(1).first else { return nil }
        let b = result.boundingBox
        return ["text": String(candidate.string.prefix(300)), "confidence": candidate.confidence,
                "bbox": [b.minX, 1 - b.maxY, b.maxX, 1 - b.minY]]
    }
    let codes: [[String: Any]] = (barcode.results ?? []).prefix(10).compactMap { result in
        guard let value = result.payloadStringValue, value.count <= 32,
              value.allSatisfy({ $0.isASCII && $0.isNumber }) else { return nil }
        let b = result.boundingBox
        return ["value": value, "symbology": result.symbology.rawValue, "bbox": [b.minX, 1 - b.maxY, b.maxX, 1 - b.minY]]
    }
    var fingerprint = [UInt8](repeating: 0, count: 256)
    if let source = CGImageSourceCreateWithData(data as CFData, nil),
       let image = CGImageSourceCreateImageAtIndex(source, 0, nil),
       let center = image.cropping(to: CGRect(x: Double(image.width) * 0.18, y: Double(image.height) * 0.12,
                                               width: Double(image.width) * 0.64, height: Double(image.height) * 0.76)) {
        fingerprint.withUnsafeMutableBytes { bytes in
            if let ctx = CGContext(data: bytes.baseAddress, width: 16, height: 16, bitsPerComponent: 8, bytesPerRow: 16,
                                   space: CGColorSpaceCreateDeviceGray(), bitmapInfo: CGImageAlphaInfo.none.rawValue) {
                ctx.draw(center, in: CGRect(x: 0, y: 0, width: 16, height: 16))
            }
        }
    }
    let result: [String: Any] = ["engine": "Apple Vision fast OCR + barcode (local; labels also read by vision LLM)",
                               "lines": lines, "barcodes": codes,
                               "fingerprint": fingerprint]
    let output = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
    FileHandle.standardOutput.write(output)
} catch {
    let e = error as NSError
    FileHandle.standardError.write(Data("Local OCR error: \(e.domain) code \(e.code).\n".utf8))
    exit(1)
}
