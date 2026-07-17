from app.destinations import destination_matches, resolve_destination, taxonomy_payload


def test_hierarchical_destination_groups_resolve_outside_the_ui():
    hawaii = resolve_destination("Any Hawaii")
    assert hawaii["level"] == "region"
    assert "HNL" in hawaii["airports"]
    assert destination_matches(["ATL", "OGG"], "HAWAII")
    assert destination_matches(["HND"], "JAPAN")
    assert destination_matches(["AMS"], "EUROPE")
    assert any(group["code"] == "CARIBBEAN" for group in taxonomy_payload())
