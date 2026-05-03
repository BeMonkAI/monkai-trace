# MonkAI Trace API — Public Proxy

This directory hosts the [Deno Deploy](https://deno.com/deploy) worker
that fronts the MonkAI Trace API at `https://api.monkai.com.br/`.

## Why a proxy

Without it, every published example would have to use the raw
Supabase URL:

```
https://lpvbvnqrozlwalnkvrgk.supabase.co/functions/v1/monkai-api/v1/sessions/create
```

The proxy gives us the clean URL the OpenAPI spec advertises:

```
https://api.monkai.com.br/trace/v1/sessions/create
```

It also future-proofs the public contract: if we ever migrate the
backend off Supabase, only the proxy upstream changes — clients
never need to update their URLs.

## What it does

A single 60-line `Deno.serve` handler that forwards `/trace/*` to
the upstream Supabase edge function and returns a structured 404
for any other path. See `proxy.ts` for the path-mapping table and
the headers it strips/forwards.

## Local dev

```bash
deno run --allow-net proxy.ts
# Listens on :8000 by default.
curl http://localhost:8000/trace/v1/health
```

## Deploy

```bash
deno install -gAfr jsr:@deno/deployctl     # one-time
DENO_DEPLOY_TOKEN=ddp_xxx deployctl deploy \
  --project=monkai-trace-proxy             \
  --prod                                   \
  proxy.ts
```

Then, in the Deno Deploy dashboard:

1. Project → Settings → **Domains** → add `api.monkai.com.br`
2. Add the verification CNAME / TXT on the GoDaddy side
3. Wait for TLS provisioning (~minutes)

## Operational notes

- **Free tier**: 100k requests/day, 1M/month. Way above current
  trace volume.
- **Edge regions**: Deno Deploy auto-routes to the nearest region.
  Brazil traffic typically lands in São Paulo.
- **No state**: the proxy is purely stateless; restart-safe.
- **Failure mode**: if Supabase is down, the proxy returns whatever
  Supabase returns (502/503). The proxy does not retry — that's
  the client's job (see `MIGRATION.md` § Retry Guidance).
- **Security**: the proxy does **not** touch the `Authorization`
  or `tracer_token` headers. Those flow through verbatim to the
  edge function which validates them.
