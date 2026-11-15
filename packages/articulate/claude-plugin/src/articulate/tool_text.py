"""Shared descriptions for the 0.5.1 MCP tools."""
from .tool_meta import EDITORS, offline

# What a set of findings covers. The desk report carries it as its scope.
SCOPE = "Names prose patterns and shows where they occur in the text."
# The one use statement that a findings tool description carries.
LIMIT = "Use the findings to improve writing. Use other evidence to decide who wrote a text."

_EDIT = ("Use negotiated sampling or return a host plan. Explicit backends may send "
         "text to a hosted model; backend none is deterministic. It edits none of your "
         "files. When a plan returns, follow its instructions and call edit_submit "
         "with the original text, rewrite or assessment, and plan_id.")
_LOCAL_EDIT = ("Runs on your machine. Default, auto and host return a host edit plan; "
               "backend none applies deterministic edits. Other backends, including "
               "sampling, are refused. It edits none of your files. Follow the plan "
               "instructions, then call edit_submit with the original text, rewrite "
               "or assessment, and plan_id.")
TOOLS = {
    "check": ("Check a passage for named prose patterns. Runs on your machine. Returns "
              "up to max_hits HIGH and MEDIUM findings (50 by default), with span "
              "records capped at about 30,000 characters. The clean/flagged verdict, "
              "texture score, advisory count and cadence cover the full text. A model "
              "checking its own reply to a person should pass profile \"chat\": it adds "
              "the structure rules (anaphora runs, parallel frames, triads, paragraph "
              "pinning, parataxis, pointer and landing sentences, in paragraphs and list "
              "items). With no profile only the default line rules run, and clean then "
              "says nothing about structure. The rules_run field names the profile and "
              "rule packs that ran. " + LIMIT),
    "score": ("Return the 0-100 device-density (texture) score, finding counts, passive-voice "
              "and adverb rates, and cadence flags. Runs on your machine. The texture score "
              "counts line rules only. A model scoring its own reply to a person should "
              "pass profile \"chat\"; rules_run names what ran. " + LIMIT),
    "judge": "Assess prose. " + _EDIT,
    "fix": "Suggest a rewrite. " + _EDIT,
    "polish": "Polish prose with meaning and regression guards. " + _EDIT,
    "edit_plan": ("Prepare local findings, protected spans and instructions for the "
                  "calling model. Runs on your machine and edits none of your files. Use "
                  "masked_text to write the rewrite or assessment, then call edit_submit "
                  "with the original text, result, and plan_id."),
    "edit_submit": ("Check a local host rewrite or assessment against its edit_plan. "
                    "Restores masks, guards protected spans and returns checked text "
                    "with a host receipt. Runs on your machine and edits none of your files. "
                    "Read the rewrite to confirm the meaning held."),
    "corpus_check": ("Review several documents as one series: title formulas, shared phrases, "
                     "repeated paragraph scaffolds, even rhythm, missing perspective. Report "
                     "only, with locations and a corpus receipt. Runs on your machine and edits "
                     "none of your files."),
    "title_workshop": ("Group titles into formula families and ask the author one question per "
                       "repeated title. Suggestions come only from the author's own answers. "
                       "Runs on your machine and edits none of your files."),
    "interview": ("Questions only the author can answer, each at its lines. The tool never "
                  "answers them; present them and wait for the author. Runs on your machine and "
                  "edits none of your files."),
    "restructure_plan": ("Propose moving per-paragraph source, confidence and limit lines into "
                         "one section, with anchors. Every sentence and citation is kept and "
                         "checked. Runs on your machine and edits none of your files."),
    "voice_compare": ("Place a draft against the measured range of the author's own voice, "
                      "saved on this computer with articulate voice learn. No total score. Runs on your machine and edits "
                      "none of your files."),
    "voice_apply_plan": ("Plan an edit that shapes the user's own draft toward their own saved "
                         "voice. Runs only with authored_by_user true. Returns a v2 host edit "
                         "plan; call edit_submit with the rewrite. Runs on your machine and edits "
                         "none of your files."),
    "house_brief": ("The Articulate house voice brief: a model's voice, versioned, with its "
                    "fingerprint. Runs on your machine and edits none of your files."),
    "house_transform": ("Apply the house voice to model output: closed-list deterministic "
                        "edits, a meaning guard, located notes and a receipt. house false "
                        "returns the text unchanged. Runs on your machine and edits none of "
                        "your files."),
    "dialogue_check": ("Check fiction dialogue: epigram shapes, antithesis, characters stating "
                       "the theme, closing zingers and abstract nouns; each line against its "
                       "character's voice sheet; and a blind attribution test of how distinct "
                       "each voice is. Runs on your machine and edits none of your files."),
    "articulate.status": "Server identity and liveness. Runs on your machine.",
    "articulate.doctor": ("Local readiness report: version, tools, optional backends "
                          "and session sampling capability. Runs on your machine."),
}


def description(name, environ=None):
    return _LOCAL_EDIT if name in EDITORS and offline(environ) else TOOLS[name]
