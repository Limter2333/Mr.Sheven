"""WBI signing for Bilibili API requests.

Pure Python implementation — no dependencies needed.
Algorithm reverse-engineered from bilibili web frontend.

Flow:
    1. Get img_key + sub_key from /x/web-interface/nav response
    2. Mix them via a fixed permutation table → mixin_key (32 chars)
    3. Add wts (timestamp) to params, sort, URL-encode, strip special chars
    4. w_rid = md5(query_string + mixin_key)

Reference: https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/misc/sign/wbi.md
"""

from __future__ import annotations

import hashlib
import time
import urllib.parse
from dataclasses import dataclass
from functools import reduce


# Fixed permutation table (64 indices into the concatenated 64-char key)
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

# Characters to strip from the query string before hashing
_STRIP_CHARS = "!'()*"


@dataclass(frozen=True)
class WbiKeys:
    """WBI signing keys extracted from Bilibili's nav API."""
    img_key: str
    sub_key: str


def get_mixin_key(img_key: str, sub_key: str) -> str:
    """Combine img_key + sub_key into a 32-char mixin_key via permutation table."""
    raw = img_key + sub_key
    return reduce(lambda s, i: s + raw[i], MIXIN_KEY_ENC_TAB, "")[:32]


def sign_params(params: dict[str, object], img_key: str, sub_key: str) -> dict[str, object]:
    """Add WBI signature (wts + w_rid) to request params.

    Args:
        params: Original request parameters (will NOT be mutated).
        img_key: WBI image key.
        sub_key: WBI sub key.

    Returns:
        New dict with wts and w_rid added.
    """
    mixin_key = get_mixin_key(img_key, sub_key)
    signed: dict[str, object] = dict(params)
    signed["wts"] = int(time.time())

    # Sort by key, URL-encode, strip special chars
    sorted_params = sorted(signed.items())
    query = urllib.parse.urlencode(sorted_params, quote_via=urllib.parse.quote)
    query = reduce(lambda s, c: s.replace(c, ""), _STRIP_CHARS, query)

    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
    signed["w_rid"] = w_rid
    return signed
