# Notice and attribution

The GitHub Actions metadata in `data/*.json` was derived from public GitHub API
responses for [`vllm-project/vllm`](https://github.com/vllm-project/vllm). Each
snapshot records its retrieval timestamp and source endpoint.

The two workflow files in `data/` are unmodified captures from immutable vLLM
commit references:

- `.github/workflows/pre-commit.yml` at
  `fca252d59efdb627549e5677263c69709590c982`
- `.github/workflows/macos-smoke-test.yml` at
  `6bcda970fde272b06cff0d8f397224dbac96d7ad`

vLLM's upstream repository declares the Apache License 2.0. The exact license
text from the pinned upstream revision is included as
`UPSTREAM-LICENSE-vLLM.txt`; its immutable source is the
[pinned upstream license](https://github.com/vllm-project/vllm/blob/fca252d59efdb627549e5677263c69709590c982/LICENSE).
This notice does not change the upstream license or claim ownership of upstream
content.

Forum is used from [`HarperZ9/forum`](https://github.com/HarperZ9/forum) at
commit `542dda464174802aa3dc0d99e686f3edc88017cf`, version `1.13.0`.
This is intentional public dependency attribution and exposes the `HarperZ9`
GitHub handle. Remove the dependency reference only if anonymous publication is
required; doing so also removes the stated Forum replay provenance.
