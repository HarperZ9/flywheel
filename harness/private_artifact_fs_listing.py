"""Bounded listing shared by the two pinned-directory backends."""
import os
import sys

from .private_artifact_fs import PrivateArtifactError, TOO_LARGE, UNSAFE_PATH


class ArtifactListing:
    def list_names(self, rel, *, max_entries: int) -> list[str]:
        if type(max_entries) is not int or max_entries < 1:
            raise PrivateArtifactError(UNSAFE_PATH)
        # Both custody backends implement this same private chain contract.
        backend = sys.modules[type(self).__module__]
        chain = self._parent_chain(backend._relative_parts(rel), create=False)
        try:
            names = []
            cap = chain[-1]
            with os.scandir(getattr(cap, "fd", cap.path)) as entries:
                for entry in entries:
                    if len(names) >= max_entries:
                        raise PrivateArtifactError(TOO_LARGE)
                    names.append(entry.name)
            backend._verify_chain(chain)
            return names
        finally:
            backend._close_caps(chain[len(self._caps):])
