import AVFoundation
let e = AVAudioEngine(); try! e.inputNode.setVoiceProcessingEnabled(true); e.connect(e.inputNode, to: e.outputNode, format: nil); try! e.start(); print("OK")
