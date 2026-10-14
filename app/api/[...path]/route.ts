import { NextRequest } from "next/server";
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const route = path.join("/");
  if (!/^(providers|tasks(?:\/[0-9a-f-]{36}(?:\/(?:events|cancel))?)?|bridge\/(?:heartbeat|claim|tasks\/[0-9a-f-]{36}\/update|browser\/(?:next|ack|tick|job|submitted)))$/.test(route)) return Response.json({ detail: "Неизвестный маршрут" }, { status: 404 });
  if (request.method === "POST") {
    const origin = request.headers.get("origin"), host = request.headers.get("host");
    if (request.headers.get("sec-fetch-site") === "cross-site" || (origin && new URL(origin).host !== host)) return Response.json({ detail: "Запрос с другого сайта запрещён" }, { status: 403 });
  }
  const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000", token = process.env.APP_ACCESS_TOKEN;
  if (!token) return Response.json({ detail: "Сервер не настроен: APP_ACCESS_TOKEN отсутствует" }, { status: 503 });
  if (route.startsWith('bridge/')) {
    const { timingSafeEqual } = await import('node:crypto');
    const supplied = Buffer.from(request.headers.get('x-portal-bridge') || '');
    const expected = Buffer.from(token);
    if (supplied.length !== expected.length || !timingSafeEqual(supplied,expected)) return Response.json({detail:'Нет доступа к обработчику'}, {status:401});
  }
  try {
    const upstream = await fetch(`${backend}/${route}${request.nextUrl.search}`, { method: request.method, headers: { "Content-Type": "application/json", "X-Portal-Token": token }, body: request.method === "POST" ? await request.text() : undefined, cache: "no-store", signal: request.signal });
    return new Response(upstream.body, { status: upstream.status, headers: { "Content-Type": upstream.headers.get("content-type") || "application/json", "Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no", "X-Content-Type-Options": "nosniff" } });
  } catch { return Response.json({ detail: "Нет связи с сервером портала. Проверьте контейнер api." }, { status: 503 }); }
}
export const GET = proxy;
export const POST = proxy;
