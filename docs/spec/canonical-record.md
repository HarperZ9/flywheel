# Canonical record v1

A receipt, a ledger entry or a manifest is hashed over bytes. Two honest parties who hold the same record must produce the same bytes, in any language. This page fixes those bytes. The identifier is `canonical-record/1`.

The JSON form is RFC 8785, the JSON Canonicalization Scheme (JCS). Numeric arrays that are too large for JSON get their own digest form, defined below. The reference implementation is `harness/canonical_record.py` (standard library only). The golden vectors are `tests/data/canonical_vectors.json`, released under CC0 1.0 so any repository can copy them whatever its licence.

## The JSON form

1. **Values.** `null`, `true`, `false`, numbers, strings, arrays and objects. Nothing else has a canonical form.
2. **Whitespace.** None. Members are separated by `,` and names from values by `:`.
3. **Object keys.** Keys are strings, sorted by their UTF-16 code units, compared as unsigned integers. This is JavaScript's default `Array.prototype.sort` order. It differs from code-point order only when a key holds a character above U+FFFF and another holds one from U+E000 to U+FFFF; the vector `astral-vs-bmp-keys` pins that case. Duplicate keys cannot occur, because the input is a parsed object.
4. **Strings.** Written as UTF-8 with no escaping except: `"` as `\"`, `\` as `\\`, the five short escapes `\b \f \n \r \t`, and every other code point below U+0020 as `\u00xx` with lowercase hex. DEL (U+007F), `/`, U+2028 and every non-ASCII character are written as themselves. A lone surrogate is refused.
5. **Numbers.** Each number is an IEEE 754 double, written in the ECMAScript `Number.prototype.toString` form: the shortest digits that round-trip, positional notation for decimal exponents from -6 to 21, and `d.ddde+N` or `d.ddde-N` outside that range. `1.0` writes `1`, `-0` writes `0`, `1e-7` writes `1e-7`, `1e21` writes `1e+21`.
6. **Refused.** NaN, positive and negative infinity, integers outside ±(2^53 − 1), lone surrogates and non-string keys have no canonical form. An implementation raises an error. It never writes a substitute.

The digest of a record is the lowercase hex sha256 of its canonical bytes.

## The float rule

A hashed field should carry an integer or a string when either carries the meaning. Counts, nanoseconds, basis points and decimal strings ("0.05") hash the same in every language with no number formatting at all. When a hashed field must carry a float, rule 5 applies, and the vectors in the `float` group are the test. Python's `json.dumps` does not write rule 5: it writes `1.0`, `1e-07` and `1e+16`. Use `harness.canonical_record` (or a port tested against the vectors) wherever a float may reach a hash.

## Numeric arrays

An array of numbers that is hashed as data, such as a kernel output or a rendered frame, is hashed over a header and its raw items:

```
sha256( "cr1-array" 0x00 DTYPE 0x00 SHAPE 0x00 ITEMS )
```

- `DTYPE` is one of `bool i8 u8 i16 u16 i32 u32 i64 u64 f32 f64`, in ASCII.
- `SHAPE` is the dimensions as decimal integers joined by `,` in ASCII. A scalar has an empty shape.
- `ITEMS` is every item in C (row-major) order, little-endian, at the dtype's width. Float arrays refuse NaN and infinities.

The same values in another dtype or shape hash differently on purpose. A record that names an array holds this digest as a string, so the record itself stays in the JSON form above.

## Where the existing implementations stand

The vectors were built by running six implementations on one case list (2026-10-31). Each case records, per implementation, `agrees` or the bytes it wrote instead. Summary of the 33 valid cases:

| Implementation | Agrees | Differs | Where it differs |
|---|---|---|---|
| CMMNS `captureCanonical` (JS) | 33 | 0 | accepts a lone surrogate and integers above 2^53 − 1 |
| field `canonJSON` (JS) | 33 | 0 | same as CMMNS |
| superframe `tools/canon.py` (canonical JSON v2) | 28 | 5 | positional numbers with no exponent (`1e-7`, `1e21`, `1e300`, `5e-324`); code-point key order |
| Flywheel `harness/certificates/base.py` `canonical()` | 22 | 11 | escapes non-ASCII and DEL (`ensure_ascii`); Python float form; code-point key order |
| studyrun `hashing.canonical()` as first written | 25 | 8 | Python float form; code-point key order |
| kernels `receipt.value_hash` body | 18 | 15 | spaces after `,` and `:`; escapes non-ASCII; Python float form; accepts NaN |

Every implementation agrees on ASCII records with integers, booleans, nulls and nesting. Flywheel's tracked receipts sit almost entirely on that ground. Of the 35 receipts the test reads (2026-10-31), 30 differ between the older `canonical()` and this spec, and all 30 for one reason: a field such as `"timeout_seconds": 30.0`, which Python writes as `30.0` and the spec writes as `30`. `tests/test_canonical_vectors.py` checks that every receipt has a canonical form and that, with integral floats set aside, the two forms are byte-identical. A receipt that leaves that ground fails the test.

The kernels array digest used the header `dtype.str|shape-tuple|`, which no language other than Python writes naturally. Each array vector records that older digest beside the new one.

## Adopting the spec

An implementation adopts the spec when it passes every case and refuses every invalid input in the vectors. Existing hashes keep their meaning: a record sealed under an older form is verified under that form, and a new seal under this spec names `canonical-record/1`. No published hash was rewritten by this page.

## What this does not settle

The spec fixes bytes. It does not say which fields a record must carry, how a record is signed, or whether two records with equal digests mean the same thing.
