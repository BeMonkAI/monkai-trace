/**
 * MonkAI Trace API — public proxy.
 *
 * Lives at https://api.monkai.com.br/ on Deno Deploy and forwards
 * requests to the underlying Supabase edge function. Decouples the
 * public hostname/path from the (much uglier) Supabase URL so we can
 * eventually move the backend off Supabase without breaking clients.
 *
 *   public:    https://api.monkai.com.br/trace/v1/sessions/create
 *   internal:  https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api/v1/sessions/create
 *
 * Path mapping
 * ------------
 * Everything under `/trace/*` is forwarded verbatim to the function,
 * with `/trace` stripped:
 *
 *   /trace/v1/sessions/create          → /functions/v1/monkai-api/v1/sessions/create
 *   /trace/sessions/create   (legacy)  → /functions/v1/monkai-api/sessions/create
 *   /trace/v1/health                   → /functions/v1/monkai-api/v1/health
 *
 * Paths outside `/trace/*` return a structured 404 with a pointer to
 * the docs site. We deliberately do NOT serve the docs from this host
 * to keep concerns separate (`trace-docs.monkai.com.br` is the docs).
 *
 * Method/header pass-through
 * --------------------------
 * - All methods forwarded as-is (GET, POST, PUT, HEAD, OPTIONS, etc.).
 * - All request headers forwarded except `host` (rewritten to upstream)
 *   and the `cf-connecting-ip` family that fetch() rejects.
 * - All response headers passed through (so X-Request-ID, X-RateLimit-*,
 *   Idempotency-Replay, etc. reach the client unchanged).
 * - Response body is streamed (no buffering).
 *
 * Deployment
 * ----------
 *   deno install -gAfr jsr:@deno/deployctl   # one-time
 *   cd deno-proxy
 *   DENO_DEPLOY_TOKEN=ddp_... deployctl deploy --project=monkai-trace-proxy proxy.ts
 *
 * Then attach the custom domain `api.monkai.com.br` in the Deno Deploy
 * dashboard and add the verification CNAME on the GoDaddy side.
 */

const UPSTREAM_BASE =
  "https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api";
const TRACE_PREFIX = "/trace";

Deno.serve(async (req: Request): Promise<Response> => {
  const url = new URL(req.url);

  // /trace            → upstream root (rare; mostly meaningful for /trace/v1/health etc)
  // /trace/<rest>     → upstream /<rest>
  // anything else     → structured 404 pointing at the docs
  let upstreamPath: string;
  if (url.pathname === TRACE_PREFIX || url.pathname === TRACE_PREFIX + "/") {
    upstreamPath = "/";
  } else if (url.pathname.startsWith(TRACE_PREFIX + "/")) {
    upstreamPath = url.pathname.slice(TRACE_PREFIX.length); // keeps leading "/"
  } else {
    return jsonError(
      404,
      "not_found",
      "This host serves the MonkAI Trace API under /trace/v1/. " +
        "See https://trace-docs.monkai.com.br for the contract.",
    );
  }

  const target = UPSTREAM_BASE + upstreamPath + url.search;

  // Strip headers that confuse `fetch()` or leak the proxy origin.
  const proxiedHeaders = new Headers(req.headers);
  proxiedHeaders.delete("host");
  proxiedHeaders.delete("cf-connecting-ip");
  proxiedHeaders.delete("cf-ipcountry");
  proxiedHeaders.delete("cf-ray");
  proxiedHeaders.delete("cf-visitor");
  // Hint upstream that this is a proxied request (useful for debugging).
  proxiedHeaders.set("x-forwarded-host", url.host);
  proxiedHeaders.set("x-forwarded-proto", url.protocol.replace(":", ""));

  // Bodyless methods must NOT carry a body or `fetch` rejects them.
  const bodylessMethod = req.method === "GET" || req.method === "HEAD";
  const upstream = await fetch(target, {
    method: req.method,
    headers: proxiedHeaders,
    body: bodylessMethod ? undefined : req.body,
    redirect: "manual",
  });

  // Pass status, headers, body straight through. Don't clone — let
  // Deno Deploy stream the response back to the client.
  return new Response(upstream.body, {
    status: upstream.status,
    headers: upstream.headers,
  });
});

function jsonError(status: number, code: string, message: string): Response {
  return new Response(
    JSON.stringify({
      error: {
        code,
        message,
        request_id: crypto.randomUUID(),
      },
    }),
    {
      status,
      headers: {
        "content-type": "application/json",
        "x-request-id": crypto.randomUUID(),
      },
    },
  );
}
