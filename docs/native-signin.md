# Native sign-in completion

Endpoints starts supported browser sign-in without waiting for the browser
callback in the HTTP request. While a flow is pending, the app reads its status
automatically. A callback means authorization was received; the app reports
`credential stored` only after exchange and storage succeed and the credential
is present. Presence does not establish token validity, expiry, or provider
permission for a particular use.

Each provider retains its declared flow. OpenRouter uses its documented PKCE
shape. Guided providers use their own tool. A registered provider needs the
operator's client registration and configured endpoints. This repair does not
establish a consumer subscription OAuth program or borrow another app's identity.

Cancel stops local completion. If an exchange is already in flight, its result
cannot be stored after cancellation wins. If storage wins first, cancellation
reports that completion already occurred. Sign-out removes the local credential;
neither action promises provider-side revocation. Refresh and expiry handling
remain outside this completion flow.

The sign-in roster and `/api/auth/*` actions require the existing gateway owner
bearer token, including when public routes use auth-off compatibility. Native
clients already supply that bearer through their authenticated HTTP transport.
An unauthenticated request receives `AUTH_REQUIRED` before credential handling.

The status UI keeps ownership of an outstanding HTTP read after its display
deadline. It reports the delay and waits for that read to settle instead of
starting overlapping requests. Leaving the view or going offline invalidates
late results. A failed exchange or store appears as a failure, with credential
values and response bodies excluded from errors.

Regression coverage uses synthetic providers, local callback HTTP, and temporary
in-memory credential stores. Native widget tests exercise automatic completion,
rejection, cancellation, and unresolved HTTP reads. These tests do not certify a
real provider registration or the installed application. Validate those separately
with the intended provider and build before claiming an operational connection.

Protocol references: [OAuth authorization response](https://www.rfc-editor.org/rfc/rfc6749#section-4.1.2),
[PKCE](https://www.rfc-editor.org/rfc/rfc7636), and
[OpenRouter OAuth](https://openrouter.ai/docs/guides/overview/auth/oauth).
