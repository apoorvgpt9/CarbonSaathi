// CarbonSaathi SSE consumer for /api/insights/stream.
//
// Hand-rolled because EventSource cannot send Authorization headers, which
// the streaming endpoint requires.
//
// Frame format (from app/services/orchestrator.py):
//
//   event: phase_start | reasoning | phase_complete | done
//   data: <single-line JSON object, no newlines inside>
//   \n
//
// Cached path emits TWO phase_complete(status="cached") + ONE done with
// NO phase_start.  Callbacks here must not assume phase_start precedes
// phase_complete.

import { getIdToken } from "./auth.js";

const FRAME_DELIMITER = "\n\n";

/**
 * Stream the Analyst → Coach pipeline.
 *
 * @param {Object} opts
 * @param {(evt: {event: "phase_start", phase: string}) => void} [opts.onPhaseStart]
 * @param {(evt: {event: "reasoning", phase: string, step: string}) => void} [opts.onReasoningStep]
 * @param {(evt: {event: "phase_complete", phase: string, status: string, reason?: string}) => void} [opts.onPhaseComplete]
 * @param {(evt: {event: "done", insights: any[], recommendations: any[], analyst_status: string, coach_status: string}) => void} [opts.onDone]
 * @param {(err: Error) => void} [opts.onError]
 * @param {AbortSignal} [opts.signal]
 * @returns {Promise<void>}
 */
export async function streamInsights(opts) {
  const {
    onPhaseStart,
    onReasoningStep,
    onPhaseComplete,
    onDone,
    onError,
    signal,
  } = opts || {};

  let token;
  try {
    token = await getIdToken();
  } catch (err) {
    if (onError) {
      onError(err instanceof Error ? err : new Error(String(err)));
    }
    return;
  }

  let response;
  try {
    response = await fetch("/api/insights/stream", {
      method: "GET",
      headers: {
        Accept: "text/event-stream",
        Authorization: "Bearer " + token,
      },
      signal,
    });
  } catch (err) {
    if (signal && signal.aborted) {
      return;
    }
    if (onError) {
      onError(err instanceof Error ? err : new Error(String(err)));
    }
    return;
  }

  if (!response.ok) {
    if (onError) {
      onError(new Error("HTTP " + response.status));
    }
    return;
  }

  if (!response.body) {
    if (onError) {
      onError(new Error("Response has no body"));
    }
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: false });
  let buffer = "";

  try {
    while (true) {
      if (signal && signal.aborted) {
        await reader.cancel();
        return;
      }
      const { value, done } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf(FRAME_DELIMITER);
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + FRAME_DELIMITER.length);
        const parsed = _parseFrame(frame);
        if (parsed) {
          const stop = _dispatch(parsed, {
            onPhaseStart,
            onReasoningStep,
            onPhaseComplete,
            onDone,
            onError,
          });
          if (stop) {
            await reader.cancel();
            return;
          }
        }
        boundary = buffer.indexOf(FRAME_DELIMITER);
      }
    }
  } catch (err) {
    if (signal && signal.aborted) {
      return;
    }
    if (onError) {
      onError(err instanceof Error ? err : new Error(String(err)));
    }
  }
}

function _parseFrame(frame) {
  if (!frame) {
    return null;
  }
  let eventName = "message";
  let dataLine = "";
  const lines = frame.split("\n");
  for (const line of lines) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLine = line.slice(5).trim();
    }
  }
  if (!dataLine) {
    return null;
  }
  let payload;
  try {
    payload = JSON.parse(dataLine);
  } catch (_err) {
    return null;
  }
  return { eventName, payload };
}

function _dispatch(parsed, callbacks) {
  const { eventName, payload } = parsed;
  switch (eventName) {
    case "phase_start":
      if (callbacks.onPhaseStart) {
        callbacks.onPhaseStart(payload);
      }
      return false;
    case "reasoning":
    case "reasoning_step":
      if (callbacks.onReasoningStep) {
        callbacks.onReasoningStep(payload);
      }
      return false;
    case "phase_complete":
      if (callbacks.onPhaseComplete) {
        callbacks.onPhaseComplete(payload);
      }
      return false;
    case "done":
      if (callbacks.onDone) {
        callbacks.onDone(payload);
      }
      return true;
    default:
      return false;
  }
}

window.csaathi = window.csaathi || {};
window.csaathi.sse = { streamInsights };
