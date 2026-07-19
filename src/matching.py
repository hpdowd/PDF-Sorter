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

    Precedence:

    1. An explicit ``match`` block on the rule (``{"all"|"any"|"none": [...]}``)
       is authoritative — the key is then just the rule's identity/name and does
       not contribute terms.
    2. Otherwise the spec is derived from the key's ``|`` alternatives as an
       *any-of* condition, reproducing the historic behavior exactly (a bare key
       with no ``|`` is a single any-of term).

    So a rule only needs a ``match`` block when it uses advanced options; simple
    rules keep just their key and existing mappings are unchanged (no on-disk
    migration — back-compat is handled here at match time). A ``match`` block with
    no positive term (``all``/``any`` both empty) is treated as unset and falls
    back to the key, so a malformed block never leaves a rule silently dead.
    """
    match = rule.get("match") if isinstance(rule, dict) else None
    if match:
        spec = {
            "all": [normalize(t) for t in (match.get("all") or []) if str(t).strip()],
            "any": [normalize(t) for t in (match.get("any") or []) if str(t).strip()],
            "none": [normalize(t) for t in (match.get("none") or []) if str(t).strip()],
        }
        if spec["all"] or spec["any"]:
            return spec

    alternatives = [normalize(part) for part in phrase_key.split("|") if part.strip()]
    return {"all": [], "any": alternatives, "none": []}


def describe_match_segments(phrase_key, rule):
    """Return the rule summary as a list of ``(text, role)`` segments for
    colour-coded rendering, where ``role`` is ``"or"`` (any term), ``"and"``
    (all term), ``"not"`` (none term), or ``"plain"`` (connectors).

    Concatenating the texts yields exactly :func:`describe_match`. Terms are shown
    as the user typed them; a simple key-only rule reads as short as today.
    """
    match = rule.get("match") if isinstance(rule, dict) else None
    any_terms = all_terms = none_terms = []
    if match:
        any_terms = [str(t).strip() for t in (match.get("any") or []) if str(t).strip()]
        all_terms = [str(t).strip() for t in (match.get("all") or []) if str(t).strip()]
        none_terms = [str(t).strip() for t in (match.get("none") or []) if str(t).strip()]
    if not (any_terms or all_terms):
        # No usable match block: fall back to the key's alternatives (any-of).
        any_terms = [part.strip() for part in phrase_key.split("|") if part.strip()]
        all_terms = none_terms = []

    parts = []  # each part is itself a list of (text, role) segments
    remaining_all = list(all_terms)
    if any_terms:
        seg = []
        for i, term in enumerate(any_terms):
            if i:
                seg.append((" or ", "plain"))
            seg.append((term, "or"))
        parts.append(seg)
    elif remaining_all:
        parts.append([(remaining_all.pop(0), "and")])
    parts.extend([("and ", "plain"), (term, "and")] for term in remaining_all)
    parts.extend([("not ", "plain"), (term, "not")] for term in none_terms)

    if not parts:
        return [("(no match terms)", "plain")]
    out = []
    for i, part in enumerate(parts):
        if i:
            out.append((" · ", "plain"))
        out.extend(part)
    return out


def describe_match(phrase_key, rule):
    """One-line, plain-language summary of when a rule matches, e.g.
    ``"invoice or receipt · and acme · not quote"`` (the plain text of
    :func:`describe_match_segments`)."""
    return "".join(text for text, _ in describe_match_segments(phrase_key, rule))


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
