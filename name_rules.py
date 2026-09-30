import re

from rapidfuzz import fuzz

# canonical first name -> nicknames. Extend this from the REVIEW list stage 3 prints.
NICKNAMES = {
    "robert": ["bob", "bobby", "rob", "robby"],
    "william": ["will", "willy", "bill", "billy"],
    "michael": ["mike", "mick", "mikey"],
    "joseph": ["joe", "joey"],
    "christopher": ["chris"],
    "kenneth": ["ken", "kenny"],
    "elizabeth": ["beth", "eliza", "liz", "lizzie"],
    "daniel": ["dan", "danny"],
    "jennifer": ["jen", "jenny"],
    "thomas": ["tom", "tommy"],
    "alexander": ["alex"],
    "benjamin": ["ben", "benny"],
    "richard": ["dick", "rich", "rick", "ricky"],
    "nicholas": ["nick"],
    "samuel": ["sam", "sammy"],
    "stephanie": ["steph"],
    "charles": ["chuck", "charlie"],
    "matthew": ["matt"],
    "susan": ["sue", "susie"],
    "timothy": ["tim", "timmy"],
    "james": ["jim", "jimmy"],
    "anthony": ["tony"],
    "andrew": ["andy", "drew"],
    "edward": ["ed", "eddie", "ted"],
    "patricia": ["pat", "patty"],
    "deborah": ["deb", "debbie"],
    "margaret": ["maggie", "peggy"],
}
CANON = {nick: full for full, nicks in NICKNAMES.items() for nick in nicks}


def name_parts(name):
    """(first, last) lower-cased, punctuation removed. Middle names are ignored."""
    toks = [t for t in re.sub(r"[^\w\s]", "", (name or "").lower()).split() if t]
    if not toks:
        return "", ""
    return toks[0], toks[-1]


def edit_le1(a, b):
    """True if a and b differ by at most one insert, delete, substitute or neighbour swap."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    if len(a) == len(b):
        if a[i + 1:] == b[i + 1:]:                                   # one substitution
            return True
        return a[i] == b[i + 1] and a[i + 1] == b[i] and a[i + 2:] == b[i + 2:]  # swap
    if len(a) > len(b):
        a, b = b, a
    return a[i:] == b[i + 1:]                                        # insert / delete


def first_compatible(a, b):
    if not a or not b:
        return False
    if a == b:
        return True
    ca, cb = CANON.get(a, a), CANON.get(b, b)
    if ca == cb:
        return True
    # initial vs a full name (check the written form and the canonical form)
    if len(a) == 1 or len(b) == 1:
        return a[0] == b[0] or ca[0] == cb[0]
    # typos: dropped / doubled / swapped letters (same first letter, 3+ letters)
    for x, y in ((a, b), (ca, cb), (a, cb), (ca, b)):
        if min(len(x), len(y)) >= 3 and x[0] == y[0] and edit_le1(x, y):
            return True
    return False


def surname_compatible(a, b):
    if not a or not b:
        return False
    if a == b:
        return True
    return len(a) > 3 and len(b) > 3 and fuzz.ratio(a, b) >= 85


def name_verdict(name1, name2):
    f1, l1 = name_parts(name1)
    f2, l2 = name_parts(name2)
    if not surname_compatible(l1, l2):
        return "surname_differs"
    return "match" if first_compatible(f1, f2) else "first_differs"


def address_parts(addr):
    """(street, city). Street = first comma part; city = first later part
    that is not a suite/flat line and not a state/zip."""
    if not addr:
        return None, None
    parts = [p.strip() for p in addr.split(",")]
    street = re.sub(r"[^\w\s]", "", parts[0]).lower().strip()
    city = None
    for p in parts[1:]:
        if re.match(r"^(suite|ste|flat|apt|apartment|unit|floor|fl|#)\b", p, re.I):
            continue
        if re.match(r"^[A-Za-z]{2}(\s+\d{5})?$", p):
            continue
        city = p.lower()
        break
    return street, city


def address_verdict(addr1, addr2):
    s1, c1 = address_parts(addr1)
    s2, c2 = address_parts(addr2)
    if not s1 or not s2:
        return "unknown", 0.0
    street_score = fuzz.ratio(s1, s2)
    if street_score < 90:
        return "different", street_score
    if c1 and c2 and fuzz.ratio(c1, c2) < 80:
        return "different", street_score
    return "same", street_score