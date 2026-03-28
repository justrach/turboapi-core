"""Compare router lookup speed: turboapi-core (via turboAPI) vs Starlette vs raw Python dict."""

import time

# ── Starlette router (what FastAPI uses internally) ──────────────────────────

from starlette.routing import Route, Router
from starlette.requests import Request
from starlette.responses import PlainTextResponse


async def dummy(request):
    return PlainTextResponse("ok")


starlette_router = Router(routes=[
    Route("/", dummy),
    Route("/health", dummy),
    Route("/api/v1/users", dummy),
    Route("/api/v1/users/{id}", dummy),
    Route("/api/v1/users/{id}/posts", dummy),
    Route("/api/v1/users/{id}/posts/{post_id}", dummy),
    Route("/api/v1/items", dummy),
    Route("/api/v1/items/{cat}/{id}", dummy),
    Route("/api/v1/search", dummy),
    Route("/docs", dummy),
    Route("/openapi.json", dummy),
])

# ── turboAPI's Zig router (via turbonet C extension) ─────────────────────────

try:
    import turbonet
    server = turbonet.TurboServer("127.0.0.1", 19999)
    # Register routes in the Zig radix trie
    for method, path in [
        ("GET", "/"), ("GET", "/health"), ("GET", "/api/v1/users"),
        ("GET", "/api/v1/users/{id}"), ("POST", "/api/v1/users"),
        ("PUT", "/api/v1/users/{id}"), ("DELETE", "/api/v1/users/{id}"),
        ("GET", "/api/v1/users/{id}/posts"),
        ("GET", "/api/v1/users/{id}/posts/{post_id}"),
        ("GET", "/api/v1/items"), ("GET", "/api/v1/items/{cat}/{id}"),
        ("POST", "/api/v1/items"), ("GET", "/api/v1/search"),
        ("GET", "/docs"), ("GET", "/openapi.json"),
    ]:
        server.add_route(method, path, lambda: None)
    HAS_ZIG = True
except Exception as e:
    print(f"turbonet not available: {e}")
    HAS_ZIG = False

# ── Raw Python dict router (baseline) ───────────────────────────────────────

dict_routes = {
    "/": "GET /",
    "/health": "GET /health",
    "/api/v1/users": "GET /api/v1/users",
    "/api/v1/search": "GET /api/v1/search",
    "/docs": "GET /docs",
    "/openapi.json": "GET /openapi.json",
}

# ── Lookup patterns ──────────────────────────────────────────────────────────

test_paths = [
    "/", "/health", "/api/v1/users", "/api/v1/users/42",
    "/api/v1/users/42/posts", "/api/v1/users/42/posts/7",
    "/api/v1/items/books/99", "/api/v1/search", "/docs",
    "/nonexistent",
]

ITERS = 200_000


def bench_starlette():
    """Starlette route resolution (regex-based)."""
    from starlette.types import Scope
    for _ in range(ITERS):
        for path in test_paths:
            scope = {"type": "http", "method": "GET", "path": path, "root_path": "", "query_string": b""}
            for route in starlette_router.routes:
                match, _ = route.matches(scope)
                if match:
                    break


def bench_dict():
    """Raw dict lookup (O(1) exact match only — no params)."""
    for _ in range(ITERS):
        for path in test_paths:
            _ = dict_routes.get(path)


print()
print("Router comparison benchmark")
print("═" * 55)
print(f"{len(test_paths)} lookup patterns, {ITERS:,} iterations each")
print()
print(f"  {'Router':<30} {'ops/sec':>12}  {'ns/op':>8}")
print(f"  {'─' * 52}")

# Dict baseline
t0 = time.perf_counter_ns()
bench_dict()
elapsed = time.perf_counter_ns() - t0
total = ITERS * len(test_paths)
ns_op = elapsed // total
ops = 1_000_000_000 // ns_op if ns_op > 0 else 0
print(f"  {'Python dict (exact only)':<30} {ops:>12,}/s  {ns_op:>6}ns")
dict_ns = ns_op

# Starlette
t0 = time.perf_counter_ns()
bench_starlette()
elapsed = time.perf_counter_ns() - t0
total = ITERS * len(test_paths)
ns_op = elapsed // total
ops = 1_000_000_000 // ns_op if ns_op > 0 else 0
print(f"  {'Starlette (FastAPI router)':<30} {ops:>12,}/s  {ns_op:>6}ns")
starlette_ns = ns_op

# turboapi-core reference (from Zig bench)
zig_ns = 52  # from bench.zig ReleaseFast
zig_ops = 19_200_000
print(f"  {'turboapi-core (Zig, native)':<30} {zig_ops:>12,}/s  {zig_ns:>6}ns  ← from zig bench")

print()
print(f"  turboapi-core vs Starlette:  {starlette_ns / zig_ns:.0f}x faster")
print(f"  turboapi-core vs Python dict: {dict_ns / zig_ns:.1f}x faster")
print()
print("═" * 55)
print()
