import Foundation
import Speech

/// Transcribes a WAV audio file using Apple Speech framework (on-device).
/// Usage: transcribe <path-to-wav>
///
/// Protocol:
///   stdout line "."         = heartbeat (partial result received, transcription is progressing)
///   stdout line "TRANSCRIPT: <text>"  = final transcript (last line before exit 0)
///   stderr "Error: ..."     = error messages
///
/// Exit codes:
///   0 = success
///   1 = usage error / file not found
///   2 = speech recognizer not available (locale or permission)
///   3 = on-device model not downloaded
///   4 = recognition failed at runtime

func writeError(_ message: String) {
    FileHandle.standardError.write("Error: \(message)\n".data(using: .utf8)!)
}

func writeHeartbeat() {
    FileHandle.standardOutput.write(".\n".data(using: .utf8)!)
}

guard CommandLine.arguments.count == 2 else {
    writeError("Usage: transcribe <path-to-wav>")
    exit(1)
}

let audioPath = CommandLine.arguments[1]
let audioURL = URL(fileURLWithPath: audioPath)

guard FileManager.default.fileExists(atPath: audioPath) else {
    writeError("File not found: \(audioPath)")
    exit(1)
}

guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US")) else {
    writeError("SPEECH_LOCALE_UNAVAILABLE: Speech recognizer not available for en-US.")
    exit(2)
}

guard recognizer.isAvailable else {
    writeError("SPEECH_NOT_AVAILABLE: On-device speech recognition is not available. Enable it in System Settings > Privacy & Security > Speech Recognition, and ensure the on-device model is downloaded in System Settings > General > Keyboard > Dictation.")
    exit(2)
}

if !recognizer.supportsOnDeviceRecognition {
    writeError("SPEECH_MODEL_NOT_DOWNLOADED: On-device speech model is not downloaded. Go to System Settings > General > Keyboard > Dictation and enable 'On-Device Dictation' to download the model.")
    exit(3)
}

let semaphore = DispatchSemaphore(value: 0)
var transcriptText = ""
var transcriptError: Error?

let request = SFSpeechURLRecognitionRequest(url: audioURL)
request.requiresOnDeviceRecognition = true
request.shouldReportPartialResults = true

recognizer.recognitionTask(with: request) { result, error in
    if let error = error {
        transcriptError = error
        semaphore.signal()
        return
    }
    if let result = result {
        if result.isFinal {
            transcriptText = result.bestTranscription.formattedString
            semaphore.signal()
        } else {
            // Emit a heartbeat so the Python caller knows we're alive
            writeHeartbeat()
        }
    }
}

semaphore.wait()

if let error = transcriptError {
    let desc = error.localizedDescription
    if desc.contains("kAFAssistantErrorDomain") || desc.contains("not authorized") {
        writeError("SPEECH_PERMISSION_DENIED: Speech recognition permission denied. Grant access in System Settings > Privacy & Security > Speech Recognition.")
        exit(2)
    }
    writeError("RECOGNITION_FAILED: \(desc)")
    exit(4)
}

// Final transcript on a prefixed line so Python can distinguish it from heartbeats
print("TRANSCRIPT: \(transcriptText)")
