# check3_v1.py: the same model as check3_v0.py (qwen2.5-coder:32b-instruct-q4_K_M) after one
# repair round. Feedback (third_checker/repair1.txt) showed its own outputs on four valid
# witnesses and restated two interface rules it broke. It saw no BootLoops code.
# The code below this header is the model's output, byte for byte, unedited.
import sys
import json
import os

def load_system_jsonl(path):
    try:
        with open(path, 'r') as f:
            rows = [json.loads(line) for line in f]
        return rows
    except Exception:
        return None

def load_witness(path):
    try:
        with open(path, 'r') as f:
            witness = json.load(f)
        return witness
    except Exception:
        return None

def verify_row(rows, wit, table_row=None):
    if wit.get('receipt_version') != '1.0':
        return False, "wrong receipt version"
    if 'p' not in wit or wit['p'] <= 1:
        return False, "invalid p"
    p = wit['p']
    if 'target' not in wit or 'col' not in wit['target']:
        return False, "missing target column"
    target_col = wit['target']['col']
    if 'c' not in wit:
        return False, "missing c"
    c = {int(k): v % p for k, v in wit['c'].items()}
    if 'lam' not in wit or 'n_rows' not in wit['lam'] or 'idx' not in wit['lam'] or 'val' not in wit['lam']:
        return False, "malformed lam"
    lam = wit['lam']
    if len(rows) != lam['n_rows']:
        return False, "lam n_rows mismatch"
    r = {}
    for idx, val in zip(lam['idx'], lam['val']):
        row = rows[idx]
        for col, row_val in row.items():
            col = int(col)
            r[col] = (r.get(col, 0) + row_val * val) % p
    expect = {target_col: 1}
    for col, val in c.items():
        expect[col] = (expect.get(col, 0) - val) % p
    if r != expect:
        return False, "identity does not hold"
    if table_row is not None:
        table_c = {int(k): v % p for k, v in table_row.items()}
        if c != table_c:
            return False, "claimed table row != certified row"
    return True, "PASS"

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Verify RECEIPT v1.0 witness files.')
    parser.add_argument('system_jsonl', help='Path to the system JSONL file.')
    parser.add_argument('witness_jsons', nargs='+', help='Paths to the witness JSON files.')
    parser.add_argument('--table', help='Path to the table JSON file.')
    args = parser.parse_args()

    system_rows = load_system_jsonl(args.system_jsonl)
    if system_rows is None:
        print(json.dumps({"witness": "system", "verdict": "MALFORMED", "reason": "unreadable system file"}))
        sys.exit(2)

    table = {}
    if args.table:
        try:
            with open(args.table, 'r') as f:
                table = json.load(f)
        except Exception:
            print(json.dumps({"witness": "table", "verdict": "MALFORMED", "reason": "unreadable table file"}))
            sys.exit(2)

    results = []
    for witness_path in args.witness_jsons:
        witness = load_witness(witness_path)
        if witness is None:
            results.append({"witness": os.path.basename(witness_path), "verdict": "MALFORMED", "reason": "unreadable witness file"})
            continue
        target_col = witness.get('target', {}).get('col')
        table_row = table.get(str(target_col)) if target_col is not None else None
        passed, reason = verify_row(system_rows, witness, table_row=table_row)
        verdict = "PASS" if passed else "FAIL"
        results.append({"witness": os.path.basename(witness_path), "verdict": verdict, "reason": reason})

    for result in results:
        print(json.dumps(result))

    if any(result['verdict'] == "MALFORMED" for result in results):
        sys.exit(2)
    if any(result['verdict'] == "FAIL" for result in results):
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
