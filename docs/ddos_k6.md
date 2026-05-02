# k6 Rate Limit Test

This project uses application-level rate limiting in `server/main.py` as a basic anti-abuse layer. k6 does not block DDoS traffic by itself; it is used here to verify that the backend starts returning `429 Too Many Requests` when a client sends too many requests in a short time.

## Current Protection Mechanism

The FastAPI middleware keeps an in-memory counter:

- `RATE_LIMIT = 100`
- `TIME_WINDOW = 60`

For every request, the middleware builds a key:

- Authenticated request: `user:<user_id>` from the JWT token.
- Anonymous request: `ip:<client_ip>` from the request client address.

If the same key sends more than 100 requests within 60 seconds, the server rejects the request with HTTP `429`.

## Run the k6 Test

Install k6 first if it is not available on your machine:

```powershell
winget install k6.k6
```

If you use Chocolatey:

```powershell
choco install k6
```

Start the FastAPI server first:

```bash
cd server
uvicorn main:app --reload
```

In another terminal, run:

```bash
k6 run load-tests/k6/rate-limit.js
```

The script targets:

```text
http://localhost:8000/api/stress-test/
```

You can override the target and intensity:

```bash
k6 run -e BASE_URL=http://localhost:8000 -e TARGET_PATH=/api/stress-test/ -e VUS=20 -e DURATION=30s load-tests/k6/rate-limit.js
```

## Expected Result

The test should show some `429` responses after the first 100 requests from the same local client. That means the rate limit middleware is working.

Important metrics:

- `rate_limited_responses`: number of blocked requests.
- `rate_limited`: ratio of requests that returned `429`.
- `allowed_or_limited`: should stay above `0.99`, meaning responses are either normal `200` or expected `429`.

## What This Does Not Cover

This is not full DDoS protection. It does not protect against network-layer floods, many distributed IPs, or attacks that exhaust the server before FastAPI can respond. For production, combine this application rate limit with a reverse proxy, CDN or WAF, request body limits, timeouts, and a shared store such as Redis for rate-limit counters.
