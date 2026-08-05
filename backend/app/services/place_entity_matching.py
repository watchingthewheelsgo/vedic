"""Conservative entity matching for agent-provided place evidence.

The geocoding agent is allowed to discover names and coordinates, but it is not
allowed to decide that an unrelated place is a valid answer.  This module keeps
that decision deterministic and shared by both the tool-evidence path and the
final Agent JSON path.
"""

from __future__ import annotations

import re

from pypinyin import lazy_pinyin


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")
_ASCII_TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)
_CATEGORY_RE = re.compile(
    r"医院|保健院|卫生院|妇幼|妇婴|医科|诊所|"
    r"\b(?:hospital|medical center|clinic|maternity)\b",
    re.I,
)
_QUERY_NOISE = {
    "china",
    "coordinates",
    "coordinate",
    "latitude",
    "longitude",
    "wgs84",
    "gps",
}
_GENERIC_ENTITY_QUERIES = {
    "医院",
    "保健院",
    "卫生院",
    "诊所",
    "人民医院",
    "hospital",
    "clinic",
    "medicalcenter",
    "maternity",
    "yiyuan",
    "renminyiyuan",
}


def place_category_in_text(value: str) -> bool:
    """Return whether text names a healthcare/place category used by the UI."""

    return bool(_CATEGORY_RE.search(value.lower()))


def matches_place_entity(query: str, candidate_text: str) -> bool:
    """Check that candidate evidence names the requested entity.

    Exact matching is preferred.  For Chinese and pinyin input we additionally
    compare a pinyin token sequence, which handles ordinary administrative
    insertions such as ``上海市`` vs ``上海`` without maintaining a hand-written
    alias table.  If the candidate only contains a translated English label for
    a Chinese query, we reject it: a translation cannot be independently tied
    to the requested entity by this deterministic layer.
    """

    query = query.strip()
    candidate_text = candidate_text.strip()
    if not query or not candidate_text:
        return False

    query_compact = _compact(query)
    candidate_compact = _compact(candidate_text)
    if query_compact in _GENERIC_ENTITY_QUERIES:
        return False
    if query_compact and query_compact in candidate_compact:
        return True

    if _CJK_RE.search(query):
        if not _contains_pinyin_sequence(
            _cjk_pinyin_tokens(query), _candidate_pinyin_tokens(candidate_text)
        ):
            return False
        if place_category_in_text(query) and not place_category_in_text(candidate_text):
            return False
        return True

    query_tokens = _meaningful_ascii_tokens(query)
    if not query_tokens:
        return False

    candidate_ascii = _meaningful_ascii_tokens(candidate_text)
    if _contains_token_sequence(query_tokens, candidate_ascii):
        return True

    # A user may type pinyin while the search result names the Chinese place.
    # Compare tokens rather than a compact string so a result can include an
    # extra administrative character, e.g. 市立 -> 市市立.
    return _contains_token_sequence(query_tokens, _candidate_pinyin_tokens(candidate_text))


def _compact(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.lower())


def _cjk_pinyin_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    for run in _CJK_RUN_RE.findall(value):
        tokens.extend(lazy_pinyin(run))
    return [token.lower() for token in tokens if token]


def _candidate_pinyin_tokens(value: str) -> list[str]:
    """Return ASCII tokens and pinyin tokens in evidence order."""

    tokens: list[str] = []
    for part in re.split(r"([\u4e00-\u9fff]+)", value):
        if not part:
            continue
        if _CJK_RE.search(part):
            tokens.extend(lazy_pinyin(part))
        else:
            tokens.extend(_ASCII_TOKEN_RE.findall(part.lower()))
    return [token.lower() for token in tokens if token]


def _meaningful_ascii_tokens(value: str) -> list[str]:
    return [token for token in _ASCII_TOKEN_RE.findall(value.lower()) if token not in _QUERY_NOISE]


def _contains_token_sequence(needle: list[str], haystack: list[str]) -> bool:
    if not needle or not haystack:
        return False
    index = 0
    for token in haystack:
        if token == needle[index]:
            index += 1
            if index == len(needle):
                return True
    return False


def _contains_pinyin_sequence(needle: list[str], haystack: list[str]) -> bool:
    return _contains_token_sequence(needle, haystack)
