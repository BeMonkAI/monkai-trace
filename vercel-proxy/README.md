# MonkAI Trace API — Public Proxy (Vercel Edge)

This directory hosts the [Vercel Edge Function](https://vercel.com/docs/functions/runtimes/edge-runtime)
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

## Why Vercel (vs Deno Deploy)

The proxy was originally on Deno Deploy. We migrated to Vercel for:

- **Preview deployments on every PR** that touches the proxy code,
  so we can test changes before they land in prod.
- **Larger ecosystem and community** — easier to debug at 3am.
- **Most of the team already has Vercel accounts** (one less vendor
  for new devs to onboard).

The Edge Function code is Web Standards (no Deno-specific APIs), so
we can move back or to any other edge platform in ~30 minutes if
needed.

## Project layout

```
vercel-proxy/
├── api/
│   └── proxy.ts        ← The Edge Function (one file, ~80 lines)
├── package.json        ← Marks this directory as a Vercel project
├── vercel.json         ← Rewrites every path → /api/proxy
└── README.md           ← This file
```

## Local dev

Use the Vercel CLI to mirror the production runtime exactly:

```bash
npx vercel dev
# Listens on :3000
curl http://localhost:3000/trace/v1/health
```

The function is plain Web Standards (Request/Response/fetch), so it
also runs under Deno or Cloudflare Workers with a 5-line wrapper if
you ever need to test it outside the Vercel runtime.

## Deploy

Production deploys happen automatically when this directory changes
on `main`, via Vercel's GitHub integration. The Vercel project root
is set to `vercel-proxy/`.

To deploy manually (e.g. before the GitHub integration is set up):

```bash
cd vercel-proxy
npx vercel deploy --prod --token "$VERCEL_TOKEN"
```

## Custom domain

`api.monkai.com.br` is configured in the Vercel project settings,
verified via a CNAME on `monkai.com.br` (managed in GoDaddy):

```
api.monkai.com.br  CNAME  cname.vercel-dns.com.
```

TLS is provisioned automatically by Vercel via Let's Encrypt.

## Operational notes

- **Free tier**: 100 GB-hours/month of edge compute. Way above
  current trace volume.
- **Edge regions**: Vercel auto-routes to the nearest region. Brazil
  traffic typically lands in São Paulo (GRU1).
- **No state**: the proxy is purely stateless.
- **Failure mode**: if Supabase is down, the proxy returns whatever
  Supabase returns (502/503). The proxy does not retry — that's
  the client's job (see `MIGRATION.md` § Retry Guidance).
- **Security**: the proxy does **not** touch the `Authorization` or
  `tracer_token` headers. Those flow through verbatim to the edge
  function which validates them.
