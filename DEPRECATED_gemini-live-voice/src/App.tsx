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
  const inputAudioContextRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const playbackContextRef = useRef<AudioContext | null>(null);
  const nextPlayTimeRef = useRef<number>(0);
  const workletUrlRef = useRef<string | null>(null);
  const vadRef = useRef<MicVAD | null>(null);

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
      const resp = await fetch(`http://127.0.0.1:8088/api/agent/memory`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool: name, args })
      });
      return JSON.stringify(await resp.json());
    } catch (err: any) {
      return JSON.stringify({ error: err.message });
    }
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
    if (inputAudioContextRef.current) {
      inputAudioContextRef.current.close();
      inputAudioContextRef.current = null;
    }
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
    if (sessionRef.current) {
      try { sessionRef.current.close(); } catch {}
      sessionRef.current = null;
    }
    if (playbackContextRef.current) {
      playbackContextRef.current.close();
      playbackContextRef.current = null;
    }
    nextPlayTimeRef.current = 0;
    isModelTalkingRef.current = false;
    isConnectedRef.current = false;
    setIsConnected(false);
    setResponseText('');
  }, [stopMicrophone]);

  const connect = useCallback(async () => {
    if (!apiKey) return setError('Please enter API Key');
    try {
      setError(null);
      const genAI = new GoogleGenAI({ apiKey });
      const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 24000 });
      playbackContextRef.current = audioCtx;
      nextPlayTimeRef.current = audioCtx.currentTime;

      sessionRef.current = await genAI.live.connect({
        model: 'gemini-2.5-flash-native-audio-preview-12-2025',
        config: {
          generationConfig: { responseModalities: ["AUDIO"] },
          voiceConfig: {
            automatic_activity_detection: { disabled: true }
          },
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
              isModelTalkingRef.current = false;
            }
            if (message.serverContent?.interrupted) {
              isModelTalkingRef.current = false;
              nextPlayTimeRef.current = playbackContextRef.current?.currentTime ?? 0;
            }

            // Audio playback — NEVER gated, always plays
            const parts = message.serverContent?.modelTurn?.parts;
            if (parts && playbackContextRef.current) {
              const ctx = playbackContextRef.current;
              for (const part of parts) {
                if (part.inlineData?.data) {
                  const raw = atob(part.inlineData.data);
                  const uint8 = new Uint8Array(raw.length);
                  for (let i = 0; i < raw.length; i++) uint8[i] = raw.charCodeAt(i);
                  const int16 = new Int16Array(uint8.buffer);
                  const float32 = new Float32Array(int16.length);
                  for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768.0;
                  const buffer = ctx.createBuffer(1, float32.length, 24000);
                  buffer.getChannelData(0).set(float32);
                  const source = ctx.createBufferSource();
                  source.buffer = buffer;
                  source.connect(ctx.destination);
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
              isModelTalkingRef.current = false;
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
    if (!sessionRef.current) return;
    try {
      // Hardware DSP constraints
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
      streamRef.current = stream;

      const audioCtx = new window.AudioContext({ sampleRate: 16000 });
      inputAudioContextRef.current = audioCtx;

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
        if (isModelTalkingRef.current) return;
        if (!isSpeechActiveRef.current) return; // ← VAD GATE

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
