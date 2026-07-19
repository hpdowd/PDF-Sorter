"""Pure, dependency-free matching logic for mapping rules.

The engine used to decide matches inline in ``Sorter.find_matching_rule``: a rule
key could hold ``a|b|c`` alternatives and matched if *any* alternative was a
substring of the normalized PDF text. That logic lives here now as pure functions
so it can be unit-tested in isolation and grown without touching the Sorter.

Two responsibilities, kept separate on purpose:

* :func:`resolve_match_spec` turns a rule into a normalized ``{all, any, none}``
  spec. This is the only place that knows about back-compat (the ``a|b|c`` key)
  and, going forward, an explicit ``match`` block on the rule. Terms come out of
  here already normalized.
* :func:`match_rule` is a pure evaluator over an already-normalized spec and an
  already-normalized text. It knows nothing about rules, keys, or JSON.

Keeping the evaluator pure means the All/Any/None model can be tested exhaustively
against hand-built specs, independently of how specs are stored on disk.
"""


def normalize(text):
    """Collapse all runs of whitespace to single spaces and lowercase.

    This is the single definition of "normalized text" shared by the scanned
    document and every rule term, so matching is whitespace- and case-insensitive.
    """
    return " ".join(text.split()).lower()


def resolve_match_spec(phrase_key, rule):
    """Return the effective ``{"all": [...], "any": [...], "none": [...]}`` spec
    for a rule, with every term already normalized.

    Today the spec is derived from the rule key's ``|`` alternatives as an
    *any-of* condition, which reproduces the historic behavior exactly (a bare key
    with no ``|`` is a single any-of term). This is the seam where an explicit
    ``match`` block will later take precedence; until one is written, every rule
    resolves to the key-derived any-of spec, so existing mappings are unchanged.
    """
    alternatives = [normalize(part) for part in phrase_key.split("|") if part.strip()]
    return {"all": [], "any": alternatives, "none": []}


def match_rule(normalized_text, spec):
    """Evaluate a normalized ``{all, any, none}`` spec against normalized text.

    Returns ``(matched: bool, which_term: str | None)`` where ``which_term`` is
    the term worth showing the user (the matched *any* term, else the first
    required *all* term).

    Semantics:

    * A rule needs at least one **positive** term (in ``all`` or ``any``); a spec
      with only exclusions — or no terms at all — never matches, so it can't
      become an accidental catch-all.
    * ``none`` — if any excluded term is present, the rule does not match.
    * ``all`` — every term must be present.
    * ``any`` — if the list is non-empty, at least one term must be present.

    Terms are assumed already normalized (see :func:`resolve_match_spec`); empty
    terms are ignored defensively.
    """
    all_terms = [t for t in (spec.get("all") or []) if t]
    any_terms = [t for t in (spec.get("any") or []) if t]
    none_terms = [t for t in (spec.get("none") or []) if t]

    if not (all_terms or any_terms):
        return False, None
    if any(term in normalized_text for term in none_terms):
        return False, None
    if not all(term in normalized_text for term in all_terms):
        return False, None

    matched_any = None
    if any_terms:
        matched_any = next((term for term in any_terms if term in normalized_text), None)
        if matched_any is None:
            return False, None

    which_term = matched_any if matched_any is not None else all_terms[0]
    return True, which_term
