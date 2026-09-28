"""EGA reference implementation."""

from .models import AuthorizationScope, DecisionRecord, EvidenceItem, ExecutionAuthority, ExecutionAttestation, RuntimeIntent
from .authority import AuthorizationError, issue_authority
from .boundary import PreparedAuthority, commit, execution_attestation, final_authority_check, prepare

__all__ = ["AuthorizationError", "AuthorizationScope", "DecisionRecord", "EvidenceItem", "ExecutionAuthority", "ExecutionAttestation", "PreparedAuthority", "RuntimeIntent", "commit", "execution_attestation", "final_authority_check", "issue_authority", "prepare"]
