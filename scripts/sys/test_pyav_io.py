import sys
import objc
import time
import AVFoundation

def input_callback(buffer, time_obj):
    print(f"Captured buffer: frameLength={buffer.frameLength()}")

def test_av_io():
    engine = AVFoundation.AVAudioEngine.alloc().init()
    inputNode = engine.inputNode()
    
    # Enable VPIO
    success, error = inputNode.setVoiceProcessingEnabled_error_(True, None)
    if not success:
        print(f"Failed to enable VPIO: {error}")
        return

    # Standard Format: Float32
    fmt = AVFoundation.AVAudioFormat.alloc().initStandardFormatWithSampleRate_channels_(
        16000.0,
        1
    )
    
    if fmt is None:
        print("Format creation failed!")
        return

    int16_fmt = AVFoundation.AVAudioFormat.alloc().initWithCommonFormat_sampleRate_channels_interleaved_(
        3, # AVAudioPCMFormatInt16
        16000.0,
        1,
        False
    )
    
    # Install tap
    inputNode.installTapOnBus_bufferSize_format_block_(
        0, 
        480, 
        int16_fmt, 
        input_callback
    )

    playerNode = AVFoundation.AVAudioPlayerNode.alloc().init()
    engine.attachNode_(playerNode)
    # Connect using default format
    engine.connect_to_format_(playerNode, engine.outputNode(), None)

    success, error = engine.startAndReturnError_(None)
    if not success:
        print(f"Engine start failed: {error}")
        return
        
    print("Engine started! Listening for 2 seconds...")
    playerNode.play()
    
    time.sleep(2.0)
    
    engine.stop()
    print("Test complete.")

if __name__ == "__main__":
    test_av_io()
