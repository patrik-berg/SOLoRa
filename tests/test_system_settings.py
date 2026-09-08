"""Domain tests for protocol-facing system authority identity."""

from solora.domain.system_settings import (
    SystemIdentity,
    SystemRole,
    primary_authority_identity,
)


def test_display_name_never_grants_primary_authority() -> None:
    identity = SystemIdentity("SOL1", SystemRole.CLIENT)

    assert primary_authority_identity(identity, 0x1234ABCD) is None


def test_explicit_primary_is_identified_by_meshtastic_node_id() -> None:
    identity = SystemIdentity("Base North", SystemRole.PRIMARY)

    authority = primary_authority_identity(identity, 0x91AB22CD)

    assert authority is not None
    assert authority.system_role is SystemRole.PRIMARY
    assert authority.node_id == 0x91AB22CD
    assert primary_authority_identity(identity, None) is None
