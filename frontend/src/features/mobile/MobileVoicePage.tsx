import { ArrowLeft, Loader2, Mic, Radio, RefreshCcw, ShieldAlert, Square } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import {
  getMobileVoiceBootstrap,
  getMobileVoiceWebSocketUrl,
  initProjectKnowledgeBase,
} from '../../lib/api';
import type { MobileVoiceBootstrap, SourceRecord } from '../../lib/types';

type ProviderEventMessage = {
  type: 'provider_event';
  event_id: number;
  event_name: string;
  payload: Record<string, unknown>;
  received_at: string;
};

type RoundStartedMessage = {
  type: 'round_started';
  project_id: string;
  source_id: string;
  source_name: string;
  initial_prompt: string;
};

type RoundSyncedMessage = {
  type: 'round_synced';
  source: SourceRecord;
};

type ErrorMessage = {
  type: 'error';
  provider: string;
  message: string;
};

type TranscriptRow = {
  id: string;
  role: 'user' | 'assistant' | 'system';
  text: string;
  final: boolean;
  questionId?: string | null;
  replyId?: string | null;
};

const TARGET_SAMPLE_RATE = 16000;
const TTS_SAMPLE_RATE = 24000;
const PACKET_SAMPLES = 320;
const PROCESSOR_BUFFER_SIZE = 2048;
const SPEECH_THRESHOLD = 0.014;
const SILENCE_HOLD_MS = 850;
const MAX_SPEECH_SEGMENT_MS = 12000;
const ASSISTANT_REPLY_RETRY_MS = 6000;
const ASSISTANT_TTS_START_GUARD_MS = 800;
const ASSISTANT_TTS_END_GUARD_MS = 1200;

function providerTone(status: string) {
  if (status === 'ready' || status === 'indexed') return 'success' as const;
  if (status.includes('config') || status.includes('required') || status.includes('failed'))
    return 'warning' as const;
  return 'default' as const;
}

function evidenceReadyForVoice(status: string) {
  return ['ready', 'empty', 'degraded', 'indexing'].includes(status);
}

function relativeTime(value: string) {
  return new Date(value).toLocaleString('zh-CN');
}

function describeRoundStatus(status: string) {
  if (status === 'indexed') return '已入库';
  if (status === 'index_failed') return '入库失败';
  if (status === 'indexing') return '入库中';
  if (status === 'pending') return '待入库';
  return status;
}

function isClosedInterviewRound(round: SourceRecord) {
  return (round.normalize_summary ?? '').includes('本轮已结束');
}

function logMobileVoiceDebug(label: string, detail?: Record<string, unknown>) {
  if (!import.meta.env.DEV) {
    return;
  }
  const timestamp = new Date().toISOString();
  if (detail) {
    console.info(`[mobile-voice] ${timestamp} ${label}`, detail);
    return;
  }
  console.info(`[mobile-voice] ${timestamp} ${label}`);
}

function mergeText(current: string, incoming: string) {
  if (!current) return incoming;
  if (incoming.startsWith(current)) return incoming;
  if (current.startsWith(incoming)) return current;

  let overlap = Math.min(current.length, incoming.length);
  while (overlap > 0) {
    if (current.endsWith(incoming.slice(0, overlap))) {
      return current + incoming.slice(overlap);
    }
    overlap -= 1;
  }
  return `${current}${incoming}`;
}

function downsampleBuffer(input: Float32Array, inputRate: number, outputRate: number) {
  if (inputRate === outputRate) return input;
  const ratio = inputRate / outputRate;
  const newLength = Math.round(input.length / ratio);
  const result = new Float32Array(newLength);
  let offsetResult = 0;
  let offsetBuffer = 0;

  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
    let accum = 0;
    let count = 0;
    for (let i = offsetBuffer; i < nextOffsetBuffer && i < input.length; i += 1) {
      accum += input[i];
      count += 1;
    }
    result[offsetResult] = count > 0 ? accum / count : 0;
    offsetResult += 1;
    offsetBuffer = nextOffsetBuffer;
  }

  return result;
}

function calculateRms(samples: Float32Array) {
  if (samples.length === 0) return 0;
  let total = 0;
  for (let i = 0; i < samples.length; i += 1) {
    total += samples[i] * samples[i];
  }
  return Math.sqrt(total / samples.length);
}

function createPcmBuffer(samples: number[]) {
  const buffer = new ArrayBuffer(samples.length * 2);
  const view = new DataView(buffer);
  samples.forEach((sample, index) => {
    view.setInt16(index * 2, sample, true);
  });
  return buffer;
}

export function MobileVoicePage() {
  const { projectId = '' } = useParams();
  const [bootstrap, setBootstrap] = useState<MobileVoiceBootstrap | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [initializingKnowledgeBase, setInitializingKnowledgeBase] = useState(false);
  const [sessionReady, setSessionReady] = useState(false);
  const [statusLabel, setStatusLabel] = useState('待开始');
  const [transcriptRows, setTranscriptRows] = useState<TranscriptRow[]>([]);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [isUserSpeaking, setIsUserSpeaking] = useState(false);

  const transcriptBottomRef = useRef<HTMLDivElement | null>(null);
  const websocketRef = useRef<WebSocket | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const playbackContextRef = useRef<AudioContext | null>(null);
  const scriptNodeRef = useRef<ScriptProcessorNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const playbackScheduledTimeRef = useRef(0);
  const playbackSourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set());
  const assistantSpeechFallbackTimerRef = useRef<number | null>(null);
  const assistantPlaybackStartedRef = useRef(false);
  const latestAssistantTextRef = useRef('');
  const outgoingSamplesRef = useRef<number[]>([]);
  const waitingAssistantReplyRef = useRef(false);
  const lastEndAsrAtRef = useRef(0);
  const assistantReplyRetryCountRef = useRef(0);
  const receivedAsrSinceEndRef = useRef(false);
  const awaitingAsrEndedRef = useRef(false);
  const speechSegmentStartedAtRef = useRef(0);
  const assistantSpeechActiveRef = useRef(false);
  const assistantSpeechGuardUntilRef = useRef(0);
  const currentUserRowIdRef = useRef<string | null>(null);
  const currentUserQuestionIdRef = useRef<string | null>(null);
  const currentAssistantRowIdRef = useRef<string | null>(null);
  const currentAssistantQuestionIdRef = useRef<string | null>(null);
  const currentAssistantReplyIdRef = useRef<string | null>(null);
  const autoInitAttemptedProjectIdRef = useRef<string | null>(null);
  const sessionLiveRef = useRef(false);
  const speechSegmentOpenRef = useRef(false);
  const silenceDurationMsRef = useRef(0);
  const activeRoundSourceIdRef = useRef<string | null>(null);

  useEffect(() => {
    autoInitAttemptedProjectIdRef.current = null;
    setStatusLabel('待开始');
    void loadBootstrap();
  }, [projectId]);

  useEffect(() => {
    if (!bootstrap || bootstrap.evidence.status !== 'knowledge_base_missing') {
      return;
    }
    if (autoInitAttemptedProjectIdRef.current === projectId) {
      return;
    }

    autoInitAttemptedProjectIdRef.current = projectId;
    setInitializingKnowledgeBase(true);
    setStatusLabel('正在初始化项目知识库…');
    void initProjectKnowledgeBase(projectId)
      .then(() => loadBootstrap({ silent: true }))
      .catch((err) => {
        setError(err instanceof Error ? err.message : '项目知识库初始化失败。');
        setStatusLabel('项目知识库初始化失败');
      })
      .finally(() => {
        setInitializingKnowledgeBase(false);
      });
  }, [bootstrap, projectId]);

  useEffect(() => {
    transcriptBottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [transcriptRows, error]);

  useEffect(() => {
    if (!sessionReady) {
      setElapsedSeconds(0);
      return;
    }
    const timer = window.setInterval(() => {
      setElapsedSeconds((current) => current + 1);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [sessionReady]);

  useEffect(() => {
    return () => {
      finalizeSessionForUnload();
      stopCapture();
      closeVoiceSocket();
      stopPlayback();
      stopBrowserSpeech();
    };
  }, []);

  useEffect(() => {
    const handlePageHide = () => {
      finalizeSessionForUnload();
    };

    window.addEventListener('pagehide', handlePageHide);
    window.addEventListener('beforeunload', handlePageHide);
    return () => {
      window.removeEventListener('pagehide', handlePageHide);
      window.removeEventListener('beforeunload', handlePageHide);
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!waitingAssistantReplyRef.current) {
        return;
      }
      const socket = websocketRef.current;
      if (!socket || socket.readyState !== WebSocket.OPEN || isUserSpeaking) {
        return;
      }
      const elapsed = Date.now() - lastEndAsrAtRef.current;
      if (assistantReplyRetryCountRef.current === 0 && elapsed >= ASSISTANT_REPLY_RETRY_MS) {
        socket.send(JSON.stringify({ type: 'end_asr' }));
        assistantReplyRetryCountRef.current = 1;
        logMobileVoiceDebug('retry_end_asr', {
          elapsed_ms: elapsed,
          transcript_rows: transcriptRows.length,
        });
        setStatusLabel('等待助手回复稍久，正在重试…');
        return;
      }
      if (
        assistantReplyRetryCountRef.current > 0 &&
        elapsed >= ASSISTANT_REPLY_RETRY_MS * 2 &&
        !receivedAsrSinceEndRef.current
      ) {
        waitingAssistantReplyRef.current = false;
        assistantReplyRetryCountRef.current = 0;
        logMobileVoiceDebug('no_asr_after_end_asr', {
          elapsed_ms: elapsed,
          transcript_rows: transcriptRows.length,
        });
        setStatusLabel('这段语音没有识别到，请再说一遍');
      }
    }, 500);

    return () => window.clearInterval(timer);
  }, [isUserSpeaking, transcriptRows.length]);

  async function loadBootstrap(options?: { silent?: boolean }) {
    if (!options?.silent) {
      setLoading(true);
    }
    setError(null);
    try {
      const data = await getMobileVoiceBootstrap(projectId);
      setBootstrap(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : '手机端语音页加载失败。');
    } finally {
      if (!options?.silent) {
        setLoading(false);
      }
    }
  }

  async function ensurePlaybackContext() {
    const context =
      playbackContextRef.current ??
      new AudioContext({
        sampleRate: TTS_SAMPLE_RATE,
      });
    playbackContextRef.current = context;
    if (context.state === 'suspended') {
      await context.resume();
    }
    return context;
  }

  function clearAssistantSpeechFallbackTimer() {
    if (assistantSpeechFallbackTimerRef.current) {
      window.clearTimeout(assistantSpeechFallbackTimerRef.current);
      assistantSpeechFallbackTimerRef.current = null;
    }
  }

  function stopBrowserSpeech() {
    clearAssistantSpeechFallbackTimer();
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
  }

  function speakAssistantText(text: string) {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
      return;
    }
    const content = text.trim();
    if (!content) {
      return;
    }

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(content);
    utterance.lang = 'zh-CN';
    const preferredVoice = window.speechSynthesis
      .getVoices()
      .find((voice) => voice.lang.toLowerCase().startsWith('zh-cn'));
    if (preferredVoice) {
      utterance.voice = preferredVoice;
    }
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.onstart = () => setStatusLabel('助手正在朗读回复…');
    utterance.onerror = () => setStatusLabel('助手回复已生成，请继续说话');
    utterance.onend = () => setStatusLabel('可以继续说话');
    window.speechSynthesis.speak(utterance);
    window.speechSynthesis.resume();
  }

  function stopPlayback() {
    stopBrowserSpeech();
    const context = playbackContextRef.current;
    if (context) {
      playbackScheduledTimeRef.current = context.currentTime;
    }
    for (const node of playbackSourcesRef.current) {
      try {
        node.stop();
      } catch {
        // ignore
      }
    }
    playbackSourcesRef.current.clear();
  }

  function interruptAssistantReply() {
    stopPlayback();
    clearAssistantSpeechFallbackTimer();
    finalizeAssistantTranscript();
    assistantPlaybackStartedRef.current = false;
    assistantSpeechActiveRef.current = false;
    assistantSpeechGuardUntilRef.current = 0;
    latestAssistantTextRef.current = '';
  }

  function flushOutgoingSamples(flushPartial = false) {
    const socket = websocketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }

    const queue = outgoingSamplesRef.current;
    while (queue.length >= PACKET_SAMPLES) {
      socket.send(createPcmBuffer(queue.splice(0, PACKET_SAMPLES)));
    }

    if (flushPartial && queue.length > 0) {
      socket.send(createPcmBuffer(queue.splice(0, queue.length)));
    }
  }

  function pushAudioSamples(samples: Float32Array) {
    const queue = outgoingSamplesRef.current;
    for (let i = 0; i < samples.length; i += 1) {
      const sample = Math.max(-1, Math.min(1, samples[i]));
      queue.push(sample < 0 ? sample * 0x8000 : sample * 0x7fff);
    }
    flushOutgoingSamples(false);
  }

  function endSpeechSegment(nextStatus: string, options?: { suppressStatus?: boolean }) {
    if (!speechSegmentOpenRef.current || websocketRef.current?.readyState !== WebSocket.OPEN) {
      return;
    }
    flushOutgoingSamples(true);
    websocketRef.current.send(JSON.stringify({ type: 'end_asr' }));
    logMobileVoiceDebug('send_end_asr', {
      next_status: nextStatus,
      suppress_status: Boolean(options?.suppressStatus),
      buffered_samples: outgoingSamplesRef.current.length,
    });
    outgoingSamplesRef.current = [];
    speechSegmentOpenRef.current = false;
    speechSegmentStartedAtRef.current = 0;
    silenceDurationMsRef.current = 0;
    waitingAssistantReplyRef.current = true;
    awaitingAsrEndedRef.current = true;
    assistantPlaybackStartedRef.current = false;
    lastEndAsrAtRef.current = Date.now();
    assistantReplyRetryCountRef.current = 0;
    receivedAsrSinceEndRef.current = false;
    setIsUserSpeaking(false);
    if (!options?.suppressStatus) {
      setStatusLabel(nextStatus);
    }
  }

  function finalizeSessionForUnload() {
    const socket = websocketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }

    try {
      endSpeechSegment('', { suppressStatus: true });
      sessionLiveRef.current = false;
      assistantSpeechActiveRef.current = false;
      assistantSpeechGuardUntilRef.current = 0;
      socket.send(JSON.stringify({ type: 'finish_session' }));
    } catch {
      // ignore best-effort unload cleanup
    }
  }

  async function ensureCapturePipeline() {
    if (mediaStreamRef.current && audioContextRef.current && scriptNodeRef.current) {
      if (audioContextRef.current.state === 'suspended') {
        await audioContextRef.current.resume();
      }
      return;
    }

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    mediaStreamRef.current = stream;

    const audioContext = new AudioContext();
    audioContextRef.current = audioContext;
    const sourceNode = audioContext.createMediaStreamSource(stream);
    sourceNodeRef.current = sourceNode;
    const processor = audioContext.createScriptProcessor(PROCESSOR_BUFFER_SIZE, 1, 1);
    scriptNodeRef.current = processor;

    processor.onaudioprocess = (event) => {
      const output = event.outputBuffer.getChannelData(0);
      output.fill(0);

      if (!sessionLiveRef.current || websocketRef.current?.readyState !== WebSocket.OPEN) {
        return;
      }

      const input = event.inputBuffer.getChannelData(0);
      const downsampled = downsampleBuffer(input, audioContext.sampleRate, TARGET_SAMPLE_RATE);
      const frameDurationMs = (downsampled.length / TARGET_SAMPLE_RATE) * 1000;
      const rms = calculateRms(downsampled);
      const hasVoice = rms >= SPEECH_THRESHOLD;
      const assistantSpeechGuardActive =
        assistantSpeechActiveRef.current || Date.now() < assistantSpeechGuardUntilRef.current;

      if (hasVoice) {
        if (!speechSegmentOpenRef.current && assistantSpeechGuardActive) {
          logMobileVoiceDebug('ignore_voice_during_assistant_speech_guard', {
            rms,
            assistant_speaking: assistantSpeechActiveRef.current,
            guard_remaining_ms: Math.max(0, assistantSpeechGuardUntilRef.current - Date.now()),
          });
          return;
        }
        if (!speechSegmentOpenRef.current && awaitingAsrEndedRef.current) {
          logMobileVoiceDebug('ignore_voice_before_asr_ended', {
            rms,
            waiting_for_asr_end: awaitingAsrEndedRef.current,
          });
          return;
        }
        if (
          !speechSegmentOpenRef.current &&
          waitingAssistantReplyRef.current &&
          !assistantPlaybackStartedRef.current
        ) {
          logMobileVoiceDebug('ignore_voice_while_waiting_reply', {
            rms,
            waiting_for_reply: waitingAssistantReplyRef.current,
          });
          return;
        }
        if (!speechSegmentOpenRef.current) {
          speechSegmentOpenRef.current = true;
          speechSegmentStartedAtRef.current = Date.now();
          silenceDurationMsRef.current = 0;
          waitingAssistantReplyRef.current = false;
          assistantReplyRetryCountRef.current = 0;
          setIsUserSpeaking(true);
          logMobileVoiceDebug('speech_segment_started', {
            rms,
            sample_rate: audioContext.sampleRate,
          });
          setStatusLabel('正在听你说话…');
          interruptAssistantReply();
        }
        pushAudioSamples(downsampled);
        silenceDurationMsRef.current = 0;
        if (Date.now() - speechSegmentStartedAtRef.current >= MAX_SPEECH_SEGMENT_MS) {
          logMobileVoiceDebug('speech_segment_force_closed', {
            duration_ms: Date.now() - speechSegmentStartedAtRef.current,
          });
          endSpeechSegment('这段语音较长，已自动发出，正在等助手回复…');
        }
        return;
      }

      if (!speechSegmentOpenRef.current) {
        return;
      }

      pushAudioSamples(downsampled);
      silenceDurationMsRef.current += frameDurationMs;
      if (silenceDurationMsRef.current >= SILENCE_HOLD_MS) {
        logMobileVoiceDebug('speech_segment_silence_closed', {
          silence_ms: silenceDurationMsRef.current,
        });
        endSpeechSegment('这段语音已发出，正在等助手回复…');
      }
    };

    sourceNode.connect(processor);
    processor.connect(audioContext.destination);
  }

  function stopCapture() {
    speechSegmentOpenRef.current = false;
    speechSegmentStartedAtRef.current = 0;
    silenceDurationMsRef.current = 0;
    assistantSpeechActiveRef.current = false;
    assistantSpeechGuardUntilRef.current = 0;
    outgoingSamplesRef.current = [];
    awaitingAsrEndedRef.current = false;
    scriptNodeRef.current?.disconnect();
    sourceNodeRef.current?.disconnect();
    scriptNodeRef.current = null;
    sourceNodeRef.current = null;
    audioContextRef.current?.close().catch(() => undefined);
    audioContextRef.current = null;
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
  }

  function closeVoiceSocket() {
    websocketRef.current?.close();
    websocketRef.current = null;
    sessionLiveRef.current = false;
    speechSegmentOpenRef.current = false;
    speechSegmentStartedAtRef.current = 0;
    silenceDurationMsRef.current = 0;
    assistantSpeechActiveRef.current = false;
    assistantSpeechGuardUntilRef.current = 0;
    waitingAssistantReplyRef.current = false;
    awaitingAsrEndedRef.current = false;
    assistantReplyRetryCountRef.current = 0;
    lastEndAsrAtRef.current = 0;
    receivedAsrSinceEndRef.current = false;
    setSessionReady(false);
    setConnecting(false);
    setIsUserSpeaking(false);
    clearAssistantSpeechFallbackTimer();
  }

  async function playPcmChunk(buffer: ArrayBuffer) {
    const context = await ensurePlaybackContext();
    assistantPlaybackStartedRef.current = true;
    stopBrowserSpeech();
    const samples = new Int16Array(buffer);
    const audioBuffer = context.createBuffer(1, samples.length, TTS_SAMPLE_RATE);
    const channel = audioBuffer.getChannelData(0);
    for (let i = 0; i < samples.length; i += 1) {
      channel[i] = samples[i] / 32768;
    }

    const source = context.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(context.destination);
    const startAt = Math.max(playbackScheduledTimeRef.current, context.currentTime + 0.01);
    source.start(startAt);
    playbackScheduledTimeRef.current = startAt + audioBuffer.duration;
    playbackSourcesRef.current.add(source);
    source.onended = () => playbackSourcesRef.current.delete(source);
    setStatusLabel('助手正在朗读回复…');
  }

  function upsertUserTranscript(text: string, final: boolean, questionId?: string | null) {
    setTranscriptRows((current) => {
      const rowId =
        currentUserRowIdRef.current && questionId === currentUserQuestionIdRef.current
          ? currentUserRowIdRef.current
          : `user-${Date.now()}`;
      const exists = current.some((row) => row.id === rowId);
      const nextRow: TranscriptRow = {
        id: rowId,
        role: 'user',
        text,
        final,
        questionId,
      };
      currentUserRowIdRef.current = final ? null : rowId;
      currentUserQuestionIdRef.current = final ? null : questionId ?? null;
      return exists
        ? current.map((row) => (row.id === rowId ? { ...row, text, final, questionId } : row))
        : [...current, nextRow];
    });
  }

  function finalizeUserTranscript() {
    if (!currentUserRowIdRef.current) return;
    const rowId = currentUserRowIdRef.current;
    setTranscriptRows((current) =>
      current.map((row) => (row.id === rowId ? { ...row, final: true } : row))
    );
    currentUserRowIdRef.current = null;
    currentUserQuestionIdRef.current = null;
  }

  function upsertAssistantTranscript(
    text: string,
    questionId?: string | null,
    replyId?: string | null,
    final = false
  ) {
    setTranscriptRows((current) => {
      const normalizedQuestionId = questionId ?? null;
      const normalizedReplyId = replyId ?? null;
      const sameAssistantTurn =
        currentAssistantRowIdRef.current !== null &&
        ((normalizedReplyId !== null &&
          normalizedReplyId === currentAssistantReplyIdRef.current) ||
          (normalizedReplyId === null &&
            currentAssistantReplyIdRef.current === null &&
            normalizedQuestionId === currentAssistantQuestionIdRef.current));
      const rowId =
        sameAssistantTurn && currentAssistantRowIdRef.current
          ? currentAssistantRowIdRef.current
          : `assistant-${Date.now()}`;
      const exists = current.some((row) => row.id === rowId);
      const previous = current.find((row) => row.id === rowId)?.text ?? '';
      const merged = exists ? mergeText(previous, text) : text;
      latestAssistantTextRef.current = merged;
      const nextRow: TranscriptRow = {
        id: rowId,
        role: 'assistant',
        text: merged,
        final,
        questionId,
        replyId,
      };
      currentAssistantRowIdRef.current = final ? null : rowId;
      currentAssistantQuestionIdRef.current = final ? null : normalizedQuestionId;
      currentAssistantReplyIdRef.current = final ? null : replyId ?? null;
      return exists
        ? current.map((row) =>
            row.id === rowId ? { ...row, text: merged, final, questionId, replyId } : row
          )
        : [...current, nextRow];
    });
  }

  function finalizeAssistantTranscript() {
    if (!currentAssistantRowIdRef.current) return;
    const rowId = currentAssistantRowIdRef.current;
    setTranscriptRows((current) =>
      current.map((row) => (row.id === rowId ? { ...row, final: true } : row))
    );
    currentAssistantRowIdRef.current = null;
    currentAssistantQuestionIdRef.current = null;
    currentAssistantReplyIdRef.current = null;
  }

  function handleProviderEvent(message: ProviderEventMessage) {
    const payload = message.payload ?? {};
    logMobileVoiceDebug('provider_event', {
      event_id: message.event_id,
      event_name: message.event_name,
      waiting_for_reply: waitingAssistantReplyRef.current,
      session_ready: sessionReady,
      is_user_speaking: isUserSpeaking,
      payload,
    });
    if (message.event_id === 150) {
      sessionLiveRef.current = true;
      setConnecting(false);
      setSessionReady(true);
      setStatusLabel('通话已连通，直接开始说话');
      return;
    }
    if (message.event_id === 350) {
      assistantSpeechActiveRef.current = true;
      assistantSpeechGuardUntilRef.current = Date.now() + ASSISTANT_TTS_START_GUARD_MS;
      logMobileVoiceDebug('assistant_speech_guard_started', {
        guard_ms: ASSISTANT_TTS_START_GUARD_MS,
      });
      stopBrowserSpeech();
      setStatusLabel('助手正在朗读回复…');
      return;
    }
    if (message.event_id === 359) {
      assistantSpeechActiveRef.current = false;
      assistantSpeechGuardUntilRef.current = Date.now() + ASSISTANT_TTS_END_GUARD_MS;
      logMobileVoiceDebug('assistant_speech_guard_tail', {
        guard_ms: ASSISTANT_TTS_END_GUARD_MS,
      });
      setStatusLabel('可以继续说话');
      return;
    }
    if (message.event_id === 450) {
      waitingAssistantReplyRef.current = false;
      awaitingAsrEndedRef.current = false;
      interruptAssistantReply();
      setStatusLabel('听到你开始说话了…');
      return;
    }
    if (message.event_id === 451) {
      receivedAsrSinceEndRef.current = true;
      const results = Array.isArray(payload.results) ? payload.results : [];
      const head = results[0] as { text?: string; is_interim?: boolean } | undefined;
      const text = head?.text?.trim();
      if (text) {
        upsertUserTranscript(
          text,
          !head?.is_interim,
          (payload.question_id as string | undefined) ?? null
        );
      }
      return;
    }
    if (message.event_id === 459) {
      receivedAsrSinceEndRef.current = true;
      awaitingAsrEndedRef.current = false;
      finalizeUserTranscript();
      setIsUserSpeaking(false);
      waitingAssistantReplyRef.current = true;
      assistantReplyRetryCountRef.current = 0;
      lastEndAsrAtRef.current = Date.now();
      setStatusLabel('正在等待助手回复…');
      return;
    }
    if (message.event_id === 550) {
      waitingAssistantReplyRef.current = false;
      const content = typeof payload.content === 'string' ? payload.content.trim() : '';
      const questionId = (payload.question_id as string | undefined) ?? null;
      const replyId = (payload.reply_id as string | undefined) ?? null;
      const assistantTurnChanged =
        (replyId !== null && replyId !== currentAssistantReplyIdRef.current) ||
        (replyId === null &&
          questionId !== null &&
          questionId !== currentAssistantQuestionIdRef.current);
      if (assistantTurnChanged) {
        finalizeAssistantTranscript();
        assistantPlaybackStartedRef.current = false;
        latestAssistantTextRef.current = '';
        clearAssistantSpeechFallbackTimer();
      }
      if (content) {
        upsertAssistantTranscript(
          content,
          questionId,
          replyId,
          false
        );
      }
      setStatusLabel('助手正在组织回复…');
      return;
    }
    if (message.event_id === 559) {
      waitingAssistantReplyRef.current = false;
      finalizeAssistantTranscript();
      clearAssistantSpeechFallbackTimer();
      assistantSpeechFallbackTimerRef.current = window.setTimeout(() => {
        assistantSpeechFallbackTimerRef.current = null;
        if (!assistantPlaybackStartedRef.current && latestAssistantTextRef.current.trim()) {
          speakAssistantText(latestAssistantTextRef.current);
        }
      }, 120);
      setStatusLabel('助手回复已生成，准备朗读…');
    }
  }

  async function startSession() {
    if (!bootstrap || connecting || sessionReady) return;
    logMobileVoiceDebug('start_session_requested', {
      project_id: projectId,
      voice_status: bootstrap.voice.status,
      evidence_status: bootstrap.evidence.status,
    });
    setConnecting(true);
    setError(null);
    setTranscriptRows([]);
    setIsUserSpeaking(false);
    setStatusLabel('正在连接语音通话…');
    latestAssistantTextRef.current = '';
    assistantPlaybackStartedRef.current = false;
    stopBrowserSpeech();
    currentUserRowIdRef.current = null;
    currentUserQuestionIdRef.current = null;
    currentAssistantRowIdRef.current = null;
    currentAssistantQuestionIdRef.current = null;
    currentAssistantReplyIdRef.current = null;
    activeRoundSourceIdRef.current = null;
    outgoingSamplesRef.current = [];
    speechSegmentOpenRef.current = false;
    speechSegmentStartedAtRef.current = 0;
    silenceDurationMsRef.current = 0;
    assistantSpeechActiveRef.current = false;
    assistantSpeechGuardUntilRef.current = 0;
    waitingAssistantReplyRef.current = false;
    awaitingAsrEndedRef.current = false;
    assistantReplyRetryCountRef.current = 0;
    lastEndAsrAtRef.current = 0;

    try {
      interruptAssistantReply();
      await ensurePlaybackContext();
      const socket = new WebSocket(getMobileVoiceWebSocketUrl(projectId));
      socket.binaryType = 'arraybuffer';
      socket.onopen = () => {
        logMobileVoiceDebug('ws_open', {
          url: getMobileVoiceWebSocketUrl(projectId),
        });
      };
      socket.onmessage = (event) => {
        if (typeof event.data === 'string') {
          const message = JSON.parse(event.data) as
            | ProviderEventMessage
            | RoundStartedMessage
            | RoundSyncedMessage
            | ErrorMessage;

          if (message.type === 'round_started') {
            activeRoundSourceIdRef.current = message.source_id;
            logMobileVoiceDebug('round_started', {
              source_id: message.source_id,
              source_name: message.source_name,
            });
            setStatusLabel('正在建立语音通话…');
            return;
          }
          if (message.type === 'round_synced') {
            logMobileVoiceDebug('round_synced', {
              source_id: message.source.id,
              index_status: message.source.index_status,
              normalize_summary: message.source.normalize_summary,
            });
            return;
          }
          if (message.type === 'provider_event') {
            handleProviderEvent(message);
            return;
          }
          if (message.type === 'error') {
            logMobileVoiceDebug('ws_error_message', {
              provider: message.provider,
              message: message.message,
            });
            setError(message.message);
            setStatusLabel('语音链路报错');
            closeVoiceSocket();
          }
          return;
        }
        if (event.data instanceof ArrayBuffer) {
          logMobileVoiceDebug('ws_audio_chunk', {
            byte_length: event.data.byteLength,
          });
          void playPcmChunk(event.data);
          return;
        }
        if (event.data instanceof Blob) {
          logMobileVoiceDebug('ws_audio_blob', {
            size: event.data.size,
          });
          void event.data.arrayBuffer().then((buffer) => playPcmChunk(buffer));
        }
      };
      socket.onerror = () => {
        logMobileVoiceDebug('ws_error');
        setError('手机端实时语音连接失败。请检查实时语音配置和网络。');
        setStatusLabel('连接失败');
        closeVoiceSocket();
      };
      socket.onclose = () => {
        const shouldRefreshRounds = Boolean(activeRoundSourceIdRef.current);
        logMobileVoiceDebug('ws_close', {
          should_refresh_rounds: shouldRefreshRounds,
          transcript_rows: transcriptRows.length,
        });
        websocketRef.current = null;
        sessionLiveRef.current = false;
        speechSegmentOpenRef.current = false;
        speechSegmentStartedAtRef.current = 0;
        silenceDurationMsRef.current = 0;
        assistantSpeechActiveRef.current = false;
        assistantSpeechGuardUntilRef.current = 0;
        waitingAssistantReplyRef.current = false;
        awaitingAsrEndedRef.current = false;
        assistantReplyRetryCountRef.current = 0;
        lastEndAsrAtRef.current = 0;
        receivedAsrSinceEndRef.current = false;
        activeRoundSourceIdRef.current = null;
        setConnecting(false);
        setSessionReady(false);
        setIsUserSpeaking(false);
        stopCapture();
        stopPlayback();
        setStatusLabel('待开始');
        if (shouldRefreshRounds) {
          void loadBootstrap({ silent: true });
        }
      };
      websocketRef.current = socket;
      await ensureCapturePipeline();
    } catch (err) {
      closeVoiceSocket();
      setConnecting(false);
      setError(err instanceof Error ? err.message : '无法打开麦克风。');
      setStatusLabel('麦克风不可用');
    }
  }

  function finishSession() {
    if (!websocketRef.current) return;
    logMobileVoiceDebug('finish_session_requested', {
      transcript_rows: transcriptRows.length,
    });
    endSpeechSegment('正在结束当前对话…');
    sessionLiveRef.current = false;
    assistantSpeechActiveRef.current = false;
    assistantSpeechGuardUntilRef.current = 0;
    awaitingAsrEndedRef.current = false;
    websocketRef.current.send(JSON.stringify({ type: 'finish_session' }));
    setSessionReady(false);
    waitingAssistantReplyRef.current = false;
    receivedAsrSinceEndRef.current = false;
    setIsUserSpeaking(false);
    setStatusLabel('本轮正在入库…');
    stopPlayback();
    stopCapture();
    stopBrowserSpeech();
  }

  const canStartSession =
    bootstrap &&
    bootstrap.voice.status === 'ready' &&
    evidenceReadyForVoice(bootstrap.evidence.status) &&
    !connecting &&
    !initializingKnowledgeBase &&
    !sessionReady;
  const visibleTranscriptRows = transcriptRows.filter((row) => row.final);
  const visibleRecentRounds = (bootstrap?.recent_rounds ?? []).filter(isClosedInterviewRound);
  const waveformHeights = connecting
    ? [12, 18, 28, 40, 52, 64, 76, 64, 52, 40, 28, 18, 12]
    : sessionReady
      ? isUserSpeaking
        ? [16, 28, 44, 60, 76, 92, 108, 92, 76, 60, 44, 28, 16]
        : [12, 18, 26, 34, 42, 50, 58, 50, 42, 34, 26, 18, 12]
      : [10, 14, 20, 26, 32, 38, 44, 38, 32, 26, 20, 14, 10];

  if (loading) {
    return (
      <main className="min-h-screen bg-[#f7efe8] px-4 py-6 text-nearBlack">
        <div className="mx-auto flex min-h-[70vh] max-w-md items-center justify-center rounded-[30px] border border-[#eadcd1] bg-ivory">
          <Loader2 className="h-5 w-5 animate-spin text-terracotta" />
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,#ffe7d8,transparent_36%),linear-gradient(180deg,#f7efe8_0%,#efe5dc_100%)] px-4 py-4 text-nearBlack">
      <div className="mx-auto flex w-full max-w-md flex-col gap-3">
        <section className="rounded-[28px] border border-[#ecd9cd] bg-[linear-gradient(165deg,#fffaf6_0%,#f8ede4_58%,#ffe8da_100%)] p-4 shadow-[0_20px_60px_-42px_rgba(45,25,13,0.42)]">
          <div className="flex items-center justify-between">
            <Button asChild variant="ghost" size="sm" className="h-8 rounded-full px-2.5 text-[13px]">
              <Link to="/">
                <ArrowLeft className="h-4 w-4" />
                返回项目
              </Link>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 rounded-full px-2.5 text-[13px]"
              onClick={() => void loadBootstrap()}
            >
              <RefreshCcw className="h-4 w-4" />
              刷新
            </Button>
          </div>

          <div className="mt-3">
            <h1 className="text-[14px] font-medium leading-5 text-nearBlack">
              {bootstrap?.project.name}
            </h1>
          </div>

          <div className="hidden mt-2 flex flex-wrap gap-2">
            <Badge
              className="rounded-full px-2 py-1 text-[10px]"
              variant={providerTone(bootstrap?.voice.status ?? 'unknown')}
            >
              实时语音 · {bootstrap?.voice.status}
            </Badge>
            <Badge
              className="rounded-full px-2 py-1 text-[10px]"
              variant={providerTone(bootstrap?.evidence.status ?? 'unknown')}
            >
              项目知识库 · {bootstrap?.evidence.status}
            </Badge>
          </div>
        </section>

        <section className="rounded-[26px] border border-[#eadcd1] bg-ivory p-3 shadow-[0_16px_50px_-40px_rgba(45,25,13,0.35)]">
          <div className="mb-2 flex items-center justify-between gap-3">
            实时转写
          </div>
          <div
            className={[
              'overflow-y-auto rounded-[20px] border border-[#f0e2d6] bg-[#fffaf5] p-3',
              visibleTranscriptRows.length === 0 ? 'max-h-[120px]' : 'max-h-[28vh]',
            ].join(' ')}
          >
            <div className="grid gap-3">
              {visibleTranscriptRows.map((row) => (
                <div
                  key={row.id}
                  className={[
                    'rounded-[18px] px-3 py-2.5 text-[13px] leading-5',
                    row.role === 'user'
                      ? 'border border-[#e9d4c5] bg-[#fff3ea]'
                      : 'border border-[#d8e2da] bg-[#eef5ef]',
                  ].join(' ')}
                >
                  <div className="mb-1 text-[11px] uppercase tracking-[0.16em] text-stone [&>span:last-child]:hidden">
                    <span>{row.role === 'user' ? '用户' : '助手'}</span>
                    <span>{row.final ? '最终稿' : '实时草稿'}</span>
                  </div>
                  <div className="whitespace-pre-wrap text-nearBlack">{row.text}</div>
                </div>
              ))}
              {visibleTranscriptRows.length === 0 ? (
                <div className="rounded-[16px] border border-dashed border-[#dfc6b6] bg-white/90 px-4 py-5 text-center text-[13px] leading-6 text-stone">
                  通话开始后，用户和助手的转写会先出现在这里，并持续写入当前轮次文件。
                </div>
              ) : null}
              <div ref={transcriptBottomRef} />
            </div>
          </div>
        </section>

        <section className="rounded-[30px] border border-[#eadcd1] bg-ivory p-3.5 shadow-[0_18px_58px_-40px_rgba(45,25,13,0.38)]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.14em] text-stone">语音状态</div>
              <div className="mt-1 text-[13px] font-medium text-nearBlack">{statusLabel}</div>
            </div>
            <div className="rounded-full border border-[#e8d4c6] bg-[#fff8f2] px-2.5 py-1.5 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.7)]">
              <div className="text-[9px] uppercase tracking-[0.14em] text-stone">轮次时长</div>
              <div className="mt-0.5 font-mono text-[0.92rem] text-nearBlack">
                {String(Math.floor(elapsedSeconds / 60)).padStart(2, '0')}:
                {String(elapsedSeconds % 60).padStart(2, '0')}
              </div>
            </div>
          </div>

          <div className="mt-4 rounded-[28px] border border-[#efdfd2] bg-[linear-gradient(180deg,#fffdfb_0%,#fff5ed_100%)] px-4 py-5">
            <div className="relative mb-4 flex h-[168px] items-center justify-center overflow-hidden rounded-[24px] bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.92)_0%,rgba(255,242,232,0.86)_58%,rgba(244,225,211,0.82)_100%)]">
              <div className="pointer-events-none absolute inset-x-4 top-1/2 flex -translate-y-1/2 items-center justify-center gap-1.5">
                {waveformHeights.map((height, index) => (
                  <div
                    key={`wave-${height}-${index}`}
                    className={[
                      'rounded-full transition-all duration-300',
                      sessionReady
                        ? isUserSpeaking
                          ? 'bg-[#d7744b]/85'
                          : 'bg-[#88b08f]/78'
                        : 'bg-[#e4bfaa]/75',
                    ].join(' ')}
                    style={{
                      height: `${height}px`,
                      width: index === Math.floor(waveformHeights.length / 2) ? '7px' : '5px',
                      opacity: sessionReady || connecting ? 1 : 0.85,
                    }}
                  />
                ))}
              </div>
            <button
              type="button"
              disabled={!sessionReady && !canStartSession}
              onClick={() => {
                if (sessionReady) {
                  finishSession();
                  return;
                }
                void startSession();
              }}
              className={[
                'relative z-10 grid h-28 w-28 place-items-center rounded-full border transition-all duration-300',
                sessionReady
                  ? isUserSpeaking
                    ? 'border-[#d6673f] bg-[radial-gradient(circle,#ffeadb_0%,#f7c8ae_58%,#de8456_100%)] shadow-[0_0_0_10px_rgba(214,103,63,0.12),0_18px_40px_-24px_rgba(160,76,42,0.45)]'
                    : 'border-[#c9dbc7] bg-[radial-gradient(circle,#f3fbf3_0%,#e1f1e2_58%,#bddfbf_100%)] shadow-[0_0_0_10px_rgba(112,153,116,0.11),0_18px_40px_-24px_rgba(80,120,85,0.32)]'
                  : 'border-[#ebd8cb] bg-[radial-gradient(circle,#fff8f1_0%,#faebdf_72%,#f1ddd0_100%)] shadow-[0_14px_34px_-22px_rgba(45,25,13,0.35)]',
                !sessionReady && !canStartSession ? 'cursor-not-allowed opacity-60' : 'active:scale-[0.98]',
              ].join(' ')}
            >
              <div className="absolute inset-2 rounded-full border border-white/65" />
              <div className="absolute inset-5 rounded-full border border-white/45" />
              {connecting ? (
                <Loader2 className="h-8 w-8 animate-spin text-terracotta" />
              ) : sessionReady ? (
                isUserSpeaking ? (
                  <Radio className="h-8 w-8 text-[#7b3019]" />
                ) : (
                  <Square className="h-8 w-8 text-[#497052]" />
                )
              ) : (
                <Mic className="h-8 w-8 text-terracotta" />
              )}
            </button>

            </div>

            <div className="text-center">
              <div className="text-[15px] font-medium text-nearBlack">
                {connecting
                  ? '正在连接语音通话…'
                  : sessionReady
                    ? '结束通话'
                    : initializingKnowledgeBase
                      ? '初始化知识库中…'
                      : '开始语音通话'}
              </div>
              <div className="mt-2 text-[12px] leading-5 text-stone">
                {sessionReady
                  ? '只要你没有点结束，对话都会继续算同一轮；系统会按停顿自动分段，并持续写入当前轮次。'
                  : '点击后会开始一轮实时语音访谈，助手回复会直接朗读出来，同时持续写入项目知识库。'}
              </div>
            </div>
          </div>

          {error ? (
            <div className="mt-4 rounded-[20px] border border-[#e3c8c4] bg-[#fbeeec] px-4 py-3 text-sm leading-6 text-errorWarm">
              <div className="flex items-center gap-2 font-medium">
                <ShieldAlert className="h-4 w-4" />
                {error}
              </div>
            </div>
          ) : null}
        </section>

        <section className="rounded-[26px] border border-[#eadcd1] bg-ivory p-3.5 shadow-[0_16px_50px_-40px_rgba(45,25,13,0.35)]">
          <div className="mb-3 text-[12px] font-medium uppercase tracking-[0.18em] text-stone">
            最近语音轮次
          </div>
          <div className="grid gap-3">
            {visibleRecentRounds.map((round) => (
              <div
                key={round.id}
                className="rounded-[18px] border border-[#eadcd1] bg-[linear-gradient(180deg,#fffdf9_0%,#faf2e9_100%)] px-3.5 py-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-[13px] font-medium text-nearBlack">{round.name}</div>
                    <div className="mt-1 text-[11px] uppercase tracking-[0.16em] text-stone">
                      {relativeTime(round.created_at)}
                    </div>
                  </div>
                  <Badge variant={providerTone(round.index_status)}>
                    {describeRoundStatus(round.index_status)}
                  </Badge>
                </div>
                <p className="mt-2 text-[13px] leading-6 text-olive">
                  {round.normalize_summary ?? '当前没有摘要。'}
                </p>
              </div>
            ))}
            {visibleRecentRounds.length === 0 ? (
              <div className="rounded-[18px] border border-dashed border-[#dfc6b6] bg-white px-4 py-5 text-center text-sm leading-6 text-stone">
                当前还没有语音轮次，开始第一轮后会自动生成并持续入库。
              </div>
            ) : null}
          </div>
        </section>
      </div>
    </main>
  );
}
