# Reseal log

Each entry records one reseal of `MANIFEST.sha256` and why it happened. This file sits
outside the seal, so a new entry here never changes a sealed digest.

## 2026-10-04: digests recomputed over the committed LF bytes

- Cause: 28 digests in `MANIFEST.sha256` were computed over CRLF working-copy bytes of
  files that Git stores with LF line endings. A checkout writes the stored LF
  bytes, so `sha256sum -c` failed on those entries on every platform once
  `.gitattributes` pinned the sealed files to their committed bytes (commit
  6217b48).
- Content did not change. For each entry below, the old digest equals the SHA-256
  of the stored blob with every LF replaced by CRLF, and the new digest is the
  SHA-256 of the stored blob itself. No sealed file was edited in this reseal.
- Method: SHA-256 over the committed blob (`git show HEAD:<path>`), the same
  computation `sha256sum` performs on a checkout that keeps committed bytes. Only
  the digest field of each line changed; paths, order and the `*./` path form are unchanged.
- Approval: the author approved this reseal in chat on 2026-10-04: "you can reseal faithful transpile and bootloops."
- `MANIFEST.sha256` before: `661f215da2a96cae2a2a56a9765d82c1fc48212bbb1a55afae3e4452cb6c7d86`
- `MANIFEST.sha256` after: `cc5a2d317ff183a50f1aec6188417c5d9c61eaaa2b73ed2695b20261933ca95d`
- The old values stay readable in Git history (`git show 6217b48:MANIFEST.sha256`) and in the
  table below.
- External anchors: none found for this seal, so none was added or replaced.
- Not resealed here, still failing `sha256sum -c`: five entries that are not
  line-ending cases. `README.md` and `.gitignore` were edited after the seal
  (their old digests match the LF bytes at commit 21651bf, the seal commit), and
  three `.ruff_cache/` entries name cache files that were never committed. Resealing
  those would attest changed content or alter the sealed file set, which this
  approval did not cover. They wait for a separate author decision.
- Does not prove: this reseal attests that the listed files now match these
  digests byte for byte. It does not re-attest any earlier claim made with the
  old digests beyond that byte identity, and it says nothing new about what the
  files contain or whether their conclusions hold.

| File | Old digest (CRLF bytes) | New digest (committed LF bytes) |
|:--|:--|:--|
| `DEMO-two-minds.md` | `ef0463c6af9863f2bf745a6c18ecb3e197f65c5d58ff75937146b5b1ca692090` | `c5b61e4863c500fa79821b3a083024b42269426ad4ceeb5855caf8e917b7c282` |
| `ENDGAME.md` | `b44c82bb40c5baf7ce566ab8f00fcae4160637f1eddb6a3d997b0d9be3384da8` | `5260a3996b2788147e0ccf4ed2183e2e5cd0d6c9da48955ea35fd843c9964bcd` |
| `PRINCIPLE.md` | `db73feab1815648b698d205c7fd1f6166cd8a9023b264b66a46060f5d7afd149` | `df793dd88c086f604f71da4d0e38238c9c245edb26532c3d8629f8536c8834c2` |
| `THESIS.md` | `3562c5724f842d58b349bb4f70506e76c43dc61876dfb9cde09057c415d4650d` | `708b946b091e1311e0e77e30f80e67d7ff982a024d80d971ac207b82519a81aa` |
| `VERDICT.md` | `f0470fb0f8d99760053f96d3354ebf2a65f7e9e03db2731f541514f572560bb6` | `c0b4cdd482bfa74bc366c8d8b9cf8f3d584fc5ebed50f0d9c04f83638183fa74` |
| `center.py` | `81f19613baeef1a74291cd693e28a80c2a7d1ba5b15485d760090ad4ee1dc2e8` | `a7d60754507f9c805502000586885bf0498232265f2353501f0082003dc9eb32` |
| `sims/contested_aperture.py` | `73a520a8541fc8bb1c358a8f4d76f3618f6cf8f6a01dd11c186e63ac559d0e00` | `a99817475daaa97210df4831144b559711d5f0fe0316ac280c2bf120b9282f76` |
| `sims/map_boundary.py` | `8c3331889879e5fa64ff2c48b59b58619324d96863ab440c5a35f13f1681187c` | `81046b29fb20bee966ef8db6cb80420850abf62da36b719d0417f99c644bc2f9` |
| `sims/probe_basin.py` | `6aee87e712c7c17eab2adaac97f5880bf4ac40095b9ead8fc5743e5960f1f9c4` | `83c5f9ad72ab017dc1f0092cca31af8bb894c1fc816b3d4fa273d6b337dbc74e` |
| `sims/probe_criterion.py` | `dafd64419db7c87988107ec3f427798cf56db6a35eb1f493d16a631327b60ba7` | `79fb64493dcb6e6c8af80ab53d66474d1a5523ff1efc6c402a446b854c76fb4d` |
| `sims/probe_gate.py` | `929d7e022421809831f61686dd2de0346578d496c391b4c2b46fbc23464d8021` | `59daba85a587bdbf030c38eb2387173528c3dc554267c6ededc4be9a3f70438f` |
| `sims/probe_law.py` | `89d3f854475100054e85d609602915ca2d75c80f71e6c1033c2afcbbb3d9c76f` | `d8f1bc5292dbd08ca9a37ee8f93ca8e1d5dfcf9a510d37b5879a64da3746fb8f` |
| `sims/probe_ownerless.py` | `1cd1965646a2717f85a5db00d6c2f5afe6104253201fcfd9a1c50c8928e984e7` | `ea4e948723652d7054f6a700c8bdd315f2530b5660209d448d8ee3a0b1992990` |
| `sims/probe_readout.py` | `453be5615fb9a39fb67d6cf8669599067d9c846b1c8a82a4b14c71430557be02` | `51347ca1fbb7a3f9331daf75079aa986faa4229944b233c6b1c55fb3a3c629af` |
| `sims/reconcile_dynamics.py` | `7f5b8312e11298704979bd0b970600d4c7f3e61fb287d9cebd52759854e99912` | `12909080d583cf4f4f86c605f32a780afbb3f0cba5e660fde9ef46d785484ed1` |
| `sims/run_gaps.py` | `ff65f9b39d9660647ad6beed82c6efa8b373b9e0793de18b6dab2a6a32789b0b` | `6d302aeee91d0a11790f05091a206eff807bbac852750b8630290a24d1e10999` |
| `sims/substrate_adversarial.py` | `a3a9f9c3421ba76641422cd3cf11bae68a92553d31f7cb2faccfcc4ef09d4300` | `f168b4b36d27a85245fdf95948bcc4137617dc90be2515222efc72bab3311b9e` |
| `sims/substrate_analog.py` | `33df63a2d8a38d1f59240b5e1ddb95de41c9d6080086f48cc76794d2fc2d773c` | `a662d4656e72a94c65d875ca0f766ae615297dbc80e20e127f3f63dbe97fa836` |
| `sims/substrate_compose.py` | `9970061d3222bc09e2831bfb791147f46e6cc160b3eeeaa666567daed6cabc1e` | `3c7b5979a2b98065334f30b82d1a531185bc025d943bf55f9d5e61f5589bd138` |
| `sims/substrate_encrypt.py` | `0985bcfa21e742d53c7324174a24bec84bb3078eeab96335fb7764d7c77fe71c` | `60aa90d6c3cffe2f8c218a4415dbeb4b15b9b12491482abb44d1ad515f11fa80` |
| `sims/substrate_geometry.py` | `8dcbda54bd081af110e003b59b73ab7ada2dfcc46390c95c3617216163a6dc52` | `7938936534eb36aa7d5dc1d0b2ab9c51867014945ef8881492c1f95fd5917e96` |
| `sims/substrate_graph.py` | `fee55341df84498170abbbb75ae2dd02ed0db85601862db8bff91f0d537698bb` | `004f46ee7dc79f51bcbf5655ad6d9dab2b5c67f1d64630634d49462d85572629` |
| `sims/substrate_phash.py` | `a5763921e96a9d54e22c7147b61da03bf9e63a0303f926d6dab1a22622122012` | `f8725cf66e37bec3fdfdd293dcf5762b204bd9b175ef07e7020b64c6f07eb519` |
| `sims/substrate_quantize.py` | `49c1e9da3b9347e703eef9d24cd409a6024dd78848a94cf61ed729c1c7633447` | `3461c2a6936d576112285e26e9998b9a191bb6367f8b9f9e13f69131d257e407` |
| `sims/substrate_sound.py` | `d0da51299b0b46dfbd84d3438afd5be315664d1e0181276f0e75bf31f7752fbd` | `e3540723b74f61a6931d252d93641126084217d52510a841e85b42ec1daf1526` |
| `sims/teardown.py` | `4d356b155c8e012467606cad9e57dae40051e81f457b5971b2fbd3afccd2efe1` | `35cf67a83df7714b7770fb84a307f307b5549545198125bd8163afd7a5973c55` |
| `sims/transpile_conservation.py` | `fdf5ffe0287259d4b5f7c84c6eb15b17f8a235078caee90c3921eb046c697a2d` | `7b35b9f9fce0003404e072506ca424cd6d70bd9c56d187c0a4d72ab7966331c1` |
| `vision-arm-REPORT.md` | `5fdbbd9a1c557bc25870b188c5565192d05da08ce2c74b257aa96cb9b5bfc2a6` | `d589c6ed527ff6031c5a9e50367a25bafa9932a3d8dc40e7f29022408a58f1be` |

## 2026-10-04: README.md and .gitignore resealed after approved content changes; cache entries removed

This entry resolves the five entries the previous entry left failing.

- Approval: the author approved this in chat on 2026-10-04, relayed verbatim:
  "You no longer need to wait on my approval. Approved. Second request is a yes as well."
- Content changed. Unlike the entry above, `README.md` and `.gitignore` were edited
  after the original seal at commit 21651bf (2026-06-23). The old digests match
  their bytes at 21651bf exactly. The new digests are SHA-256 over the committed
  LF blobs at commit 70db4f0, so they attest the current text, which differs from
  the text the original seal covered.
  - `README.md`, edited in 9100d79, 0ca2107, 0ad5832, f5475a4 and b5f6dfc
    (banner, name, licence and art changes):
    - before (bytes at 21651bf): `2dd4c00f02de980778c32fc16ed9b494936b76db7b1bd88556c5c99a24dcd2d0`
    - after (bytes at 70db4f0): `e3b02b906c61e9d3fe2f4c85e68131f5e3935eb1e841f21cb466cddbece7a05c`
  - `.gitignore`, edited in be0b498, 01817d8, e54a00a and c770981 (ignore rules
    for CLAUDE.local.md, .env, dist/ and .envrc):
    - before (bytes at 21651bf): `862263fa1f46c20f0d1e4dac5ffcc75abd55c08211b2c3864c5f8764b9d87793`
    - after (bytes at 70db4f0): `a6cc68210e57dd7989c5eb7a3ea106fe677f5432cdf736759e776bd6cbdac3f5`
  - The text the original seal covered stays readable with `git show 21651bf:README.md`
    and `git show 21651bf:.gitignore`.
- Removed lines: three entries named files under `.ruff_cache/`, a local lint cache.
  No commit on any branch of this repository has ever contained `.ruff_cache/`, so
  those lines never covered published content and no reader could check them. They
  are removed. Their old digests, for the record:
  - `.ruff_cache/.gitignore`: `9e3a60f1e6ec4ae60215c11d54b171392745ec25e9dded433d5bd921363af316`
  - `.ruff_cache/0.15.11/14640478600706016845`: `2ad0f5a0cd278003a8a44e3d09d6f261c51277a433b95dfa1decd6f5c34970a2`
  - `.ruff_cache/CACHEDIR.TAG`: `5953156d7e0c564a427251316eaf26f8870e6483ae2197f916b630e4f93e31ae`
- The other 43 digests are unchanged. The manifest now lists 45 files.
- `MANIFEST.sha256` before: `cc5a2d317ff183a50f1aec6188417c5d9c61eaaa2b73ed2695b20261933ca95d`
- `MANIFEST.sha256` after: `95a923102af31037507b955855dd307f404c728bb81086c1e5953e895e5c4c98`
- CI now runs `sha256sum -c MANIFEST.sha256` on Linux and on Windows with
  `core.autocrlf=true`, so a future edit to a sealed file fails CI until it is
  resealed with an entry here.
- External anchors: none exist for this seal; none was added.
- Does not prove: the new `README.md` and `.gitignore` digests attest their current
  bytes only. They do not carry the original 2026-06-23 seal forward to the new
  text, and they make no claim about what the edits changed beyond the bytes.
