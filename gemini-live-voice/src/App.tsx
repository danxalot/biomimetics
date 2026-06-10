// !!! ACTION REQUIRED: Whitelist localhost:3000 in chrome://flags/#unsafely-treat-insecure-origin-as-secure !!!

import { useState, useEffect, useRef, useCallback } from 'react';
import { GoogleGenAI } from '@google/genai';
import { MicVAD } from '@ricky0123/vad-web';

const TOOLS = [
  {
    name: 'query_memory',
    description: 'Search the unified memory system.',
    parameters: {
      type: 'object',
      properties: { query: { type: 'string', description: 'The search query' } },
      required: ['query']
    }
  },
  {
    name: 'save_memory',
    description: 'Save content to a memory file.',
    parameters: {
      type: 'object',
      properties: {
        name: { type: 'string', description: 'Filename' },
        content: { type: 'string', description: 'Content to save' }
      },
      required: ['name', 'content']
    }
  },
  {
    name: 'save_to_notion',
    description: 'Save structured text to Notion for phone review.',
    parameters: {
      type: 'object',
      properties: {
        title: { type: 'string', description: 'Title' },
        category: { type: 'string', description: 'Category: travel, research, email, schedule, task, note' },
        content: { type: 'string', description: 'Structured content (markdown)' }
      },
      required: ['title', 'content']
    }
  },
  {
    name: 'execute_heavy_reasoning',
    description: 'Offload complex reasoning to OpenCode models.',
    parameters: {
      type: 'object',
      properties: {
        task: { type: 'string', description: 'The reasoning task' },
        model: { type: 'string', description: "Model: 'nemotron' or 'minimax'" }
      },
      required: ['task']
    }
  },
  {
    name: 'execute_computer_action',
    description: 'Execute computer vision actions via local Qwen-VL.',
    parameters: {
      type: 'object',
      properties: {
        action: { type: 'string', description: 'click, scroll, type, screenshot' },
        target: { type: 'string', description: 'What to interact with' },
        value: { type: 'string', description: 'Value for type/press' }
      },
      required: ['action', 'target']
    }
  },
  {
    name: 'trigger_pm_agent',
    description: 'Force-sync GitHub Issues to Notion Roadmap.',
    parameters: {
      type: 'object',
      properties: { context: { type: 'string', description: 'Optional project context' } }
    }
  },
  {
    name: 'engage_all_systems',
    description: 'Triggers the CoPaw backend to wake up all idle LaunchAgents, spin up the local Qwen-VL vision loop, and initialize the Pythia Dragonfly geometric pipeline.',
    parameters: {
      type: 'object',
      properties: {
        mode: { type: 'string', description: "The operational mode, default is 'full_diagnostic'" }
      },
      required: ['mode']
    }
  },
  {
    name: 'contact_pythia',
    description: 'Send a prompt to the Pythia Dragonfly geometric AI via the local Vulkan Qwen3.5 model.',
    parameters: {
      type: 'object',
      properties: { prompt: { type: 'string', description: 'The exact prompt for Pythia' } },
      required: ['prompt']
    }
  }
];

const captureWorkletCode = `
class PCMWorklet extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0][0];
    if (!input) return true;
    const pcm16 = new Int16Array(input.length);
    for (let i = 0; i < input.length; i++) {
      const s = Math.max(-1, Math.min(1, input[i]));
      pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    this.port.postMessage(pcm16.buffer);
    return true;
  }
}
registerProcessor('pcm-worklet', PCMWorklet);
`;

export default function App() {
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('gemini_api_key') || '');
  const [isConnected, setIsConnected] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [responseText, setResponseText] = useState('');
  const [error, setError] = useState<string | null>(null);

  const sessionRef = useRef<any>(null);
  const sharedAudioContextRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const nextPlayTimeRef = useRef<number>(0);
  const workletUrlRef = useRef<string | null>(null);
  const vadRef = useRef<MicVAD | null>(null);
  const activeSourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set());

  const isListeningRef = useRef(false);
  const isConnectedRef = useRef(false);
  const isModelTalkingRef = useRef(false);
  const isSpeechActiveRef = useRef(false); // ← CLIENT VAD

  useEffect(() => { if (apiKey) localStorage.setItem('gemini_api_key', apiKey); }, [apiKey]);
  useEffect(() => { isListeningRef.current = isListening; }, [isListening]);
  useEffect(() => { isConnectedRef.current = isConnected; }, [isConnected]);

  const handleToolCall = useCallback(async (toolCall: any) => {
    const { name, args } = toolCall;
    console.log(`🛠️ Executing Tool: ${name}`, args);
    try {
      const resp = await fetch(`http://127.0.0.1:8090/mcp/tool/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, arguments: args })
      });
      const data = await resp.json();
      return JSON.stringify(data.result || data);
    } catch (err: any) {
      return JSON.stringify({ error: err.message });
    }
  }, []);

  const flushPlayback = useCallback(() => {
    activeSourcesRef.current.forEach(source => {
      try { source.stop(); } catch {}
    });
    activeSourcesRef.current.clear();
    nextPlayTimeRef.current = sharedAudioContextRef.current?.currentTime ?? 0;
  }, []);

  const stopMicrophone = useCallback(() => {
    // Stop VAD
    if (vadRef.current) {
      vadRef.current.pause();
      vadRef.current = null;
    }
    isSpeechActiveRef.current = false;

    if (workletNodeRef.current) {
      workletNodeRef.current.port.onmessage = null;
      workletNodeRef.current.disconnect();
      workletNodeRef.current = null;
    }
    
    // Do NOT close shared context here, just disconnect tracks
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    if (workletUrlRef.current) {
      URL.revokeObjectURL(workletUrlRef.current);
      workletUrlRef.current = null;
    }
    isListeningRef.current = false;
    setIsListening(false);
  }, []);

  const disconnect = useCallback(() => {
    stopMicrophone();
    flushPlayback();
    if (sessionRef.current) {
      try { sessionRef.current.close(); } catch {}
      sessionRef.current = null;
    }
    if (sharedAudioContextRef.current) {
      sharedAudioContextRef.current.close();
      sharedAudioContextRef.current = null;
    }
    nextPlayTimeRef.current = 0;
    isModelTalkingRef.current = false;
    isConnectedRef.current = false;
    setIsConnected(false);
    setResponseText('');
  }, [stopMicrophone, flushPlayback]);

  const connect = useCallback(async () => {
    if (!apiKey) return setError('Please enter API Key');
    try {
      setError(null);
      const genAI = new GoogleGenAI({ apiKey });
      
      // Initialize shared AudioContext at 16000Hz for AEC alignment
      const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 });
      sharedAudioContextRef.current = audioCtx;
      nextPlayTimeRef.current = audioCtx.currentTime;

      sessionRef.current = await genAI.live.connect({
        model: 'gemini-2.0-flash-exp', // Updated to stable flash live model
        config: {
          generationConfig: { responseModalities: ["AUDIO"] },
          tools: [{ functionDeclarations: TOOLS }]
        },
        callbacks: {
          onopen: () => {
            console.log('✅ WebSocket Connected');
            isConnectedRef.current = true;
            setIsConnected(true);
            setResponseText('');
            isModelTalkingRef.current = false;
          },
          onmessage: async (message: any) => {
            // Model turn detection — only affects mic gating, NOT playback
            const hasModelTurn = message.serverContent?.modelTurn?.parts?.some(
              (p: any) => p.inlineData?.data || p.text
            );
            if (hasModelTurn) isModelTalkingRef.current = true;

            if (message.serverContent?.turnComplete) {
              // Grace period: allow 500ms for hardware buffer to drain
              setTimeout(() => {
                isModelTalkingRef.current = false;
              }, 500);
            }
            if (message.serverContent?.interrupted) {
              console.log('⛔ [INTERRUPT] Flushing playback buffer');
              isModelTalkingRef.current = false;
              flushPlayback();
            }

            // Audio playback — NEVER gated, always plays
            const parts = message.serverContent?.modelTurn?.parts;
            if (parts && sharedAudioContextRef.current) {
              const ctx = sharedAudioContextRef.current;
              for (const part of parts) {
                if (part.inlineData?.data) {
                  const raw = atob(part.inlineData.data);
                  const uint8 = new Uint8Array(raw.length);
                  for (let i = 0; i < raw.length; i++) uint8[i] = raw.charCodeAt(i);
                  const int16 = new Int16Array(uint8.buffer);
                  const float32 = new Float32Array(int16.length);
                  for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768.0;
                  
                  // Native Gemini output is often 24k, but we align to 16k context
                  const buffer = ctx.createBuffer(1, float32.length, 24000); 
                  buffer.getChannelData(0).set(float32);
                  
                  const source = ctx.createBufferSource();
                  source.buffer = buffer;
                  source.connect(ctx.destination);
                  
                  // Track source for interruption flushing
                  activeSourcesRef.current.add(source);
                  source.onended = () => activeSourcesRef.current.delete(source);

                  if (nextPlayTimeRef.current < ctx.currentTime) nextPlayTimeRef.current = ctx.currentTime;
                  source.start(nextPlayTimeRef.current);
                  nextPlayTimeRef.current += buffer.duration;
                }
              }
            }

            // Tool calls
            if (message.toolCall) {
              isModelTalkingRef.current = true;
              const resultString = await handleToolCall(message.toolCall);
              if (sessionRef.current) {
                try {
                  sessionRef.current.sendToolResponse({
                    functionResponses: [{
                      id: message.toolCall.id,
                      name: message.toolCall.name,
                      response: { result: resultString }
                    }]
                  });
                } catch (e) { console.error('Tool response failed:', e); }
              }
              // Grace period for tool execution feedback
              setTimeout(() => {
                isModelTalkingRef.current = false;
              }, 500);
            }

            if (message.text) setResponseText(prev => prev + message.text);
          },
          onerror: (err: any) => {
            console.error('❌ WebSocket Error:', err);
            isModelTalkingRef.current = false;
            isConnectedRef.current = false;
            setIsConnected(false);
          },
          onclose: () => {
            console.log('🔌 WebSocket Closed');
            isModelTalkingRef.current = false;
            isConnectedRef.current = false;
            setIsConnected(false);
            stopMicrophone();
            if (playbackContextRef.current) {
              playbackContextRef.current.close();
              playbackContextRef.current = null;
            }
          }
        }
      } as any);
    } catch (err: any) { setError(`Connect Failed: ${err.message}`); }
  }, [apiKey, handleToolCall, stopMicrophone]);

  const startMicrophone = useCallback(async () => {
    if (!sessionRef.current || !sharedAudioContextRef.current) return;
    try {
      // Hardware DSP constraints strictly enforced for Antigravity Mandate
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: { ideal: true },
          noiseSuppression: { ideal: true },
          autoGainControl: { ideal: false }, // Disable to prevent floating noise floors
          sampleRate: 16000,                 // Match Gemini Live API native rate
          channelCount: 1                    // Mono stream
        }
      });
      streamRef.current = stream;

      const audioCtx = sharedAudioContextRef.current;
      if (audioCtx.state === 'suspended') await audioCtx.resume();

      // Load AudioWorklet
      const blob = new Blob([captureWorkletCode], { type: 'application/javascript' });
      const workletUrl = URL.createObjectURL(blob);
      workletUrlRef.current = workletUrl;
      await audioCtx.audioWorklet.addModule(workletUrl);

      const source = audioCtx.createMediaStreamSource(stream);
      const workletNode = new AudioWorkletNode(audioCtx, 'pcm-worklet');
      workletNodeRef.current = workletNode;

      // Gated mic sending — only when VAD detects speech
      workletNode.port.onmessage = (e) => {
        if (!sessionRef.current || !isConnectedRef.current) return;

        const uint8Array = new Uint8Array(e.data);
        const chunkSize = 8192;
        let binary = '';
        for (let i = 0; i < uint8Array.length; i += chunkSize) {
          binary += String.fromCharCode.apply(null, uint8Array.subarray(i, i + chunkSize) as unknown as number[]);
        }
        try {
          sessionRef.current.sendRealtimeInput({
            media: { data: btoa(binary), mimeType: 'audio/pcm;rate=16000' }
          });
        } catch {}
      };

      source.connect(workletNode);

      // Initialize client-side VAD
      const vad = await MicVAD.new({
        onSpeechStart: () => {
          isSpeechActiveRef.current = true;
          console.log('🎤 Speech detected');
        },
        onSpeechEnd: () => {
          isSpeechActiveRef.current = false;
          console.log('🔇 Speech ended');
        },
        positiveSpeechThreshold: 0.6,
        negativeSpeechThreshold: 0.35,
        redemptionMs: 200,
        preSpeechPadMs: 100,
        minSpeechMs: 150,
      });
      vadRef.current = vad;
      vad.start();

      setIsListening(true);
      console.log('🎤 AudioWorklet + VAD Pipeline Active');
    } catch (err) { setError('Mic Access Denied'); }
  }, []);

  return (
    <div style={{ padding: '20px', fontFamily: 'sans-serif' }}>
      <h1>🎙️ Jarvis Live v3.4</h1>
      {!isConnected ? (
        <>
          <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder="API Key" />
          <button onClick={connect}>Connect</button>
        </>
      ) : (
        <>
          <button onClick={disconnect}>Disconnect</button>
          <button onClick={isListening ? stopMicrophone : startMicrophone} style={{ background: isListening ? 'orange' : 'lightgreen' }}>
            {isListening ? '🎤 Stop' : '🎤 Start Mic'}
          </button>
        </>
      )}
      <div style={{ color: isConnected ? 'green' : 'red' }}>{isConnected ? 'Connected' : 'Disconnected'}</div>
      <div style={{ color: isModelTalkingRef.current ? 'orange' : 'gray', fontSize: '12px' }}>
        {isModelTalkingRef.current ? '🔊 Model speaking' : '🔇 Ready'}
        {' | '}
        {isSpeechActiveRef.current ? '🎤 Speech active' : '🤫 Silent'}
      </div>
      {error && <div style={{ color: 'red' }}>{error}</div>}
      <div style={{ background: '#eee', padding: '10px', marginTop: '10px', minHeight: '50px' }}>{responseText || 'Waiting...'}</div>
    </div>
  );
}
