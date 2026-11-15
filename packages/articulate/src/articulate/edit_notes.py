"""Notes a fix, polish or judge result carries about itself.

judge_floor marks a judge result unreliable when the gate blocked the text and
the assessment names none of the blocking findings. kept_reason says, in one
line, why a fix or polish result kept the original text; annotate_kept puts
that line in the result as `kept_original_reason` so an MCP host can read it.
"""
import re


def _blocking(findings):
    return [f for f in findings if str(f.get('tier', '')).upper() == 'HIGH']


def _terms(finding):
    """Words a reader would use to name one finding: its category and its label parts."""
    category = finding.get('category', '')
    label = finding.get('label', '')
    parts = {category, category.replace('-', ' '), category.replace('-', '')}
    for chunk in [re.sub(r'\([^)]*\)', '', label)] + re.findall(r'\(([^)]*)\)', label):
        parts.update(part.strip() for part in chunk.split('/'))
    return {part.lower() for part in parts if len(part) >= 3 or (part and not part.isascii())}


def _names(assessment, finding):
    text = ' '.join(assessment.lower().split())
    for term in _terms(finding):
        if not term.isascii():
            if term in text:
                return True
        elif re.search(r'(?<![a-z])' + re.escape(term) + r'(?![a-z])', text):
            return True
    return False


def judge_floor(result, assessment):
    """Mark a judge result unreliable when the gate blocked the text and the
    assessment names none of the blocking findings. The floor checks naming, not
    the quality of the advice."""
    result['assessment'] = assessment
    blocking = _blocking(result.get('findings_before', []))
    if result.get('gate_before') == 'ok' or not blocking:
        return result
    if not isinstance(assessment, str) or not any(_names(assessment, f) for f in blocking):
        cats = sorted({f['category'] for f in blocking})
        result['quality_status'] = 'unreliable'
        result['quality_note'] = ('The judge named none of the {} blocking finding(s) ({}); '
                                  'treat this assessment as unreliable.').format(len(blocking), ', '.join(cats))
        if isinstance(result.get('receipt'), dict):
            result['receipt']['quality_status'] = 'unreliable'
    return result


def kept_reason(result):
    """Why an edit returned the original text, in one line."""
    reasons = sorted({r for item in result.get("refused") or [] for r in item.get("reasons", [])})
    if reasons:
        return "the checks refused the rewrite (" + "; ".join(reasons) + ")"
    if result.get("note"):
        return result["note"]
    if result.get("backend") in ("none", "host", None):
        return "no model backend ran, and the deterministic pass found nothing it may change"
    if result.get("gate_after") == "ok" and result.get("quality_met"):
        return "the text already met the quality bar"
    return "no rewrite passed the gate and the no-regression checks"


def annotate_kept(result, original, goal):
    """Add kept_original_reason to a fix or polish result that kept the original."""
    if goal in ("fix", "polish") and isinstance(result, dict) and result.get("text") == original:
        result["kept_original_reason"] = kept_reason(result)
    return result
