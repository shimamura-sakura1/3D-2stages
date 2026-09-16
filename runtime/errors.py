class WorkflowError(Exception):
    """An actionable, expected workflow failure."""


class ValidationError(WorkflowError):
    pass


class BoundaryError(WorkflowError):
    pass


class ProviderError(WorkflowError):
    pass
