"""Provider boundary: no adapter, credentials, media upload or billing is configured."""


class ProviderUnavailable(RuntimeError):
    """A real render cannot be submitted with the current configuration."""


def require_render_provider():
    """Fail before persisting a render or contacting any external service.

    A future adapter needs documented inputs, authorized media, dedicated
    credentials and explicit submission/reconciliation semantics. A creative
    brief alone does not provide those inputs.
    """
    raise ProviderUnavailable(
        'Real video rendering is unavailable: no provider adapter is configured. '
        'No video was generated and no provider charge was submitted.'
    )
