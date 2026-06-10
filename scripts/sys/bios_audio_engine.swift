import Foundation
import AVFoundation

// Ensure unbuffered IO for binary data
setbuf(stdout, nil)
setbuf(stdin, nil)

var activeEngine: AVAudioEngine?
var activePlayer: AVAudioPlayerNode?
var shouldExit = false

func configureAudioSession(useAEC: Bool) -> Bool {
    // AVAudioSession is iOS-only. On macOS there is no audio session to
    // configure — AVAudioEngine drives the default device directly — so this
    // is a no-op. (The previous code guarded this with `#if os(macOS)`, which
    // is exactly backwards and fails to compile on macOS.)
    #if os(iOS)
    let session = AVAudioSession.sharedInstance()
    do {
        try session.setCategory(.playAndRecord, mode: useAEC ? .voiceChat : .default, options: [.defaultToSpeaker, .allowBluetooth])
        try session.setActive(true)
    } catch {
        fputs("Failed to configure AVAudioSession: \(error)\n", stderr)
        return false
    }
    #endif
    return true
}

func teardownEngine() {
    guard let engine = activeEngine else { return }
    engine.stop()
    engine.reset()
    if let player = activePlayer {
        engine.detach(player)
    }
    activePlayer = nil
    activeEngine = nil
}

func runAudioEngine(useAEC: Bool) -> Bool {
    // Ensure clean state before creating new engine
    teardownEngine()

    guard configureAudioSession(useAEC: useAEC) else { return false }

    let engine = AVAudioEngine()
    let inputNode = engine.inputNode
    let playerNode = AVAudioPlayerNode()

    if useAEC {
        do {
            try inputNode.setVoiceProcessingEnabled(true)
        } catch {
            fputs("Warning: Failed to enable VPIO (AEC): \(error).\n", stderr)
            return false
        }
    }

    // Hardware format (from input device)
    let hwFormat = inputNode.outputFormat(forBus: 0)
    
    // Standard format for mic capture (16 kHz mono for VAD efficiency)
    guard let micFormat = AVAudioFormat(standardFormatWithSampleRate: 16000.0, channels: 1) else {
        fputs("Failed to create mic format\n", stderr)
        return false
    }

    // Playback format (24 kHz mono for Gemini Live native output)
    guard let playbackFormat = AVAudioFormat(standardFormatWithSampleRate: 24000.0, channels: 1) else {
        fputs("Failed to create playback format\n", stderr)
        return false
    }

    guard let micConverter = AVAudioConverter(from: hwFormat, to: micFormat) else {
        fputs("Failed to create mic converter\n", stderr)
        return false
    }

    // Resample incoming 24 kHz Gemini audio up to the hardware rate. VPIO/AEC
    // requires the output node to run at the hardware format, so we feed it
    // hwFormat buffers and connect the player at hwFormat to match.
    guard let playbackConverter = AVAudioConverter(from: playbackFormat, to: hwFormat) else {
        fputs("Failed to create playback converter\n", stderr)
        return false
    }

    engine.attach(playerNode)
    // CRITICAL: connect at hwFormat (NOT playbackFormat). We schedule hwFormat
    // buffers onto this node; if the node were declared at 24 kHz, those
    // hardware-rate samples would be clocked out at 24 kHz -> deep/slow audio.
    engine.connect(playerNode, to: engine.outputNode, format: hwFormat)

    // Setup Capture (Mic -> stdout) - 16 kHz for VAD
    inputNode.installTap(onBus: 0, bufferSize: AVAudioFrameCount(hwFormat.sampleRate * 0.1), format: hwFormat) { (buffer, time) in
        let convertedFrameCapacity = AVAudioFrameCount((Double(buffer.frameLength) / hwFormat.sampleRate) * 16000.0)
        guard let convertedBuffer = AVAudioPCMBuffer(pcmFormat: micFormat, frameCapacity: convertedFrameCapacity) else { return }
        
        var hasProvidedData = false
        var error: NSError?
        let inputBlock: AVAudioConverterInputBlock = { inNumPackets, outStatus in
            if hasProvidedData {
                outStatus.pointee = .noDataNow
                return nil
            }
            hasProvidedData = true
            outStatus.pointee = .haveData
            return buffer
        }
        
        micConverter.convert(to: convertedBuffer, error: &error, withInputFrom: inputBlock)
        
        guard let channelData = convertedBuffer.floatChannelData?[0] else { return }
        let frameLength = Int(convertedBuffer.frameLength)
        
        var pcm16Data = [Int16](repeating: 0, count: frameLength)
        for i in 0..<frameLength {
            var sample = channelData[i]
            if sample > 1.0 { sample = 1.0 }
            if sample < -1.0 { sample = -1.0 }
            pcm16Data[i] = Int16(sample * 32767.0)
        }
        
        pcm16Data.withUnsafeBytes { bufferPointer in
            let data = Data(bytes: bufferPointer.baseAddress!, count: bufferPointer.count)
            FileHandle.standardOutput.write(data)
        }
    }

    // Start Engine
    do {
        engine.prepare()
        try engine.start()
        
        activeEngine = engine
        activePlayer = playerNode
        
        if useAEC {
            fputs("AVAudioEngine Started (AEC Enabled).\n", stderr)
        } else {
            fputs("AVAudioEngine Started (AEC Disabled).\n", stderr)
        }
    } catch {
        fputs("Engine start failed: \(error)\n", stderr)
        return false
    }

    playerNode.play()

    // Setup Playback (stdin -> Speaker) - handles 24 kHz input, converts to hw format
    DispatchQueue.global(qos: .userInitiated).async {
        let stdinHandle = FileHandle.standardInput
        var readBuffer = Data()
        let targetFrameSize = 960 // 480 frames * 2 bytes = 960 bytes @ 16 kHz, but we accept any size
        
        while !shouldExit {
            // Read up to 4096 bytes at a time
            let chunk = stdinHandle.readData(ofLength: 4096)
            if chunk.count == 0 {
                // EOF or closed pipe
                break
            }
            
            readBuffer.append(chunk)
            
            // Process complete frames
            while readBuffer.count >= targetFrameSize {
                let frameData = readBuffer.prefix(targetFrameSize)
                readBuffer.removeFirst(targetFrameSize)
                
                let frameCount = frameData.count / 2 // 16-bit samples
                guard frameCount > 0 else { continue }
                
                // Create buffer at 24 kHz (since input is 24 kHz from Gemini)
                guard let buffer = AVAudioPCMBuffer(pcmFormat: playbackFormat, frameCapacity: AVAudioFrameCount(frameCount)) else { continue }
                buffer.frameLength = AVAudioFrameCount(frameCount)
                
                guard let floatData = buffer.floatChannelData?[0] else { continue }

                frameData.withUnsafeBytes { rawBufferPointer in
                    let int16Pointer = rawBufferPointer.bindMemory(to: Int16.self)
                    for i in 0..<frameCount {
                        floatData[i] = Float32(int16Pointer[i]) / 32767.0
                    }
                }

                // Resample 24 kHz -> hardware rate, then schedule onto the player
                // node (which is connected at hwFormat). Output sample COUNT must
                // scale by the rate ratio, else the buffer is the wrong length and
                // plays at the wrong speed.
                var hasProvidedData = false
                var error: NSError?
                let ratio = hwFormat.sampleRate / 24000.0
                let convertedFrameCapacity = AVAudioFrameCount(Double(frameCount) * ratio)
                guard convertedFrameCapacity > 0,
                      let convertedBuffer = AVAudioPCMBuffer(pcmFormat: hwFormat, frameCapacity: convertedFrameCapacity) else { continue }

                let inputBlock: AVAudioConverterInputBlock = { inNumPackets, outStatus in
                    if hasProvidedData {
                        outStatus.pointee = .noDataNow
                        return nil
                    }
                    hasProvidedData = true
                    outStatus.pointee = .haveData
                    return buffer
                }

                playbackConverter.convert(to: convertedBuffer, error: &error, withInputFrom: inputBlock)

                if error != nil {
                    fputs("Playback conversion error: \(error!)\n", stderr)
                } else {
                    playerNode.scheduleBuffer(convertedBuffer, completionHandler: nil)
                }
            }
        }
    }

    return true
}

func handleInterruptSignal() {
    fputs("Interrupt received, shutting down...\n", stderr)
    shouldExit = true
    // Stop player immediately to cut off any scheduled audio
    if let player = activePlayer {
        player.stop()
    }
    teardownEngine()
    exit(0)
}

// Signal handlers for graceful shutdown
signal(SIGTERM) { _ in handleInterruptSignal() }
signal(SIGINT) { _ in handleInterruptSignal() }

let aecEnv = ProcessInfo.processInfo.environment["BIOS_AEC_ENABLED"] ?? "1"
if aecEnv == "1" {
    if !runAudioEngine(useAEC: true) {
        fputs("Retrying engine setup without AEC...\n", stderr)
        if !runAudioEngine(useAEC: false) {
            fputs("Engine failed completely even without AEC.\n", stderr)
            exit(1)
        }
    }
} else {
    if !runAudioEngine(useAEC: false) {
        fputs("Engine failed completely.\n", stderr)
        exit(1)
    }
}

// Keep the main thread alive with an active RunLoop to receive CoreAudio hardware callbacks
RunLoop.main.run()