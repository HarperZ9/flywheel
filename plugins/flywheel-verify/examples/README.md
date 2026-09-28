# Sample data

Files for trying Flywheel Verify without bringing your own.

- `check-answer/`: a contract that checks an hourly rate against a rate card. `answer.json` agrees with `rates.json` and passes. `answer-wrong.json` states 135 where the table says 120, so it fails and the release is HOLD. Pass the table to `check_answer` in `sources` under the key `rates.json`.
- `bundle/`: a demonstration receipt bundle. Its receipts are made-up records whose hashes name no real run. One carries an Ed25519 signature from a key made for this sample, and one is unsigned, so `verify_bundle` reports MATCH with one verified and one unsigned signature.

The bundle's files are hashed byte for byte, so editing any of them turns the verdict to DRIFT. That is the tool working.
