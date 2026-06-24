import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchStatus, fetchDeepSeekResearch } from "./client";

/**
 * Smoke tests for the request helper exposed via fetchStatus / fetchDeepSeekResearch.
 *
 * We exercise the public surface (fetchStatus uses a plain GET; fetchDeepSeekResearch
 * exposes the timeout + signal branches) rather than reaching into requestJson.
 */
describe("api client requestJson branches", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("returns data on a 200 OK response", async () => {
    const payload = { status: "ok", time: "2026-06-24T00:00:00Z" };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        })
      )
    );

    const result = await fetchStatus();
    expect(result.error).toBeNull();
    expect(result.data).toEqual(payload);
  });

  it("returns an HTTP-error message when the server returns 500", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("internal boom", { status: 500 })
      )
    );

    const result = await fetchStatus();
    expect(result.data).toBeNull();
    expect(result.error).toMatch(/HTTP 500/);
  });

  it("returns the thrown error message when fetch rejects with a network failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("network down"))
    );

    const result = await fetchStatus();
    expect(result.data).toBeNull();
    expect(result.error).toBe("network down");
  });

  it("returns a timeout message when the request exceeds timeoutMs", async () => {
    // fetch never resolves on its own — the AbortController inside requestJson
    // must fire after timeoutMs and the catch must translate AbortError into
    // the "seconds" timeout message.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_url: string, init: RequestInit) => {
        return new Promise((_resolve, reject) => {
          const signal = init.signal;
          if (signal) {
            signal.addEventListener("abort", () => {
              const err = new Error("aborted");
              err.name = "AbortError";
              reject(err);
            });
          }
        });
      })
    );

    // 50ms timeout via fetchDeepSeekResearch — it forwards a timeoutMs.
    // We override the default 180s by passing through; instead, call requestJson
    // indirectly: the easiest way is to use fetchDeepSeekResearch with an
    // immediately-aborting signal to force the AbortError + timed-out=false
    // path. But for timed-out=true we need timeoutMs. So we monkey-patch the
    // call by wrapping fetchDeepSeekResearch which already sets timeoutMs: 180_000.
    //
    // Simpler approach: trigger by faking timers and waiting for the 180s
    // default to elapse via vi.useFakeTimers.
    vi.useFakeTimers();
    const promise = fetchDeepSeekResearch("daily_brief", "brief", "test");
    await vi.advanceTimersByTimeAsync(180_001);
    const result = await promise;
    vi.useRealTimers();

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/秒/);
  });

  it("returns a cancellation message when the caller's AbortSignal is already aborted", async () => {
    // When the signal is pre-aborted, the controller inside requestJson aborts
    // before fetch resolves, so fetch should reject with AbortError.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_url: string, init: RequestInit) => {
        return new Promise((_resolve, reject) => {
          const signal = init.signal;
          if (signal?.aborted) {
            const err = new Error("aborted");
            err.name = "AbortError";
            reject(err);
            return;
          }
          signal?.addEventListener("abort", () => {
            const err = new Error("aborted");
            err.name = "AbortError";
            reject(err);
          });
        });
      })
    );

    const controller = new AbortController();
    controller.abort();

    const result = await fetchDeepSeekResearch(
      "daily_brief",
      "brief",
      "test",
      controller.signal
    );
    expect(result.data).toBeNull();
    // When timedOut is false the branch returns "请求已取消。".
    expect(result.error).toBe("请求已取消。");
  });
});
