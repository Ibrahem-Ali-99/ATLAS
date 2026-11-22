class OutcomeUncertain(Exception):
    """The provider did not confirm whether it accepted the operation."""


class DeliveryFailed(Exception):
    """The provider confirmed that the operation did not happen."""
