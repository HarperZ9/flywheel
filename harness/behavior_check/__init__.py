"""behavior_check -- replay fixed scripted sessions on two builds and compare.

`flywheel behavior-check A B` runs each scenario in scenarios.json with
`flywheel code -p --output-format stream-json` from source tree A and from
source tree B, against a scripted OpenAI-compatible model that records every
request body. It compares five streams per scenario and reports MATCH, or
DRIFT with the first diverging event. Only the rules in normalization.json are
applied before the comparison.
"""
