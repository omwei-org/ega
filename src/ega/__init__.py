"""EGA reference implementation."""

from .models import AuthorizationScope, ExecutionAuthority, ExecutionAttestation, RuntimeIntent
from .authority import AuthorizationError, issue_authority
from .boundary import PreparedAuthority, commit, execution_attestation, final_authority_check, prepare

__all__ = ["AuthorizationError", "AuthorizationScope", "ExecutionAuthority", "ExecutionAttestation", "PreparedAuthority", "RuntimeIntent", "commit", "execution_attestation", "final_authority_check", "issue_authority", "prepare"]
