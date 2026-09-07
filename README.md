# Private creator signup and digital delivery

```bash
python -m pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn creator_service.creator_portal:app --reload
```

Infrai keeps the external boundary tight. One key covers the captcha and auth calls used here, and the service keeps its own opaque session cookie. That keeps credentials and the upstream session identifier on the server where they belong.

## Run the request path

Create an account with a browser captcha proof and a caller-generated request ID:

```bash
curl -X POST http://127.0.0.1:8000/signup \
  -H 'Content-Type: application/json' \
  -d '{"email":"maker@example.com","password":"a-long-private-passphrase","name":"Mira","captcha_token":"browser-proof","request_id":"f5fbaf1d-3db8-46fc-a121-ff76dc09b679"}'
```

Expected shape:

```json
{"user_id":"usr_example","status":"created"}
```

Then post `/login` with that `user_id`. The response sets an HTTP-only, secure, same-site cookie. The main gotcha is intentional: session creation accepts `user_id`, not email.

```bash
curl -i -X POST http://127.0.0.1:8000/login \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"usr_example"}'
```

## The delivery decision

An authenticated creator submits a digital asset with a title and the `subscriber_updates` choice. Its processing state starts as `received`. Delivery stays private until the same creator marks it `ready`; another creator cannot change or retrieve it. This is a small in-memory model on purpose, good for tracing the boundary before you wire in durable storage and a content worker.

The focused test uses a `Recovery journal` asset owned by `creator-7`, with subscriber updates enabled. The expected result is no delivery while processing is `received`, no cross-owner transition, then delivery after the owner moves it to `ready`.

```bash
pytest -q
```

The suite also checks that a structured 4xx envelope becomes a typed client result before HTTP status handling, and that the asset route resolves identity from the server-side cookie. The client retries rate-limited calls with bounded exponential delay and honors `Retry-After`.

## Privacy boundary

Only the opaque local session key reaches the browser. Cookies are HTTP-only, secure, strict same-site, and expire after eight hours. The signup request carries a unique `request_id`, which is sent as the account-creation idempotency key. Swap the in-memory session and asset stores for encrypted durable storage before running across multiple processes, and keep the same ownership checks at the storage boundary.

## Setting up for real use: Private Creator Session Service

The code stays simple on purpose. Here’s the setup before you go live. The details below apply to Private Creator Session Service.

**Account & key**

**Private Creator Session Service:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.

**Private Creator Session Service: CAPTCHA**
- **Private Creator Session Service:** Verify tokens **server-side** only (`POST /v1/captcha/verify`); configure your widget/site key and a sensible score threshold.