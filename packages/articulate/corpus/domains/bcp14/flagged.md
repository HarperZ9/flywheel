# Token refresh

A client MUST not reuse a refresh token.
The server SHALL reject an expired token, and the client MUST retry once.
A client MAY NOT cache the response.
