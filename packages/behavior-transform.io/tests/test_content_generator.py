import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from content_generator import ContentGenerator, GeneratedContent


def test_generator_instantiates():
    gen = ContentGenerator()
    assert gen is not None


def test_generate_variants_returns_list():
    gen = ContentGenerator()
    variants = gen.generate_variants("test", count=3)
    assert isinstance(variants, list)


def test_generate_variants_respects_count():
    gen = ContentGenerator()
    variants = gen.generate_variants("test", count=5)
    assert len(variants) <= 5


def test_generated_content_dataclass():
    gc = GeneratedContent(
        original="test",
        variants=["v1", "v2"],
        classifier_probe_prompts=["p1"],
        obfuscations=["o1"],
        generation_method="synonym",
    )
    assert gc.original == "test"
    assert len(gc.variants) == 2


def test_synonym_map_built():
    gen = ContentGenerator()
    assert isinstance(gen._synonyms, dict)


def test_obfuscation_map_built():
    gen = ContentGenerator()
    assert isinstance(gen._obfuscation_techniques, dict)
