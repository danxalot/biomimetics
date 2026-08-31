import sys
import objc
import AVFoundation

def test_av():
    engine = AVFoundation.AVAudioEngine.alloc().init()
    inputNode = engine.inputNode()
    
    # Try enabling Voice Processing
    try:
        success, error = inputNode.setVoiceProcessingEnabled_error_(True, None)
        if success:
            print("Voice Processing Enabled!")
        else:
            print(f"Failed to enable voice processing: {error}")
            return
    except Exception as e:
        print(f"Exception enabling voice processing: {e}")
        return

    print("Engine configured successfully.")

if __name__ == "__main__":
    test_av()
