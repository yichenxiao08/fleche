"""Explicit domain curation for the modern fencing training corpus."""

MODERN_DOMAINS = {"modern_electric_fencing", "modern_fencing_footwork_drill"}


def eligible_source(source):
    digest = source.get("sha256")
    return (
        isinstance(digest, str)
        and len(digest) == 64
        and all(c in "0123456789abcdef" for c in digest)
        and source.get("training_eligible") is True
        and source.get("training_domain") in MODERN_DOMAINS
        and source.get("curation_sha256") == digest
    )


def eligible_training_source(source):
    """Modern provenance plus the current MVP footage scope."""
    return eligible_source(source) and source.get("mvp_training_eligible", True)
