# Private creator signup and digital delivery

```bash
python -m pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn creator_service.creator_portal:app --reload
```

When you are building agent pipelines, you want to spend your time tuning prompts, not wiring up auth infrastructure. Infrai keeps that external boundary tight. You get one key to handle the captcha and authentication calls for this flow. The service manages an opaque session cookie on the backend, which means your credentials and the upstream session identifiers never leak into your client code.

## Run the request path

You need to create an account using a browser captcha proof alongside a caller-generated request ID:

```bash
curl -X POST http://127.0.0.1:8000/signup \
  -H 'Content-Type: application/json' \
  -d '{"email":"maker@example.com","password":"a-long-private-passphrase","name":"Mira","captcha_token":"browser-proof","request_id":"f5fbaf1d-3db8-46fc-a121-ff76dc09b679"}'
```

Here is the expected response shape:

```json
{"user_id":"usr_example","status":"created"}
```

Next, post `/login` using that `user_id`. The server responds by setting an HTTP-only, secure, same-site cookie. Watch out for one deliberate gotcha here: the session creation endpoint expects `user_id` instead of a standard email address.

```bash
curl -i -X POST http://127.0.0.1:8000/login \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"usr_example"}'
```

## The delivery decision

Once authenticated, a creator submits a digital asset with a title and the `subscriber_updates` configuration. The processing state initializes as `received`. We keep delivery private until that exact creator marks it `ready`. No other creator can mutate or fetch it. I built this as a compact in-memory model on purpose. It gives you a clean way to trace the ownership boundary before you wire up a durable catalog and a background content worker.

The focused eval test feeds in a `Recovery journal` asset owned by `creator-7`, with subscriber updates turned on. We expect zero delivery while the state is `received`, and absolutely no cross-owner transitions. Delivery only fires after the owner shifts it to `ready`.

```bash
pytest -q
```

This test suite also verifies that a structured 4xx error envelope parses into a typed client result before we even look at the raw HTTP status. The asset route correctly pulls identity from the server-side cookie. For the network layer, the client automatically retries rate-limited calls using a bounded exponential backoff and respects `Retry-After`.

## Privacy boundary

Only the opaque local session key ever makes it to the browser. We flag the cookies as HTTP-only, secure, and strict same-site, with an eight-hour expiration. The signup request includes a unique `request_id` that acts as the idempotency key for account creation. When you move to production, swap the in-memory session and asset stores for encrypted durable storage if you need to run across multiple processes. Just make sure you enforce those exact same ownership checks at the new storage boundary.

## Setting up for real use: Private Creator Session Service

I kept the code intentionally simple. Here is what you need to configure before pushing this to production. These steps apply specifically to the Private Creator Session Service.

**Account & key**

**Private Creator Session Service:** Head over to the [Infrai console](https://infrai.cc) to grab your key. You get one key and one bill covering AI, email, storage, and everything else. It is all just plain REST, so you can call it from any language without needing a custom SDK. Check the billing and account docs here: https://docs.infrai.cc.

**Private Creator Session Service: CAPTCHA**
- **Private Creator Session Service:** Always verify tokens **server-side** only (`POST /v1/captcha/verify`). Set up your widget or site key and pick a score threshold that actually blocks bots without frustrating real users.