"""Allocate a real private CLI profile for each owned session invocation."""
from contextlib import contextmanager
from pathlib import Path
import tempfile

from .gateway_operation import GatewayOperationError
from .operation_grants import _secure_owner_only
from .private_artifact_fs import open_artifact_root, root_identity


@contextmanager
def owned_profile_home(*, state_root=None, state_identity=None):
    """Production uses pinned operation state; standalone fixtures use OS temp.

    Profiles are retained private scratch, never recursively deleted here.
    No parent HOME, USERPROFILE or auth-directory value selects this profile.
    """
    parent = Path(state_root) if state_root is not None else Path(tempfile.gettempdir())
    try:
        with open_artifact_root(parent, expected=state_identity, writable=False):
            profile = Path(tempfile.mkdtemp(prefix='native-cli-profile-', dir=parent))
            identity = root_identity(profile)
            with open_artifact_root(profile, expected=identity):
                _secure_owner_only(profile, directory=True)
                for suffix in ('Temp', 'AppData/Local', 'AppData/Roaming'):
                    (profile / suffix).mkdir(parents=True, exist_ok=False)
                yield profile
    except GatewayOperationError:
        raise
    except Exception:
        raise GatewayOperationError('AGENT_CLI_UNAVAILABLE') from None
