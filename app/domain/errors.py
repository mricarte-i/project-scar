class DomainError(Exception):
    code = "domain_error"
    status = 400

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


class InvalidWindowError(DomainError):
    code = "invalid_window"
    status = 422


class NoAssetValidError(DomainError):
    code = "no_asset_valid"
    status = 404


class HistoricalEditError(DomainError):
    code = "historical_edit"
    status = 409

    def __init__(self, message: str, affected_version_ids: list[int]):
        super().__init__(
            message, details={"affected_version_ids": affected_version_ids}
        )
        self.affected_version_ids = affected_version_ids
