/**
 * MonkAI Trace API — public proxy on Vercel Edge.
 *
 * Lives at https://api.monkai.com.br/ and forwards `/trace/*` to the
 * underlying Supabase edge function. Decouples the public hostname/
 * path from the (much uglier) Supabase URL so we can eventually move
 * the backend off Supabase without breaking clients.
 *
 *   public:    https://api.monkai.com.br/trace/v1/sessions/create
 *   internal:  https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api/v1/sessions/create
 *
 * `vercel.json` rewrites every incoming path to this single Edge
 * function so it can implement the prefix-strip logic itself instead
 * of relying on Vercel's filesystem routing (which doesn't compose
 * well with a single catch-all proxy).
 */

export const config = {
  runtime: "edge",
};

const UPSTREAM_BASE =
  "https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api";
const TRACE_PREFIX = "/trace";

export default async function handler(req: Request): Promise<Response> {
  const url = new URL(req.url);

  // /trace            → upstream root
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
  proxiedHeaders.set("x-forwarded-host", url.host);
  proxiedHeaders.set("x-forwarded-proto", url.protocol.replace(":", ""));

  const bodylessMethod = req.method === "GET" || req.method === "HEAD";
  const upstream = await fetch(target, {
    method: req.method,
    headers: proxiedHeaders,
    body: bodylessMethod ? undefined : req.body,
    redirect: "manual",
  });

  // Stream the upstream body and pass status/headers through unchanged.
  return new Response(upstream.body, {
    status: upstream.status,
    headers: upstream.headers,
  });
}

function jsonError(status: number, code: string, message: string): Response {
  const requestId = crypto.randomUUID();
  return new Response(
    JSON.stringify({
      error: { code, message, request_id: requestId },
    }),
    {
      status,
      headers: {
        "content-type": "application/json",
        "x-request-id": requestId,
      },
    },
  );
}
