"""A tiny seeded synthetic-data generator.

Deliberately dependency-free (no Faker) to keep the install lean (NFR-DEP-1).
Everything derives from an injected ``random.Random`` so generated datasets are
byte-identical under a fixed seed (REQ-STATE-2, REQ-DET-1).
"""

from __future__ import annotations

import random

_FIRST = [
    "Ada", "Grace", "Alan", "Linus", "Katherine", "Dennis", "Barbara", "Ken",
    "Margaret", "Edsger", "Radia", "Vint", "Hedy", "Claude", "Shafi", "Leslie",
]
_LAST = [
    "Lovelace", "Hopper", "Turing", "Torvalds", "Johnson", "Ritchie", "Liskov",
    "Thompson", "Hamilton", "Dijkstra", "Perlman", "Cerf", "Lamarr", "Shannon",
]
_COMPANIES = [
    "Acme", "Globex", "Initech", "Umbra", "Hooli", "Stark", "Wayne", "Wonka",
    "Cyberdyne", "Tyrell", "Soylent", "Pied Piper",
]
_WORDS = [
    "report", "invoice", "summary", "draft", "notes", "export", "archive",
    "backup", "receipt", "manifest", "ledger", "statement", "record", "payload",
]
_TLDS = ["example.com", "test.dev", "sandbox.io", "mock.local"]


class DataGen:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def first_name(self) -> str:
        return self.rng.choice(_FIRST)

    def last_name(self) -> str:
        return self.rng.choice(_LAST)

    def name(self) -> str:
        return f"{self.first_name()} {self.last_name()}"

    def email(self, name: str | None = None) -> str:
        base = (name or self.name()).lower().replace(" ", ".")
        return f"{base}@{self.rng.choice(_TLDS)}"

    def company(self) -> str:
        return self.rng.choice(_COMPANIES)

    def word(self) -> str:
        return self.rng.choice(_WORDS)

    def sentence(self, words: int = 6) -> str:
        return " ".join(self.rng.choice(_WORDS) for _ in range(words)).capitalize() + "."

    def amount_cents(self, lo: int = 100, hi: int = 500_00) -> int:
        return self.rng.randint(lo, hi)

    def choice(self, options: list) -> object:
        return self.rng.choice(options)
