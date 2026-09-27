export default {
  async fetch(request, env) {
    const origin = (await env.ORIGIN_KV.get("HELIX_ORIGIN"))?.trim();
    if (!origin) {
      return offline("Demo temporarily offline: origin not registered.");
    }

    let target;
    try {
      target = new URL(origin);
      if (target.protocol !== "http:" && target.protocol !== "https:") {
        throw new Error("unsupported origin protocol");
      }
    } catch {
      return offline("Demo temporarily offline: registered origin is invalid.");
    }

    const incoming = new URL(request.url);
    target.pathname = incoming.pathname;
    target.search = incoming.search;
    const headers = new Headers(request.headers);
    headers.set("x-forwarded-host", incoming.host);
    headers.set("x-forwarded-proto", incoming.protocol.replace(":", ""));

    const visitor = request.headers.get("cf-connecting-ip");
    if (visitor) {
      headers.set("x-helix-client-ip", visitor);
    } else {
      headers.delete("x-helix-client-ip");
    }

    try {
      const response = await fetch(new Request(target, { method: request.method, headers, body: request.body, redirect: "manual" }));
      if (response.status === 530) {
        return offline("Demo temporarily offline: the registered origin's tunnel is down.");
      }
      return response;
    } catch {
      return offline("Demo temporarily offline: registered origin is unreachable.");
    }
  },
};

function offline(message) {
  return new Response(JSON.stringify({ error: "origin_unavailable", message }), {
    status: 503,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}
