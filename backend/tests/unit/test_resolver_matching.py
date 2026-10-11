from hjemmefra.catalog.resolver import ProductResolver
from hjemmefra.core.confidence import MatchConfidence
from hjemmefra.demo.dataset import NEGATIVE_ALIASES, PRODUCTS


def test_resolver_aliases():
    r = ProductResolver(PRODUCTS, NEGATIVE_ALIASES)
    assert r.resolve("Kyllingebrystfilet").canonical_id == "CHICKEN_BREAST"
    assert r.resolve("Kyllingefilet 900 g").confidence == MatchConfidence.HIGH
    assert r.resolve("Brystfilet af kylling, 2 pk").canonical_id == "CHICKEN_BREAST"


def test_whole_chicken_is_not_chicken_breast():
    r = ProductResolver(PRODUCTS, NEGATIVE_ALIASES)
    res = r.resolve("Hel kylling 1,2 kg")
    assert res.canonical_id == "WHOLE_CHICKEN"


def test_unmatched_returns_unmatched():
    r = ProductResolver(PRODUCTS, NEGATIVE_ALIASES)
    assert r.resolve("Opvasketabs 60 stk").confidence == MatchConfidence.UNMATCHED


def test_alias_must_match_whole_words():
    r = ProductResolver(PRODUCTS, NEGATIVE_ALIASES)
    assert r.resolve("frisk koriander").confidence == MatchConfidence.UNMATCHED
    assert r.resolve("Jasminris 1 kg").canonical_id == "RICE"
