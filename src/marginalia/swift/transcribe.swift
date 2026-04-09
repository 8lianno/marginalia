import Foundation
import Speech

/// Transcribes a WAV audio file using Apple Speech framework (on-device).
/// Usage: transcribe <path-to-wav>
/// Outputs the transcript text to stdout. Exits 1 on failure with error on stderr.

guard CommandLine.arguments.count == 2 else {
    FileHandle.standardError.write("Usage: transcribe <path-to-wav>\n".data(using: .utf8)!)
    exit(1)
}

let audioPath = CommandLine.arguments[1]
let audioURL = URL(fileURLWithPath: audioPath)

guard FileManager.default.fileExists(atPath: audioPath) else {
    FileHandle.standardError.write("Error: File not found: \(audioPath)\n".data(using: .utf8)!)
    exit(1)
}

guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US")) else {
    FileHandle.standardError.write("Error: Speech recognizer not available for en-US\n".data(using: .utf8)!)
    exit(1)
}

guard recognizer.isAvailable else {
    FileHandle.standardError.write("Error: Speech recognizer is not available. Check System Settings > Privacy > Speech Recognition.\n".data(using: .utf8)!)
    exit(1)
}

let semaphore = DispatchSemaphore(value: 0)
var transcriptText = ""
var transcriptError: Error?

let request = SFSpeechURLRecognitionRequest(url: audioURL)
request.requiresOnDeviceRecognition = true
request.shouldReportPartialResults = false

recognizer.recognitionTask(with: request) { result, error in
    if let error = error {
        transcriptError = error
        semaphore.signal()
        return
    }
    if let result = result, result.isFinal {
        transcriptText = result.bestTranscription.formattedString
        semaphore.signal()
    }
}

semaphore.wait()

if let error = transcriptError {
    FileHandle.standardError.write("Error: \(error.localizedDescription)\n".data(using: .utf8)!)
    exit(1)
}

print(transcriptText)
